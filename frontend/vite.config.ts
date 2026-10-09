import { defineConfig } from 'vite'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
export default defineConfig({
  plugins: [{ name: 'real-python-evaluator', configureServer(server) {
    server.middlewares.use('/api/evaluate', (req, res) => {
      if (req.method !== 'POST') { res.statusCode = 405; res.end(); return }
      let body = ''; req.on('data', chunk => { body += chunk; if (body.length > 1024 * 1024) req.destroy() }); req.on('end', () => {
        const py = spawn(resolve('../.venv/bin/python'), [resolve('demo/evaluate.py')], { cwd: resolve('..'), stdio: ['pipe', 'pipe', 'pipe'] }); let out = ''; let err = ''
        py.stdout.on('data', b => { out += b }); py.stderr.on('data', b => { err += b }); py.on('error', () => { res.statusCode = 500; res.end('{"error":"Python evaluator unavailable"}') }); py.on('close', code => { res.setHeader('Content-Type', 'application/json; charset=utf-8'); res.statusCode = code ? 400 : 200; res.end(out || JSON.stringify({ error: 'Python evaluation failed', detail: err.slice(0, 200) })) }); py.stdin.end(body)
      })
    })
  } }], server: { host: '0.0.0.0', port: 5173, strictPort: true }, build: { assetsInlineLimit: 1000000 },
})
