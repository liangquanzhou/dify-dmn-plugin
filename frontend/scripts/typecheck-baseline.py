#!/usr/bin/env python3
"""Check the installed overlay against official baseline translation resources and matching i18n APIs."""
import argparse, json, pathlib, shutil, subprocess
HERE = pathlib.Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('dify', type=pathlib.Path, help='Official checkout with this adapter applied')
args = parser.parse_args()
root = args.dify.resolve()
version = json.loads((root/'web/package.json').read_text())['version']
legacy = version == '1.11.1'
assert version in ('1.11.1', '1.17.1')
manifest = json.loads((HERE/'baselines/dify-1.11.1.json' if legacy else HERE/'baseline.json').read_text())
# Verify this is the exact installed candidate before checking types.
import importlib.util
spec = importlib.util.spec_from_file_location('installer', HERE/'scripts/apply-patch.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
assert not installer.hashes_match(root, manifest['after']), 'Apply the exact version-specific patch first'
target = HERE/'test-results'/f'types-{version}'
if target.exists(): shutil.rmtree(target)
(target/'types').mkdir(parents=True)
shutil.copytree(root/'web/i18n/en-US', target/'i18n/en-US')
shutil.copytree(root/'web/app/components/workflow/nodes/tool/components/dmn-editor', target/'overlay')
if legacy:
    shutil.copy2(root/'web/types/i18n.d.ts', target/'types/i18n.d.ts')
else:
    # Restrict the exact official JSON resource types to the two namespaces used here.
    (target/'types/i18n.d.ts').write_text("import 'i18next'\ndeclare module 'i18next' { interface CustomTypeOptions { defaultNS: 'common'; enableSelector: 'optimize'; keySeparator: false; resources: {common: typeof import('../i18n/en-US/common.json'); workflow: typeof import('../i18n/en-US/workflow.json')} } }\n")
deps = HERE/'compatibility/1.11.1/node_modules' if legacy else HERE/'node_modules'
paths = {
    'react': [str(deps/'@types/react/index.d.ts')],
    'react/*': [str(deps/'@types/react/*')],
    'react-dom/*': [str(deps/'@types/react-dom/*')],
    'i18next': [str(deps/'i18next/index.d.ts')],
    'react-i18next': [str(deps/'react-i18next/index.d.ts')],
}
config = {'compilerOptions': {'target':'ES2022','lib':['ES2022','DOM','DOM.Iterable'],'module':'ESNext','moduleResolution':'Bundler','jsx':'react-jsx','strict':True,'skipLibCheck':True,'noEmit':True,'resolveJsonModule':True,'allowSyntheticDefaultImports':True,'baseUrl':str(target),'paths':paths,'typeRoots':[str(deps/'@types')]},'include':['overlay/**/*.ts','overlay/**/*.tsx','types/**/*.d.ts']}
(target/'tsconfig.json').write_text(json.dumps(config,indent=2))
command = [str(HERE/'node_modules/.bin/tsc'), '-p', str(target/'tsconfig.json')]
subprocess.run(command, check=True)
print(f'PASS {version}: actual installed editor/adapter with official en-US resource types and matching i18next/React types')
if legacy:
    # A negative control proves that the old selector-based shim does not accidentally pass.
    panel = target/'overlay/panel-adapter.tsx'
    correct = panel.read_text()
    panel.write_text((HERE/'overlay/panel-adapter.tsx').read_text())
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode != 0, 'Negative control failed: 1.17.1 shim unexpectedly passed 1.11.1 types'
        print('PASS negative control: 1.17.1 selector shim rejected by 1.11.1 translation types')
    finally:
        panel.write_text(correct)
