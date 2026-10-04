import json
import os
import numpy as np

RUN_DIR = "runs/litqa-grounded-m3/"
baseline_path = os.path.join(RUN_DIR, "baseline", "development", "rows.json")
finetuned_path = os.path.join(RUN_DIR, "development", "rows.json")

def load_rows(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Could not find: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
            return list(data.values())
        return data

baseline_rows = load_rows(baseline_path)
finetuned_rows = load_rows(finetuned_path)

CHOICE_KEYS = ["A", "B", "C", "D", "E"]

def extract_info(row):
    # Do NOT use 'or' with numeric 0! In Python: 0 or None evaluates to None!
    raw_label = row.get("label")
    if raw_label is None:
        raw_label = row.get("target")
    if raw_label is None:
        raw_label = row.get("y")

    # Map raw_label: 0/None -> A, 1 -> B, 2 -> C
    if raw_label == 0 or raw_label in ("0", "A", "T", "True") or raw_label is None:
        label = "A"
    elif raw_label == 1 or raw_label in ("1", "B", "F", "False"):
        label = "B"
    elif raw_label == 2 or raw_label in ("2", "C", "IDK"):
        label = "C"
    else:
        label = str(raw_label)

    # Probabilities
    raw_probs = row.get("probabilities") or row.get("p") or row.get("probs") or []
    if isinstance(raw_probs, list):
        probs = {CHOICE_KEYS[i]: float(val) for i, val in enumerate(raw_probs) if i < len(CHOICE_KEYS)}
    elif isinstance(raw_probs, dict):
        probs = {k: float(v) for k, v in raw_probs.items()}
    else:
        probs = {}

    # Argmax Prediction
    raw_pred = row.get("prediction") if row.get("prediction") is not None else row.get("pred")
    if raw_pred == 0 or raw_pred in ("0", "A", "T"):
        pred = "A"
    elif raw_pred == 1 or raw_pred in ("1", "B", "F"):
        pred = "B"
    elif raw_pred == 2 or raw_pred in ("2", "C", "IDK"):
        pred = "C"
    elif not raw_pred and probs:
        pred = max(probs, key=probs.get)
    else:
        pred = str(raw_pred)

    return label, probs, pred

idk_baseline_probs = []
idk_finetuned_probs = []
idk_base_correct = 0
idk_fine_correct = 0
total_idk = 0

sample_shifts = []

for b_row, f_row in zip(baseline_rows, finetuned_rows):
    b_label, b_probs, b_pred = extract_info(b_row)
    f_label, f_probs, f_pred = extract_info(f_row)

    # In triplets, Option C (index 2) is 'There is not enough information' / IDK
    if b_label in ("C", "IDK", "2"):
        total_idk += 1
        
        p_c_base = b_probs.get("C", 0.0)
        p_c_fine = f_probs.get("C", 0.0)
        
        idk_baseline_probs.append(p_c_base)
        idk_finetuned_probs.append(p_c_fine)
        
        if b_pred in ("C", "IDK", "2"):
            idk_base_correct += 1
        if f_pred in ("C", "IDK", "2"):
            idk_fine_correct += 1
            
        question_text = (
            b_row.get("instructions") 
            or b_row.get("question") 
            or b_row.get("state")
            or f"Item #{total_idk}"
        )
        sample_shifts.append({
            "question": str(question_text).replace("\n", " ")[:90] + "...",
            "p_base": p_c_base,
            "p_fine": p_c_fine,
            "pred_base": b_pred,
            "pred_fine": f_pred
        })

print("\n" + "=" * 70)
print("EVALUATION: 'THERE IS NOT ENOUGH INFORMATION' (OPTION C / IDK)")
print("=" * 70)

if total_idk == 0:
    print("Warning: No records found with label 'C' / 'IDK' / 2.")
    print("First row inspect:", baseline_rows[0] if baseline_rows else "Empty")
else:
    mean_p_base = np.mean(idk_baseline_probs)
    mean_p_fine = np.mean(idk_finetuned_probs)
    delta_p = mean_p_fine - mean_p_base

    print(f"Total unanswerable (IDK) evaluation records : {total_idk}")
    print("-" * 70)
    print(f"Untrained Baseline Accuracy on IDK         : {idk_base_correct / total_idk * 100:.1f}% ({idk_base_correct}/{total_idk})")
    print(f"Fine-Tuned Model Accuracy on IDK           : {idk_fine_correct / total_idk * 100:.1f}% ({idk_fine_correct}/{total_idk})")
    print("-" * 70)
    print(f"Mean P(Option C) BEFORE Fine-Tuning        : {mean_p_base:.4f} ({mean_p_base * 100:.1f}%)")
    print(f"Mean P(Option C) AFTER Fine-Tuning         : {mean_p_fine:.4f} ({mean_p_fine * 100:.1f}%)")
    print(f"Net Probability Shift on IDK Questions     : {delta_p:+.4f} ({delta_p * 100:+.1f}%)")
    print("=" * 70)
    
    print("\nSAMPLE QUESTIONS & PROBABILITY SHIFTS:")
    print("-" * 70)
    # Sort by largest increase in P(IDK)
    sample_shifts.sort(key=lambda x: x["p_fine"] - x["p_base"], reverse=True)
    for s in sample_shifts[:5]:
        print(f"Q: {s['question']}")
        print(f"   P(IDK): {s['p_base']:.3f} -> {s['p_fine']:.3f} | Pred: {s['pred_base']} -> {s['pred_fine']}")
        print()

# Normalized Breakdown across all 3 classes
LABEL_MAP = {
    "A": ["A", "T", "True", "0"],
    "B": ["B", "F", "False", "1"],
    "C": ["C", "IDK", "There is not enough information", "2"]
}

print("\nPER-CLASS ACCURACY BREAKDOWN:")
print("-" * 70)

for class_key, aliases in [("A (True)", LABEL_MAP["A"]), 
                           ("B (False)", LABEL_MAP["B"]), 
                           ("C (IDK)", LABEL_MAP["C"])]:
    tot = 0
    b_corr = 0
    f_corr = 0
    
    for b_row, f_row in zip(baseline_rows, finetuned_rows):
        b_label, _, b_pred = extract_info(b_row)
        f_label, _, f_pred = extract_info(f_row)
        
        if b_label in aliases:
            tot += 1
            if b_pred in aliases:
                b_corr += 1
            if f_pred in aliases:
                f_corr += 1
                
    if tot > 0:
        b_pct = (b_corr / tot) * 100
        f_pct = (f_corr / tot) * 100
        print(f"Class {class_key:10s} (N={tot:2d}) : Baseline = {b_corr:2d}/{tot:2d} ({b_pct:5.1f}%) -> Finetuned = {f_corr:2d}/{tot:2d} ({f_pct:5.1f}%)")
    else:
        print(f"Class {class_key:10s} : No records found.")
print("-" * 70)
