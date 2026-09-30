# Dify 1.11.1 / 1.17.1 DMN Tool-panel adapters

This is a **real, version-gated source patch for Dify's existing Tool panel**. It is not a new workflow node type, and it is not installed by the `.difypkg` alone. Install the backend plugin, apply this adapter to self-hosted Dify, and rebuild the web application.

## Exact baselines

Two separate patches are supplied. They are not interchangeable:

- **Dify 1.11.1:** [official release](https://github.com/langgenius/dify/releases/tag/1.11.1), commit `2058186f22b4e4d4e155f380c130f4e8f21622fa`; Node **>=22.11.0**, **pnpm 10.25.0**; run installation/build from `web/`
- **Dify 1.17.1:** [official release](https://github.com/langgenius/dify/releases/tag/1.17.1), commit `8387590ace4a094de812b7847fc6a4c3a27cd52b`; Node **24.20.0+ within v24**, **pnpm 12.3.4**; root workspace commands
- Integration: `web/app/components/workflow/nodes/tool/panel.tsx`
- Existing persistence owner is unchanged: `use-config.ts` (1.11.1) or `hooks/use-config.ts` (1.17.1) → `setToolSettingValue` → `useNodeCrud` → Dify's existing graph/draft sync
- Production dependency: `dmn-js` **17.12.2**, exact version

The 1.11.1 adapter uses its real string-key i18n API and nested `workflow.ts` resources. The 1.17.1 adapter uses selector-based i18n and flat `workflow.json` resources. Their panel import paths also differ. The core editor, native configuration shape, node identity and session-scoped draft protections are shared. The original 1.17.1 patch and baseline hashes are byte-for-byte preserved. See [the compatibility evidence](COMPATIBILITY.md).

The adapter activates only for `provider_type=builtin`, `provider_id=liangquanzhou/dmn_decision/dmn`, `tool_name=evaluate`, and matching `plugin_id=liangquanzhou/dmn_decision` when that optional DSL field is present. The canonical provider ID already includes the plugin identity. A conflicting plugin ID is rejected. Unrelated Tool nodes retain their original form.

## Apply to a clean checkout

Do this in a development checkout, review the diff, and stage/test the custom web build before production deployment.

### Dify 1.11.1

```bash
git clone --branch 1.11.1 --depth 1 https://github.com/langgenius/dify.git dify-1.11.1
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.11.1 --version 1.11.1 --check
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.11.1 --version 1.11.1
cd /path/to/dify-1.11.1/web
# Use pnpm 10.25.0 and Node >=22.11.0 as declared in web/package.json.
pnpm install --no-frozen-lockfile
# Review and commit web/pnpm-lock.yaml with the adapter changes.
pnpm lint
pnpm type-check:tsgo
pnpm build
```

### Dify 1.17.1

```bash
git clone --branch 1.17.1 --depth 1 https://github.com/langgenius/dify.git dify-1.17.1
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1 --version 1.17.1 --check
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1 --version 1.17.1
cd /path/to/dify-1.17.1
# Use the Node and pnpm versions declared by this Dify checkout.
pnpm install --no-frozen-lockfile
# Review and commit root pnpm-lock.yaml together with the adapter changes.
pnpm exec vp run -w check
pnpm --filter dify-web type-check
pnpm --filter dify-web build
```

`pnpm-lock.yaml` is intentionally not rewritten by the source installer. The web manifest pins dmn-js exactly; the installation step resolves its transitive packages using the deployment's Dify workspace and creates the deployment lockfile. The standalone verification harness has its own `package-lock.json`; do not copy that npm lock into Dify.

Then build and deploy the customized Dify **web** image using your existing self-hosted deployment process. This package does not deploy anything or modify a running company Dify instance.

The installer auto-selects by exact HEAD commit, checks the matching official tag target, and SHA-256 of every affected baseline file. An explicit `--version` must also match HEAD and cannot override the guard. It refuses other versions, cross-version adapters, conflicting local changes, partially applied adapters, and unexpected pre-existing adapter files. It runs `git apply --check` before changing files and verifies all output hashes. Repeating the same successful apply is a no-op. No checkout/reset, network request, package installation, or database migration is performed by the installer.

Removal, before editing the adapter files (use the matching checkout/version):

```bash
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.11.1 --version 1.11.1 --reverse --check
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.11.1 --version 1.11.1 --reverse
# Regenerate/review pnpm-lock.yaml again after removing the dependency.
```

If you commit the patch, HEAD no longer equals the pinned baseline; use your normal Git revert/review process instead of this strict installer. Never force either patch onto a different Dify release; port and retest it.

## User flow and persistence

1. Add the plugin's **Evaluate** Tool node. The DMN editor appears inside its normal Tool panel, above the unchanged native input fields.
2. Enter `decision_id=eligibility`; bind `facts_json` through Dify's native variable selector, e.g. a JSON string containing `{"age":25,"risk_score":30}`.
3. Import a `.dmn` file or edit the starter model, which matches `../examples/eligibility.dmn`. Use the view selector to switch between available DMN views and the fullscreen button for wide tables.
4. Click **Save** in the DMN editor, then wait for Dify's normal workflow draft synchronization before running or publishing.

Save writes only `tool_configurations.model_xml` as `{ "type": "constant", "value": "<definitions…>" }`, preserving other settings. `decision_id` stays in its existing native settings form. `tool_parameters.facts_json` and its native variable binding are untouched. Legacy plain-string XML is accepted for reading; explicit Save converts it to the current static-value shape.

Opening a model does not rewrite its stored XML. Import and editing produce an unsaved draft; only explicit Save changes the workflow configuration. Export downloads the current valid draft without saving it to Dify. Reset returns to the current stored XML and asks before discarding dirty work. Unsaved drafts survive switching panels/nodes within the same workflow-store session in memory; they are **not durable across a full browser refresh or closing the app**. A before-unload warning is installed while the mounted editor is dirty. Save or export before leaving the workflow. Saved XML reopens from Dify's graph. JSON serialization preservation is tested; server-side draft persistence and actual DSL export/import must be verified in staging.

Read-only nodes use `NavigatedViewer`, with import/save/reset disabled. If another workflow edit changes the stored XML while this editor has a draft, Save is blocked: export the draft and Reset to reconcile instead of overwriting the newer XML.

Imports are limited to **512 KiB**, reject DTD/entity declarations, and use a disposable viewer before replacing the current canvas. Parser/import warnings fail closed. Errors remain visible, rejected XML can be inspected/copied, and stored XML is never silently replaced by a sample. The editor is not a FEEL evaluator: backend validation determines which DMN constructs and expressions the execution engine supports.

## Verification harness

The harness uses the **same production editor component** and simulates only the Dify graph callback. It is explicitly labelled as a harness. It does not impersonate a company Dify deployment or prove the full Dify runtime.

```bash
cd /path/to/dify-dmn-plugin/frontend
npm ci
npm run typecheck
npm test
npm run build
# Exact 1.11.1 React/i18n compatibility suite:
npm ci --prefix compatibility/1.11.1
npm run test:compatibility
npm test --prefix compatibility/1.11.1
npm run dev
# Optional real-browser suite, on a machine where Chromium can run:
npx playwright install chromium
npm run test:browser
# Or use an already installed Chromium explicitly:
CHROMIUM_PATH=/path/to/chromium npm run test:browser
```

### Checked in this environment

- **PASS:** the original 11 contract/real-dmn-js DOM tests, all 11 replayed on exact 1.11.1 React 19.2.3, and production Vite harness build
- **PASS:** version-specific adapter TypeScript checks using official translation resources and matching React/i18n types for both 1.11.1 and 1.17.1; a negative control rejects the 1.17.1 selector shim on the 1.11.1 type boundary
- **PASS:** three 1.11.1 adapter runtime checks with React 19.2.3, i18next 23.16.8 and react-i18next 15.7.4, including Chinese labels, native writeback preservation and read-only/error forwarding
- **PASS:** both official Git baselines pass dry-run, exact output hashes, apply, repeat/idempotence, reverse dry-run, reverse and clean-tree checks; wrong-version, missing-tag, modified-source, unexpected overlay and modified-after-apply inputs are rejected
- **BLOCKED in the original verification, not passed:** real Chromium scenarios; this runtime could not create a process socket, and the separate browser surface rejected the local URL. This adaptation does not claim a new browser visual test
- **NOT RUN:** complete Dify install/lint/typecheck/Next build, deployed Dify end-to-end behavior, server-side draft persistence, actual Dify DSL export/import and company-network integration

Reproduce installer proof on clean **disposable** official Git checkouts:

```bash
python3 scripts/verify-baselines.py /path/to/dify-1.11.1 /path/to/dify-1.17.1
# This script temporarily applies/removes the adapter and tests local tag guards.
# For each version, apply its patch then check the actual installed source boundary:
python3 scripts/apply-patch.py /path/to/dify-1.11.1 --version 1.11.1
python3 scripts/typecheck-baseline.py /path/to/dify-1.11.1
python3 scripts/apply-patch.py /path/to/dify-1.11.1 --reverse
# Repeat those three commands for the 1.17.1 checkout/version.
```

The DOM simulator proves actual dmn-js/component behavior but cannot certify layout, fullscreen, native download/file chooser behavior, browser focus, or visible watermark geometry. Those checks and a staging Dify run remain required before production. The editor's canvas is horizontally scrollable for narrow Tool panels. Fullscreen gives the table more room.

## Files and licensing

- `overlay/`: shared production editor, 1.17.1 adapter, identity/config contract, scoped draft storage, vendor types, styles
- `overlays/1.11.1/panel-adapter.tsx`: replacement shim for 1.11.1 string-key i18n
- `patches/dify-1.11.1-dmn-editor.patch`, `patches/dify-1.17.1-dmn-editor.patch`: separate installable patches, including each baseline's supported locales
- `baseline.json`: unchanged 1.17.1 before/after hashes; `baselines/dify-1.11.1.json`: separate 1.11.1 hashes
- `scripts/apply-patch.py`: guarded installer
- `scripts/generate-patch.py --version VERSION`, `scripts/locales*.json`: maintainer regeneration inputs; baseline source lives outside this deliverable
- `compatibility/1.11.1/`: isolated exact-version React/i18n dependency lock and shared editor test replay
- `harness/`, `tests/`, `playwright.config.mjs`: focused verification sources

Dmn-js uses the bpmn.io license; `THIRD_PARTY_NOTICES.txt` preserves its terms. Its watermark source and all relevant CSS are kept intact, with no hiding or overlay rule. Preserve and visually verify the visible bpmn.io watermark in your final deployment. Dify itself retains its upstream license and trademark requirements.
