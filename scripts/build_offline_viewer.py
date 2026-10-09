"""Embed the actual built React component. No alternate renderer or network assets."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
dist=root/'frontend/dist'
html=(dist/'index.html').read_text()
def script(m):
    content=(dist/m.group(1).lstrip('/')).read_text().replace('</script', '<\\/script')
    return '<script type="module">'+content+'</script>'
def css(m):
    return '<style>'+(dist/m.group(1).lstrip('/')).read_text()+'</style>'
html=re.sub(r'<script[^>]*src="([^"]+)"[^>]*></script>',script,html)
html=re.sub(r'<link[^>]*href="([^"]+\.css)"[^>]*>',css,html)
notices=(root/'frontend/THIRD_PARTY_LICENSES.txt').read_text()
html=html.replace('</head>', '<!--\n'+notices+'\n-->\n</head>')
out=root/'dist/dmn-decision-matrix-0.4.1-offline.html';out.parent.mkdir(exist_ok=True);out.write_text(html)
assert '<script src=' not in html and '/assets/' not in html
print(out)
