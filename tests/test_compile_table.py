import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from evaluator import TableError
from io_contract import compile_table_config, invoke_table


ROOT = Path(__file__).resolve().parents[1]
RAW = '{"id":"compile","hit_policy":"FIRST","unknown_policy":"strict","rules":[{"id":"r","when":{"eq":["x",1]}}]}\n'


def test_compile_adds_external_pin_without_evaluating_or_changing_table():
    with patch('io_contract.evaluate_table', side_effect=AssertionError('Compile must not evaluate')):
        config = compile_table_config(RAW)
    assert set(config) == {'table_json', 'expected_sha256'}
    assert config['table_json'] == RAW
    assert 'expected_sha256' not in json.loads(RAW)
    assert invoke_table({**config, 'values_json': '{"x":1}'})['decision_status'] == 'matched'


def test_compiled_pin_detects_changed_model():
    config = compile_table_config(RAW)
    config['table_json'] = RAW.replace('"strict"', '"compatible"')
    with pytest.raises(TableError) as exc:
        invoke_table({**config, 'values_json': '{}'})
    assert exc.value.code == 'HASH_MISMATCH'


def test_compiler_cli_emits_only_static_config(tmp_path):
    source, target = tmp_path/'table.json', tmp_path/'node-config.json'
    source.write_text(RAW)
    result = subprocess.run([sys.executable, str(ROOT/'scripts/compile_table.py'), str(source), '--output', str(target)], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == ''
    assert json.loads(target.read_text()) == compile_table_config(RAW)


def test_compiler_rejects_invalid_json(tmp_path):
    source = tmp_path/'bad.json'; source.write_text('{')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/compile_table.py'), str(source)], capture_output=True, text=True)
    assert result.returncode == 1 and result.stdout == ''
    assert json.loads(result.stderr)['code'] == 'INVALID_JSON'
