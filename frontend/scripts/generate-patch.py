#!/usr/bin/env python3
"""Generate a version-specific patch from the untouched official Dify source."""
import argparse, difflib, hashlib, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
COMMITS = {
    '1.11.1': '2058186f22b4e4d4e155f380c130f4e8f21622fa',
    '1.17.1': '8387590ace4a094de812b7847fc6a4c3a27cd52b',
}


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'Expected exactly one baseline marker: {old!r}')
    return source.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dify', type=pathlib.Path)
    parser.add_argument('--version', choices=COMMITS, default='1.17.1')
    args = parser.parse_args()
    root = args.dify.resolve()
    version = args.version
    legacy = version == '1.11.1'
    changes = {}
    panel = 'web/app/components/workflow/nodes/tool/panel.tsx'
    s = (root/panel).read_text()
    s = replace_once(s, "import { useStore } from '@/app/components/workflow/store'", "import { useStore, useWorkflowStore } from '@/app/components/workflow/store'")
    config_import = "import useConfig from './use-config'" if legacy else "import useConfig from './hooks/use-config'"
    s = replace_once(s, config_import, config_import + "\nimport { isDmnTool } from './components/dmn-editor/contract'\nimport DmnPanelAdapter from './components/dmn-editor/panel-adapter'")
    s = replace_once(s, '  const [collapsed, setCollapsed]', '''  const draftScope = useWorkflowStore()
  const showDmnEditor = isDmnTool(inputs)
  const visibleToolSettingSchema = showDmnEditor
    ? toolSettingSchema.filter(item => item.variable !== 'model_xml')
    : toolSettingSchema

  const [collapsed, setCollapsed]''')
    if s.count('toolSettingSchema.length') != 2 or s.count('schema={toolSettingSchema as any}') != 1:
        raise ValueError('Unexpected Tool settings render structure')
    s = s.replace('toolSettingSchema.length', 'visibleToolSettingSchema.length').replace('schema={toolSettingSchema as any}', 'schema={visibleToolSettingSchema as any}')
    marker = "        <div className='relative'>" if legacy else '        <div className="relative">'
    s = replace_once(s, marker, marker + '''
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
    pkg = json.loads((root/package).read_text())
    if pkg['version'] != version:
        raise ValueError(f'Expected package version {version}, got {pkg["version"]}')
    pkg['dependencies']['dmn-js'] = '17.12.2'
    pkg['dependencies'] = dict(sorted(pkg['dependencies'].items()))
    changes[package] = json.dumps(pkg, ensure_ascii=False, indent=2)+'\n'
    keys = ['saved', 'dirty', 'help', 'replaceConfirm', 'conflict']
    locales = json.loads((HERE/'scripts/locales.json').read_text())
    if legacy:
        extra = json.loads((HERE/'scripts/locales-1.11.1.json').read_text())
        locale_paths = sorted((root/'web/i18n').glob('*/workflow.ts'))
        if {path.parent.name for path in locale_paths} != set(extra):
            raise ValueError('Unexpected 1.11.1 locale set')
        for path in locale_paths:
            values = dict(zip(keys, locales[path.parent.name])) | extra[path.parent.name]
            # Keep the existing nested TypeScript resource structure and formatting.
            block = '      dmn: {\n' + ''.join('        '+key+': '+json.dumps(value, ensure_ascii=False)+',\n' for key, value in values.items()) + '      },\n'
            changes[str(path.relative_to(root))] = replace_once(path.read_text(), '    tool: {\n', '    tool: {\n'+block)
    else:
        for locale, values in locales.items():
            path = f'web/i18n/{locale}/workflow.json'
            data = json.loads((root/path).read_text())
            for key, value in zip(keys, values): data[f'nodes.tool.dmn.{key}'] = value
            changes[path] = json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2)+'\n'
    overlay = {path.name: path for path in (HERE/'overlay').iterdir() if path.is_file()}
    specific = HERE/'overlays'/version
    if specific.exists():
        overlay.update({path.name: path for path in specific.iterdir() if path.is_file()})
    for name, path in overlay.items():
        changes['web/app/components/workflow/nodes/tool/components/dmn-editor/'+name] = path.read_text()
    manifest = {'tag':version,'commit':COMMITS[version],'dmnJs':'17.12.2','before':{},'after':{}}
    patch = []
    for path, modified in sorted(changes.items()):
        src=root/path
        original=src.read_text() if src.exists() else ''
        manifest['before'][path] = hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else None
        manifest['after'][path] = hashlib.sha256(modified.encode()).hexdigest()
        patch.append(f'diff --git a/{path} b/{path}\n')
        if not src.exists(): patch.append('new file mode 100644\n')
        patch.extend(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='a/'+path if src.exists() else '/dev/null',tofile='b/'+path))
    (HERE/f'patches/dify-{version}-dmn-editor.patch').write_text(''.join(patch))
    baseline_path = HERE/'baselines/dify-1.11.1.json' if legacy else HERE/'baseline.json'
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Generated {version}: {len(changes)}-file patch')


if __name__ == '__main__':
    main()
