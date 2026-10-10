"""Build a reproducible source ZIP from an explicitly reviewed file manifest."""
from pathlib import Path, PurePosixPath
import stat
import zipfile

root = Path(__file__).resolve().parents[1]
manifest = root / 'scripts/source-manifest.txt'
output = root / 'dist/dify-dmn-plugin-0.7.0-source.zip'
output.parent.mkdir(exist_ok=True)
files = [line.strip() for line in manifest.read_text().splitlines()
         if line.strip() and not line.startswith('#')]
if len(files) != len(set(files)):
    raise ValueError('Duplicate source-manifest entries')
# Validate all entries before opening/replacing the output.
for name in files:
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Unsafe manifest path: {name}')
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f'Missing or unsafe source file: {name}')
    if any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
        raise ValueError(f'Symlink source parent: {name}')
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in sorted(files):
        path = root / name
        info = zipfile.ZipInfo(f'dify-dmn-integration/{name}', date_time=(2026, 10, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        archive.writestr(info, path.read_bytes(), compresslevel=9)
print(f'{output.name}: {len(files)} reviewed source files')
