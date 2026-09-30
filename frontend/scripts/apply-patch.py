#!/usr/bin/env python3
"""Fail-closed Dify adapter installer. Never runs git checkout/reset or downloads software."""
import argparse, hashlib, json, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent.parent
BASELINE = json.loads((HERE/'baseline.json').read_text())

def run(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.strip()}')
    return result.stdout.strip()

def hashes_match(root, expected):
    failures = []
    for name, digest in expected.items():
        file = root/name
        actual = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
        if actual != digest: failures.append(name)
    return failures

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dify', type=pathlib.Path, help='Dify Git checkout root')
    parser.add_argument('--check', action='store_true', help='verify only; change no files')
    parser.add_argument('--reverse', action='store_true', help='remove exactly this patch; fail if files changed afterward')
    args = parser.parse_args(); root = args.dify.resolve()
    if run(root, 'rev-parse', '--show-toplevel') != str(root):
        raise RuntimeError('Pass the exact Git repository root, not a subdirectory')
    if run(root, 'rev-parse', 'HEAD') != BASELINE['commit']:
        raise RuntimeError(f"Unsupported Dify commit. Require tag {BASELINE['tag']} at {BASELINE['commit']}")
    if run(root, 'rev-parse', f"refs/tags/{BASELINE['tag']}^{{commit}}") != BASELINE['commit']:
        raise RuntimeError('The required tag is absent or points to a different commit')
    expected = BASELINE['after'] if args.reverse else BASELINE['before']
    if not args.reverse and not hashes_match(root, BASELINE['after']):
        print('This exact adapter is already applied; no changes made.'); return
    failures = hashes_match(root, expected)
    if failures:
        raise RuntimeError('Refusing modified/unexpected files:\n'+'\n'.join(failures))
    patch = HERE/'patches/dify-1.17.1-dmn-editor.patch'
    direction = ['--reverse'] if args.reverse else []
    run(root, 'apply', '--check', *direction, str(patch))
    if args.check:
        print(f"Verified {BASELINE['tag']} ({BASELINE['commit']}); patch {'removal' if args.reverse else 'application'} can proceed.")
        return
    run(root, 'apply', *direction, str(patch))
    if hashes_match(root, BASELINE['before'] if args.reverse else BASELINE['after']):
        raise RuntimeError('Post-application hash verification failed; inspect the Git diff')
    print('Patch removed.' if args.reverse else 'Patch applied and every output hash verified. Review git diff, regenerate the pnpm lockfile, then build Dify web.')

if __name__ == '__main__':
    try: main()
    except (OSError, RuntimeError) as error:
        print(f'ERROR: {error}', file=sys.stderr); sys.exit(1)
