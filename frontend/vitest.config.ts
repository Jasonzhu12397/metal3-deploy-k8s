import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.ts on purpose -- keeps test-only settings
// (environment, setupFiles) out of the dev/build config rather than
// merging a `test` key into it, so `npm run dev`/`build` never need to
// know vitest exists.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
