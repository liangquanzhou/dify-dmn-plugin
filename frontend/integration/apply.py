#!/usr/bin/env python3
"""Install the review-only matrix on the exact, unmodified Dify 1.11.1 baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parent
MANIFEST = json.loads((HERE / 'baseline.json').read_text())
PATCH = FRONTEND / 'patches/dify-1.11.1-decision-matrix.patch'
DESTINATION = Path('web/app/components/workflow/nodes/tool/components/dmn-decision-table')
SOURCES = {
    'decision-table.tsx': FRONTEND / 'src/decision-table.tsx',
    'decision-table.module.css': FRONTEND / 'src/decision-table.module.css',
    'model.ts': FRONTEND / 'src/model.ts',
    'identity.ts': HERE / 'identity.ts',
}


def run(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root: Path, check: bool) -> None:
    root = root.resolve(strict=True)
    if Path(run(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise RuntimeError('Pass the Dify repository root, not its web directory.')
    head = run(root, 'rev-parse', 'HEAD')
    if head != MANIFEST['dify_commit']:
        raise RuntimeError(f"Wrong Dify commit: {head}; required {MANIFEST['dify_commit']}")
    states = []
    for relative, hashes in MANIFEST['files'].items():
        path = root / relative
        if path.is_symlink():
            raise RuntimeError(f'Refusing a symlink target: {relative}')
        current = digest(path.read_bytes())
        if current == hashes['original_sha256']:
            states.append('original')
        elif current == hashes['patched_sha256']:
            states.append('patched')
        else:
            raise RuntimeError(f'Target differs from the exact baseline or this patch: {relative}')
    if len(set(states)) != 1:
        raise RuntimeError('Partially patched targets found. Restore the three patch targets before retrying.')
    state = states[0]
    dest = root / DESTINATION
    # Never follow a path redirected outside this checkout by a symlink.
    for parent in [dest, *dest.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise RuntimeError(f'Refusing a symlink destination: {parent}')
    content = {name: source.read_bytes() for name, source in SOURCES.items()}
    if dest.exists():
        for existing in dest.iterdir():
            if existing.is_symlink() or not existing.is_file() or existing.name not in content:
                raise RuntimeError(f'Unrecognized existing destination: {existing}')
            if existing.read_bytes() != content[existing.name]:
                raise RuntimeError(f'Refusing to overwrite a differing component: {existing}')
    run(root, 'apply', '--check', *(['--reverse'] if state == 'patched' else []), str(PATCH))
    if check:
        print(f'PASS: exact Dify commit, target hashes and patch {state} state; all component sources readable.')
        print('No files changed. This checks patch compatibility, not a Dify build.')
        return
    created = []
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in content.items():
            target = dest / name
            if not target.exists():
                atomic_write(target, data)
                created.append(target)
        if state == 'original':
            run(root, 'apply', str(PATCH))
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    for relative, hashes in MANIFEST['files'].items():
        if digest((root / relative).read_bytes()) != hashes['patched_sha256']:
            raise RuntimeError(f'Post-apply hash mismatch: {relative}')
    for name, data in content.items():
        if (dest / name).read_bytes() != data:
            raise RuntimeError(f'Post-copy byte mismatch: {name}')
    print(f'PASS: {"installed" if state == "original" else "already installed"}; all patch and component bytes verified.')
    print('Next: run Dify web lint, type checks, tests and build. No deploy or push was performed.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dify_root', type=Path)
    parser.add_argument('--check', action='store_true', help='Verify preconditions and patch without modifying files')
    args = parser.parse_args()
    try:
        install(args.dify_root, args.check)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
