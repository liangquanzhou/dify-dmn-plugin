# Third-party notices

The original evaluator, Tool integration, tests and documentation in v0.2.0 are licensed under the root MIT license. They are independently implemented from an abstract condition protocol; no company source code or real business rules are included.

The plugin uses the official `dify-plugin==0.10.2` Python SDK and its dependencies, pinned in `plugin/requirements.txt`. Each dependency retains its own license. Review the dependency list and official projects as part of company supply-chain approval. The SDK itself uses Apache-2.0: https://github.com/langgenius/dify-plugin-sdks

Dify is a separate product with its own license: https://github.com/langgenius/dify/blob/1.11.1/LICENSE
The release does not include or relicense Dify. Compatibility tests import official Dify/daemon sources supplied separately; no upstream Dify source is bundled in this source archive.

v0.2.0 contains no dmn-js, bpmn.io, KIE, Java engine or Dify frontend patch. Those were components of the incompatible v0.1.x integration. Their earlier licenses and notices remain applicable when using those older releases.
