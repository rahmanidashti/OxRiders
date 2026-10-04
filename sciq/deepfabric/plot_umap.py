"""UMAP of the DeepFabric SciQ-format questions, coloured by science domain.

Mirrors fig_umap in agentharm_blog/plot_sft_v1_overview.py: semantic embeddings
(L2-normalised) -> cosine UMAP with n_neighbors=30, min_dist=0.15, seed 42, same
matplotlib style. Embeddings come from the Gemini API (gemini-embedding-2) rather
than sentence-transformers all-mpnet-base-v2, because torch does not fit in the
JupyterHub box's 4 GB memory limit; they are cached next to the figure.
(a) coloured by domain, (b) coloured by batch.

Domain = the first-level node of the DeepFabric topic tree/graph the question was
generated from. SciQ records carry no topic id, so each question is matched back to
its raw transcript (metadata.topic_id) by question text.

Usage:
    python plot_umap.py --out-dir figures
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import umap
from matplotlib.lines import Line2D

HERE = Path(__file__).parent
BATCHES = [  # (key, label, colour, sciq file, raw transcripts, topics file)
    ("batch1", "Batch 1 (topic tree)", "#e87ba4", "sciq_batch1_filtered.jsonl", "raw/batch1.jsonl", "raw/topics_batch1.jsonl"),
    ("batch2", "Batch 2 (topic graph)", "#52514e", "sciq_batch2_filtered.jsonl", "raw/batch2.jsonl", "raw/topics_batch2.json"),
]
DOMAINS = [  # (key, label, colour, keyword matched against the first-level topic)
    ("physics", "Physics", "#1c5cab", r"physics|mechanics"),
    ("chemistry", "Chemistry", "#c24e1e", r"chemi"),
    ("biology", "Biology", "#008300", r"biology|genetic"),
    ("earth", "Earth science", "#8a5a2b", r"earth|tectonic"),
    ("astronomy", "Astronomy", "#4a3aa7", r"astronom|celestial"),
    ("environment", "Environmental science", "#eda100", r"environment|ecosystem"),
]
TEXTWIDTH_IN = 5.5
INK, INK_2, INK_3 = "#0b0b0b", "#52514e", "#8a8983"


def set_style(base_pt=7.0):
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Nimbus Roman", "Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": base_pt, "axes.titlesize": base_pt + 0.5, "axes.labelsize": base_pt,
        "xtick.labelsize": base_pt - 0.5, "ytick.labelsize": base_pt - 0.5,
        "legend.fontsize": base_pt - 0.5, "legend.frameon": False,
        "axes.linewidth": 0.5, "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def domain_of(first_level_topic):
    for key, _, _, pattern in DOMAINS:
        if re.search(pattern, first_level_topic, re.I):
            return key
    raise ValueError(f"no domain for topic {first_level_topic!r}")


def topic_domains(path):
    """topic_id -> domain key, for a DeepFabric topic tree (JSONL) or graph (JSON)."""
    if path.suffix == ".jsonl":  # tree: topic_id = sha256(json(path))[:16], see deepfabric Tree._path_to_id
        out = {}
        for line in path.open():
            p = json.loads(line)["path"]
            out[hashlib.sha256(json.dumps(p).encode()).hexdigest()[:16]] = domain_of(p[1])
        return out
    graph = json.loads(path.read_text())
    nodes, root = graph["nodes"], graph["root_id"]
    out = {}
    for node in nodes.values():
        if node["id"] == root:
            continue
        # Map every node, not just leaves: DeepFabric's path walk stops at a node whose
        # children are all on the current path (a cycle), so some samples sit on inner nodes.
        # Walk up the first parent to the root's child; cross-links make a few nodes
        # reachable from two domains, the first parent is the one that created the node.
        cur = node
        while cur["parents"][0] != root:
            cur = nodes[str(cur["parents"][0])]
        out[node["metadata"]["uuid"]] = domain_of(cur["topic"])
    return out


def load(base):
    rows = []
    for key, *_, sciq_file, raw_file, topics_file in BATCHES:
        domains = topic_domains(base / topics_file)
        q2domain = {}
        for line in (base / raw_file).open():
            r = json.loads(line)
            user = next(m["content"] for m in r["messages"] if m["role"] == "user")
            q = " ".join(re.search(r"Question:\s*(.+?)\s*\n\s*A[).:]", user, re.S).group(1).split())
            q2domain[q] = domains[r["metadata"]["topic_id"]]
        for line in (base / sciq_file).open():
            q = json.loads(line)["question"]
            rows.append(dict(batch=key, domain=q2domain[q], question=q))
    return rows


def embed(texts, model_name, cache):
    if cache.exists():
        X = np.load(cache)
        if len(X) == len(texts):
            return X
    from google import genai  # deferred: only needed when the cache is missing
    from google.genai import types

    client = genai.Client()
    config = types.EmbedContentConfig(task_type="CLUSTERING")
    vecs = []
    for i in range(0, len(texts), 100):  # API limit: 100 texts per request
        # One Content per text: a bare list of strings is embedded as a single input.
        contents = [types.Content(parts=[types.Part(text=t)]) for t in texts[i : i + 100]]
        resp = client.models.embed_content(model=model_name, contents=contents, config=config)
        vecs += [e.values for e in resp.embeddings]
    if len(vecs) != len(texts):
        raise SystemExit(f"got {len(vecs)} embeddings for {len(texts)} texts")
    X = np.asarray(vecs, dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    np.save(cache, X)
    return X


def fig_umap(rows, X, w, seed):
    emb = umap.UMAP(n_neighbors=30, min_dist=0.15, metric="cosine", random_state=seed).fit_transform(X)
    fig, axes = plt.subplots(1, 2, figsize=(w, w * 0.52))
    order = np.random.default_rng(seed).permutation(len(rows))  # random z-order
    for ax, field, spec, title in [
        (axes[0], "domain", DOMAINS, "(a) Coloured by domain"),
        (axes[1], "batch", BATCHES, "(b) Coloured by batch"),
    ]:
        cmap = {s[0]: s[2] for s in spec}
        ax.scatter(emb[order, 0], emb[order, 1], s=7, lw=0,
                   c=[cmap[rows[i][field]] for i in order], alpha=0.85, rasterized=True)
        ax.set_xticks([]), ax.set_yticks([])
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#c9c8c2")
        ax.set_xlabel("UMAP 1", color=INK_2), ax.set_ylabel("UMAP 2", color=INK_2)
        ax.set_title(title, loc="left", pad=3)
        cnt = Counter(r[field] for r in rows)
        handles = [Line2D([], [], ls="", marker="o", ms=3.5, mfc=s[2], mec="none",
                          label=f"{s[1]} ({cnt[s[0]]:,})") for s in spec if cnt[s[0]]]
        ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2,
                  handletextpad=0.2, columnspacing=0.8, fontsize=5.8)
    fig.subplots_adjust(wspace=0.12)
    return fig


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", type=Path, default=HERE, help="folder holding the sciq_*.jsonl files and raw/")
    p.add_argument("--out-dir", type=Path, default=HERE / "figures")
    p.add_argument("--embed-model", default="gemini-embedding-2", help="Gemini embedding model")
    p.add_argument("--dpi", type=int, default=600)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()

    set_style()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    rows = load(a.base)
    print(f"{len(rows)} questions;", dict(Counter(r["domain"] for r in rows)))
    X = embed([r["question"] for r in rows], a.embed_model, a.out_dir / f"emb_{a.embed_model}.npy")
    fig = fig_umap(rows, X, TEXTWIDTH_IN, a.seed)
    for ext in ("pdf", "png"):
        fig.savefig(a.out_dir / f"sciq_deepfabric_umap.{ext}", dpi=a.dpi)
    print(f"wrote {a.out_dir}/sciq_deepfabric_umap.pdf/.png")


if __name__ == "__main__":
    main()
