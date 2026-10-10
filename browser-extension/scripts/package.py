#!/usr/bin/env python3
"""Create deterministic candidate archives from an explicit safe file allowlist."""
from pathlib import Path
import hashlib, json, zipfile
root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
fixed_time = (2026, 10, 9, 0, 0, 0)

def make_archive(path, entries):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for src, name in sorted(entries, key=lambda e:e[1]):
            if src.is_symlink():
                raise RuntimeError('Refusing symlink in archive: '+str(src))
            info = zipfile.ZipInfo(name, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, src.read_bytes())

extension_entries = [(p,p.relative_to(dist/'extension').as_posix()) for p in (dist/'extension').rglob('*') if p.is_file()]
for name in ['README.zh-CN.md','THIRD_PARTY_NOTICES.md','docs/VALIDATION.md','docs/PROVENANCE.md']:
    extension_entries.append((root/name,name))
# Code and public synthetic test evidence only. Never package browser profiles or private host inputs.
source_entries=[]
for folder in ['src','tests','scripts','docs','evidence']:
    for p in (root/folder).rglob('*'):
        if p.is_file() and not any(part.startswith('.') for part in p.relative_to(root).parts):
            source_entries.append((p, 'dmn-browser-preview/'+p.relative_to(root).as_posix()))
for name in ['README.md','README.zh-CN.md','THIRD_PARTY_NOTICES.md','LICENSE','manifest.json','package.json','package-lock.json','tsconfig.json']:
    source_entries.append((root/name,'dmn-browser-preview/'+name))
for p,name in extension_entries:
    source_entries.append((p, 'dmn-browser-preview/dist/extension/'+name))
paths=[dist/'dmn-browser-preview-0.1.0-candidate-unpacked.zip',dist/'dmn-browser-preview-0.1.0-candidate-source.zip']
make_archive(paths[0],extension_entries);make_archive(paths[1],source_entries)
report={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in paths}
(dist/'SHA256SUMS.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
