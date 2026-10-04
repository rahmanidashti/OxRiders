"""Lossless, schema-aware mechanical conversion of local LABBench2 Parquet files."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "labbench/lab-bench-text/Lab-Bench2"
OUTPUT = SOURCE / "exports"


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def encode(value):
    if value is None:
        return "\\N"
    if isinstance(value, str):
        return "\\" + value if value.startswith("\\") else value
    return dump(value)


def decode(value, field):
    if value == "\\N":
        return None
    if pa.types.is_string(field.type):
        return value[1:] if value.startswith("\\\\") else value
    return json.loads(value)


def convert():
    paths = sorted(SOURCE.glob("*/*.parquet"))
    if not paths:
        raise RuntimeError("No input Parquet files")
    OUTPUT.mkdir(exist_ok=False)
    csv.field_size_limit(100_000_000)
    reports = []
    records = {}
    for subset in sorted({p.parent.name for p in paths}):
        inputs = [p for p in paths if p.parent.name == subset]
        table = pa.concat_tables([pq.read_table(p) for p in inputs])
        rows = table.to_pylist()
        records[subset] = rows
        csv_path = OUTPUT / f"{subset}.csv"
        jsonl_path = OUTPUT / f"{subset}.jsonl"
        with jsonl_path.open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(dump(row) + "\n")
        with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(table.column_names)
            writer.writerows([[encode(row[name]) for name in table.column_names] for row in rows])
        with jsonl_path.open(encoding="utf-8") as stream:
            assert [json.loads(line) for line in stream] == rows
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == table.column_names
            restored = [{f.name: decode(row[f.name], f) for f in table.schema} for row in reader]
            assert restored == rows, f"CSV round-trip failed: {subset}"
        report = {
            "subset": subset, "rows": len(rows), "columns": table.column_names,
            "schema": {f.name: str(f.type) for f in table.schema},
            "csv": csv_path.name, "jsonl": jsonl_path.name,
            "csv_round_trip_equal": True, "jsonl_round_trip_equal": True,
            "null_counts": {f.name: table[f.name].null_count for f in table.schema},
            "empty_ideal_count": sum(r.get("ideal") in (None, "") for r in rows),
            "source_files": [{"path": str(p.relative_to(SOURCE)),
                              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
            "output_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [csv_path, jsonl_path]},
        }
        reports.append(report)
        print(subset, len(rows), "CSV/JSONL verified")
    canonical = lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True)
    all_rows = Counter(canonical(r) for r in records.get("all", []))
    subset_rows = Counter(canonical(r) for name, rows in records.items() if name != "all" for r in rows)
    manifest = {
        "source_url": "https://huggingface.co/datasets/EdisonScientific/labbench2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "license": "CC-BY-SA-4.0; original dataset notices retained",
        "external_assets_downloaded": False,
        "all_rows": sum(all_rows.values()),
        "subsets_rows_total": sum(subset_rows.values()),
        "all_equals_union_of_subsets": all_rows == subset_rows,
        "records_only_in_all": sum((all_rows - subset_rows).values()),
        "records_only_in_subsets": sum((subset_rows - all_rows).values()),
        "exports": reports,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("All equals subset union:", manifest["all_equals_union_of_subsets"])


if __name__ == "__main__":
    convert()
