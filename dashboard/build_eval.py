"""Build the dashboard data (data/eval.json) from a KEV run pulled from Modal, and the Agent page's
example questions (data/examples.json) from the development set.

A run pulled with
    modal run skills/kev-finetune/scripts/kev_modal.py::pull --name <run>
lands in runs/<run>/ with result.json, development/rows.json and baseline/development/rows.json.
Row ids are "custom/<line>" and point at line <line> (0-based) of the development file the run was
scored on, which is where the question, candidate answer and passage text come from.

Usage (from dashboard/):
    python build_eval.py --run ../runs/<run>                # dashboard data + examples
    python build_eval.py                                    # examples only
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from decision import FALSE, IDK, THRESHOLD, TRUE, decide

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "data" / "development.jsonl"
OUT_DIR = HERE / "data"

CATEGORIES = ["Correct answer", "Wrong answer", "Unsupported answer", "False abstention", "Correct abstention"]
EXAMPLES_PER_CATEGORY = 25
SWEEP = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
INSTRUCTION_RE = re.compile(r'Question:\s*(.*?)\s*\nIs "(.*)" the correct answer', re.S)


# ---------- development records ----------

def load_records(path):
    """{line number: record}, numbered like kev.data.load_records (0-based, blank lines counted)."""
    records = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f):
            if line.strip():
                records[n] = json.loads(line)
    return records


def describe(record):
    """Scenario, passage, question and candidate answer of a development record."""
    q = record["questions"]["question"]
    header, _, context = record["state"].partition("Context:")
    first = header.split("\n", 1)[0]
    scenario = first.split("scenario:", 1)[1].strip() if "scenario:" in first else first.strip()
    m = INSTRUCTION_RE.search(q["instructions"])
    question, answer = (m.group(1), m.group(2)) if m else (q["instructions"], "")
    return {"scenario": scenario, "passage": context.strip(), "question": question.strip(),
            "answer": answer.strip(), "label": q["label"]}


# ---------- KEV rows ----------

def calibrated(row, temperature):
    """The row's probabilities at the run's fitted temperature (same as kev.metrics.probabilities_at_temperature)."""
    p = np.asarray(row["p"], dtype=float)
    if temperature == 1:
        return p
    z = np.asarray(row["logits"], dtype=float) if "logits" in row else np.log(np.maximum(p, 1e-9))
    z = (z - z.max()) / temperature
    e = np.exp(z)
    return e / e.sum()


def load_rows(path, temperature):
    """Clean rows as dicts with calibrated probabilities keyed A/B/C."""
    out = []
    for row in json.loads(Path(path).read_text(encoding="utf-8")):
        if row.get("variant", "clean") != "clean":
            continue
        p = calibrated(row, temperature)
        out.append({"id": row["id"], "probs": dict(zip(row["keys"], p.tolist())),
                    "label": row["keys"][row["label"]]})
    if not out:
        raise SystemExit(f"{path}: no clean rows")
    return out


def classify(row, threshold=THRESHOLD):
    p = row["probs"]
    choice, conf = decide(p[TRUE], p[FALSE], threshold)
    should_answer = row["label"] != IDK
    if choice is None:
        category = "False abstention" if should_answer else "Correct abstention"
    elif not should_answer:
        category = "Unsupported answer"
    else:
        category = "Correct answer" if choice == row["label"] else "Wrong answer"
    return choice, conf, category


# ---------- metrics ----------

def ece(conf, correct, bins=10):
    """Expected calibration error, binned like kev.metrics.ece."""
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf >= lo) & (conf < hi) if hi < 1 else (conf >= lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(total)


def reliability(conf, correct, bins=10):
    """[[mean confidence, accuracy, count]] per non-empty bin."""
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    points = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf >= lo) & (conf < hi) if hi < 1 else (conf >= lo) & (conf <= hi)
        if m.any():
            points.append([round(float(conf[m].mean()), 4), round(float(correct[m].mean()), 4), int(m.sum())])
    return points


def auroc(scores, positives):
    """Probability that a random positive scores higher than a random negative (ties count half)."""
    scores, positives = np.asarray(scores, dtype=float), np.asarray(positives, dtype=bool)
    n_pos, n_neg = positives.sum(), (~positives).sum()
    if not n_pos or not n_neg:
        return None
    order = scores.argsort(kind="mergesort")
    ranks = np.empty(len(scores))
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):  # average ranks over ties
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def ratio(a, b):
    return a / b if b else None


def summarize(rows, threshold=THRESHOLD):
    """Every number the dashboard shows, for one model's rows."""
    keys = [TRUE, FALSE, IDK]
    p = np.array([[r["probs"][k] for k in keys] for r in rows])
    y = np.array([keys.index(r["label"]) for r in rows])
    top_conf, top_ok = p.max(axis=1), p.argmax(axis=1) == y

    cats = Counter(classify(r, threshold)[2] for r in rows)
    n = len(rows)
    should_answer = int((y != 2).sum())
    should_abstain = n - should_answer
    answered = cats["Correct answer"] + cats["Wrong answer"] + cats["Unsupported answer"]
    precision = ratio(cats["Correct answer"], answered)
    recall = ratio(cats["Correct answer"], should_answer)
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None

    sweep = []
    for t in SWEEP:
        c = Counter(classify(r, t)[2] for r in rows)
        ans = c["Correct answer"] + c["Wrong answer"] + c["Unsupported answer"]
        sweep.append({"threshold": t, "coverage": ratio(ans, n), "accuracy": ratio(c["Correct answer"], ans)})

    return {
        "n": n,
        "should_answer": should_answer,
        "should_abstain": should_abstain,
        "categories": {c: cats[c] for c in CATEGORIES},
        "overall_accuracy": ratio(cats["Correct answer"] + cats["Correct abstention"], n),
        "answer_accuracy": precision,
        "correct_abstention_rate": ratio(cats["Correct abstention"], should_abstain),
        "unsupported_answer_rate": ratio(cats["Unsupported answer"], answered),
        "coverage": ratio(answered, n),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier": float(((p - np.eye(3)[y]) ** 2).sum(axis=1).mean()),
        "ece": ece(top_conf, top_ok),
        "auroc": auroc(top_conf, top_ok),
        "false_answer_rate": ratio(cats["Wrong answer"] + cats["Unsupported answer"], answered),
        "false_abstention_rate": ratio(cats["False abstention"], should_answer),
        "classification_accuracy": float(top_ok.mean()),
        "sweep": sweep,
        "calibration": reliability(top_conf, top_ok),
    }


def examples(rows, records, threshold=THRESHOLD):
    """Up to EXAMPLES_PER_CATEGORY questions per outcome, most confident first, with their text."""
    by_cat = defaultdict(list)
    for r in rows:
        choice, conf, cat = classify(r, threshold)
        by_cat[cat].append((conf, r, choice))
    out = []
    for cat in CATEGORIES:
        for conf, r, choice in sorted(by_cat[cat], key=lambda x: -x[0])[:EXAMPLES_PER_CATEGORY]:
            line = int(r["id"].rsplit("/", 1)[1])
            text = describe(records[line]) if line in records else {}
            out.append({"id": r["id"], "category": cat, "confidence": round(conf, 4),
                        "label": r["label"], "decision": choice or "abstain",
                        "probs": {k: round(v, 4) for k, v in r["probs"].items()},
                        "question": text.get("question", "(question text unavailable)"),
                        "answer": text.get("answer", ""), "passage": text.get("passage", ""),
                        "scenario": text.get("scenario", "")})
    return out


def check_alignment(rows, records):
    """Make sure the development file is the one the run was scored on."""
    missing = [r["id"] for r in rows if int(r["id"].rsplit("/", 1)[1]) not in records]
    mismatched = [r["id"] for r in rows if int(r["id"].rsplit("/", 1)[1]) in records
                  and records[int(r["id"].rsplit("/", 1)[1])]["questions"]["question"]["label"] != r["label"]]
    if missing or mismatched:
        raise SystemExit(
            f"the development file does not match this run ({len(missing)} ids missing, "
            f"{len(mismatched)} labels differ). Pass the file the run was scored on with --data.")


def build_eval(run_dir, records):
    run_dir = Path(run_dir)
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    name = result.get("name", run_dir.name)
    rows = load_rows(run_dir / "development" / "rows.json", result.get("temperature", 1.0))
    check_alignment(rows, records)

    models = []
    baseline_rows = run_dir / "baseline" / "development" / "rows.json"
    if baseline_rows.exists() and "baseline" in result:
        b_temp = result["baseline"].get("development", {}).get("temperature", 1.0)
        b = summarize(load_rows(baseline_rows, b_temp))
        models.append({"name": f"Base model ({result['baseline'].get('run', 'init')})", "final": False, **b})
    main = summarize(rows)
    models.append({"name": f"Fine-tuned KEV ({name})", "final": True, **main})

    return {
        "run": name,
        "init_from": result.get("init_from"),
        "temperature": result.get("temperature"),
        "threshold": THRESHOLD,
        "summary": main,
        "models": [{k: m[k] for k in ("name", "final", "n", "overall_accuracy", "unsupported_answer_rate",
                                      "correct_abstention_rate", "ece")} for m in models],
        "examples": examples(rows, records),
    }


def pick_examples(records, per_label=2):
    """Short, varied development items for the Agent page's starter cards."""
    candidates = defaultdict(list)
    for line, rec in records.items():
        d = describe(rec)
        if (80 <= len(d["passage"]) <= 450 and len(d["question"]) <= 160 and d["answer"]
                and not d["answer"].lower().startswith("there is not enough")):
            candidates[d["label"]].append((len(d["passage"]), line, d))
    picked, passages = [], set()
    for label in (TRUE, FALSE, IDK):
        seen = set()
        for _, line, d in sorted(candidates[label]):
            if d["scenario"] in seen or d["passage"] in passages:
                continue
            seen.add(d["scenario"])
            passages.add(d["passage"])
            picked.append({"id": f"custom/{line}", "label": d["scenario"] or "Development set",
                           "passage": d["passage"], "question": d["question"], "answer": d["answer"]})
            if len(seen) == per_label:
                break
    return picked


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="pulled run directory, e.g. ../runs/<run>")
    parser.add_argument("--data", default=DEFAULT_DATA, help="development JSONL the run was scored on")
    args = parser.parse_args()

    records = load_records(args.data)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "examples.json").write_text(json.dumps(pick_examples(records), indent=1, ensure_ascii=False))
    print(f"wrote {OUT_DIR / 'examples.json'}")

    if args.run:
        data = build_eval(args.run, records)
        (OUT_DIR / "eval.json").write_text(json.dumps(data, ensure_ascii=False))
        s = data["summary"]
        print(f"wrote {OUT_DIR / 'eval.json'}: run {data['run']}, {s['n']} questions, "
              f"overall accuracy {s['overall_accuracy']:.1%}, coverage {s['coverage']:.1%}")


if __name__ == "__main__":
    main()
