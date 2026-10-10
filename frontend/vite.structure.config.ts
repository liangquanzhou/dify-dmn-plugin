import { defineConfig } from 'vite'
import { resolve } from 'node:path'
// Separate from the matrix demo server: this viewer has no evaluator middleware.
export default defineConfig({
  define: { 'process.env.NODE_ENV': '"production"' },
  build: { outDir: '../dist/structure-build', emptyOutDir: true, lib: { entry: resolve('src/structure-main.tsx'), name: 'DmnStructureViewer', formats: ['iife'], fileName: () => 'viewer.js', cssFileName: 'viewer' }, rollupOptions: { output: { inlineDynamicImports: true } }, sourcemap: false },
})
