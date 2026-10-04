"""Add this to your Hugging Face / TRL trainer so the dashboard gets your real loss curves.

    from metrics.hf_callback import DashboardLogger
    trainer = SFTTrainer(..., callbacks=[DashboardLogger("metrics/training_log.json")])
"""
import json

from transformers import TrainerCallback


class DashboardLogger(TrainerCallback):
    def __init__(self, path="metrics/training_log.json"):
        self.path = path
        self.rows = {}

    def on_log(self, args, state, control, logs=None, **kwargs):
        if not logs:
            return
        row = self.rows.setdefault(
            state.global_step,
            {"step": state.global_step, "train_loss": None, "eval_loss": None, "learning_rate": None},
        )
        if "loss" in logs:
            row["train_loss"] = logs["loss"]
        if "eval_loss" in logs:
            row["eval_loss"] = logs["eval_loss"]
        if "learning_rate" in logs:
            row["learning_rate"] = logs["learning_rate"]
        with open(self.path, "w") as f:
            json.dump(sorted(self.rows.values(), key=lambda r: r["step"]), f, indent=1)
