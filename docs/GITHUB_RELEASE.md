# GitHub distribution checklist

Recommended repository name: `dify-dmn-plugin`. Initial release tag: `v0.1.0` (manifest version `0.1.0`).

## Required before publication

1. Confirm the actual GitHub account/organization and authorize public visibility.
2. Match the plugin `author` in `plugin/manifest.yaml`, `plugin/provider/dmn.yaml`, and `plugin/tools/evaluate.yaml` to the verified owner handle. This release is prepared for the verified owner `liangquanzhou`; every manifest and frontend identity uses that namespace.
3. If the owner changes, update the frontend's exact plugin/provider identity (`AUTHOR/dmn_decision`, `AUTHOR/dmn_decision/dmn`), its tests and docs; regenerate the Dify baseline patch and output hashes; rerun tests and the guarded installer checks; repackage the plugin. Do not merely rename the `.difypkg` filename.
4. Review source/dependencies and decide the company's signature policy. The supplied development package is unsigned and not Marketplace-reviewed. If signature enforcement is enabled, an administrator must sign with an approved key and configure its trusted public key without disabling verification.
5. Confirm the operator will deploy the included engine and configure `engine_url`/`api_token`. No engine is hosted or installed by GitHub.

## Release layout

- Push the clean source tree to the repository's `main` branch.
- Create tag `v0.1.0` against that exact source commit.
- Publish a non-draft release with the final `.difypkg` as an uploaded Release asset, plus `SHA256SUMS.txt`.
- A source ZIP or committed `.difypkg` alone is not a substitute for the uploaded release asset.
- Keep `release-assets/` out of the source commit; it is a local upload staging folder.
- Do not call an unsigned package signed or verified. If distributing both signed and unsigned assets, clearly identify which asset the administrator approved.

Suggested release notes:

> First integration-starter release: standard Dify Tool, private Apache KIE 10.2.0 engine source, and a Dify 1.17.1-specific dmn-js frontend patch. The `.difypkg` installs only the Python Tool. A separately deployed reachable engine is required; the visual editor requires a separate customized Web build. This asset is unsigned unless its name and verification metadata explicitly state otherwise. Read the README before installing. Company deployment/browser/persistence acceptance is still required.

## Installation and verification

Dify: Plugins → Install Plugin → From GitHub → repository URL → `v0.1.0` → `.difypkg` asset → review permissions → Install. Configure the provider's private `engine_url` and `api_token`. Test `examples/eligibility.dmn`, decision ID `eligibility`, facts JSON `{"age":25,"risk_score":30}`; expect matched / eligible true / rule_eligible.

Standard documented GitHub distribution uses a public repository. The pinned Dify 1.17.1 code downloads the asset from `https://github.com/OWNER/REPO/releases/download/TAG/ASSET` without a per-repository GitHub token. Do not promise private-repository installation unless the target deployment has an independently verified custom integration. Private source can instead use the approved local-file installation route.

GitHub distribution still goes through Dify installation-scope and signature checks. A workspace restricted to Marketplace-only plugins can reject this plugin even if a GitHub button is present elsewhere in the UI.

Official references:

- https://docs.dify.ai/en/develop-plugin/publishing/marketplace-listing/release-to-individual-github-repo
- https://docs.dify.ai/en/develop-plugin/publishing/standards/third-party-signature-verification
- https://github.com/langgenius/dify/blob/8387590ace4a094de812b7847fc6a4c3a27cd52b/api/core/plugin/plugin_service.py#L1086
