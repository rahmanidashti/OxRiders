"""Dry-run every guard over a batch script's EDITS and report ALL violations."""
import re
import sys
from collections import Counter

import pyarrow.parquet as pq

path = sys.argv[1]
ns = {}
src = open(path, encoding="utf-8").read()
exec(src[src.index("EDITS = {"):src.index("\nBANNED")], ns)
exec(src[src.index("BANNED = {"):src.index("\nSCHEMA")], ns)
EDITS, BANNED = ns["EDITS"], ns["BANNED"]
RETIRED, OVERDELETED = ns["RETIRED"], ns["OVERDELETED"]

t = pq.read_table("data/train-00000-of-00001.parquet")
qs = t.column("question").to_pylist()
C = Counter()
for q in qs:
    C.update(set(re.findall(r"[a-z]+", q.lower())))

bad = 0
for i, newq in sorted(EDITS.items()):
    ow = set(re.findall(r"[a-z]+", qs[i].lower()))
    nw = set(re.findall(r"[a-z]+", newq.lower()))
    probs = []
    if {w for w in nw if w in BANNED} - ow:
        probs.append(f"banned {sorted({w for w in nw if w in BANNED} - ow)}")
    if {w for w in nw if w in RETIRED} - ow:
        probs.append(f"retired {sorted({w for w in nw if w in RETIRED} - ow)}")
    if {w for w in ow if w in OVERDELETED} - nw:
        probs.append(f"over-deleted {sorted({w for w in ow if w in OVERDELETED} - nw)}")
    rare = {w: C[w] for w in nw - ow if C[w] < 15 and len(w) > 3}
    if rare:
        probs.append(f"too rare {rare}")
    if probs:
        bad += 1
        print(f"{i}: {'; '.join(probs)}")
        print(f"     {newq}")
print(f"\n{bad} of {len(EDITS)} rows need a different swap"
      if bad else f"\nall {len(EDITS)} rows pass all four guards")
