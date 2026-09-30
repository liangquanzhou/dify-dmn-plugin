"""Bounded private-engine client. No model or fact data is written to logs or disk."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
import simplejson

MAX_XML_BYTES = 512 * 1024
MAX_FACTS_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_FACTS_DEPTH = 32
MAX_JSON_NODES = 10000
MAX_NUMBER_CHARS = 256
MAX_DECIMAL_EXPONENT = 10000
TIMEOUT = httpx.Timeout(15.0, connect=3.0)


class DMNError(ValueError):
    """Sanitized failure suitable for Dify's node error channel."""


class _JSONBoundaryError(ValueError):
    """Only static, non-sensitive validation messages belong in this exception."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _JSONBoundaryError("duplicate JSON keys are not allowed")
        result[key] = value
    return result


def _invalid_constant(_: str) -> None:
    raise _JSONBoundaryError("non-finite numbers are not allowed")


def _integer(raw: str) -> int:
    if len(raw) > MAX_NUMBER_CHARS:
        raise _JSONBoundaryError("JSON numbers exceed the 256-character limit")
    return int(raw)


def _decimal(raw: str) -> Decimal:
    if len(raw) > MAX_NUMBER_CHARS:
        raise _JSONBoundaryError("JSON numbers exceed the 256-character limit")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise _JSONBoundaryError("invalid decimal number") from None
    # Bound both scale and magnitude without ever converting through binary float.
    if (not value.is_finite() or abs(value.as_tuple().exponent) > MAX_DECIMAL_EXPONENT
            or abs(value.adjusted()) > MAX_DECIMAL_EXPONENT):
        raise _JSONBoundaryError("decimal exponent exceeds the supported limit")
    return value


def _check_json(value: Any, depth: int = 0, count: list[int] | None = None, *,
                max_depth: int = MAX_FACTS_DEPTH, max_nodes: int = MAX_JSON_NODES) -> None:
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > max_nodes:
        raise _JSONBoundaryError(f"JSON exceeds {max_nodes} values")
    if depth > max_depth:
        raise _JSONBoundaryError(f"JSON nesting exceeds {max_depth} levels")
    if isinstance(value, dict):
        for key, child in value.items():
            key.encode("utf-8")  # Reject escaped lone surrogates in keys too.
            _check_json(child, depth + 1, count, max_depth=max_depth, max_nodes=max_nodes)
    elif isinstance(value, list):
        for child in value:
            _check_json(child, depth + 1, count, max_depth=max_depth, max_nodes=max_nodes)
    elif isinstance(value, str):
        value.encode("utf-8")


def _json_object(raw: str | bytes | bytearray, code: str) -> dict[str, Any]:
    try:
        # Decimal hooks preserve FEEL numeric values on both sides of the engine.
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid_constant,
                           parse_float=_decimal, parse_int=_integer)
        if not isinstance(value, dict):
            raise _JSONBoundaryError("expected a JSON object")
        # The response has an envelope around the engine's bounded result tree.
        _check_json(value, max_depth=MAX_FACTS_DEPTH + (code == "ENGINE_RESPONSE"),
                    max_nodes=MAX_JSON_NODES * (2 if code == "ENGINE_RESPONSE" else 1))
        return value
    except _JSONBoundaryError as exc:
        raise DMNError(f"{code}: {exc}") from None
    except (ValueError, UnicodeError, RecursionError):
        raise DMNError(f"{code}: invalid JSON object") from None


def _utf8(value: str, code: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeError:
        raise DMNError(f"{code}: invalid Unicode text") from None


def exact_json(value: Any) -> str:
    """Preserve decimal JSON numbers; never stringify or round them for transport."""
    return simplejson.dumps(value, use_decimal=True, ensure_ascii=False, allow_nan=False,
                            separators=(",", ":"))


def parse_inputs(parameters: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    xml = parameters.get("model_xml")
    decision = parameters.get("decision_id")
    raw = parameters.get("facts_json")
    if not isinstance(xml, str) or not xml.strip():
        raise DMNError("INVALID_MODEL: model_xml is required")
    if len(_utf8(xml, "INVALID_MODEL")) > MAX_XML_BYTES:
        raise DMNError("INVALID_MODEL: XML exceeds 512 KiB")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml, re.I):
        raise DMNError("UNSAFE_XML: DTD and entity declarations are forbidden")
    if not isinstance(decision, str) or not decision.strip() or len(decision) > 256:
        raise DMNError("INVALID_DECISION: decision_id is required and limited to 256 characters")
    _utf8(decision, "INVALID_DECISION")
    if not isinstance(raw, str) or len(_utf8(raw, "INVALID_FACTS")) > MAX_FACTS_BYTES:
        raise DMNError("INVALID_FACTS: facts_json must be a JSON string of at most 128 KiB")
    facts = _json_object(raw, "INVALID_FACTS")
    return xml, decision.strip(), facts


def engine_origin(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise DMNError("INVALID_ENDPOINT: configure the private DMN engine origin")
    # urlsplit silently removes CR/LF/TAB; reject before parsing or normalization.
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DMNError("INVALID_ENDPOINT: invalid engine origin")
    try:
        value.encode("utf-8")
        url = urlsplit(value.strip())
        _ = url.port
        parsed = httpx.URL(value.strip())
    except (ValueError, UnicodeError, httpx.InvalidURL):
        raise DMNError("INVALID_ENDPOINT: invalid engine origin") from None
    if (url.scheme not in ("https", "http") or not url.hostname or url.username is not None
            or url.password is not None or not parsed.host
            or url.path not in ("", "/") or url.query or url.fragment):
        raise DMNError("INVALID_ENDPOINT: use an HTTP(S) origin without path, credentials, query or fragment")
    return str(parsed).rstrip("/")


class EngineClient:
    def __init__(self, credentials: dict[str, Any], *, transport: httpx.BaseTransport | None = None):
        self.origin = engine_origin(credentials.get("engine_url"))
        token = credentials.get("api_token", "")
        if token is None:
            token = ""
        if (not isinstance(token, str) or not token.isascii()
                or any(ord(c) < 33 or ord(c) == 127 for c in token)):
            raise DMNError("INVALID_CREDENTIAL: invalid bearer token")
        self.headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.transport = transport

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            headers = dict(self.headers)
            content = None
            if payload is not None:
                content = exact_json(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
            # Do not forward credentials on redirects or through process-wide HTTP proxies.
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream("GET" if payload is None else "POST", self.origin + path,
                                   content=content, headers=headers) as response:
                    if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                        raise DMNError("ENGINE_RESPONSE: compressed engine responses are not accepted")
                    data = bytearray()
                    # iter_raw avoids HTTPX's unbounded decompression. Check before copying.
                    for chunk in response.iter_raw():
                        if len(chunk) > MAX_RESPONSE_BYTES - len(data):
                            raise DMNError("ENGINE_RESPONSE: engine response exceeds 1 MiB")
                        data.extend(chunk)
                    body = _json_object(data, "ENGINE_RESPONSE")
                    if response.status_code >= 300:
                        error = body.get("error")
                        code = error.get("code") if isinstance(error, dict) else None
                        if not isinstance(code, str) or not re.fullmatch(r"[A-Z_]{1,64}", code):
                            code = "ENGINE_REJECTED"
                        # Server messages might contain business inputs; do not expose them.
                        raise DMNError(f"{code}: DMN engine rejected the request (HTTP {response.status_code})")
                    return body
        except httpx.TimeoutException:
            raise DMNError("ENGINE_TIMEOUT: DMN engine did not respond within the configured timeout") from None
        except httpx.HTTPError:
            raise DMNError("ENGINE_UNAVAILABLE: could not connect securely to the DMN engine") from None
        except httpx.InvalidURL:
            raise DMNError("INVALID_ENDPOINT: invalid engine origin") from None

    def health(self) -> None:
        if self._request("/health").get("status") != "ok":
            raise DMNError("ENGINE_UNAVAILABLE: engine health check failed")

    def evaluate(self, parameters: dict[str, Any]) -> dict[str, Any]:
        xml, decision, facts = parse_inputs(parameters)
        result = self._request("/evaluate", {"model_xml": xml, "decision_id": decision, "facts": facts})
        if (result.get("status") not in ("matched", "no_match")
                or "result" not in result
                or not isinstance(result.get("matched_rule_ids"), list)
                or not all(isinstance(x, str) for x in result["matched_rule_ids"])
                or result.get("model_version") != hashlib.sha256(xml.encode("utf-8")).hexdigest()):
            raise DMNError("ENGINE_RESPONSE: invalid result contract or model hash mismatch")
        return result
