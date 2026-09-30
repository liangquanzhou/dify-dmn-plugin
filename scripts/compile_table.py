"""Compile one JSON table to static Tool parameters with an automatic JCS pin.

This emits configuration data, not a Dify workflow DSL or business result.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin'))
from evaluator import TableError
from io_contract import MAX_TABLE_BYTES, compile_table_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('table', type=Path)
    parser.add_argument('--output', type=Path, help='Write configuration JSON here; default is stdout')
    args = parser.parse_args()
    try:
        with args.table.open('rb') as source:
            raw = source.read(MAX_TABLE_BYTES + 1)
        if len(raw) > MAX_TABLE_BYTES:
            raise TableError('LIMIT_EXCEEDED', '$.table_json', 'JSON input exceeds the byte limit')
        output = json.dumps(compile_table_config(raw.decode('utf-8')), ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
    except (TableError, UnicodeError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, TableError) else {'code': 'INPUT_OUTPUT_ERROR', 'message': 'Unable to read UTF-8 input or write the requested output'}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
