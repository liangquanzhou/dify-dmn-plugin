"""Build a separate static/offline read-only viewer with a content-hash CSP.

No downloaded assets or runtime network requests. Requires frontend's locked dependencies.
"""
from pathlib import Path
import base64
import hashlib
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BASE_CSP = "default-src 'none'; connect-src 'none'; img-src data:; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; style-src 'self' 'unsafe-inline'"

def build() -> None:
    subprocess.run(["npm", "exec", "--", "vite", "build", "--config", "vite.structure.config.ts"], cwd=FRONTEND, check=True)
    dist = ROOT / "dist" / "structure-build"
    output = ROOT / "plugin" / "viewer_static"
    output.mkdir(parents=True, exist_ok=True)
    js = (dist / "viewer.js").read_text()
    css = (dist / "viewer.css").read_text()
    notices = (FRONTEND / "THIRD_PARTY_LICENSES.txt").read_text()
    for name, contents in (("viewer.js", js), ("viewer.css", css), ("THIRD_PARTY_LICENSES.txt", notices)):
        (output / name).write_text(contents)
    shell = '<!doctype html>\n<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="{csp}"><title>DMN 只读结构查看器</title>{css}</head><body><div id="root"></div>{script}</body></html>\n'
    (output / "index.html").write_text(shell.format(csp=BASE_CSP + "; script-src 'self'", css='<link rel="stylesheet" href="./viewer.css">', script='<script defer src="./viewer.js"></script>'))
    inline_js = js.replace('</script', '<\\/script')
    digest = base64.b64encode(hashlib.sha256(inline_js.encode()).digest()).decode()
    offline = shell.format(csp=BASE_CSP + f"; script-src 'sha256-{digest}'", css='<style>' + css + '</style>', script='<script>' + inline_js + '</script>')
    offline = offline.replace('</head>', '<!--\n' + notices.replace('--', '—') + '\n-->\n</head>')
    (output / "offline.html").write_text(offline)
    print(f"Built {output}; offline script CSP sha256-{digest}")

if __name__ == "__main__":
    build()
