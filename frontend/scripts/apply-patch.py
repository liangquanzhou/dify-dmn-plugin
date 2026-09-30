#!/usr/bin/env python3
"""Fail-closed Dify adapter installer. Never runs git checkout/reset or downloads software."""
import argparse, hashlib, json, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent.parent
BASELINES = [json.loads(path.read_text()) for path in [HERE/'baseline.json', *sorted((HERE/'baselines').glob('*.json'))]]


def run(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def hashes_match(root, expected):
    failures = []
    for name, digest in expected.items():
        file = root/name
        # Symlinks are not ordinary baseline files, even if the target hashes match.
        actual = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() and not file.is_symlink() else None
        if file.is_symlink() or actual != digest: failures.append(name)
    return failures


def select_baseline(head, version=None):
    matches = [baseline for baseline in BASELINES if baseline['commit'] == head and (version is None or baseline['tag'] == version)]
    if len(matches) != 1:
        supported = ', '.join(f"{baseline['tag']} ({baseline['commit']})" for baseline in BASELINES)
        raise RuntimeError(f'Unsupported Dify commit/version combination. Supported exact baselines: {supported}')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dify', type=pathlib.Path, help='Dify Git checkout root')
    parser.add_argument('--version', choices=[baseline['tag'] for baseline in BASELINES], help='optional explicit version; must also match HEAD and tag')
    parser.add_argument('--check', action='store_true', help='verify only; change no files')
    parser.add_argument('--reverse', action='store_true', help='remove exactly this patch; fail if files changed afterward')
    args = parser.parse_args(); root = args.dify.resolve()
    if run(root, 'rev-parse', '--show-toplevel') != str(root):
        raise RuntimeError('Pass the exact Git repository root, not a subdirectory')
    baseline = select_baseline(run(root, 'rev-parse', 'HEAD'), args.version)
    if run(root, 'rev-parse', f"refs/tags/{baseline['tag']}^{{commit}}") != baseline['commit']:
        raise RuntimeError('The required tag is absent or points to a different commit')
    expected = baseline['after'] if args.reverse else baseline['before']
    if not args.reverse and not hashes_match(root, baseline['after']):
        print(f"This exact {baseline['tag']} adapter is already applied; no changes made."); return
    failures = hashes_match(root, expected)
    if failures:
        raise RuntimeError('Refusing modified/unexpected files:\n'+'\n'.join(failures))
    patch = HERE/f"patches/dify-{baseline['tag']}-dmn-editor.patch"
    direction = ['--reverse'] if args.reverse else []
    run(root, 'apply', '--check', *direction, str(patch))
    if args.check:
        print(f"Verified {baseline['tag']} ({baseline['commit']}); patch {'removal' if args.reverse else 'application'} can proceed.")
        return
    run(root, 'apply', *direction, str(patch))
    if hashes_match(root, baseline['before'] if args.reverse else baseline['after']):
        raise RuntimeError('Post-application hash verification failed; inspect the Git diff')
    print('Patch removed.' if args.reverse else f"{baseline['tag']} patch applied and every output hash verified. Review git diff, regenerate the correct pnpm lockfile, then build Dify web.")


if __name__ == '__main__':
    try: main()
    except (OSError, RuntimeError) as error:
        print(f'ERROR: {error}', file=sys.stderr); sys.exit(1)
