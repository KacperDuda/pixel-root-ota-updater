import { defineConfig } from 'vite';

export default defineConfig({
    root: '.',
    base: './', // Relative paths for bucket hosting
    build: {
        outDir: 'dist',
        emptyOutDir: true,
        target: 'esnext' // Top-level await support if needed
    }
});
