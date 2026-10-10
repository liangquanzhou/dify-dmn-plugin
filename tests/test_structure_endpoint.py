"""Independent static-endpoint tests against the installed Dify SDK API."""
from __future__ import annotations

import inspect
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.entities.plugin.request import EndpointInvokeRequest
from dify_plugin.core.plugin_executor import PluginExecutor
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.endpoint import EndpointProviderConfiguration
from werkzeug import Request
from werkzeug.routing import Map

import endpoints.structure_viewer as viewer


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_ASSETS = {
    "index.html": b'<!doctype html><script src="./viewer.js" defer></script>',
    "viewer.js": b'"use strict"; // SYNTHETIC static fixture\n',
    "viewer.css": b"body { color: black; }\n",
}


class UnusedSession:
    def __getattr__(self, name):
        raise AssertionError(f"Static endpoint accessed the SDK session: {name}")


@pytest.fixture
def assets(tmp_path, monkeypatch):
    directory = tmp_path / "viewer_static"
    directory.mkdir()
    for name, body in SYNTHETIC_ASSETS.items():
        (directory / name).write_bytes(body)
    (directory / "secret.txt").write_text("PRIVATE-FIXTURE")
    (directory / "offline.html").write_text("NOT-AN-ENDPOINT-ASSET")
    monkeypatch.setattr(viewer, "STATIC_ROOT", directory)
    return directory


@pytest.fixture
def endpoint(assets):
    return viewer.StructureViewerEndpoint(UnusedSession())


@pytest.fixture
def registration(monkeypatch, assets):
    """Use real SDK YAML validation, class loading, and routing resolution."""
    monkeypatch.chdir(ROOT / "plugin")
    config = EndpointProviderConfiguration.model_validate(
        yaml.safe_load((ROOT / "plugin/endpoints/structure_viewer.yaml").read_text())
    )
    assert config.settings == []
    registration = object.__new__(PluginRegistration)
    registration.endpoints = Map()
    registration.endpoints_configuration = [config]
    registration._resolve_endpoints()
    # The SDK intentionally loads fresh module objects, so patch each resolved
    # endpoint's asset root rather than the module imported by direct tests.
    for rule in registration.endpoints.iter_rules():
        monkeypatch.setitem(rule.endpoint._invoke.__globals__, "STATIC_ROOT", assets)
    return registration


def invoke(endpoint, path="/", method="GET", *, asset_path=None, **kwargs):
    request = Request.from_values(path=path, method=method, **kwargs)
    values = {} if asset_path is None else {"asset_path": asset_path}
    return endpoint.invoke(request, values, {"unused": "PRIVATE-SETTING"})


def assert_security_headers(response):
    assert dict((name, response.headers[name]) for name in viewer.SECURITY_HEADERS) == viewer.SECURITY_HEADERS
    assert response.headers.get("Access-Control-Allow-Origin") is None
    assert response.headers.get("Set-Cookie") is None
    assert response.headers.get("Location") is None


@pytest.mark.parametrize("asset_name", SYNTHETIC_ASSETS)
def test_get_exact_bundled_files(endpoint, asset_name):
    response = invoke(endpoint, f"/{asset_name}", asset_path=asset_name)
    assert response.status_code == 200
    assert response.data == SYNTHETIC_ASSETS[asset_name]
    assert response.headers["Content-Type"] == viewer.ASSETS[asset_name]
    assert response.content_length == len(response.data)
    assert_security_headers(response)


def test_root_serves_index_without_redirect(endpoint):
    response = invoke(endpoint)
    assert response.status_code == 200
    assert response.data == SYNTHETIC_ASSETS["index.html"]
    assert_security_headers(response)


@pytest.mark.parametrize("asset_name", SYNTHETIC_ASSETS)
def test_head_has_get_headers_but_no_body_even_before_wsgi(endpoint, asset_name):
    get = invoke(endpoint, f"/{asset_name}", asset_path=asset_name)
    head = invoke(endpoint, f"/{asset_name}", "HEAD", asset_path=asset_name)
    assert head.status_code == 200
    assert head.data == b""
    assert dict(head.headers) == dict(get.headers)


@pytest.mark.parametrize("asset_path", [
    "../manifest.yaml", "../../.env", "/etc/passwd", "..\\manifest.yaml",
    "%2e%2e/manifest.yaml", "%252e%252e/manifest.yaml", "viewer.js/../secret.txt",
    "./viewer.js", "viewer.js/", "viewer.js\x00", "viewer.js?file=.env",
    "nested/viewer.js", "secret.txt", "offline.html", "index.HTML", "", [], {},
])
def test_allowlist_blocks_traversal_and_arbitrary_files(endpoint, asset_path):
    response = invoke(endpoint, asset_path=asset_path)
    assert response.status_code == 404
    assert response.data == b"Not found\n"
    assert_security_headers(response)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
def test_direct_non_read_methods_are_rejected(endpoint, method):
    response = invoke(endpoint, method=method)
    assert response.status_code == 405
    assert response.headers["Allow"] == "GET, HEAD"
    assert_security_headers(response)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("request_input", [
    {"query_string": "url=https%3A%2F%2Fexample.invalid%2Fprivate.json"},
    {"data": b'{"PRIVATE-INPUT":true}', "content_type": "application/json"},
    {"data": {"table_json": "PRIVATE-INPUT"}},
    {"headers": {"Transfer-Encoding": "chunked"}},
])
def test_rejects_request_inputs_without_parsing_or_echoing(endpoint, monkeypatch, method, request_input):
    def forbidden(*args, **kwargs):
        raise AssertionError("Request data must not be read")
    monkeypatch.setattr(Request, "get_data", forbidden)
    monkeypatch.setattr(Request, "get_json", forbidden)
    monkeypatch.setattr(Request, "_load_form_data", forbidden)
    response = invoke(endpoint, method=method, **request_input)
    assert response.status_code == 400
    assert b"PRIVATE-INPUT" not in response.data
    assert response.data == (b"" if method == "HEAD" else b"Request inputs are not supported\n")
    assert_security_headers(response)


def test_missing_file_has_generic_error(endpoint, assets):
    (assets / "viewer.js").unlink()
    response = invoke(endpoint, asset_path="viewer.js")
    assert response.status_code == 404
    assert str(assets).encode() not in response.data
    assert_security_headers(response)


def test_read_error_has_generic_error(endpoint, monkeypatch):
    def denied(path):
        raise PermissionError("PRIVATE-FILESYSTEM-PATH")
    monkeypatch.setattr(Path, "read_bytes", denied)
    response = invoke(endpoint, asset_path="viewer.js")
    assert response.status_code == 404
    assert b"PRIVATE" not in response.data
    assert_security_headers(response)


def test_asset_symlink_is_not_followed(endpoint, assets, tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("PRIVATE-FIXTURE")
    (assets / "viewer.js").unlink()
    (assets / "viewer.js").symlink_to(outside)
    response = invoke(endpoint, asset_path="viewer.js")
    assert response.status_code == 404
    assert b"PRIVATE" not in response.data


def test_static_root_symlink_is_not_followed(endpoint, assets, tmp_path, monkeypatch):
    link = tmp_path / "linked_static"
    link.symlink_to(assets, target_is_directory=True)
    monkeypatch.setattr(viewer, "STATIC_ROOT", link)
    assert invoke(endpoint).status_code == 404


def test_directory_cannot_be_served(endpoint, assets):
    (assets / "viewer.js").unlink()
    (assets / "viewer.js").mkdir()
    assert invoke(endpoint, asset_path="viewer.js").status_code == 404


def test_csp_disables_connections_and_executable_inline_content():
    directives = dict(item.split(" ", 1) for item in viewer.CONTENT_SECURITY_POLICY.split("; "))
    assert directives == {
        "default-src": "'none'", "script-src": "'self'",
        "style-src": "'self' 'unsafe-inline'", "connect-src": "'none'",
        "img-src": "data:", "base-uri": "'none'", "form-action": "'none'",
        "frame-ancestors": "'none'",
    }


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("path, expected_values", [
    ("/", {}), ("/viewer.js", {"asset_path": "viewer.js"}),
    ("/nested/forbidden.txt", {"asset_path": "nested/forbidden.txt"}),
])
def test_real_sdk_routes_root_and_path_converter(registration, method, path, expected_values):
    cls, values = registration.dispatch_endpoint_request(Request.from_values(path=path, method=method))
    assert cls.__name__ == "StructureViewerEndpoint"
    assert Path(inspect.getfile(cls)).resolve() == ROOT / "plugin/endpoints/structure_viewer.py"
    assert values == expected_values


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
def test_real_sdk_routing_rejects_non_read_methods(registration, method):
    # SDK 0.10.2 wraps Werkzeug's 405 as ValueError; its executor turns that
    # dispatch failure into 404. No mutating method reaches the endpoint.
    with pytest.raises(ValueError, match="405 Method Not Allowed"):
        registration.dispatch_endpoint_request(Request.from_values(path="/", method=method))


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("target, status, expected", [
    ("/", 200, SYNTHETIC_ASSETS["index.html"]),
    ("/viewer.js", 200, SYNTHETIC_ASSETS["viewer.js"]),
    ("/viewer.css", 200, SYNTHETIC_ASSETS["viewer.css"]),
    ("/%2e%2e/manifest.yaml", 404, b"Not found\n"),
    ("/viewer.js?url=https://example.invalid", 400, b"Request inputs are not supported\n"),
])
def test_real_sdk_http_parser_executor_and_head_serialization(assets, registration, method, target, status, expected):
    executor = PluginExecutor(DifyPluginEnv(), registration)
    raw = f"{method} {target} HTTP/1.1\r\nHost: viewer.invalid\r\n\r\n".encode()
    messages = list(executor.invoke_endpoint(
        UnusedSession(), EndpointInvokeRequest(settings={}, raw_http_request=raw.hex())
    ))
    assert len(messages) == 1
    message = messages[0]
    assert message["status"] == status
    assert bytes.fromhex(message["result"]) == (b"" if method == "HEAD" else expected)
    assert message["headers"]["Content-Length"] == str(len(expected))
    assert message["headers"]["Content-Security-Policy"] == viewer.CONTENT_SECURITY_POLICY


@pytest.mark.parametrize("length_header", [b"Content-Length: 18\r\n", b""])
def test_real_sdk_rejects_get_body_even_without_content_length(assets, registration, length_header):
    executor = PluginExecutor(DifyPluginEnv(), registration)
    raw = b"GET / HTTP/1.1\r\nHost: viewer.invalid\r\n" + length_header + b'\r\n{"PRIVATE": true} '
    messages = list(executor.invoke_endpoint(
        UnusedSession(), EndpointInvokeRequest(settings={}, raw_http_request=raw.hex())
    ))
    assert messages[0]["status"] == 400
    assert b"PRIVATE" not in bytes.fromhex(messages[0]["result"])


def test_generated_packaged_index_uses_relative_assets_and_compatible_csp():
    """Inspect the real committed/generated files, without the synthetic fixture."""
    class EntryParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []
            self.inline_script = []
            self.in_script = False

        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, dict(attrs)))
            self.in_script = tag == "script"

        def handle_endtag(self, tag):
            if tag == "script":
                self.in_script = False

        def handle_data(self, data):
            if self.in_script and data.strip():
                self.inline_script.append(data)

    directory = ROOT / "plugin/viewer_static"
    parser = EntryParser()
    parser.feed((directory / "index.html").read_text(encoding="utf-8"))
    scripts = [attrs for tag, attrs in parser.tags if tag == "script"]
    styles = [attrs for tag, attrs in parser.tags if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert [attrs.get("src") for attrs in scripts] == ["./viewer.js"]
    assert [attrs.get("href") for attrs in styles] == ["./viewer.css"]
    assert all("defer" in attrs for attrs in scripts)
    assert parser.inline_script == []
    assert not any(tag == "base" for tag, attrs in parser.tags)
    assert not any(name.startswith("on") for tag, attrs in parser.tags for name in attrs)
    policies = [attrs["content"] for tag, attrs in parser.tags
                if tag == "meta" and attrs.get("http-equiv", "").lower() == "content-security-policy"]
    assert len(policies) == 1
    directives = dict(part.strip().split(" ", 1) for part in policies[0].split(";") if part.strip())
    # Header-only frame-ancestors is intentionally absent from the HTML meta.
    for name, value in (part.split(" ", 1) for part in viewer.CONTENT_SECURITY_POLICY.split("; ")):
        if name != "frame-ancestors":
            assert directives[name] == value
    assert (directory / "viewer.js").stat().st_size > 0
    assert (directory / "viewer.css").stat().st_size > 0


def test_generated_packaged_assets_through_full_sdk_registration_and_executor(monkeypatch):
    """Use the final manifest and actual asset bytes, then interleave errors."""
    monkeypatch.chdir(ROOT / "plugin")
    config = DifyPluginEnv()
    registration = PluginRegistration(config)
    assert "endpoints/structure_viewer.yaml" in registration.configuration.plugins.endpoints
    assert registration.configuration.resource.permission.endpoint.enabled is True
    executor = PluginExecutor(config, registration)
    directory = ROOT / "plugin/viewer_static"
    assert (directory / "offline.html").is_file(), "Offline deliverable must exist separately"
    cases = [
        ("/", 200, (directory / "index.html").read_bytes(), viewer.ASSETS["index.html"]),
        ("/offline.html", 404, b"Not found\n", "text/plain; charset=utf-8"),
        ("/viewer.js", 200, (directory / "viewer.js").read_bytes(), viewer.ASSETS["viewer.js"]),
        ("/%2e%2e/manifest.yaml", 404, b"Not found\n", "text/plain; charset=utf-8"),
        ("/viewer.css", 200, (directory / "viewer.css").read_bytes(), viewer.ASSETS["viewer.css"]),
        ("/THIRD_PARTY_LICENSES.txt", 404, b"Not found\n", "text/plain; charset=utf-8"),
        ("/index.html", 200, (directory / "index.html").read_bytes(), viewer.ASSETS["index.html"]),
        ("/?definition=PRIVATE-INPUT", 400, b"Request inputs are not supported\n", "text/plain; charset=utf-8"),
        ("/", 200, (directory / "index.html").read_bytes(), viewer.ASSETS["index.html"]),
    ]
    for target, status, expected, content_type in cases:
        for method in ("GET", "HEAD"):
            raw = f"{method} {target} HTTP/1.1\r\nHost: viewer.invalid\r\n\r\n".encode()
            messages = list(executor.invoke_endpoint(
                UnusedSession(), EndpointInvokeRequest(
                    settings={"unused": "PRIVATE-SETTING"}, raw_http_request=raw.hex(),
                ),
            ))
            assert len(messages) == 1
            message = messages[0]
            assert message["status"] == status, (method, target)
            body = bytes.fromhex(message["result"])
            assert body == (b"" if method == "HEAD" else expected), (method, target)
            assert message["headers"]["Content-Type"] == content_type
            assert message["headers"]["Content-Length"] == str(len(expected))
            for name, value in viewer.SECURITY_HEADERS.items():
                assert message["headers"][name] == value
            assert "Set-Cookie" not in message["headers"]
            assert "Access-Control-Allow-Origin" not in message["headers"]
            if status != 200:
                assert b"PRIVATE" not in body
                assert str(ROOT).encode() not in body
