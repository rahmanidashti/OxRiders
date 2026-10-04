"""Write sciq_deepfabric.jsonl as CSV: SciQ columns plus id, domain and source batch."""

import csv
import json
from pathlib import Path

from plot_umap import HERE, load

FIELDS = ["id", "question", "distractor1", "distractor2", "distractor3", "correct_answer", "support", "domain", "batch"]

meta = {r["question"]: r for r in load(HERE)}
rows = [json.loads(line) for line in (HERE / "sciq_deepfabric.jsonl").open()]
with (HERE / "sciq_deepfabric.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    for i, r in enumerate(rows):
        m = meta[r["question"]]
        w.writerow({"id": f"deepfabric-{i:05d}", **r, "domain": m["domain"], "batch": m["batch"]})
print(f"wrote {len(rows)} rows -> sciq_deepfabric.csv")
