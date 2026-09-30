# Privacy

The evaluator performs no external requests, invokes no other tools, and reads/writes no business files. One table and its values are evaluated in the Dify plugin process. No external engine, API credential, LLM, telemetry, arbitrary code execution, or evaluation cache is used by the evaluator.

Dify and its plugin SDK may keep invocation inputs, outputs, errors, workflow snapshots and normal operational metadata under the deployment's policies. This package cannot disable or guarantee the absence of platform logging. Error messages use fixed descriptions and structural paths rather than actual input values. Rule/variable identifiers intentionally appear in returned results.

Dependency installation may require access to your approved Python package registry. Runtime transport between Dify and the plugin is provided by the official SDK. This is distinct from external calls by the decision evaluator.

Only synthetic rules and data are included. Administrators should review dependencies, trust/signature policies, resource limits and workflow access before installing. No company source code or production rules are bundled.
