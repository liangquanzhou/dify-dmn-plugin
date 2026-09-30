"""Create an inspectable source ZIP; omit dependencies, build products and secrets."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root/'dist/dify-dmn-integration-0.1.1-source.zip'
output.parent.mkdir(exist_ok=True)
exclude_dirs = {'node_modules','.venv','.git','__pycache__','.pytest_cache','target','test-results','playwright-report'}
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for file in sorted(root.rglob('*')):
        if not file.is_file():
            continue
        rel=file.relative_to(root)
        if any(part in exclude_dirs for part in rel.parts) or file.name in ('.env',):
            continue
        if rel.parts[0] in ('dist','release-assets') or (rel.parts[0]=='frontend' and len(rel.parts)>1 and rel.parts[1]=='dist'):
            continue
        if file.suffix in ('.pyc','.jar','.pem') or file.name.startswith('.env.') and file.name != '.env.example':
            continue
        archive.write(file,Path('dify-dmn-integration')/rel)
print(output)
