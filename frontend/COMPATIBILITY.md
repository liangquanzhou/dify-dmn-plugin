# Dify 1.11.1 frontend port: verified compatibility boundary

This is a source-level adapter candidate for self-hosted Dify, not certification of a running company deployment. Install the backend plugin and rebuild the customized Dify web image separately.

## Official evidence and decisions

The pinned 1.11.1 Git commit is `2058186f22b4e4d4e155f380c130f4e8f21622fa`, peeled from the official annotated release tag `1.11.1`. The tag object itself (`83ace173c78cdd10d86cfddb0ec632047fb0c144`) is not the checkout commit.

- [Tool panel](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/nodes/tool/panel.tsx) imports `./use-config`, receives `id` from `NodePanelProps` and uses the normal `ToolForm` callbacks. The patch inserts the DMN editor into this panel, hides only `model_xml` from native settings, and leaves other settings/input bindings unchanged
- [Configuration hook](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/nodes/tool/use-config.ts) exposes `readOnly`, `toolSettingValue` and `setToolSettingValue`; the callback still owns graph changes through `useNodeCrud`. This hook is not patched
- [Tool types](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/nodes/tool/types.ts) preserve `tool_configurations`, dynamic `tool_parameters`, canonical provider identity and optional `plugin_id`. [Form schema conversion](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/tools/utils/to-form-schema.ts) creates constant form values with `{ type: 'constant', value: ... }`. The shared XML contract writes that shape, not a raw string
- [Workflow store](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/store/workflow/index.ts) exports `useWorkflowStore`, providing the object identity used to isolate in-memory unsaved drafts by workflow and node
- [i18n setup](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/i18n-config/i18next-config.ts) puts nested TypeScript resources under one `translation` namespace. Therefore this version calls string keys such as `workflow.nodes.tool.dmn.help`; the 1.17.1 selector API must not be transplanted
- [1.11.1 workflow locale](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/i18n/en-US/workflow.ts) stores nested `nodes.tool` values. The new patch adds `dmn` keys to all 21 shipped locale files, without converting them into JSON. Several common labels present in 1.17.1 do not exist in 1.11.1, so this shim owns localized export/import/fullscreen/loading/error keys too
- [Web package](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/package.json) and [lockfile](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/pnpm-lock.yaml) establish React 19.2.3, i18next 23.16.8, react-i18next 15.7.4, pnpm 10.25.0 and Node >=22.11.0. Commands run from `web/`, unlike the 1.17.1 root workspace

## Adapter boundary

The following production files are shared byte-for-byte with the existing 1.17.1 implementation: editor, XML/identity contract, draft store, DMN vendor/type definitions and CSS. The 1.11.1 overlay replaces only `panel-adapter.tsx`. The installer selects the matching complete patch from exact HEAD plus tag; `--version` adds an explicit check and never bypasses it.

The new patch modifies 30 files: seven editor/adapter files, one panel, 21 locale files and the web manifest. The retained 1.17.1 patch modifies 33 files and its old patch/manifest are byte-for-byte unchanged.

Read-only viewing, explicit Save, dirty/import discard confirmation, unsaved per-workflow/node memory, invalid XML retention, and stale-XML conflict blocking are implemented in the same shared production editor. The 1.11.1 shim forwards the corresponding props and callback without changing their semantics.

## Tests and remaining deployment gates

Both official clean Git checkouts passed the guarded install lifecycle and rejection suite. Both installed overlays passed isolated TypeScript checks against the actual official translation resources with matching React/i18n type libraries. Replacing the 1.11.1 shim with the newer selector-based shim fails that check, as expected.

Three additional 1.11.1 shim runtime tests passed using exact 1.11.1 React/i18n versions. The shared 11-test editor contract/DOM suite passed both the original harness and an exact React 19.2.3 replay (22 checks total), and the Vite harness build also passed. See README for reproducible commands and the exact-version editor replay.

These are focused integration-boundary tests. They do not replace a complete Dify dependency install, lint/typecheck/Next build, real-browser visual tests or deployed company-Dify acceptance. Before production, regenerate/review the correct Dify lockfile, build the custom web image, and verify plugin selection, XML Save/reopen, native facts binding, workflow draft persistence, DSL export/import, read-only views, interrupted/dirty edits, conflict handling and visible bpmn.io watermark in staging.
