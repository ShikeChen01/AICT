import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/webview/**/*.test.{ts,tsx}'],
    globals: false,
  },
});
