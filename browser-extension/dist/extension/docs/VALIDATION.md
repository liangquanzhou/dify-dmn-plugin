# Validation — 2026-10-10 final

Real MV3 + official unmodified Dify 1.11.1 ARM64: **30/30 passed**. Chrome for Testing 155.0.8059.39, isolated macOS profile, normal sandboxed launch, synthetic data only. DMN plugin 0.7.0 installed successfully. Official browser toolbar simulation Extensions.triggerAction exercised actual installed extension, service worker, activeTab and chrome.scripting MAIN/ISOLATED worlds. No physical mouse/OS shortcut verification is claimed.

Passed: A/B switching, native JSON editing, invalid/empty/unresolved-variable clearing, non-DMN clearing, repeated enable, close/reopen, close between content and reader injection, SPA exit/back with explicit reactivation, refresh, browser restart, UI disable/re-enable, tab permission denial and action grant. Preview-only tool configuration unchanged and database workflow/node counts zero. Then four synthetic plugin regression groups ran with extension off/on: first match, fallback, invalid JSON failure, UNIQUE conflict. All outputs/statuses equal; final counts 0 workflow runs and 8 intentional node runs. Original tool configuration restored.

Observed 491 browser-context requests all reached loopback Dify; worker observation window had zero requests. These are bounded observation windows, not universal network proof. All candidate runtime bytes and stock frontend asset hashes remained unchanged. BUILD_ID KF3EEtM5H7HqbHKGBJF2q. Original evidence is retained privately. See docs/PUBLIC-ACCEPTANCE.md in the source distribution for the public acceptance summary.

Earlier cloud layer: 23 unit tests/typecheck plus 20 stock-page script checks; separately 37 real-MV3 synthetic-host checks. Historical SCRIPT-ONLY evidence is retained privately as history, not proof of extension installation. The previous cloud full-extension environment blocker was resolved by authorized Mac testing; no browser sandbox/system security bypass was used.

All test containers and the isolated browser were stopped; data retained. Company deployment, modified company frontend, future versions and physical toolbar mouse input are untested. React private __reactProps$ properties remain a compatibility risk.

Final ZIP packaging is documentation-only, without rebuilding. docs/RUNTIME-INTEGRITY.json proves byte equality against accepted candidate for manifest, background/content/reader scripts and CSS; source/test equality is recorded there too.
