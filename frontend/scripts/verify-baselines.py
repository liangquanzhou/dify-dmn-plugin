#!/usr/bin/env python3
"""Exercise installer against clean official Git checkouts; always remove this adapter afterward."""
import argparse, hashlib, json, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent.parent
INSTALLER = HERE/'scripts/apply-patch.py'


def invoke(root, *args, ok=True):
    process = subprocess.run([sys.executable, str(INSTALLER), str(root), *args], capture_output=True, text=True)
    if (process.returncode == 0) != ok:
        raise AssertionError(process.stdout + process.stderr)
    return process.stdout + process.stderr


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def verify(root):
    version = json.loads((root/'web/package.json').read_text())['version']
    path = HERE/'baseline.json' if version == '1.17.1' else HERE/f'baselines/dify-{version}.json'
    baseline = json.loads(path.read_text())
    assert not git(root, 'status', '--porcelain'), 'Verification needs a clean disposable checkout'
    assert git(root, 'rev-parse', 'HEAD') == baseline['commit']
    panel = root/'web/app/components/workflow/nodes/tool/panel.tsx'
    original = panel.read_bytes()
    overlay = root/'web/app/components/workflow/nodes/tool/components/dmn-editor/contract.ts'
    applied = False
    try:
        invoke(root, '--check', '--version', version)
        assert not git(root, 'status', '--porcelain'), 'Dry run changed files'
        wrong = '1.17.1' if version == '1.11.1' else '1.11.1'
        assert 'Unsupported Dify commit/version' in invoke(root, '--check', '--version', wrong, ok=False)
        panel.write_bytes(original+b'\n// local customization\n')
        assert 'Refusing modified' in invoke(root, '--check', ok=False)
        panel.write_bytes(original)
        overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_text('// unexpected pre-existing adapter\n')
        assert 'Refusing modified' in invoke(root, '--check', ok=False)
        overlay.unlink()
        # An absent pinned tag must fail even though HEAD is exact.
        tag = f'refs/tags/{version}'
        tag_object = git(root, 'rev-parse', tag)
        git(root, 'update-ref', '-d', tag)
        try:
            invoke(root, '--check', ok=False)
        finally:
            git(root, 'update-ref', tag, tag_object)
        invoke(root)
        applied = True
        for name, digest in baseline['after'].items():
            assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
        assert 'already applied' in invoke(root)
        after = panel.read_bytes()
        panel.write_bytes(after+b'\n// do not discard edits\n')
        assert 'Refusing modified' in invoke(root, '--reverse', '--check', ok=False)
        assert 'Refusing modified' in invoke(root, '--check', ok=False)
        panel.write_bytes(after)
        invoke(root, '--reverse', '--check')
        invoke(root, '--reverse')
        applied = False
        assert not git(root, 'status', '--porcelain'), 'Reverse did not restore clean checkout'
        print(f'PASS {version}: clean dry-run, wrong-version/tag/modified/pre-existing rejection, apply hashes, idempotence, modified-after rejection, reverse dry-run, reverse and clean tree')
    finally:
        if applied:
            result = subprocess.run([sys.executable, str(INSTALLER), str(root), '--reverse'], capture_output=True, text=True)
            if result.returncode:
                print('Cleanup could not reverse modified files; inspect '+str(root), file=sys.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkouts', nargs='+', type=pathlib.Path)
    args = parser.parse_args()
    for root in args.checkouts:
        verify(root.resolve())
