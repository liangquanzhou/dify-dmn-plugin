"""Run the real SDK 0.10.2 process with the plugin-daemon 0.5.1 stdio wire.

Synthetic single-table cases only. There is no HTTP engine, network fixture,
Dify database, company environment, or installation UI in this test. --package
runs the files extracted from the exact release archive, not the source tree.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_NAMES = {"result", "result_json", "matched", "outputs", "evaluations",
                "matched_rule_ids", "status", "table_id", "table_version"}
SUCCESS_SESSIONS = ["invoke-first", "invoke-collect", "invoke-no-match", "invoke-unknown",
                    "invoke-raw-outputs", "invoke-literal-key"]
ERROR_SESSIONS = ["error-table-json", "error-values-json", "error-table-root", "error-values-root",
                  "error-duplicate-key", "error-nonfinite", "error-unsafe-integer", "error-value-type",
                  "error-operator", "error-expression", "error-policy", "error-duplicate-rule",
                  "error-table-size", "error-values-depth", "error-rule-count",
                  "error-missing-table", "error-missing-values", "error-output-frame"]


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def trace(rule_id, condition, read):
    return {"rule_id": rule_id, "condition": condition, "read_variables": read,
            "supporting_variables": read if condition is True else [],
            "supporting_alternatives": [read] if condition is True else [],
            "refuting_variables": read if condition is False else [], "trace_compressed": False}


def table(rules, policy="COLLECT"):
    return {"id": "compat-synthetic", "hit_policy": policy, "rules": rules}


def cases():
    rules = [
        {"id": "low", "when": {"lt": ["x", 0]}, "output": "low"},
        {"id": "first", "when": {"gte": ["x", 10]}, "output": {"picked": 1}, "载荷": {"opaque": True}},
        {"id": "second", "when": {"eq": ["x", 10]}, "output": "second"},
    ]
    evaluations = [trace("low", False, ["x"]), trace("first", True, ["x"]), trace("second", True, ["x"])]
    yield "invoke-first", table(rules, "FIRST"), {"x": 10}, [rules[1]], evaluations
    yield "invoke-collect", table(rules), {"x": 10}, rules[1:], evaluations
    yield "invoke-no-match", table(rules), {"x": 5}, [], [trace(r["id"], False, ["x"]) for r in rules]
    unknown = [{"id": "missing", "when": {"eq": ["missing", 1]}},
               {"id": "null", "when": {"eq": ["null", 1]}}]
    yield "invoke-unknown", table(unknown), {"null": None}, [], [trace("missing", None, ["missing"]), trace("null", None, ["null"])]
    output_values = [{"nested": [None, {"text": "保留"}]}, "text", True, 1.25, [1, "x", False, None], None]
    raw_rules = [{"id": f"raw-{i}", "when": True, "output": value} for i, value in enumerate(output_values)]
    raw_rules.append({"id": "payload-only", "when": True, "载荷": {"operation": "opaque_not_executed"}})
    yield "invoke-raw-outputs", table(raw_rules), {}, raw_rules, [trace(r["id"], True, []) for r in raw_rules]
    dotted = [{"id": "literal", "when": {"eq": ["a.b", 7]}, "output": "literal-key"},
              {"id": "no-traversal", "when": {"eq": ["nested.value", 7]}}]
    yield "invoke-literal-key", table(dotted), {"a.b": 7, "nested": {"value": 7}}, [dotted[0]], [trace("literal", True, ["a.b"]), trace("no-traversal", None, ["nested.value"])]


def error_cases():
    base = table([{"id": "one", "when": True}])
    good = {"table_json": dumps(base), "values_json": "{}"}
    def changed(**kwargs):
        return {**good, **kwargs}
    yield "error-table-json", changed(table_json="{"), "INVALID_JSON"
    yield "error-values-json", changed(values_json="{"), "INVALID_JSON"
    yield "error-table-root", changed(table_json="[]"), "INVALID_INPUT"
    yield "error-values-root", changed(values_json="[]"), "INVALID_INPUT"
    yield "error-duplicate-key", changed(values_json='{"x": 1, "x": 2}'), "INVALID_JSON"
    yield "error-nonfinite", changed(values_json='{"x": NaN}'), "INVALID_JSON"
    yield "error-unsafe-integer", changed(values_json='{"x": 9007199254740993}'), "INVALID_INPUT"
    yield "error-value-type", changed(table_json=dumps(table([{"id": "bad", "when": {"gt": ["x", 1]}}])), values_json='{"x":"PRIVATE-VALUE-FOR-ERROR"}'), "INVALID_VALUE"
    yield "error-operator", changed(table_json=dumps(table([{"id": "bad", "when": {"eval": "PRIVATE-VALUE-FOR-ERROR"}}]))), "UNSUPPORTED_OPERATOR"
    yield "error-expression", changed(table_json=dumps(table([{"id": "bad", "when": {"gt": ["x"]}}]))), "INVALID_EXPRESSION"
    yield "error-policy", changed(table_json=dumps(table([], "UNIQUE"))), "UNSUPPORTED_HIT_POLICY"
    yield "error-duplicate-rule", changed(table_json=dumps(table([{"id": "same", "when": True}, {"id": "same", "when": False}]))), "INVALID_TABLE"
    yield "error-table-size", changed(table_json=dumps({**base, "opaque": "x" * (512 * 1024)})), "LIMIT_EXCEEDED"
    yield "error-values-depth", changed(values_json='{"x":' + '[' * 34 + '0' + ']' * 34 + '}'), "LIMIT_EXCEEDED"
    yield "error-rule-count", changed(table_json=dumps(table([{"id": f"r{i}", "when": True} for i in range(1001)]))), "LIMIT_EXCEEDED"
    yield "error-missing-table", {"values_json": "{}"}, "INVALID_INPUT"
    yield "error-missing-values", {"table_json": dumps(base)}, "INVALID_INPUT"
    # Valid table/values fit input/result limits, but repeated evidence plus all
    # convenience fields exceed the daemon frame limit in the aggregate JSON.
    long_key = "k" * 400
    repeated = table([{"id": f"r{i}", "when": {"eq": [long_key, 1]}} for i in range(1000)])
    yield "error-output-frame", {"table_json": dumps(repeated), "values_json": dumps({long_key: 1})}, "LIMIT_EXCEEDED"


@contextmanager
def plugin_directory(root, package):
    if package is None:
        yield root
        return
    with tempfile.TemporaryDirectory(prefix="dmn-v020-package-") as destination:
        dest = Path(destination)
        with zipfile.ZipFile(package) as archive:
            for item in archive.infolist():
                target = (dest / item.filename).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise AssertionError("Unsafe path in release archive")
            archive.extractall(dest)
        assert (dest / "main.py").is_file(), "Package must have root-level main.py"
        yield dest


def run(output, root, package=None):
    assert sys.version_info[:2] == (3, 12), "Use the pinned Python 3.12 runtime"
    sdk_version = importlib.metadata.version("dify-plugin")
    assert sdk_version == "0.10.2", sdk_version
    assert [item[0] for item in cases()] == SUCCESS_SESSIONS
    assert [item[0] for item in error_cases()] == ERROR_SESSIONS
    with plugin_directory(root, package) as working:
        proc = subprocess.Popen(
            [sys.executable, "-u", "main.py"], cwd=working,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
            env={**os.environ, "INSTALL_METHOD": "local", "PYTHONUNBUFFERED": "1"},
        )
        pending = queue.Queue()
        captured, errors, wire_line_sizes = [], [], []

        def collect_stdout():
            for line in proc.stdout:
                wire_line_sizes.append(len(line.encode("utf-8")))
                if line.strip():
                    try:
                        item = json.loads(line)
                    except ValueError:
                        errors.append(line)
                    else:
                        captured.append(item)
                        pending.put(item)

        def collect_stderr():
            errors.extend(proc.stderr.readlines())

        stdout_thread = threading.Thread(target=collect_stdout, daemon=True)
        stderr_thread = threading.Thread(target=collect_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        def receive(predicate):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    item = pending.get(timeout=max(0.01, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if predicate(item):
                    return item
            raise AssertionError(f"SDK output timeout; stderr={errors!r}, returncode={proc.poll()}")

        def request(session_id, action, parameters=None):
            # Official 0.5.1 Session.Message/GetInvokePluginMap request envelope.
            data = {"user_id": "compat-test-user", "type": "tool", "action": action,
                    "provider": "dmn", "credentials": {}}
            if parameters is not None:
                data.update(tool="evaluate", tool_parameters=parameters)
            envelope = {"session_id": session_id, "conversation_id": None, "message_id": None,
                        "app_id": None, "endpoint_id": None, "context": None,
                        "event": "request", "data": data}
            proc.stdin.write(dumps(envelope) + "\n")
            proc.stdin.flush()
            receive(lambda item: item.get("event") == "session" and item.get("session_id") == session_id
                    and item["data"].get("type") == "end")
            return [item["data"] for item in captured
                    if item.get("event") == "session" and item.get("session_id") == session_id]

        try:
            manifest = receive(lambda item: item.get("type") == "plugin")
            assert manifest["version"] == "0.2.0"
            assert manifest["author"] == "liangquanzhou" and manifest["name"] == "dmn_decision"
            assert manifest["meta"]["minimum_dify_version"] == "1.11.1"
            assert manifest["meta"]["runner"]["version"] == "3.12"
            credentials = request("credential-empty", "validate_tool_credentials")
            assert credentials == [{"type": "stream", "data": {"result": True}}, {"type": "end", "data": {}}], credentials
            for session_id, raw_table, values, matched, evaluations in cases():
                # Deliberate whitespace verifies hashing of exact input text.
                table_text = json.dumps(raw_table, ensure_ascii=False, indent=2) + "\n"
                replies = request(session_id, "invoke_tool", {"table_json": table_text, "values_json": dumps(values)})
                assert len(replies) == 11, (session_id, replies)
                assert replies[-1] == {"type": "end", "data": {}}
                assert all(reply["type"] == "stream" for reply in replies[:-1]), (session_id, replies)
                messages = [reply["data"] for reply in replies[:-1]]
                variables = {message["message"]["variable_name"]: message["message"]["variable_value"]
                             for message in messages if message["type"] == "variable"}
                expected_result = {"matched": matched, "evaluations": evaluations}
                assert set(variables) == OUTPUT_NAMES, (session_id, variables.keys())
                assert variables["result"] == expected_result, (session_id, variables["result"], expected_result)
                assert json.loads(variables["result_json"]) == expected_result
                assert variables["matched"] == matched
                assert variables["outputs"] == [rule.get("output") for rule in matched]
                assert variables["evaluations"] == evaluations
                assert variables["matched_rule_ids"] == [rule["id"] for rule in matched]
                assert variables["status"] == ("matched" if matched else "no_match")
                assert variables["table_id"] == raw_table["id"]
                assert variables["table_version"] == hashlib.sha256(table_text.encode("utf-8")).hexdigest()
                assert messages[-1]["type"] == "json" and messages[-1]["message"]["json_object"] == variables
            for session_id, parameters, expected_code in error_cases():
                replies = request(session_id, "invoke_tool", parameters)
                assert len(replies) == 2 and replies[0]["type"] == "error" and replies[-1]["type"] == "end", (session_id, replies)
                error = replies[0]["data"]
                assert error["error_type"] == "TableInvocationError", (session_id, error)
                assert expected_code in error["message"], (session_id, error)
                assert "PRIVATE-VALUE-FOR-ERROR" not in dumps(error), (session_id, error)
            assert max(wire_line_sizes) <= 4 * 1024 * 1024, "SDK emitted an unsafe daemon frame"
            evidence = {"manifest": manifest, "events": captured,
                        "compatibility": {"plugin_version": "0.2.0", "sdk_version": sdk_version,
                                          "python_version": sys.version.split()[0],
                                          "success_sessions": SUCCESS_SESSIONS, "error_sessions": ERROR_SESSIONS,
                                          "credential_session": "credential-empty",
                                          "max_observed_wire_line_bytes": max(wire_line_sizes),
                                          "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest() if package else None}}
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(dumps(evidence) + "\n")
            print("PASS: real SDK stdio bootstrap; no-credential validation; 6 successful calls; 18 explicit errors; 54 variables; 6 JSON messages; 25 session ends")
            print(f"Wire evidence: {output}")
            if package:
                print(f"Exact tested package SHA-256: {evidence['compatibility']['package_sha256']}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/dmn-v020-stdio-evidence.json"))
    parser.add_argument("--plugin-root", type=Path, default=ROOT / "plugin")
    parser.add_argument("--package", type=Path, help="Run files extracted from this exact .difypkg")
    args = parser.parse_args()
    run(args.output, args.plugin_root, args.package)
