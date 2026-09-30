#!/usr/bin/env python3
"""Maintainer utility; generate patch from the official extracted 1.17.1 archive."""
import difflib, hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
here = pathlib.Path(__file__).resolve().parent.parent
changes = {}
panel = 'web/app/components/workflow/nodes/tool/panel.tsx'
s = (root/panel).read_text()
s = s.replace("import { useStore } from '@/app/components/workflow/store'", "import { useStore, useWorkflowStore } from '@/app/components/workflow/store'")
s = s.replace("import useConfig from './hooks/use-config'", "import useConfig from './hooks/use-config'\nimport { isDmnTool } from './components/dmn-editor/contract'\nimport DmnPanelAdapter from './components/dmn-editor/panel-adapter'")
s = s.replace("  const [collapsed, setCollapsed]", "  const draftScope = useWorkflowStore()\n  const showDmnEditor = isDmnTool(inputs)\n  const visibleToolSettingSchema = showDmnEditor\n    ? toolSettingSchema.filter(item => item.variable !== 'model_xml')\n    : toolSettingSchema\n\n  const [collapsed, setCollapsed]")
s = s.replace('toolSettingSchema.length', 'visibleToolSettingSchema.length').replace('schema={toolSettingSchema as any}', 'schema={visibleToolSettingSchema as any}')
s = s.replace('        <div className="relative">', '''        <div className="relative">
          {showDmnEditor && (
            <DmnPanelAdapter
              nodeId={id}
              draftScope={draftScope}
              configuration={toolSettingValue}
              readOnly={readOnly}
              onChange={setToolSettingValue}
            />
          )}''')
changes[panel] = s
package = 'web/package.json'
pkg = json.loads((root/package).read_text()); pkg['dependencies']['dmn-js'] = '17.12.2'
pkg['dependencies'] = dict(sorted(pkg['dependencies'].items()))
changes[package] = json.dumps(pkg, ensure_ascii=False, indent=2)+'\n'
keys = ['saved', 'dirty', 'help', 'replaceConfirm', 'conflict']
locales = json.loads((here/'scripts/locales.json').read_text())
for locale, values in locales.items():
    path = f'web/i18n/{locale}/workflow.json'
    data = json.loads((root/path).read_text())
    for key, value in zip(keys, values): data[f'nodes.tool.dmn.{key}'] = value
    changes[path] = json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2)+'\n'
for path in (here/'overlay').glob('*'):
    if path.is_file(): changes['web/app/components/workflow/nodes/tool/components/dmn-editor/'+path.name] = path.read_text()
manifest = {'tag':'1.17.1','commit':'8387590ace4a094de812b7847fc6a4c3a27cd52b','dmnJs':'17.12.2','before':{},'after':{}}
patch = []
for path, modified in sorted(changes.items()):
    src=root/path
    original=src.read_text() if src.exists() else ''
    manifest['before'][path] = hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else None
    manifest['after'][path] = hashlib.sha256(modified.encode()).hexdigest()
    patch.append(f'diff --git a/{path} b/{path}\n')
    if not src.exists(): patch.append('new file mode 100644\n')
    patch.extend(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='a/'+path if src.exists() else '/dev/null',tofile='b/'+path))
(here/'patches/dify-1.17.1-dmn-editor.patch').write_text(''.join(patch))
(here/'baseline.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'Generated {len(changes)}-file patch')
