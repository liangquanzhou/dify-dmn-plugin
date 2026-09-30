// Replay the exact shared dmn-js/editor tests under Dify 1.11.1's React runtime.
import { cpSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
const here = fileURLToPath(new URL('.', import.meta.url))
const frontend = path.resolve(here, '../..')
const root = path.join(here, 'test-results/runtime')
const target = path.join(root, 'frontend')
mkdirSync(path.join(target, 'tests'), { recursive:true })
mkdirSync(path.join(root, 'examples'), { recursive:true })
cpSync(path.join(frontend, 'overlay'), path.join(target, 'overlay'), { recursive:true })
cpSync(path.join(frontend, 'overlays/1.11.1'), path.join(target, 'overlay'), { recursive:true })
for (const name of ['editor.dom.test.mjs', 'contract.test.mjs']) cpSync(path.join(frontend, 'tests', name), path.join(target, 'tests', name))
cpSync(path.join(frontend, '../examples/eligibility.dmn'), path.join(root, 'examples/eligibility.dmn'))
const result = spawnSync(process.execPath, ['--test', 'tests/editor.dom.test.mjs', 'tests/contract.test.mjs'], { cwd:target, stdio:'inherit' })
process.exit(result.status ?? 1)
