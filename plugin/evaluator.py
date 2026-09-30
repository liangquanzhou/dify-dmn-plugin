"""Pure-Python evaluation of a single, custom JSON decision table.

This module does not interpret DMN XML, FEEL, JavaScript, dotted paths, or output
payloads. An input key is always looked up literally in the supplied object.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


class TableError(ValueError):
    """A safe, machine-readable error without actual input values."""

    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


_MISSING = object()
_BINARY = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "all_values", "is_minimum"})
_NUMERIC = frozenset({"gt", "gte", "lt", "lte"})
_TOLERANCE = frozenset({"within", "below", "above"})
_UNARY = frozenset({"is_unknown", "is_empty"})
_OPERATORS = _BINARY | _TOLERANCE | _UNARY | {"all", "any", "constraint_set"}
_MAX_ALTERNATIVES = 256
_CARTESIAN_COMPRESSION_THRESHOLD = 32
_MAX_SAFE_INTEGER = 2**53 - 1


def _fail(code: str, path: str, message: str) -> None:
    raise TableError(code, path, message)


def _is_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _unknown(value: Any) -> bool:
    return value is _MISSING or value is None


def _key(value: Any, path: str) -> None:
    if not isinstance(value, str):
        _fail("INVALID_EXPRESSION", path, "A variable key must be a string.")


def _operand(value: Any, path: str) -> None:
    if isinstance(value, dict) and "ref" in value:
        if set(value) != {"ref"}:
            _fail("INVALID_EXPRESSION", path, "A reference must contain only the ref field.")
        _key(value["ref"], path + ".ref")


def _is_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"ref"}


def _validate_expression(expression: Any, path: str, depth: int = 0) -> int:
    if depth > 32:
        _fail("LIMIT_EXCEEDED", path, "Expression nesting exceeds the supported limit.")
    if type(expression) is bool:
        return 1
    if not isinstance(expression, dict) or len(expression) != 1:
        _fail("INVALID_EXPRESSION", path, "A condition must be a boolean or exactly one operator.")
    operator, argument = next(iter(expression.items()))
    if operator not in _OPERATORS:
        _fail("UNSUPPORTED_OPERATOR", path, "The condition operator is not supported.")
    arg_path = path + "." + operator
    if operator in {"all", "any"}:
        if not isinstance(argument, list):
            _fail("INVALID_EXPRESSION", arg_path, "A logical operator requires an array of conditions.")
        return 1 + sum(_validate_expression(child, f"{arg_path}[{i}]", depth + 1) for i, child in enumerate(argument))
    if operator in _UNARY:
        _key(argument, arg_path)
        return 1
    if operator in _BINARY | _TOLERANCE:
        expected = 3 if operator in _TOLERANCE else 2
        if not isinstance(argument, list) or len(argument) != expected:
            _fail("INVALID_EXPRESSION", arg_path, "The operator has the wrong argument shape.")
        _key(argument[0], arg_path + "[0]")
        _operand(argument[1], arg_path + "[1]")
        if operator == "all_values" and _is_ref(argument[1]):
            _fail("INVALID_EXPRESSION", arg_path + "[1]", "all_values requires a raw literal, not a reference.")
        return 1
    # Constraint records are runtime data, not executable expressions.
    return _validate_special(operator, argument, arg_path)


def _validate_special(operator: str, argument: Any, path: str) -> int:
    if operator == "constraint_set":
        if not isinstance(argument, dict) or set(argument) != {"record", "mode"}:
            _fail("INVALID_EXPRESSION", path, "A constraint set requires record and mode fields.")
        _key(argument["record"], path + ".record")
        if argument["mode"] not in ("satisfied", "violated"):
            _fail("INVALID_EXPRESSION", path + ".mode", "Constraint mode must be satisfied or violated.")
        return 1
    _fail("UNSUPPORTED_OPERATOR", path, "The condition operator is not supported.")


def validate_table(table: Any) -> int:
    """Validate every condition before evaluation; return expression node count."""
    if not isinstance(table, dict):
        _fail("INVALID_TABLE", "$", "A decision table must be an object.")
    if not isinstance(table.get("id"), str) or not table["id"].strip():
        _fail("INVALID_TABLE", "$.id", "A table id must be a nonempty string.")
    if table.get("hit_policy") not in ("FIRST", "COLLECT"):
        _fail("UNSUPPORTED_HIT_POLICY", "$.hit_policy", "Only FIRST and COLLECT hit policies are supported.")
    rules = table.get("rules")
    if not isinstance(rules, list):
        _fail("INVALID_TABLE", "$.rules", "Rules must be an array.")
    seen: set[str] = set()
    nodes = 0
    for i, rule in enumerate(rules):
        path = f"$.rules[{i}]"
        if not isinstance(rule, dict):
            _fail("INVALID_TABLE", path, "A rule must be an object.")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            _fail("INVALID_TABLE", path + ".id", "A rule id must be a nonempty string.")
        if rule_id in seen:
            _fail("INVALID_TABLE", path + ".id", "Rule ids must be unique.")
        seen.add(rule_id)
        if "when" not in rule:
            _fail("INVALID_TABLE", path + ".when", "A rule must have a when condition.")
        nodes += _validate_expression(rule["when"], path + ".when")
    return nodes


def _strict_equal(left: Any, right: Any) -> bool:
    """JSON-compatible JavaScript ===, including container reference identity."""
    if _is_number(left) and _is_number(right):
        return float(left) == float(right)
    if type(left) is not type(right):
        return False
    if isinstance(left, (dict, list)):
        return left is right
    return left == right


def _ordered_union(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(key for group in groups for key in group))


@dataclass
class _Trace:
    condition: bool | None
    read: list[str]
    support: list[list[str]]
    refute: list[list[str]]
    compressed: bool = False


def _leaf(condition: bool | None, read: list[str]) -> _Trace:
    return _Trace(condition, read, [read.copy()] if condition is True else [], [read.copy()] if condition is False else [])


def _is_discount(value: Any) -> bool:
    return isinstance(value, dict) and value.get("operator") == "discount_share"


def _safe_integer(value: Any, lower: int, upper: int) -> bool:
    return _is_number(value) and float(value).is_integer() and lower <= value <= upper


def _amount(value: Any) -> Any:
    """Convert only the explicitly tagged amount operand, without float drift."""
    if not _is_discount(value):
        return value
    base, percent = value.get("base_fen"), value.get("pay_percent")
    if not _safe_integer(base, 0, _MAX_SAFE_INTEGER) or not _safe_integer(percent, 0, 100):
        return None
    whole, remainder = divmod(int(base) * (100 - int(percent)), 100)
    if remainder == 0:
        return whole
    if value.get("rounding") != "half_up_fen":
        return None
    return whole + (1 if remainder >= 50 else 0)


def _resolve(operand: Any, values: dict[str, Any], read: list[str]) -> Any:
    if isinstance(operand, dict) and set(operand) == {"ref"}:
        key = operand["ref"]
        if key not in read:
            read.append(key)
        return values.get(key, _MISSING)
    return operand


def _number(value: Any, path: str) -> float:
    if not _is_number(value):
        _fail("INVALID_VALUE", path, "A numeric operand must be a finite number; coercion is not supported.")
    return float(value)


def _evaluate(expression: Any, values: dict[str, Any], path: str) -> _Trace:
    if type(expression) is bool:
        return _leaf(expression, [])
    operator, argument = next(iter(expression.items()))
    arg_path = path + "." + operator
    if operator in {"all", "any"}:
        children = [_evaluate(child, values, f"{arg_path}[{i}]") for i, child in enumerate(argument)]
        read = _ordered_union(*(child.read for child in children))
        conditions = [child.condition for child in children]
        if operator == "all":
            condition = False if False in conditions else None if None in conditions else True
        else:
            condition = True if True in conditions else None if None in conditions else False
        return _combine(operator, condition, read, children, arg_path)
    if operator in _UNARY:
        value = values.get(argument, _MISSING)
        if operator == "is_unknown":
            return _leaf(_unknown(value), [argument])
        if _unknown(value):
            return _leaf(None, [argument])
        if not isinstance(value, (str, list)):
            _fail("INVALID_VALUE", arg_path, "is_empty requires a string or array.")
        return _leaf(not value, [argument])
    if operator == "constraint_set":
        return _evaluate_special(operator, argument, values, arg_path)
    read = [argument[0]]
    left = values.get(argument[0], _MISSING)
    right = argument[1] if operator == "all_values" else _resolve(argument[1], values, read)
    if operator == "all_values":
        return _evaluate_collection(operator, left, right, read, arg_path)
    right = _amount(right)
    if operator not in {"contains", "not_contains"}:
        left = _amount(left)
    if _unknown(left) or _unknown(right):
        return _leaf(None, read)
    if operator in {"eq", "ne"}:
        equal = _strict_equal(left, right)
        return _leaf(equal if operator == "eq" else not equal, read)
    if operator in _NUMERIC:
        a, b = _number(left, arg_path), _number(right, arg_path)
        condition = {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[operator]
        return _leaf(condition, read)
    if operator in _TOLERANCE:
        if not _is_number(left) or not _is_number(right) or not _is_number(argument[2]) or argument[2] < 0:
            return _leaf(None, read)
        a, b, tolerance = float(left), float(right), float(argument[2])
        condition = {"within": abs(a - b) <= tolerance, "below": a < b - tolerance, "above": a > b + tolerance}[operator]
        return _leaf(condition, read)
    return _evaluate_collection(operator, left, right, read, arg_path)


def _combine(operator: str, condition: bool | None, read: list[str], children: list[_Trace], path: str) -> _Trace:
    compressed = any(child.compressed for child in children)
    if condition is None:
        return _Trace(None, read, [], [], compressed)
    support, refute = [], []
    if (operator == "all" and condition is True) or (operator == "any" and condition is False):
        paths = [[]]
        for child in children:
            alternatives = child.support if condition is True else child.refute
            if len(paths) * len(alternatives) > _CARTESIAN_COMPRESSION_THRESHOLD:
                paths = [_ordered_union(*paths, *alternatives)]
                compressed = True
            else:
                paths = [_ordered_union(prefix, alternative) for prefix in paths for alternative in alternatives]
        if condition is True:
            support = paths
        else:
            refute = paths
    else:
        paths = []
        for child in children:
            if child.condition is condition:
                paths.extend(child.support if condition is True else child.refute)
                if len(paths) > _MAX_ALTERNATIVES:
                    _fail("LIMIT_EXCEEDED", path, "Evidence alternatives exceed the supported limit.")
        if condition is True:
            support = paths
        else:
            refute = paths
    return _Trace(condition, read, support, refute, compressed)


def _evaluate_collection(operator: str, left: Any, right: Any, read: list[str], path: str) -> _Trace:
    if operator == "all_values":
        if not isinstance(left, list) or not left:
            return _leaf(None, read)
        return _leaf(all(_strict_equal(item, right) for item in left), read)
    if operator == "is_minimum":
        if not _is_number(left) or not isinstance(right, list) or not right:
            return _leaf(None, read)
        candidates = [_amount(item) for item in right]
        if not all(_is_number(item) for item in candidates):
            return _leaf(None, read)
        return _leaf(float(left) == min(float(item) for item in candidates), read)
    if not isinstance(left, list):
        _fail("INVALID_VALUE", path, "A collection operand must be an array.")
    found = any(_strict_equal(_amount(item), right) for item in left)
    return _leaf(found if operator == "contains" else not found, read)


def _evaluate_special(operator: str, argument: Any, values: dict[str, Any], path: str) -> _Trace:
    key = argument["record"]
    record = values.get(key)
    read = [key]
    if not isinstance(record, dict) or record.get("scope_bound") is not True or record.get("logical_role") != "necessary_conjunction":
        return _leaf(None, read)
    conditions = record.get("conditions")
    if not isinstance(conditions, list):
        conditions = []
    unrestricted = record.get("explicitly_unrestricted") is True
    complete = record.get("applicable_condition_set_complete") is True
    if unrestricted and conditions:
        return _leaf(None, read)
    violated = argument["mode"] == "violated"
    if record.get("platform_asserted_violation") is True:
        return _leaf(None if conditions else violated, read)
    results = [_constraint_row(row) for row in conditions]
    if False in results:
        return _leaf(violated, read)
    if results and complete and all(result is True for result in results):
        return _leaf(not violated, read)
    if not results and complete and unrestricted and not violated:
        return _leaf(True, read)
    return _leaf(None, read)


def _js_truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if type(value) in (int, float):
        return value != 0 and not (isinstance(value, float) and math.isnan(value))
    return value != "" if isinstance(value, str) else True


def _scalar_type(value: Any) -> str | None:
    if isinstance(value, str):
        return "string"
    if type(value) is bool:
        return "boolean"
    if _is_number(value):
        return "number"
    return None


def _constraint_row(row: Any) -> bool | None:
    if not isinstance(row, dict):
        return None
    status = row.get("status")
    if _js_truthy(status) and status != "known":
        return None
    left, right = row.get("left", _MISSING), row.get("right", _MISSING)
    if _unknown(left) or _unknown(right):
        return None
    operator = row.get("operator")
    if operator in ("eq", "ne"):
        if _scalar_type(left) is None or _scalar_type(left) != _scalar_type(right):
            return None
        equal = _strict_equal(left, right)
        return equal if operator == "eq" else not equal
    if operator in ("gt", "gte", "lt", "lte"):
        if not _is_number(left) or not _is_number(right):
            return None
        a, b = float(left), float(right)
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[operator]
    if operator in ("in", "not_in"):
        kind = _scalar_type(left)
        if kind is None or not isinstance(right, list) or not right or any(_scalar_type(item) != kind for item in right):
            return None
        found = any(_strict_equal(left, item) for item in right)
        return found if operator == "in" else not found
    if operator == "between":
        if not _is_number(left) or not isinstance(right, list) or len(right) != 2 or not all(_is_number(item) for item in right):
            return None
        lower_inclusive, upper_inclusive = row.get("lower_inclusive"), row.get("upper_inclusive")
        if type(lower_inclusive) is not bool or type(upper_inclusive) is not bool:
            return None
        lower = left >= right[0] if lower_inclusive else left > right[0]
        upper = left <= right[1] if upper_inclusive else left < right[1]
        return lower and upper
    return None


def evaluate_table(table: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Evaluate every rule and select raw rules according to FIRST or COLLECT."""
    validate_table(table)
    if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
        _fail("INVALID_VALUES", "$", "Values must be an object with string keys.")
    evaluations = []
    true_rules = []
    for i, rule in enumerate(table["rules"]):
        trace = _evaluate(rule["when"], values, f"$.rules[{i}].when")
        evaluations.append({
            "rule_id": rule["id"],
            "condition": trace.condition,
            "read_variables": trace.read,
            "supporting_variables": _ordered_union(*trace.support),
            "supporting_alternatives": trace.support,
            "refuting_variables": _ordered_union(*trace.refute),
            "trace_compressed": trace.compressed,
        })
        if trace.condition is True:
            true_rules.append(rule)
    return {
        "matched": true_rules[:1] if table["hit_policy"] == "FIRST" else true_rules,
        "evaluations": evaluations,
    }
