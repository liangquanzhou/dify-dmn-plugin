import json
from pathlib import Path
import pytest
from io_contract import invoke_table

BASELINE = json.loads((Path(__file__).parent/'vectors/v020-default-baseline.json').read_text())


@pytest.mark.parametrize('case', BASELINE['cases'], ids=lambda x:x['id'])
def test_default_legacy_outputs_are_unchanged(case):
    result = invoke_table(case['parameters'])
    assert {name:result[name] for name in case['expected_legacy_outputs']} == case['expected_legacy_outputs']
