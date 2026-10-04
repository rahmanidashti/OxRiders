"""Embed dataset questions with a sentence embedder, project them with UMAP, and
write a front-end-ready JSON file (plus a self-contained HTML viewer).

One point per item: the item's original question (the label-A row), without
the candidate answer. Each point carries two categorical fields:

  origin  - the dataset the item came from (SciQ, templated SciQ-style, LitQA2,
            SuppQA, HLE, DeepFabric, evidence-limits)
  domain  - the science domain. Taken from the scenario label where the source
            has one (HLE-Physics, deepfabric "chemistry", ...); otherwise
            assigned zero-shot by cosine similarity between the question
            embedding and per-domain prototype descriptions. `domain_source`
            says which ("label" or "zero-shot").

Usage:
  .venv/bin/python viz/question_umap/build_question_umap.py \
      --inputs data/train.jsonl [data/development.jsonl data/calibration.jsonl]

Writes, next to this script:
  points.json   data contract consumed by umap-scatter.js
  index.html    standalone viewer (data + module inlined, works from file://)
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# Categories are emitted largest-first: that order is the color-slot order, so the
# three slots that validate all-pairs on a scatter go to the classes that dominate it.
ORIGINS = [
    ("sciq", "SciQ"),
    ("templated", "Templated (SciQ-style)"),
    ("litqa2", "LitQA2"),
    ("deepfabric", "DeepFabric"),
    ("hle", "HLE"),
    ("suppqa", "SuppQA"),
    ("evidence_limits", "Evidence-limits"),
]
DOMAINS = [
    ("biology", "Biology"),
    ("physics", "Physics"),
    ("chemistry", "Chemistry"),
    ("earth", "Earth & environment"),
    ("medicine", "Medicine & health"),
    ("astronomy", "Astronomy & space"),
    ("engineering", "Engineering & other"),
]

# Zero-shot prototypes: each domain is the mean embedding of these descriptions.
DOMAIN_PROTOTYPES = {
    "biology": [
        "a biology question about cells, genes, DNA, proteins, evolution, ecology, plants or animals",
        "What organelle carries out photosynthesis in plant cells?",
        "Which molecule carries genetic information from DNA to the ribosome?",
        "What do we call organisms that make their own food?",
    ],
    "physics": [
        "a physics question about forces, motion, energy, electricity, magnetism, waves, light or heat",
        "What is the magnitude of the magnetic field near a long straight wire carrying current?",
        "What is the unit of electrical resistance?",
        "What happens to the speed of a wave when it enters a denser medium?",
    ],
    "chemistry": [
        "a chemistry question about atoms, elements, molecules, chemical reactions, bonds, acids and bases",
        "What is the pH of a weak acid solution?",
        "What type of bond forms when electrons are shared between atoms?",
        "What is the rate law of this chemical reaction?",
    ],
    "earth": [
        "an earth science question about rocks, minerals, earthquakes, volcanoes, weather, climate, oceans or the environment",
        "What type of rock forms when magma cools underground?",
        "What causes most outdoor air pollution?",
        "Which layer of the atmosphere contains the ozone layer?",
    ],
    "medicine": [
        "a medical question about human disease, patients, clinical treatment, drugs, anatomy or health",
        "Which drug is the first-line treatment for this patient's condition?",
        "What disease is caused by a deficiency of insulin?",
        "Which tumour mutation predicts response to the targeted therapy?",
    ],
    "astronomy": [
        "an astronomy question about stars, planets, galaxies, the sun, the moon, the solar system or the universe",
        "What is the closest star to Earth after the Sun?",
        "Why do the planets orbit the Sun?",
        "What is a light-year a measure of?",
    ],
}

# Engineering & other is kept for sources labelled that way (HLE) but is not a
# zero-shot target: as a catch-all it absorbs heat-transfer and ecology questions.
ZERO_SHOT_DOMAINS = [k for k, _ in DOMAINS if k != "engineering"]

# Scenario label -> domain, for sources that carry one. None = zero-shot.
SCENARIO_DOMAIN = {
    "hle-physics": "physics",
    "hle-chemistry": "chemistry",
    "hle-engineering": "engineering",
    "hle-other": "engineering",
    "biology": "biology",
    "physics": "physics",
    "chemistry": "chemistry",
    "astronomy": "astronomy",
    "earth": "earth",
    "environment": "earth",
    "litqa2": "biology",
    "suppqa": "biology",
    "evidence-limits": "medicine",
}
# HLE-Biology/Medicine is labelled but spans two of our domains: zero-shot within them.
RESTRICTED_ZERO_SHOT = {"hle-biology/medicine": ["biology", "medicine"]}


def origin_of(scenario, item_id):
    s = scenario.lower()
    if s.startswith("hle-"):
        return "hle"
    if item_id.startswith("json_arr"):
        return "templated"
    if item_id.startswith("deepfabric"):
        return "deepfabric"
    return {"science": "sciq", "sciq": "sciq", "litqa2": "litqa2", "suppqa": "suppqa",
            "evidence-limits": "evidence_limits"}.get(s, "sciq")


def question_text(instructions):
    m = re.match(r"Question: (.*?)\nIs \".*\" the (?:guaranteed )?correct answer", instructions, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"statement true\? \"(.*)\"", instructions, re.S)  # evidence-limits
    if m:
        return m.group(1).strip()
    return instructions.strip()


def load_items(paths):
    items = []
    for path in paths:
        split = Path(path).stem
        for line in open(path):
            if not line.strip():
                continue
            row = json.loads(line)
            q = row["questions"]["question"]
            if q["label"] != "A":  # one point per item: the original question
                continue
            state = row["state"]
            scenario = re.search(r"scenario: (.*)", state).group(1).strip()
            item_id = re.search(r"Item ID: (.*)", state).group(1).strip()
            items.append({
                "id": item_id,
                "q": question_text(q["instructions"]),
                "scenario": scenario,
                "origin": origin_of(scenario, item_id),
                "split": split,
            })
    return items


def assign_domains(items, emb, model):
    keys = list(DOMAIN_PROTOTYPES)
    protos = np.stack([
        model.encode(DOMAIN_PROTOTYPES[k], normalize_embeddings=True).mean(0) for k in keys
    ])
    protos /= np.linalg.norm(protos, axis=1, keepdims=True)
    sims = emb @ protos.T
    for it, s in zip(items, sims):
        scen = it["scenario"].lower()
        if scen in SCENARIO_DOMAIN:
            it["domain"], it["domain_source"] = SCENARIO_DOMAIN[scen], "label"
            continue
        allowed = RESTRICTED_ZERO_SHOT.get(scen, ZERO_SHOT_DOMAINS)
        idx = [keys.index(k) for k in allowed]
        best = idx[int(np.argmax(s[idx]))]
        it["domain"], it["domain_source"] = keys[best], "zero-shot"

    # Sanity check: zero-shot accuracy on the items that do carry a label.
    zs = [keys.index(k) for k in ZERO_SHOT_DOMAINS]
    by_scenario = {}
    for it, s in zip(items, sims):
        if it["domain_source"] == "label" and it["domain"] in ZERO_SHOT_DOMAINS:
            guess = keys[zs[int(np.argmax(s[zs]))]]
            hit, total = by_scenario.get(it["scenario"], (0, 0))
            by_scenario[it["scenario"]] = (hit + (guess == it["domain"]), total + 1)
    hits, total = (sum(v[i] for v in by_scenario.values()) for i in (0, 1))
    if total:
        print(f"zero-shot agreement with scenario labels: {hits}/{total} ({100 * hits / total:.1f}%)")
        for scen, (h, t) in sorted(by_scenario.items(), key=lambda kv: -kv[1][1]):
            print(f"  {scen:24s} {h}/{t}")


def categories(items, field, spec):
    counts = Counter(it[field] for it in items)
    cats = [{"key": k, "label": label, "count": counts[k]} for k, label in spec if counts[k]]
    return sorted(cats, key=lambda c: -c["count"])  # slot order: largest first


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="+", default=["data/train.jsonl"])
    ap.add_argument("--model", default="sentence-transformers/all-mpnet-base-v2")
    ap.add_argument("--n-neighbors", type=int, default=15)
    ap.add_argument("--min-dist", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=str(HERE))
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    import umap

    items = load_items(args.inputs)
    print(f"{len(items)} items from {', '.join(args.inputs)}")

    model = SentenceTransformer(args.model)
    emb = model.encode([it["q"] for it in items], batch_size=128, normalize_embeddings=True,
                       show_progress_bar=True, convert_to_numpy=True)
    assign_domains(items, emb, model)

    xy = umap.UMAP(n_neighbors=args.n_neighbors, min_dist=args.min_dist, metric="cosine",
                   random_state=args.seed).fit_transform(emb)
    for it, (x, y) in zip(items, xy):
        it["x"], it["y"] = round(float(x), 4), round(float(y), 4)

    fields = {
        "domain": {"label": "Domain", "categories": categories(items, "domain", DOMAINS)},
        "origin": {"label": "Origin dataset", "categories": categories(items, "origin", ORIGINS)},
    }
    splits = sorted({it["split"] for it in items})
    if len(splits) > 1:
        fields["split"] = {"label": "Split", "categories": categories(items, "split", [(s, s) for s in splits])}

    keep = ["id", "q", "x", "y", "domain", "domain_source", "origin", "scenario", "split"]
    payload = {
        "meta": {
            "title": "Question embeddings (UMAP)",
            "model": args.model,
            "umap": {"n_neighbors": args.n_neighbors, "min_dist": args.min_dist, "metric": "cosine",
                     "random_state": args.seed},
            "inputs": args.inputs,
            "n_points": len(items),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "fields": fields,
        "points": [{k: it[k] for k in keep} for it in items],
    }

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (out / "points.json").write_text(data_json)

    # Standalone viewer: inline the module and the data so it opens from file://.
    template = (HERE / "index.template.html").read_text()
    module = (HERE / "umap-scatter.js").read_text().replace("export function", "function")
    html = (template
            .replace("/*__MODULE__*/", module)
            .replace("/*__DATA__*/null", data_json.replace("</", "<\\/")))
    (out / "index.html").write_text(html)
    for f in fields:
        print(f, Counter(it[f] for it in items).most_common())
    print(f"wrote {out / 'points.json'} and {out / 'index.html'}")


if __name__ == "__main__":
    main()
