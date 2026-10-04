# LABBench2 CSV / JSONL exports

Source: https://huggingface.co/datasets/EdisonScientific/labbench2

The original local Parquet files and dataset card in the parent directory are unchanged.
This is a mechanical format conversion, not a new training dataset. Original canary
and other notices are retained. The source is labeled CC BY-SA 4.0; its benchmark
notice says that these records should not appear in training corpora.

## Files

- `all.csv` / `all.jsonl`: 1,912 original records, all 16 original columns.
- The other 15 CSV / JSONL pairs preserve the corresponding source subsets.
- `manifest.json`: row counts, source schemas, hashes and validation results.

`all` already contains the 15 subsets. Do not concatenate `all` with them.
Different input-mode variants remain separate, exactly as in the source dataset.
Every CSV and JSONL was read back and compared field-by-field with its source.
The multiset of all records equals the union of the 15 subsets.

## Encoding

JSONL is UTF-8, one original record per line. It preserves null, empty strings,
booleans, arrays, objects and embedded newlines. Prefer it for programmatic use.

CSV is UTF-8 with BOM, one record per row, quoted fields and a single header row.
Arrays and objects are JSON-encoded; booleans use `true` / `false`.
Null uses the literal `\N`, distinct from an empty string. Original strings
beginning with a backslash have one extra leading backslash; remove that one
backslash when decoding non-null string columns. Schema types are in the manifest.
Strings that contain JSON in the original data remain strings in JSONL.

Import CSV columns as text in spreadsheet software to prevent automatic formula,
date or numeric conversion. No original question or answer text was rewritten.

## Scope

Reference answers remain in `ideal`; empty values are preserved and were not
filled or labeled unanswerable. Some tasks use validators rather than a single
reference answer. Consult `type`, `validator_params` and the official harness.

External PDFs, images and other files referenced by dataset fields are not
embedded in these exports and were not downloaded during conversion. Preserving
their references does not make a standalone executable benchmark environment.
