# Dify 1.17.1 DMN Tool-panel adapter

This is a **real, version-gated source patch for Dify's existing Tool panel**. It is not a new workflow node type, and it is not installed by the `.difypkg` alone. Install the backend plugin, apply this adapter to self-hosted Dify, and rebuild the web application.

## Exact baseline

- Official release/tag: [Dify 1.17.1](https://github.com/langgenius/dify/releases/tag/1.17.1)
- Commit: `8387590ace4a094de812b7847fc6a4c3a27cd52b`
- Dify tool integration: `web/app/components/workflow/nodes/tool/panel.tsx`
- Existing persistence owner, **unchanged**: `hooks/use-config.ts` → `setToolSettingValue` → `useNodeCrud` → Dify's existing graph/draft sync
- New production dependency: `dmn-js` **17.12.2**, exact version
- Official baseline requires Node **24.20.0+ within v24** and **pnpm 12.3.4** (see Dify's root `package.json`)

The adapter activates only for `provider_type=builtin`, `provider_id=liangquanzhou/dmn_decision/dmn`, `tool_name=evaluate`, and matching `plugin_id=liangquanzhou/dmn_decision` when that optional DSL field is present. The canonical provider ID already includes the plugin identity. A conflicting plugin ID is rejected. Unrelated Tool nodes retain their original form.

## Apply to a clean checkout

Do this in a development checkout, review the diff, and stage/test the custom web build before production deployment.

```bash
git clone --branch 1.17.1 --depth 1 https://github.com/langgenius/dify.git dify-1.17.1
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1 --check
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1
cd /path/to/dify-1.17.1
# Use the Node and pnpm versions declared by this Dify checkout.
pnpm install --no-frozen-lockfile
# Review and commit the resulting pnpm-lock.yaml together with the adapter changes.
pnpm exec vp run -w check
pnpm --filter dify-web type-check
pnpm --filter dify-web build
```

`pnpm-lock.yaml` is intentionally not rewritten by the source installer. The web manifest pins dmn-js exactly; the installation step resolves its transitive packages using the deployment's Dify workspace and creates the deployment lockfile. The standalone verification harness has its own `package-lock.json`; do not copy that npm lock into Dify.

Then build and deploy the customized Dify **web** image using your existing self-hosted deployment process. This package does not deploy anything or modify a running company Dify instance.

The installer checks the exact HEAD commit, the exact `1.17.1` tag target, and SHA-256 of every affected baseline file. It refuses other versions, conflicting local changes, partially applied adapters, and unexpected pre-existing adapter files. It runs `git apply --check` before changing files and verifies all output hashes. Repeating the same successful apply is a no-op. No checkout/reset, network request, package installation, or database migration is performed by the installer.

Removal, before editing the adapter files:

```bash
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1 --reverse --check
python3 /path/to/dify-dmn-plugin/frontend/scripts/apply-patch.py /path/to/dify-1.17.1 --reverse
# Regenerate/review pnpm-lock.yaml again after removing the dependency.
```

If you commit the patch, HEAD no longer equals the pinned baseline; use your normal Git revert/review process instead of this strict installer. Never force this patch onto another Dify release; port and retest it.

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
npm run dev
# Optional real-browser suite, on a machine where Chromium can run:
npx playwright install chromium
npm run test:browser
# Or use an already installed Chromium explicitly:
CHROMIUM_PATH=/path/to/chromium npm run test:browser
```

### Checked in this environment

- **PASS:** focused TypeScript check, including the adapter against an isolated i18n type boundary
- **PASS:** production Vite build of the real editor harness
- **PASS:** 11 Node/DOM tests, including real dmn-js loading, XML import/export, explicit Save, malformed XML retention, native-binding/configuration JSON preservation, read-only behavior, workflow-scoped dirty reopen/reset, and conflicting external XML
- **PASS:** patch dry-run, apply, every post-apply hash, repeat/idempotent apply, reverse dry-run, reverse apply, clean working tree afterward, modified-file rejection, and wrong-commit rejection on an actual checkout of the official commit
- **BLOCKED, not passed:** six real Chromium browser scenarios. Chromium in this runtime cannot create its process socket (`socket() failed: Operation not permitted`), including after an approved execution retry. A separate browser surface also rejected the local test URL with `ERR_BLOCKED_BY_CLIENT`. No browser screenshot or visual-layout certification is claimed
- **NOT RUN:** complete Dify workspace install/typecheck/lint/Next build, a deployed Dify end-to-end test, server-side draft persistence, and company-network integration

The DOM simulator proves actual dmn-js/component behavior but cannot certify layout, fullscreen, native download/file chooser behavior, browser focus, or visible watermark geometry. Those checks and a staging Dify run remain required before production. The editor's canvas is horizontally scrollable for narrow Tool panels. Fullscreen gives the table more room.

## Files and licensing

- `overlay/`: production editor, Dify adapter, identity/config contract, scoped draft storage, vendor types, styles
- `patches/dify-1.17.1-dmn-editor.patch`: installable source patch, including all supported Dify locale entries
- `baseline.json`: pinned version and before/after file hashes
- `scripts/apply-patch.py`: guarded installer
- `scripts/generate-patch.py`, `scripts/locales.json`: maintainer regeneration inputs; baseline source lives outside this deliverable
- `harness/`, `tests/`, `playwright.config.mjs`: focused verification sources

Dmn-js uses the bpmn.io license; `THIRD_PARTY_NOTICES.txt` preserves its terms. Its watermark source and all relevant CSS are kept intact, with no hiding or overlay rule. Preserve and visually verify the visible bpmn.io watermark in your final deployment. Dify itself retains its upstream license and trademark requirements.
