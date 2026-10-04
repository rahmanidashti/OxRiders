


# create question dataset
python reformat_merge_and_split.py \\
  --csv sciq-impossible-devin.csv hle_unanswerable_184.csv hle_natural_science_184.csv sciq_deepfabric.csv sciq-adversarial_claude.csv sciq-adversarial-devin.csv lab-bench-adv-part1v2.csv  \\
  --json adversarial_sciq_3000.json \\
  --jsonl triplets.jsonl \\
  --out data/all_deduped_triplets \\
  --max_tokens 360

# train
modal run skills/kev-finetune/scripts/kev_modal.py::train \\
  --data data/all_deduped_triplets \\
  --name final-final-final \\
  --init-from jaredpalmer/kev-4b \\
  --epochs 3 \\
  --replay 100 \\
  --lr 5e-05

# get train stats
modal run skills/kev-finetune/scripts/kev_modal.py::pull --name litqa-grounded-m3

# deploy the model
modal deploy serve.py
