"""Serve only the bundled, display-only structure viewer.

The endpoint is a static file boundary, not an API for definitions or execution.
Local JSON imports stay in the browser. No request body, settings, SDK session,
evaluator, storage, or remote URL is used here.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from dify_plugin import Endpoint
from werkzeug import Request, Response


STATIC_ROOT = Path(__file__).resolve().parents[1] / "viewer_static"
# Never use a request value as a filesystem path before this exact lookup.
ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "viewer.js": "text/javascript; charset=utf-8",
    "viewer.css": "text/css; charset=utf-8",
}
CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'none'",
    "script-src 'self'",
    # React uses inline style attributes for the canvas layout and zoom.
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'none'",
    "img-src data:",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
))
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-DNS-Prefetch-Control": "off",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}


def _response(request: Request, body: bytes, status: int, content_type: str) -> Response:
    # SDK 0.10.2 serializes Response.response itself, rather than calling its
    # WSGI adapter. Strip HEAD bodies explicitly while retaining GET length.
    response = Response(
        b"" if request.method == "HEAD" else body,
        status=status,
        content_type=content_type,
        headers=SECURITY_HEADERS,
    )
    response.content_length = len(body)
    return response


class StructureViewerEndpoint(Endpoint):
    """A read-only endpoint with an exact three-file allowlist."""

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        if r.method not in {"GET", "HEAD"}:
            response = _response(r, b"Method not allowed\n", 405, "text/plain; charset=utf-8")
            response.headers["Allow"] = "GET, HEAD"
            return response

        # Do not parse or consume submitted JSON, uploads, URLs, or form data.
        # The SDK HTTP parser supplies CONTENT_LENGTH for a body even when the
        # incoming request omitted it. Reject bodies and query inputs outright.
        if r.query_string or r.content_length or r.headers.get("Transfer-Encoding"):
            return _response(r, b"Request inputs are not supported\n", 400, "text/plain; charset=utf-8")

        asset_name = values.get("asset_path", "index.html")
        if not isinstance(asset_name, str) or asset_name not in ASSETS:
            return _response(r, b"Not found\n", 404, "text/plain; charset=utf-8")

        asset = STATIC_ROOT / asset_name
        try:
            # Only regular packaged files are served, including if a package
            # was accidentally constructed with a symlinked asset or folder.
            if STATIC_ROOT.is_symlink() or asset.is_symlink() or not asset.is_file():
                raise FileNotFoundError
            body = asset.read_bytes()
        except OSError:
            return _response(r, b"Not found\n", 404, "text/plain; charset=utf-8")

        return _response(r, body, 200, ASSETS[asset_name])
