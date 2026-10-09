"""Local demo bridge to the exact plugin kernel; never a substitute evaluator."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'plugin'))
from io_contract import invoke_table
from evaluator import TableError
try:
    print(json.dumps(invoke_table(json.load(sys.stdin)), ensure_ascii=False))
except TableError as error:
    print(json.dumps({'error': error.message, **error.as_dict()}, ensure_ascii=False))
    sys.exit(1)
