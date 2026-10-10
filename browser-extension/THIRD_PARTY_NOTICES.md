# Third-party and reused source notices

The read-only matrix model derives from the MIT-licensed original integration code identified in `docs/PROVENANCE.md`; its MIT notice is retained in `LICENSE`. All other extension runtime source is newly authored for this candidate. No Dify frontend source, React, jsdom or esbuild runtime library is shipped in the extension bundle.

Development dependencies are recorded by version and integrity in `package-lock.json`. esbuild is MIT-licensed; jsdom is MIT-licensed; TypeScript is Apache-2.0-licensed. Their transitive development dependencies retain their own licenses in their installed npm packages. Development dependencies are not included in the extension archive or source archive.
