import csv
import json
import os
import re
import random
import argparse
from collections import defaultdict

# 1. Load Tokenizer for exact token length verification
TOKENIZER = None
try:
    from transformers import AutoTokenizer
    try:
        TOKENIZER = AutoTokenizer.from_pretrained("jaredpalmer/kev-4b", trust_remote_code=True)
    except Exception:
        TOKENIZER = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Base", trust_remote_code=True)
except Exception:
    pass

def count_tokens(text: str) -> int:
    """Calculates exact token length including the +1 special token counted by Kev."""
    if TOKENIZER is not None:
        try:
            return len(TOKENIZER.encode(text, add_special_tokens=False)) + 1
        except Exception:
            pass
    # Conservative fallback if tokenizer is unavailable (~3 chars per token)
    return (len(text) // 3) + 1

def is_within_token_limit(state_text: str, max_tokens: int = 360) -> bool:
    """Returns True if the state strictly fits within max_tokens."""
    return count_tokens(state_text) <= max_tokens

def normalize_question(q_text: str) -> str:
    """Normalizes question text for exact duplicate detection."""
    q_clean = re.sub(r"^question:\s*", "", q_text.strip(), flags=re.IGNORECASE)
    q_clean = re.sub(r'\s+', ' ', q_clean).strip().lower()
    return q_clean

CRITERIA = {
    "A": "True",
    "B": "False",
    "C": "There is not enough information"
}

LABEL_MAP = {
    "T": "A", "TRUE": "A", "A": "A", "0": "A",
    "F": "B", "FALSE": "B", "B": "B", "1": "B",
    "IDK": "C", "C": "C", "2": "C", "THERE IS NOT ENOUGH INFORMATION": "C"
}

def clean_str(s):
    return " ".join(str(s or "").strip().split())

def make_triplet_records(item_id, scenario_name, context_text, q_true, a_true, a_false, q_idk, max_tokens=360):
    """Constructs the standard A (True), B (False), C (IDK) triplet if state fits max_tokens."""
    ctx = clean_str(context_text) if context_text else "Evaluation task requiring scientific and biological domain knowledge."
    state_text = (
        f"Biomedical literature scenario: {scenario_name}\n"
        f"Item ID: {item_id}\n"
        f"Context: {ctx}"
    )

    # Filter out if state exceeds token limit
    if not is_within_token_limit(state_text, max_tokens=max_tokens):
        return None

    rec_true = {
        "state": state_text,
        "questions": {
            "question": {
                "type": "choice",
                "instructions": f"Question: {q_true}\nIs \"{a_true}\" the correct answer to this question?",
                "criteria": CRITERIA,
                "label": "A"
            }
        }
    }

    rec_false = {
        "state": state_text,
        "questions": {
            "question": {
                "type": "choice",
                "instructions": f"Question: {q_true}\nIs \"{a_false}\" the correct answer to this question?",
                "criteria": CRITERIA,
                "label": "B"
            }
        }
    }

    rec_idk = {
        "state": state_text,
        "questions": {
            "question": {
                "type": "choice",
                "instructions": f"Question: {q_idk}\nIs \"{a_true}\" the correct answer to this question?",
                "criteria": CRITERIA,
                "label": "C"
            }
        }
    }

    return [rec_true, rec_false, rec_idk]

def parse_csv_files(csv_paths, max_tokens=360):
    groups = {}
    hle_f1 = {}
    hle_f2 = {}
    dropped_token_count = 0

    for path in csv_paths:
        if not os.path.exists(path):
            continue
        print(f"Scanning CSV: {path}...")
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = [h.strip() for h in (reader.fieldnames or [])]

            is_hle_f1 = "ideal" in headers and "distractors" in headers
            is_hle_f2 = "original_question" in headers and "modified_question" in headers
            is_deepfabric = "correct_answer" in headers and "distractor1" in headers and "support" in headers

            for row in reader:
                item_id = clean_str(row.get("id"))
                if not item_id:
                    continue

                # 1. HLE f1
                if is_hle_f1:
                    hle_f1[item_id] = row
                    continue

                # 2. HLE f2
                if is_hle_f2:
                    hle_f2[item_id] = row
                    continue

                # 3. DeepFabric f6 / sciq_deepfabric
                if is_deepfabric:
                    q = clean_str(row.get("question"))
                    d1 = clean_str(row.get("distractor1"))
                    d2 = clean_str(row.get("distractor2"))
                    domain = clean_str(row.get("domain", "science"))
                    support = clean_str(row.get("support", ""))

                    state = f"Scientific reasoning scenario: {domain}\nItem ID: {item_id}\nContext: {support}"
                    if not is_within_token_limit(state, max_tokens=max_tokens):
                        dropped_token_count += 1
                        continue

                    r_true = {
                        "state": state,
                        "questions": {"question": {
                            "type": "choice",
                            "instructions": f"Question: {q}\nIs \"There is not enough information to determine the answer\" the correct answer to this question?",
                            "criteria": CRITERIA,
                            "label": "A"
                        }}
                    }
                    r_false = {
                        "state": state,
                        "questions": {"question": {
                            "type": "choice",
                            "instructions": f"Question: {q}\nIs \"{d2}\" the guaranteed correct answer to this question?",
                            "criteria": CRITERIA,
                            "label": "B"
                        }}
                    }
                    r_idk = {
                        "state": state,
                        "questions": {"question": {
                            "type": "choice",
                            "instructions": f"Question: {q}\nIs \"{d1}\" the correct answer to this question?",
                            "criteria": CRITERIA,
                            "label": "C"
                        }}
                    }
                    groups[item_id] = [r_true, r_false, r_idk]
                    continue

                # 4. Standard Adversarial (f3, f4, f5, sciq-adversarial, lab-bench)
                raw_q = row.get("question", "")
                raw_adv_q = row.get("question_adversarial", "")
                answer = clean_str(row.get("answer"))
                passage = clean_str(row.get("key_passage") or row.get("support"))
                subset = clean_str(row.get("subset") or row.get("part") or "Science")

                if "\n\n" in raw_q:
                    parts = raw_q.split("\n\n", 1)
                    if not passage:
                        passage = clean_str(parts[0])
                    q_clean = clean_str(parts[1])
                else:
                    q_clean = clean_str(raw_q)

                if "\n\n" in raw_adv_q:
                    q_adv_clean = clean_str(raw_adv_q.split("\n\n")[-1])
                else:
                    q_adv_clean = clean_str(raw_adv_q) if raw_adv_q else q_clean

                if not q_clean or not answer:
                    continue

                distractor = None
                for i in range(1, 11):
                    d = clean_str(row.get(f"distractor_{i}") or row.get(f"distractor{i}"))
                    if d and d.lower() not in ["i don't know", "idk", "none of the above", ""]:
                        distractor = d
                        break
                if not distractor:
                    distractor = "Unknown alternative"

                triplets = make_triplet_records(item_id, subset, passage, q_clean, answer, distractor, q_adv_clean, max_tokens)
                if triplets is None:
                    dropped_token_count += 1
                else:
                    groups[item_id] = triplets

    # Pair HLE f1 and f2 records
    common_hle_ids = set(hle_f1.keys()).union(set(hle_f2.keys()))
    for hid in common_hle_ids:
        r1 = hle_f1.get(hid, {})
        r2 = hle_f2.get(hid, {})

        q_orig = clean_str(r1.get("question") or r2.get("original_question"))
        a_orig = clean_str(r1.get("ideal") or r2.get("original_answer"))
        q_mod = clean_str(r2.get("modified_question") or q_orig)
        reason = clean_str(r2.get("reason", ""))
        category = clean_str(r1.get("category") or r2.get("category", "Physics"))

        raw_dists = r1.get("distractors", "")
        distractor = "Unknown alternative"
        if raw_dists:
            try:
                parsed_d = json.loads(raw_dists)
                if isinstance(parsed_d, list) and len(parsed_d) > 0:
                    distractor = clean_str(parsed_d[0])
            except Exception:
                distractor = clean_str(raw_dists.replace('"', '').replace('[', '').replace(']', '').split(',')[0])

        if q_orig and a_orig:
            triplets = make_triplet_records(hid, f"HLE-{category}", reason, q_orig, a_orig, distractor, q_mod, max_tokens)
            if triplets is None:
                dropped_token_count += 1
            else:
                groups[hid] = triplets

    if dropped_token_count > 0:
        print(f"-> Dropped {dropped_token_count} CSV items exceeding {max_tokens} tokens.")
    return groups

def parse_json_arrays(json_paths, max_tokens=360):
    """Parses JSON list files such as F_adversarial_sciq_3000.json."""
    groups = {}
    dropped_token_count = 0

    for path in json_paths:
        if not os.path.exists(path):
            continue
        print(f"Scanning JSON Array: {path}...")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading JSON {path}: {e}")
            continue

        if not isinstance(data, list):
            continue

        for idx, item in enumerate(data):
            item_id = item.get("id") or f"json_arr_{idx}"
            q = clean_str(item.get("question"))
            d1 = clean_str(item.get("distractor1") or item.get("distractor_1"))
            d2 = clean_str(item.get("distractor2") or item.get("distractor_2"))
            support = clean_str(item.get("support", ""))

            state = f"Scientific reasoning scenario: SciQ\nItem ID: {item_id}\nContext: {support}"
            if not is_within_token_limit(state, max_tokens=max_tokens):
                dropped_token_count += 1
                continue

            r_true = {
                "state": state,
                "questions": {"question": {
                    "type": "choice",
                    "instructions": f"Question: {q}\nIs \"There is not enough information to determine the answer\" the correct answer to this question?",
                    "criteria": CRITERIA,
                    "label": "A"
                }}
            }
            r_false = {
                "state": state,
                "questions": {"question": {
                    "type": "choice",
                    "instructions": f"Question: {q}\nIs \"{d2}\" the guaranteed correct answer to this question?",
                    "criteria": CRITERIA,
                    "label": "B"
                }}
            }
            r_idk = {
                "state": state,
                "questions": {"question": {
                    "type": "choice",
                    "instructions": f"Question: {q}\nIs \"{d1}\" the correct answer to this question?",
                    "criteria": CRITERIA,
                    "label": "C"
                }}
            }
            groups[item_id] = [r_true, r_false, r_idk]

    if dropped_token_count > 0:
        print(f"-> Dropped {dropped_token_count} JSON array items exceeding {max_tokens} tokens.")
    return groups

def parse_jsonls(jsonl_paths, max_tokens=360):
    """Parses JSONL files like triplets.txt, enforcing the token ceiling without truncating."""
    groups = {}
    dropped_token_count = 0

    for path in jsonl_paths:
        if not os.path.exists(path):
            continue
        print(f"Scanning JSONL: {path}...")
        
        file_groups = defaultdict(list)
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue

                state = rec.get("state", "")
                item_id = None
                for s_line in state.split("\n"):
                    if s_line.startswith("Item ID:"):
                        item_id = s_line.split("Item ID:")[1].strip()
                        break
                if not item_id:
                    item_id = f"jsonl_{idx // 3}"

                q_dict = rec["questions"]["question"]
                q_dict["criteria"] = CRITERIA
                raw_lbl = str(q_dict.get("label", "")).strip().upper()
                q_dict["label"] = LABEL_MAP.get(raw_lbl, "A")

                file_groups[item_id].append(rec)

        # Check token limit per group; drop entire group if any question exceeds ceiling
        for gid, recs in file_groups.items():
            exceeds = any(not is_within_token_limit(r.get("state", ""), max_tokens=max_tokens) for r in recs)
            if exceeds:
                dropped_token_count += 1
            else:
                groups[gid] = recs

    if dropped_token_count > 0:
        print(f"-> Dropped {dropped_token_count} JSONL items exceeding {max_tokens} tokens.")
    return groups

def deduplicate_groups(all_groups):
    """Removes duplicate question items across all sources."""
    unique_groups = {}
    seen_questions = set()
    dup_count = 0

    for gid, triplets in all_groups.items():
        if not triplets or len(triplets) == 0:
            continue
        
        # Use True question instructions as canonical stem
        first_q = triplets[0]["questions"]["question"]["instructions"]
        norm_q = normalize_question(first_q)

        if norm_q in seen_questions:
            dup_count += 1
            continue

        seen_questions.add(norm_q)
        unique_groups[gid] = triplets

    if dup_count > 0:
        print(f"-> Deduplication: Dropped {dup_count} exact duplicate question items.")
    return unique_groups

def main():
    parser = argparse.ArgumentParser(description="Reformat, merge, filter by token limit, deduplicate, and split Kev triplets.")
    parser.add_argument("--csv", nargs="*", default=[], help="Path(s) to CSV files")
    parser.add_argument("--json", nargs="*", default=[], help="Path(s) to JSON array files (e.g. F_adversarial_sciq_3000.json)")
    parser.add_argument("--jsonl", nargs="*", default=[], help="Path(s) to JSONL files (triplets.txt, etc.)")
    parser.add_argument("--out", default="data/all_deduped_triplets", help="Output directory")
    parser.add_argument("--max_tokens", type=int, default=360, help="Maximum allowed token count for state (default 360)")
    parser.add_argument("--train_ratio", type=float, default=0.70)
    parser.add_argument("--calib_ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    all_raw_groups = {}

    # 1. Parse CSVs
    if args.csv:
        csv_groups = parse_csv_files(args.csv, max_tokens=args.max_tokens)
        all_raw_groups.update(csv_groups)

    # 2. Parse JSON arrays
    if args.json:
        json_groups = parse_json_arrays(args.json, max_tokens=args.max_tokens)
        all_raw_groups.update(json_groups)

    # 3. Parse JSONLs
    if args.jsonl:
        jsonl_groups = parse_jsonls(args.jsonl, max_tokens=args.max_tokens)
        all_raw_groups.update(jsonl_groups)

    # 4. Deduplicate questions across all sources
    print("\nRunning final duplicate check across all sources...")
    all_groups = deduplicate_groups(all_raw_groups)

    total_records = sum(len(v) for v in all_groups.values())
    print(f"\n=======================================================")
    print(f"Total clean, unique retained items: {len(all_groups)} ({total_records} questions)")
    print(f"=======================================================")

    # 5. Group-level split (keeps True, False, IDK together)
    group_keys = list(all_groups.keys())
    rng = random.Random(args.seed)
    rng.shuffle(group_keys)

    n_total = len(group_keys)
    n_train = int(n_total * args.train_ratio)
    n_calib = int(n_total * args.calib_ratio)

    splits = {
        "train.jsonl": group_keys[:n_train],
        "calibration.jsonl": group_keys[n_train:n_train + n_calib],
        "development.jsonl": group_keys[n_train + n_calib:]
    }

    print("\nWriting Kev splits:")
    print("-" * 65)
    for filename, keys in splits.items():
        out_path = os.path.join(args.out, filename)
        label_counter = defaultdict(int)
        count = 0
        with open(out_path, "w", encoding="utf-8") as out_f:
            for k in keys:
                for rec in all_groups[k]:
                    out_f.write(json.dumps(rec) + "\n")
                    label_counter[rec["questions"]["question"]["label"]] += 1
                    count += 1
        print(f"-> {filename:18s}: {count:4d} records ({len(keys):3d} groups) | Labels: {dict(sorted(label_counter.items()))}")
    print("-" * 65)
    print(f"All files successfully generated in: {args.out}/\n")

if __name__ == "__main__":
    main()
