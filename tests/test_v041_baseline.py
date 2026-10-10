"""Full-output regression snapshots of immutable release commit 3e3eca1."""
import json
from pathlib import Path
import pytest
from io_contract import invoke_table

BASELINE = json.loads((Path(__file__).parent / 'vectors/v041-output-baseline.json').read_text())


@pytest.mark.parametrize('case', BASELINE['cases'], ids=lambda case: case['id'])
def test_first_collect_full_v041_outputs_are_unchanged(case):
    assert invoke_table(case['parameters']) == case['expected_outputs']
