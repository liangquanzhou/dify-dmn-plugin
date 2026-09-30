"""Contract-focused tests for the plugin-internal JSON table evaluator."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from evaluator import TableError, evaluate_table, validate_table


def table(*conditions, policy="COLLECT"):
    return {"id": "synthetic", "hit_policy": policy, "rules": [
        {"id": f"r{i}", "when": condition} for i, condition in enumerate(conditions)
    ]}


def condition(expression, values=None):
    return evaluate_table(table(expression), values or {})["evaluations"][0]["condition"]


def test_raw_outputs_and_every_first_rule_evaluated():
    raw = table(True, False, True, policy="FIRST")
    raw["rules"][0].update({"output": {"eq": ["do not evaluate", 10]}, "载荷": [1, "two"], "metadata": {"any": []}})
    result = evaluate_table(raw, {})
    assert set(result) == {"matched", "evaluations"}
    assert result["matched"] == [raw["rules"][0]]
    assert result["matched"][0] is raw["rules"][0]
    assert [item["condition"] for item in result["evaluations"]] == [True, False, True]
    assert result["matched"][0]["载荷"] == [1, "two"]


def test_collect_and_empty_rules():
    raw = table(True, False, True)
    assert evaluate_table(raw, {})["matched"] == [raw["rules"][0], raw["rules"][2]]
    assert evaluate_table(table(), {}) == {"matched": [], "evaluations": []}


@pytest.mark.parametrize("value,expected", [(1, True), (1.0, True), (True, False), ("1", False), (None, None)])
def test_strict_equality(value, expected):
    assert condition({"eq": ["x", 1]}, {"x": value}) is expected


def test_equality_uses_container_identity_not_deep_comparison():
    same = [1, {"n": 2}]
    assert condition({"eq": ["a", {"ref": "b"}]}, {"a": same, "b": same}) is True
    assert condition({"eq": ["a", {"ref": "b"}]}, {"a": [1], "b": [1]}) is False
    assert condition({"eq": ["a", [1]]}, {"a": [1]}) is False


def test_exact_key_lookup_and_empty_key():
    assert condition({"eq": ["a.b", 2]}, {"a.b": 2, "a": {"b": 3}}) is True
    assert condition({"eq": ["a.b", 2]}, {"a": {"b": 2}}) is None
    assert condition({"eq": ["", 2]}, {"": 2}) is True


@pytest.mark.parametrize("operator", ["eq", "ne", "gt", "gte", "lt", "lte"])
def test_absent_and_null_are_unknown(operator):
    expression = {operator: ["x", 2]}
    assert condition(expression) is None
    assert condition(expression, {"x": None}) is None
    assert condition({operator: ["x", {"ref": "y"}]}, {"x": 2}) is None


@pytest.mark.parametrize("operator,left,right,expected", [("gt", 2, 1, True), ("gt", 1, 1, False), ("gte", 1, 1, True), ("lt", 1, 2, True), ("lte", 1, 1, True), ("ne", False, 0, True)])
def test_comparisons(operator, left, right, expected):
    assert condition({operator: ["x", right]}, {"x": left}) is expected


@pytest.mark.parametrize("operator", ["gt", "gte", "lt", "lte"])
@pytest.mark.parametrize("wrong", [True, "3", [], {}, float("inf"), float("nan")])
def test_numeric_input_types_are_not_coerced(operator, wrong):
    with pytest.raises(TableError) as caught:
        condition({operator: ["x", 3]}, {"x": wrong})
    assert caught.value.code == "INVALID_VALUE"


def test_unknown_precedes_numeric_type_validation():
    assert condition({"gt": ["missing", "secret value"]}) is None
    assert condition({"gt": ["x", {"ref": "missing"}]}, {"x": "wrong type"}) is None
    with pytest.raises(TableError) as caught:
        evaluate_table(table(True, {"gt": ["x", "secret value"]}, policy="FIRST"), {"x": 1})
    assert caught.value.code == "INVALID_VALUE"
    assert "secret" not in str(caught.value)


def test_all_and_any_three_valued_truth_tables():
    unknown = {"eq": ["absent", 1]}
    for a, b, all_result, any_result in [
        (True, True, True, True), (True, False, False, True),
        (True, unknown, None, True), (False, unknown, False, None),
        (unknown, unknown, None, None), (False, False, False, False),
    ]:
        assert condition({"all": [a, b]}) is all_result
        assert condition({"any": [a, b]}) is any_result


def test_is_unknown_includes_null_but_not_false_or_zero():
    assert condition({"is_unknown": "x"}) is True
    assert condition({"is_unknown": "x"}, {"x": None}) is True
    for value in (False, 0, "", [], {}):
        assert condition({"is_unknown": "x"}, {"x": value}) is False


@pytest.mark.parametrize("expression", [{"bogus": 1}, {"eq": ["x", 1], "lt": ["y", 2]}, {}, None, 1, "true", {"all": True}, {"eq": ["x"]}, {"eq": ["x", {"ref": "y", "extra": 1}]}])
def test_malformed_and_unsupported_expressions_rejected(expression):
    with pytest.raises(TableError):
        evaluate_table(table(True, expression, policy="FIRST"), {})


def test_deep_invalid_branch_is_validated_before_input_evaluation():
    raw = table({"gt": ["x", 1]}, {"all": [False, {"mystery": "never"}]})
    with pytest.raises(TableError) as caught:
        evaluate_table(raw, {"x": "runtime failure"})
    assert caught.value.code == "UNSUPPORTED_OPERATOR"
    assert caught.value.path == "$.rules[1].when.all[1]"


@pytest.mark.parametrize("policy", ["RULE_ORDER", "COLLECT SUM", "first", "", None])
def test_only_two_hit_policies(policy):
    with pytest.raises(TableError) as caught:
        evaluate_table(table(True, policy=policy), {})
    assert caught.value.code == "UNSUPPORTED_HIT_POLICY"


def test_rule_ids_required_nonempty_unique():
    for invalid_id in (None, "", "  ", 4):
        raw = table(True)
        raw["rules"][0]["id"] = invalid_id
        with pytest.raises(TableError):
            validate_table(raw)
    raw = table(True, True)
    raw["rules"][1]["id"] = raw["rules"][0]["id"]
    with pytest.raises(TableError):
        validate_table(raw)


def test_reads_are_ordered_and_deduplicated():
    raw = table({"all": [{"eq": ["b", {"ref": "a"}]}, {"eq": ["a", {"ref": "b"}]}]})
    result = evaluate_table(raw, {"a": 1, "b": 1})
    assert result["evaluations"][0]["read_variables"] == ["b", "a"]


def test_all_branches_evaluated_even_after_decisive_condition():
    for expression in ({"all": [False, {"gt": ["x", 1]}]}, {"any": [True, {"gt": ["x", 1]}]}):
        with pytest.raises(TableError):
            condition(expression, {"x": "wrong"})


@pytest.mark.parametrize("value,expected", [(None, None), ([], True), ("", True), ([None], False), (" ", False)])
def test_is_empty(value, expected):
    assert condition({"is_empty": "x"}, {"x": value}) is expected


@pytest.mark.parametrize("value", [{}, {"x": 1}, 0, False])
def test_is_empty_wrong_type_raises(value):
    with pytest.raises(TableError):
        condition({"is_empty": "x"}, {"x": value})


def test_contains_strict_equality_and_unknown_precedence():
    assert condition({"contains": ["xs", 1]}, {"xs": [True, "1", 2]}) is False
    assert condition({"contains": ["xs", 1]}, {"xs": [True, 1]}) is True
    assert condition({"contains": ["xs", 1]}, {"xs": []}) is False
    assert condition({"not_contains": ["xs", 1]}, {"xs": []}) is True
    assert condition({"contains": ["xs", 1]}) is None
    assert condition({"contains": ["xs", None]}, {"xs": "not array"}) is None
    assert condition({"contains": ["xs", {"ref": "missing"}]}, {"xs": "wrong"}) is None
    with pytest.raises(TableError):
        condition({"contains": ["xs", 1]}, {"xs": "wrong"})


def test_contains_container_identity():
    item = {"v": 1}
    assert condition({"contains": ["xs", {"ref": "needle"}]}, {"xs": [item], "needle": item}) is True
    assert condition({"contains": ["xs", {"v": 1}]}, {"xs": [{"v": 1}]}) is False


@pytest.mark.parametrize("value,expected", [([1, 1.0], True), ([1, True], False), ([1, None], False), ([], None), (None, None), ("1", None), ({}, None)])
def test_all_values(value, expected):
    assert condition({"all_values": ["xs", 1]}, {"xs": value}) is expected


def test_all_values_raw_literal_including_null():
    assert condition({"all_values": ["xs", None]}, {"xs": [None]}) is True
    assert condition({"all_values": ["xs", None]}, {"xs": [0]}) is False
    with pytest.raises(TableError) as caught:
        condition({"all_values": ["xs", {"ref": "x"}]}, {"xs": [1], "x": 1})
    assert caught.value.code == "INVALID_EXPRESSION"


def discount(base=100, percent=50, **extra):
    return {"operator": "discount_share", "base_fen": base, "pay_percent": percent, **extra}


@pytest.mark.parametrize("amount,expected", [
    (discount(100, 30), 70), (discount(5, 100), 0), (discount(5, 0), 5),
    (discount(5, 50), None), (discount(5, 50, rounding="half_up_fen"), 3),
    (discount(3, 90, rounding="half_up_fen"), 0),
    (discount(100.0, 30.0), 70), (discount(2**53 - 1, 0), 2**53 - 1),
    (discount(2**53, 0), None), (discount(-1, 30), None), (discount(True, 50), None),
    (discount(5, False), None), (discount(1.5, 50), None), (discount(5, 1.5), None),
    (discount(5, 101), None), (discount(5, -1), None),
    (discount(None, 50), None), (discount(5, "50"), None),
])
def test_discount_share(amount, expected):
    result = condition({"eq": ["x", expected if expected is not None else 0]}, {"x": amount})
    assert result is (None if expected is None else True)


def test_discount_share_is_amount_not_expression():
    with pytest.raises(TableError) as caught:
        condition({"discount_share": {"base_fen": 100, "pay_percent": 50}})
    assert caught.value.code == "UNSUPPORTED_OPERATOR"


def test_discount_conversion_only_matches_tagged_object():
    ordinary = {"base_fen": 100, "pay_percent": 50}
    assert condition({"eq": ["x", {"ref": "y"}]}, {"x": ordinary, "y": ordinary}) is True
    assert condition({"eq": ["x", 50]}, {"x": ordinary}) is False


def test_discount_on_right_reference_and_in_collections():
    assert condition({"eq": ["x", {"ref": "amount"}]}, {"x": 50, "amount": discount()}) is True
    assert condition({"contains": ["xs", discount()]}, {"xs": [None, discount(100, 50)]}) is True
    assert condition({"contains": ["xs", discount(-1, 50)]}, {"xs": []}) is None
    assert condition({"all_values": ["xs", 50]}, {"xs": [discount()]}) is False
    with pytest.raises(TableError):
        condition({"contains": ["xs", 50]}, {"xs": discount(-1, 50)})


@pytest.mark.parametrize("left,right,expected", [
    (1, [1, 2, 3], True), (1, [1, 1], True), (2, [1, 2], False),
    (1, [], None), (1, [1, None], None), (1, "bad", None),
    ("1", [1], None), (True, [1], None), (1, [True], None),
    (1, [1, float("inf")], None), (1, [1, discount(-1)], None),
    (50, [discount(), 100], True), (discount(), [50, 100], True),
])
def test_is_minimum(left, right, expected):
    assert condition({"is_minimum": ["x", right]}, {"x": left}) is expected


def test_is_minimum_reference_reads_both():
    result = evaluate_table(table({"is_minimum": ["x", {"ref": "others"}]}), {"x": 1, "others": [1, 2]})
    assert result["evaluations"][0]["read_variables"] == ["x", "others"]


@pytest.mark.parametrize("operator,left,expected", [
    ("within", 9, True), ("within", 11, True), ("within", 8.99, False),
    ("below", 9, False), ("below", 8.99, True),
    ("above", 11, False), ("above", 11.01, True),
])
def test_tolerance_boundaries(operator, left, expected):
    assert condition({operator: ["x", 10, 1]}, {"x": left}) is expected


@pytest.mark.parametrize("tolerance", [-1, "1", None, True, {}, {"ref": "tol"}, float("inf")])
def test_tolerance_bad_business_literals_are_unknown(tolerance):
    result = evaluate_table(table({"within": ["x", 10, tolerance]}), {"x": 10, "tol": 1})
    assert result["evaluations"][0]["condition"] is None
    assert result["evaluations"][0]["read_variables"] == ["x"]


def test_tolerance_bad_values_are_unknown_and_amounts_supported():
    assert condition({"within": ["x", "bad", 1]}, {"x": 10}) is None
    assert condition({"within": ["x", 10, 1]}, {"x": True}) is None
    assert condition({"within": ["x", discount(), 0]}, {"x": discount()}) is True


def record(conditions=None, **changes):
    result = {"scope_bound": True, "logical_role": "necessary_conjunction", "applicable_condition_set_complete": True,
              "explicitly_unrestricted": False, "conditions": conditions if conditions is not None else []}
    result.update(changes)
    return result


def row(operator="eq", left=1, right=1, **extra):
    return {"operator": operator, "left": left, "right": right, **extra}


def constraint(value, mode="satisfied"):
    return condition({"constraint_set": {"record": "checks", "mode": mode}}, {"checks": value})


def test_constraint_conjunction_completeness_and_unknown():
    assert constraint(record([row()])) is True
    assert constraint(record([row()]), "violated") is False
    assert constraint(record([row(right=2)])) is False
    assert constraint(record([row(right=2)]), "violated") is True
    assert constraint(record([row()], applicable_condition_set_complete=False)) is None
    assert constraint(record([row(left=None)])) is None
    assert constraint(record([row(left=None), row(right=2)], applicable_condition_set_complete=False)) is False
    assert constraint(record([row(left=None), row(right=2)], applicable_condition_set_complete=False), "violated") is True


@pytest.mark.parametrize("value", [None, [], "bad", {}, record([row()], scope_bound=False), record([row()], scope_bound=1), record([row()], logical_role="other")])
def test_constraint_scope_guard(value):
    assert constraint(value) is None


def test_constraint_empty_unrestricted_platform_and_contradictions():
    assert constraint(record()) is None
    assert constraint(record(), "violated") is None
    assert constraint(record(explicitly_unrestricted=True)) is True
    assert constraint(record(explicitly_unrestricted=True), "violated") is None
    assert constraint(record([row()], explicitly_unrestricted=True)) is None
    assert constraint(record(conditions="wrong", explicitly_unrestricted=True)) is True
    assert constraint(record(platform_asserted_violation=True, applicable_condition_set_complete=False)) is False
    assert constraint(record(platform_asserted_violation=True, applicable_condition_set_complete=False), "violated") is True
    assert constraint(record([row()], platform_asserted_violation=True)) is None


@pytest.mark.parametrize("item,expected", [
    (row(left=1, right=True), None), (row(left=1, right="1"), None), (row(left={}, right={}), None),
    (row(left="a", right="a"), True), (row(left=False, right=False), True),
    (row("ne", 1, 2), True), (row("ne", 1, 1), False),
    (row("gt", 3, 2), True), (row("gte", 2, 2), True), (row("lt", 2, 3), True), (row("lte", 2, 2), True),
    (row("gt", "3", 2), None), (row("gt", True, 0), None),
    (row("in", 1, [1, 2]), True), (row("in", 3, [1, 2]), False),
    (row("not_in", "a", ["b", "c"]), True),
    (row("in", 1, [1, True]), None), (row("in", 1, []), None),
    (row("in", 1, "bad"), None), (row("eq", discount(), 50), None),
    (row("eq", {"ref": "x"}, 1), None), (row("bogus", 1, 1), None),
    (row(status="unknown"), None), (row(status={}), None), (row(status="known"), True),
    (row(status=""), True), (row(status=False), True),
])
def test_constraint_rows(item, expected):
    assert constraint(record([item])) is expected


def test_constraint_between_explicit_boundary_flags():
    assert constraint(record([row("between", 1, [1, 2], lower_inclusive=True, upper_inclusive=True)])) is True
    assert constraint(record([row("between", 1, [1, 2], lower_inclusive=False, upper_inclusive=True)])) is False
    assert constraint(record([row("between", 2, [1, 2], lower_inclusive=True, upper_inclusive=False)])) is False
    assert constraint(record([row("between", 1, [1, 2])])) is None
    assert constraint(record([row("between", 1, [1, 2], lower_inclusive=1, upper_inclusive=True)])) is None
    assert constraint(record([row("between", 1, [1, None], lower_inclusive=True, upper_inclusive=True)])) is None


def test_constraint_trace_only_record_key():
    result = evaluate_table(table({"constraint_set": {"record": "a.b", "mode": "satisfied"}}), {"a.b": record([row()])})
    evaluation = result["evaluations"][0]
    assert evaluation["read_variables"] == ["a.b"]
    assert evaluation["supporting_alternatives"] == [["a.b"]]


def evaluation(expression, values=None):
    return evaluate_table(table(expression), values or {})["evaluations"][0]


def test_empty_logical_identities_and_constant_evidence():
    yes, no = evaluation({"all": []}), evaluation({"any": []})
    assert yes["condition"] is True and yes["supporting_alternatives"] == [[]]
    assert no["condition"] is False and no["refuting_variables"] == []
    assert yes["trace_compressed"] is False and no["trace_compressed"] is False


def test_alternative_support_paths_preserved():
    expression = {"any": [{"eq": ["a", 1]}, {"all": [{"eq": ["b", 2]}, {"eq": ["c", 3]}]}]}
    result = evaluation(expression, {"a": 1, "b": 2, "c": 3})
    assert result["read_variables"] == ["a", "b", "c"]
    assert result["supporting_variables"] == ["a", "b", "c"]
    assert result["supporting_alternatives"] == [["a"], ["b", "c"]]
    assert result["refuting_variables"] == []


def test_reads_include_all_branches_but_evidence_only_decisive_ones():
    predicates = [{"eq": ["a", 1]}, {"eq": ["b", 2]}, {"eq": ["missing", 3]}]
    values = {"a": 1, "b": 0}
    yes = evaluation({"any": predicates}, values)
    no = evaluation({"all": predicates}, values)
    assert yes["read_variables"] == no["read_variables"] == ["a", "b", "missing"]
    assert yes["supporting_variables"] == ["a"] and yes["refuting_variables"] == []
    assert no["supporting_variables"] == [] and no["refuting_variables"] == ["b"]
    unknown = evaluation({"all": [predicates[0], predicates[2]]}, values)
    assert unknown["supporting_variables"] == unknown["supporting_alternatives"] == unknown["refuting_variables"] == []


def test_cartesian_support_order_and_per_path_deduplication():
    expression = {"all": [
        {"any": [{"eq": ["a", 1]}, {"eq": ["b", 1]}]},
        {"any": [{"eq": ["a", 1]}, {"eq": ["c", 1]}]},
    ]}
    result = evaluation(expression, {"a": 1, "b": 1, "c": 1})
    assert result["supporting_alternatives"] == [["a"], ["a", "c"], ["b", "a"], ["b", "c"]]


def test_cartesian_compression_and_any_limit_are_different():
    clauses = [{"any": [{"eq": [f"v{i}_{j}", 1]} for j in range(3)]} for i in range(4)]
    values = {f"v{i}_{j}": 1 for i in range(4) for j in range(3)}
    result = evaluation({"all": clauses}, values)
    assert result["trace_compressed"] is True
    assert result["supporting_alternatives"] == [["v0_0", "v1_0", "v2_0", "v2_1", "v2_2", "v1_1", "v1_2", "v0_1", "v0_2", "v3_0", "v3_1", "v3_2"]]
    assert result["read_variables"] == list(values)
    alternatives = [{"eq": [f"x{i}", 1]} for i in range(40)]
    result = evaluation({"any": alternatives}, {f"x{i}": 1 for i in range(40)})
    assert len(result["supporting_alternatives"]) == 40 and result["trace_compressed"] is False
    with pytest.raises(TableError) as caught:
        evaluation({"any": [True] * 257})
    assert caught.value.code == "LIMIT_EXCEEDED"


def test_false_cartesian_compression_is_visible():
    clauses = [{"all": [{"eq": [f"v{i}_{j}", 1]} for j in range(3)]} for i in range(4)]
    values = {f"v{i}_{j}": 0 for i in range(4) for j in range(3)}
    result = evaluation({"any": clauses}, values)
    assert result["condition"] is False
    assert result["trace_compressed"] is True
    assert result["refuting_variables"] == ["v0_0", "v1_0", "v2_0", "v2_1", "v2_2", "v1_1", "v1_2", "v0_1", "v0_2", "v3_0", "v3_1", "v3_2"]
    assert result["read_variables"] == list(values)
    assert result["supporting_alternatives"] == []


def test_compression_flag_survives_an_unknown_parent():
    wide = {"all": [{"any": [True] * 6}, {"any": [True] * 6}]}
    result = evaluation({"all": [wide, {"eq": ["missing", 1]}]})
    assert result["condition"] is None
    assert result["trace_compressed"] is True
    assert result["supporting_alternatives"] == []


def test_errors_have_safe_fields_and_no_actual_input_value():
    with pytest.raises(TableError) as caught:
        condition({"gt": ["x", 1]}, {"x": "sensitive value"})
    assert caught.value.as_dict() == {"code": "INVALID_VALUE", "path": "$.rules[0].when.gt", "message": "A numeric operand must be a finite number; coercion is not supported."}
    assert "sensitive value" not in repr(caught.value.as_dict())


@pytest.mark.parametrize("raw", [None, [], "{}", {}, {"id": "x", "hit_policy": "FIRST"},
                                    {"id": "x", "hit_policy": "FIRST", "rules": {}},
                                    {"id": "x", "hit_policy": "FIRST", "rules": [None]},
                                    {"id": "x", "hit_policy": "FIRST", "rules": [{"id": "x"}]}])
def test_non_literal_table_structure_errors(raw):
    with pytest.raises(TableError):
        evaluate_table(raw, {})


@pytest.mark.parametrize("expression", [
    {"eq": [None, 1]}, {"is_unknown": 1}, {"is_empty": []},
    {"eq": ["x", {"ref": None}]}, {"eq": ["x", {"ref": []}]},
    {"contains": ["x", 1, 2]}, {"all_values": "x"}, {"is_minimum": ["x"]},
    {"within": ["x", 1]}, {"within": ["x", 1, 2, 3]},
    {"constraint_set": None}, {"constraint_set": []},
    {"constraint_set": {"record": "x"}}, {"constraint_set": {"record": "x", "mode": "other"}},
    {"constraint_set": {"record": None, "mode": "satisfied"}},
    {"constraint_set": {"record": "x", "mode": "satisfied", "extra": True}},
])
def test_non_literal_operand_structure_errors(expression):
    with pytest.raises(TableError) as caught:
        evaluate_table(table(True, expression, policy="FIRST"), {})
    assert caught.value.code == "INVALID_EXPRESSION"


@pytest.mark.parametrize("values", [None, [], "{}", {1: "bad key"}])
def test_values_require_string_keyed_object(values):
    with pytest.raises(TableError) as caught:
        evaluate_table(table(True), values)
    assert caught.value.code == "INVALID_VALUES"


def test_expression_count_and_depth_guard():
    assert validate_table(table({"all": [True, {"any": [False, True]}]})) == 5
    expression = True
    for _ in range(33):
        expression = {"all": [expression]}
    with pytest.raises(TableError) as caught:
        validate_table(table(expression))
    assert caught.value.code == "LIMIT_EXCEEDED"


def test_exact_alternatives_limit():
    result = evaluation({"any": [True] * 256})
    assert len(result["supporting_alternatives"]) == 256
    assert result["trace_compressed"] is False
    with pytest.raises(TableError) as caught:
        evaluation({"all": [False] * 257})
    assert caught.value.code == "LIMIT_EXCEEDED"


def test_evaluation_does_not_mutate_inputs_or_payloads():
    import copy
    raw = table({"contains": ["amounts", discount()]})
    raw["rules"][0]["output"] = {"unchanged": discount()}
    values = {"amounts": [discount(), None]}
    expected_table, expected_values = copy.deepcopy(raw), copy.deepcopy(values)
    result = evaluate_table(raw, values)
    assert raw == expected_table and values == expected_values
    assert result["matched"][0] is raw["rules"][0]
