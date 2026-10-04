import os
import json
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel
import modal

# Define the Modal App and Volume
app = modal.App("kev-serving")
runs_volume = modal.Volume.from_name("kev-finetune-runs", create_if_missing=True)

# Container Image with Kev dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch>=2.2.0",
        "transformers>=4.40.0",
        "peft>=0.10.0",
        "pydantic>=2.0",
        "fastapi",
        "accelerate",
        "datasets",
    )
    .add_local_python_source("kev")  # Mounts the local 'kev' package inside the container
)

# API Request Schema
class QueryRequest(BaseModel):
    state: str
    instructions: str
    criteria: Optional[Dict[str, str]] = {
        "A": "True",
        "B": "False",
        "C": "There is not enough information"
    }

@app.cls(
    image=image,
    gpu="H100",                    # Or "L4" / "A10G"
    volumes={"/runs": runs_volume},
    scaledown_window=300,          # 5 minutes idle timeout
    timeout=60,
)
class KevModel:
    @modal.enter()
    def load_model(self):
        import torch
        from kev.checkpoint import load

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.run_name = os.environ.get("KEV_RUN_NAME", "litqa-triplets-v1")
        run_dir = Path(f"/runs/{self.run_name}")
        
        checkpoint_dir = run_dir / "checkpoint" if (run_dir / "checkpoint").exists() else run_dir
        if not checkpoint_dir.exists():
            print(f"--> {checkpoint_dir} not on volume. Using base 'jaredpalmer/kev-4b'.")
            target = "jaredpalmer/kev-4b"
        else:
            target = str(checkpoint_dir)

        # Calibrated temperature
        self.temperature = 1.0
        result_path = run_dir / "result.json"
        if result_path.exists():
            try:
                with open(result_path, "r") as f:
                    res = json.load(f)
                    self.temperature = float(res.get("fitted_temperature", res.get("temperature", 1.0)))
            except Exception as e:
                print(f"Warning: could not read temperature: {e}")

        print(f"--> Loading Kev from '{target}' onto {self.device}...")
        self.tok, self.model = load(target, self.device)
        self.model.eval()
        print("--> Kev model loaded and ready.")

    @modal.fastapi_endpoint(method="POST", docs=True)
    def predict(self, req: QueryRequest):
        import torch
        from kev.api import SystemOneRequest, to_record

        # Construct official SystemOneRequest
        req_payload = {
            "state": req.state,
            "questions": {
                "question": {
                    "type": "choice",
                    "instructions": req.instructions,
                    "criteria": req.criteria
                }
            }
        }

        try:
            # 1. Convert to Kev internal record via official api.to_record
            sys_req = SystemOneRequest.model_validate(req_payload)
            rec, meta = to_record(sys_req)

            with torch.no_grad():
                # 2. Encode on GPU
                enc = self.model.encode(self.tok, rec, max_state=384, strict=False)
                
                # Move tensors to GPU if needed
                if hasattr(enc, "to"):
                    enc = enc.to(self.device)
                elif isinstance(enc, dict):
                    enc = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in enc.items()}

                # 3. Model forward pass for probabilities
                raw_out = self.model.probs(enc)

                if isinstance(raw_out, dict):
                    prob_tensor = raw_out.get("question", list(raw_out.values())[0])
                elif isinstance(raw_out, (list, tuple)):
                    prob_tensor = raw_out[0]
                else:
                    prob_tensor = raw_out

                # Convert tensor to Python floats
                if hasattr(prob_tensor, "cpu"):
                    probs = prob_tensor.squeeze().cpu().tolist()
                else:
                    probs = list(prob_tensor)

            if isinstance(probs, float):
                probs = [probs]

            # Map probabilities back to criteria keys (A, B, C)
            keys = list(req.criteria.keys())
            prob_dict = {k: round(probs[i], 4) for i, k in enumerate(keys) if i < len(probs)}
            predicted_winner = max(prob_dict, key=prob_dict.get)

            return {
                "prediction": predicted_winner,
                "label_meaning": req.criteria.get(predicted_winner),
                "confidence": prob_dict[predicted_winner],
                "probabilities": prob_dict,
                "calibrated_temperature": self.temperature
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e), "traceback": traceback.format_exc()}
