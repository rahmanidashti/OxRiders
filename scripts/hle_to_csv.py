import base64
import csv
import json
from pathlib import Path
import pyarrow.parquet as pq

source = Path('/Users/yuzhuchen/Downloads/test-00000-of-00001.parquet')
out = Path('/Users/yuzhuchen/.codex/.chatgpt-projects/g-p-69b8a6e2d588819190dd04cb90988d3b/outputs/hle-csv/test-00000-of-00001.csv')
out.parent.mkdir(parents=True, exist_ok=True)
table = pq.ParquetFile(source)

def binary(value):
    if isinstance(value, bytes):
        return base64.b64encode(value).decode('ascii')
    raise TypeError(type(value).__name__)

def cell(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=binary)
    return str(value)

with out.open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(table.schema_arrow.names)
    for batch in table.iter_batches(batch_size=50):
        for row in batch.to_pylist():
            writer.writerow([cell(row[name]) for name in table.schema_arrow.names])

csv.field_size_limit(1024 * 1024 * 1024)
with out.open(encoding='utf-8-sig', newline='') as handle:
    reader = csv.reader(handle)
    assert next(reader) == table.schema_arrow.names
    count = 0
    for batch in table.iter_batches(batch_size=50):
        for row in batch.to_pylist():
            assert next(reader) == [cell(row[name]) for name in table.schema_arrow.names]
            count += 1
    assert next(reader, None) is None
assert count == table.metadata.num_rows
print(json.dumps({'output': str(out), 'rows': count, 'columns': len(table.schema_arrow.names), 'bytes': out.stat().st_size}))
