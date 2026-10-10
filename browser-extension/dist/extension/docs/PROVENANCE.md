# Source provenance

- This extension was created in a separate directory. No Dify server source or frozen plugin source was edited.
- `src/model.ts` is derived from the independently authored MIT-licensed matrix model in `dify-dmn-plugin` integration commit `acf92a24ca45d737e90545e91d7e2d073ac35e83`, version 0.7.0.
- The original model SHA-256 is `d127c9da4548c16288d1bf51bad2a2d521bd4c944df269a6cb75e5d8505d5238`.
- The derived model tightens `constraint_set.mode` validation to accept only literal `satisfied` or `violated` strings, rejecting coercible arrays/objects before rendering. The frozen original was not changed.
- The extension binding, DOM renderer, activation code, styles and tests are new code. No Dify frontend source is bundled into the extension.
- The MIT license accompanying the original model is included as `LICENSE`. npm development dependencies retain their own licenses and are not bundled as runtime libraries.
- The dependency lock was narrowed from the existing integration lock, preserving recorded package versions/integrities for esbuild, jsdom, TypeScript and their transitive dependencies. Cloud checks used the pre-provisioned same-version dependencies. A new online `npm ci` was not part of this offline build check.

## Final documentation-only packaging (2026-10-10)
Real MV3 and stock Dify acceptance is complete; see VALIDATION.md. Runtime and source remain byte-identical to accepted candidate. No server frontend patches.
