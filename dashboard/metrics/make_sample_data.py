"""Creates fake training data so the dashboard has something to show.
Replace training_log.json / eval_results.json with your real results later."""
import json
import math
import random
from pathlib import Path

random.seed(0)
here = Path(__file__).parent
log = []
for step in range(0, 1001, 10):
    row = {
        "step": step,
        "train_loss": round(2.6 * math.exp(-step / 300) + 0.9 + random.uniform(-0.08, 0.08), 4),
        "learning_rate": round(2e-4 * min(1, step / 100) * (1 - step / 1100), 8),
        "eval_loss": None,
    }
    if step % 100 == 0:
        row["eval_loss"] = round(2.5 * math.exp(-step / 350) + 1.05, 4)
    log.append(row)
(here / "training_log.json").write_text(json.dumps(log, indent=1))
