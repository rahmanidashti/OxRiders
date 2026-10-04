"""Paired original vs question_adversarial probes on sciq-impossible-authored.csv.

Logistic regression, 5-fold CV grouped by row id, on (a) word count and (b) binary
bag-of-words. Also prints the length gap and the most class-indicative words.
"""

import collections
import csv
import os

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict

ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ROOT, "sciq-impossible-authored.csv"), newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

X = [r["question"] for r in rows] + [r["question_adversarial"] for r in rows]
y = np.array([0] * len(rows) + [1] * len(rows))
groups = np.array(list(range(len(rows))) * 2)
cv = GroupKFold(n_splits=min(5, len(rows)))


def auc(features, model):
    p = cross_val_predict(model, features, y, cv=cv, groups=groups, method="predict_proba")[:, 1]
    return roc_auc_score(y, p)


lengths = np.array([[len(t.split())] for t in X])
vec = CountVectorizer(binary=True, min_df=2)
bow = vec.fit_transform(X)
print(f"pairs: {len(rows)}")
print(f"length AUC: {auc(lengths, LogisticRegression()):.3f}")
print(f"bag-of-words AUC: {auc(bow, LogisticRegression(max_iter=2000)):.3f}")
delta = lengths[len(rows):, 0] - lengths[:len(rows), 0]
print(f"words orig {lengths[:len(rows)].mean():.1f}  adv {lengths[len(rows):].mean():.1f}  "
      f"delta mean {delta.mean():+.2f}  share delta<=0 {np.mean(delta <= 0):.2f}")
coef = LogisticRegression(max_iter=2000).fit(bow, y).coef_[0]
vocab = np.array(vec.get_feature_names_out())
print("top adversarial words:", ", ".join(vocab[np.argsort(coef)[-15:][::-1]]))
adv_counts = collections.Counter(w for t in X[len(rows):] for w in set(t.lower().split()))
orig_counts = collections.Counter(w for t in X[:len(rows)] for w in set(t.lower().split()))
gap = sorted(adv_counts, key=lambda w: adv_counts[w] - orig_counts[w], reverse=True)[:10]
print("most over-represented:", ", ".join(f"{w} {adv_counts[w]}/{orig_counts[w]}" for w in gap))
