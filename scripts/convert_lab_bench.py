"""Convert downloaded LAB-Bench Parquet files to CSV, JSONL and external images.

Install pyarrow and Pillow, then run from any directory:
    python scripts/convert_lab_bench.py
Original Parquet files and license notices are retained unchanged.
"""
import csv
import hashlib
import io
import json
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "datasets" / "lab-bench"
OUTPUT = ROOT / "datasets" / "lab-bench-text"
EXCLUDED = {"FigQA", "TableQA"}
REVISION = "5c77cec648430f30611808808861eb86f81d5eaa"


def convert():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for path in sorted(SOURCE.glob("*/*.parquet")):
        subset = path.parent.name
        if subset in EXCLUDED:
            continue
        table = pq.read_table(path)
        rows = table.to_pylist()
        image_count = 0

        def externalize(value):
            nonlocal image_count
            if isinstance(value, dict) and isinstance(value.get("bytes"), bytes):
                data = value["bytes"]
                with Image.open(io.BytesIO(data)) as im:
                    extension = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tiff", "WEBP": ".webp", "GIF": ".gif"}.get(im.format, ".bin")
                    im.verify()
                digest = hashlib.sha256(data).hexdigest()
                relative = Path("images") / subset / (digest + extension)
                target = OUTPUT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(data)
                assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
                image_count += 1
                return {"path": relative.as_posix(), "original_path": value.get("path")}
            if isinstance(value, dict):
                return {k: externalize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [externalize(v) for v in value]
            return value

        encoded = []
        json_records = []
        for row in rows:
            row = externalize(row)
            json_records.append(row)
            record = {}
            for key, value in row.items():
                if value is None:
                    record[key] = ""
                elif isinstance(value, (dict, list)):
                    record[key] = json.dumps(value, ensure_ascii=False)
                else:
                    record[key] = str(value)
            encoded.append(record)
        dest = OUTPUT / f"{subset}.csv"
        with dest.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=table.column_names)
            writer.writeheader()
            writer.writerows(encoded)
        with dest.open(encoding="utf-8-sig", newline="") as stream:
            restored = list(csv.DictReader(stream))
        assert restored == encoded, f"CSV round-trip failed for {subset}"
        json_dest = OUTPUT / f"{subset}.jsonl"
        with json_dest.open("w", encoding="utf-8") as stream:
            for row in json_records:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        with json_dest.open(encoding="utf-8") as stream:
            restored_json = [json.loads(line) for line in stream]
        assert restored_json == json_records, f"JSONL round-trip failed for {subset}"
        result = {"subset": subset, "rows": len(rows), "image_references": image_count,
                  "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "csv": dest.name,
                  "jsonl": json_dest.name}
        summary.append(result)
        print(json.dumps(result), flush=True)
    (OUTPUT / "LICENSE").write_bytes((SOURCE / "LICENSE").read_bytes())
    (OUTPUT / "manifest.json").write_text(json.dumps({
        "source": "https://huggingface.co/datasets/futurehouse/lab-bench",
        "revision": REVISION, "excluded_subsets": sorted(EXCLUDED),
        "total_rows": sum(s["rows"] for s in summary),
        "subsets": summary}, indent=2), encoding="utf-8")
    print("Total rows:", sum(s["rows"] for s in summary))


if __name__ == "__main__":
    convert()
