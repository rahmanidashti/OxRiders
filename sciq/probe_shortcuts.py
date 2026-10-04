"""Shortcut probe: can a classifier tell adversarial from original without science?

Two probes, reported per edit_style:
  length-only  -- AUC of a single feature, len(question)
  bag-of-words -- multinomial Naive Bayes over word counts

Folds are grouped by row, so both variants of a question land in the same fold
and the model cannot memorise the pair. AUC is reported as max(auc, 1-auc):
a cleanly inverted separator is just as exploitable as a direct one.
"""

import csv
import math
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
K = 5


def auc(scores, labels):
    pairs = sorted(zip(scores, labels))
    ranks, i = {}, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        r = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[k] = r
        i = j
    pos = sum(l for _, l in pairs)
    neg = len(pairs) - pos
    if not pos or not neg:
        return float("nan")
    s = sum(ranks[k] for k, (_, l) in enumerate(pairs) if l)
    a = (s - pos * (pos + 1) / 2.0) / (pos * neg)
    return max(a, 1 - a)


def nb_fold(train, test):
    cnt = {0: Counter(), 1: Counter()}
    tot = {0: 0, 1: 0}
    ndoc = {0: 0, 1: 0}
    vocab = set()
    for txt, y in train:
        ws = re.findall(r"[a-z]+", txt.lower())
        cnt[y].update(ws)
        tot[y] += len(ws)
        ndoc[y] += 1
        vocab.update(ws)
    V = len(vocab) or 1
    prior = {y: math.log((ndoc[y] + 1) / (len(train) + 2)) for y in (0, 1)}
    out = []
    for txt, y in test:
        ws = [w for w in re.findall(r"[a-z]+", txt.lower()) if w in vocab]
        lp = {}
        for c in (0, 1):
            s = prior[c]
            for w in ws:
                s += math.log((cnt[c][w] + 1) / (tot[c] + V))
            lp[c] = s
        out.append((lp[1] - lp[0], y))
    return out


def probe(rows, name):
    docs, groups = [], []
    for gi, r in enumerate(rows):
        docs.append((r["question"], 0))
        docs.append((r["question_adversarial"], 1))
        groups += [gi, gi]
    lab = [y for _, y in docs]
    lauc = auc([len(t) for t, _ in docs], lab)

    scores, labels = [], []
    for f in range(K):
        tr = [d for d, g in zip(docs, groups) if g % K != f]
        te = [d for d, g in zip(docs, groups) if g % K == f]
        if not te or not tr:
            continue
        for s, y in nb_fold(tr, te):
            scores.append(s)
            labels.append(y)
    bauc = auc(scores, labels)

    d = [len(r["question_adversarial"]) - len(r["question"]) for r in rows]
    print("  %-18s n=%4d  length %.3f  bag-of-words %.3f  mean delta %+.1f"
          % (name, len(rows), lauc, bauc, sum(d) / len(d)))
    return lauc, bauc


rows = list(csv.DictReader(open(os.path.join(ROOT, "sciq-adversarial-manual.csv"),
                                encoding="utf-8")))
by = defaultdict(list)
for r in rows:
    by[r["edit_style"]].append(r)

print("shortcut probe (effective AUC = max(auc, 1-auc); 0.500 = no signal)\n")
for style in sorted(by):
    probe(by[style], style)
print()
probe(rows, "ALL")
