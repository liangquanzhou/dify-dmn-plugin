# Third-party notices

The original evaluator, Tool integration, tests and documentation in v0.3.0 are licensed under the root MIT license. They are independently implemented from an abstract condition protocol; no company source code or real business rules are included.

The plugin uses the official `dify-plugin==0.10.2` Python SDK and its dependencies, pinned in `plugin/requirements.txt`. Each dependency retains its own license. Review the dependency list and official projects as part of company supply-chain approval. The SDK itself uses Apache-2.0: https://github.com/langgenius/dify-plugin-sdks

Dify is a separate product with its own license: https://github.com/langgenius/dify/blob/1.11.1/LICENSE
The release does not include or relicense Dify. Compatibility tests import official Dify/daemon sources supplied separately; no upstream Dify source is bundled in this source archive.

v0.3.0 contains no dmn-js, bpmn.io, KIE, Java engine or Dify frontend patch. Those were components of the incompatible v0.1.x integration. Their earlier licenses and notices remain applicable when using those older releases.

Canonical model identity uses `rfc8785==0.1.4` from the official PyPI registry, maintained by Trail of Bits under Apache-2.0. It is installed as a dependency, not copied from the compared third-party plugin. Its upstream source and notices remain applicable: https://pypi.org/project/rfc8785/ and https://github.com/trailofbits/rfc8785.py . No code from the compared unlicensed plugin is included.

The installed wheel published on PyPI has SHA-256 `520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48`. The package requirements pin the version; corporate dependency mirror approval remains an administrator responsibility.
