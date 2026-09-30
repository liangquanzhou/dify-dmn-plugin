# Dify DMN Decision Tool

A Dify Tool plugin backed by an included, privately deployed Apache KIE DMN engine, plus an optional Dify-specific dmn-js editor integration.

## Read before installing

**Installing the `.difypkg` from GitHub installs the Python Tool only. It does not install the engine or change the Dify frontend.**

1. An operator must deploy the included Java 21 / Apache KIE 10.2.0 service from `engine/` on a private network reachable by Dify's plugin-daemon.
2. Configure the Tool provider's `engine_url` (engine HTTP(S) origin) and `api_token` (the matching bearer token). Saving credentials checks `/health`.
3. You can then execute a standard `.dmn` XML snapshot and bind upstream JSON through `facts_json` using the standard Tool configuration.
4. To edit DMN visually inside the Tool panel, a developer must separately apply `frontend/` to an exact supported Dify baseline (1.11.1 or 1.17.1) and build/deploy a customized Dify Web image.

Without a reachable engine, this plugin cannot run a decision. No public/free hosted engine is provided. The standard plugin package alone cannot add the visual editor.

## Compatibility

Plugin v0.1.1 targets Dify 1.11.1 and keeps the standard Tool runtime. Its older-daemon compatibility checks are recorded in [the 1.11.1 report](docs/COMPATIBILITY-1.11.1.md). Version-specific frontend adapters keep the different panel hooks and translation APIs separate. Do not apply a patch for another Dify version.

## Install from GitHub

After an owner-matched release is published: Plugins → Install Plugin → From GitHub → paste this repository's URL → select `v0.1.1` and its `.difypkg` asset.

The package is **unsigned**. A corporate Dify installation enforcing signature verification will require administrator review/signing and a trusted public key. GitHub installation does not bypass signature or workspace installation policy. Do not disable verification to make this package install.

Use a public repository for Dify's documented GitHub-install flow. A private repository is not a supported assumption for the standard anonymous release-download flow; use your administrator-approved local package process when source must remain private.

## Documentation

- [中文安装与验收说明](README.zh-CN.md)
- [Engine deployment and security](docs/engine.md)
- [Version-gated frontend patch](frontend/README.md)
- [Verification record and limitations](docs/VALIDATION.md)
- [GitHub release checklist](docs/GITHUB_RELEASE.md)
- [Privacy](plugin/PRIVACY.md)

This is an integration starter, not a production-certified deployment. The tests include a real KIE service and real dmn-js DOM behavior; complete Dify deployment/browser/persistence validation and Docker image execution remain deployment responsibilities. FEEL arithmetic follows Decimal128/34-significant-digit semantics.
