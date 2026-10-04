import json
import os
import random
from collections import defaultdict

INPUT_FILE = "triplets.jsonl"
OUTPUT_DIR = "data/litqa_triplets4"
os.makedirs(OUTPUT_DIR, exist_ok=True)

KEY_MAP = {
    "T": "A",
    "F": "B",
    "IDK": "C"
}

def clean_record(line):
    data = json.loads(line.strip())
    q_data = data["questions"]["question"]
    
    # Standardize criteria to A, B, C
    new_criteria = {
        "A": "True",
        "B": "False",
        "C": "There is not enough information"
    }
    
    # Map label
    old_label = q_data["label"]
    new_label = KEY_MAP.get(old_label, old_label)
    
    data["questions"]["question"]["criteria"] = new_criteria
    data["questions"]["question"]["label"] = new_label
    return data

# 1. Group records by Item ID to prevent data leakage
groups = defaultdict(list)

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = clean_record(line)
        
        # Extract item ID from state header (e.g. lb-litqa2-0000 or ev-0001)
        state_text = rec["state"]
        item_id = None
        for s_line in state_text.split("\n"):
            if s_line.startswith("Item ID:"):
                item_id = s_line.split("Item ID:")[1].strip()
                break
        if not item_id:
            item_id = f"group_{len(groups)}"
            
        groups[item_id].append(rec)

print(f"Loaded {sum(len(v) for v in groups.values())} records across {len(groups)} distinct triplet groups.")

# 2. Split by group (Triplets stay together)
# Ratio: ~70% train, 15% calibration, 15% development
group_ids = list(groups.keys())
rng = random.Random(42)
rng.shuffle(group_ids)

n_total = len(group_ids)
n_train = int(n_total * 0.70)
n_calib = int(n_total * 0.15)

train_groups = group_ids[:n_train]
calib_groups = group_ids[n_train:n_train + n_calib]
dev_groups = group_ids[n_train + n_calib:]

def write_split(filename, group_keys):
    filepath = os.path.join(OUTPUT_DIR, filename)
    count = 0
    with open(filepath, "w", encoding="utf-8") as out:
        for gid in group_keys:
            for rec in groups[gid]:
                out.write(json.dumps(rec) + "\n")
                count += 1
    print(f"Wrote {count} records ({len(group_keys)} groups) to {filepath}")

write_split("train.jsonl", train_groups)
write_split("calibration.jsonl", calib_groups)
write_split("development.jsonl", dev_groups)
print("\nReformatting and group-splitting complete!")
