# Third-party notices

Original adapter code is provided under the root MIT license. Dependencies and patch context retain their own licenses; this file is not a substitute for a company software/legal review or a complete transitive dependency inventory.

- **Dify 1.11.1 and 1.17.1**: Dify Open Source License, based on Apache 2.0 with additional conditions. The frontend patch adapts Dify source and must follow Dify's license. Full license copied to `licenses/Dify-LICENSE.txt`. Source: https://github.com/langgenius/dify/tree/8387590ace4a094de812b7847fc6a4c3a27cd52b
- **dmn-js 17.12.2**: bpmn.io license. Full text in `licenses/dmn-js-LICENSE.txt`. Keep the bpmn.io logo and link visible and unobstructed. This package does not remove, modify or cover it. Source: https://github.com/bpmn-io/dmn-js
- **Apache KIE DMN 10.2.0**: Apache License 2.0, copied to `licenses/Apache-2.0.txt`. Source: https://github.com/apache/incubator-kie-drools and https://kie.apache.org/drools/dmn/
- **Dify Plugin Python SDK 0.10.2**: Apache License 2.0. Source: https://github.com/langgenius/dify-plugin-sdks
- React (MIT), Vite (MIT), TypeScript (Apache 2.0), Playwright (Apache 2.0), httpx (BSD-3-Clause), simplejson (MIT/AFL-2.1, see upstream notices), Jackson (Apache 2.0), and other declared/transitive dependencies retain their own distributed notices. Frontend `package-lock.json`, plugin `requirements.txt` and engine Maven dependency tree identify the actual dependency versions.

The source ZIP excludes third-party node_modules, Python environment and Java JAR binaries. Building images or distributing a shaded JAR/Web bundle requires retaining the notices for the actual bundled dependencies. No dependency security audit or legal approval is asserted by this starter's functional tests.
