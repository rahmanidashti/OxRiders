"""When the live OxRiders agent (server.py) answers and when it says "I don't know".

The model scores a candidate answer against a passage with three options (the criteria it was trained on):
  A = "True", B = "False", C = "There is not enough information".
The agent answers with the more likely of True/False when that probability is at least THRESHOLD;
otherwise it abstains. Because the three probabilities sum to 1, abstaining always covers the case
where "not enough information" is the model's top choice (then max(P(True), P(False)) < 0.5).
"""
import os

THRESHOLD = float(os.getenv("OXRIDERS_THRESHOLD", "0.6"))

TRUE, FALSE, IDK = "A", "B", "C"
CRITERIA = {TRUE: "True", FALSE: "False", IDK: "There is not enough information"}


def decide(p_true, p_false, threshold=THRESHOLD):
    """Return (choice, confidence): choice is TRUE, FALSE, or None (abstain);
    confidence is the probability of the more likely of True/False."""
    best, confidence = (TRUE, p_true) if p_true >= p_false else (FALSE, p_false)
    return (best if confidence >= threshold else None), confidence


def build_request(passage, question, answer):
    """The model request in the same shape as the training data (data/development.jsonl)."""
    state = "Biomedical literature scenario: User question\nContext: " + passage.strip()
    instructions = f'Question: {question.strip()}\nIs "{answer.strip()}" the correct answer to this question?'
    return {"state": state, "instructions": instructions, "criteria": CRITERIA}
