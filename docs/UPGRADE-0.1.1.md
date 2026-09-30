# v0.1.1 compatibility update

This release targets Dify 1.11.1 while preserving the separately gated Dify 1.17.1 frontend patch. It does not change the KIE engine or decision-result semantics.

## Why v0.1.0 was rejected

The v0.1.0 package declared `minimum_dify_version: 1.17.1`, matching its original frontend baseline. Dify 1.11.1 correctly rejected that requirement before installation. This release checks the actual older Tool contracts/runtime protocol and adds a genuinely version-specific frontend adapter; it does not disable Dify's compatibility or signature checks.

## Install the corrected Tool

1. Open Plugins → Install Plugin → From GitHub.
2. Enter `https://github.com/liangquanzhou/dify-dmn-plugin`.
3. Refresh the release list if needed and choose **v0.1.1**, not v0.1.0.
4. Select the `liangquanzhou-dmn_decision-0.1.1-unsigned.difypkg` asset and review permissions.
5. If your installation enforces signatures or Marketplace-only policy, ask the administrator for the approved signing/installation process. A GitHub release does not waive those controls.
6. Configure the private engine URL and bearer token. The separately deployed engine is still required; installing the plugin does not create it.

If v0.1.0 never installed successfully, there is no installed version to remove. If it is installed on a newer Dify, retain its configuration/backup and use the normal upgrade workflow; the author/provider/tool IDs have not changed.

## Add the editor on Dify 1.11.1

Use the exact 1.11.1 frontend adapter documented in `frontend/README.md`; do not apply the 1.17.1 patch. The 1.11.1 source has different hook paths and translation APIs. Operators must build/deploy the customized Web application and verify real browser behavior and workflow persistence in staging.

## Still required

The package remains unsigned, requires Python 3.12 and a reachable private KIE service, and has not been exercised against a company's running Dify stack. Local protocol/schema/component tests do not replace staging installation, credential, workflow-save/publish/run, or DSL import/export acceptance.
