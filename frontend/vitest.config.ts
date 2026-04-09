import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // consultation_outcomes.json lives at app/core/ in the repository.
      // The Dockerfile copies it into the frontend workdir at build time so
      // the relative import in OutcomeScreen.tsx resolves correctly in
      // production. Vitest runs from frontend/ on the real filesystem where
      // no such copy exists, so we alias the path explicitly here.
      '../../consultation_outcomes.json': path.resolve(
        __dirname,
        '../app/core/consultation_outcomes.json'
      ),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
    globals: true,
  }
})