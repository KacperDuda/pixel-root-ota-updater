
import { defineConfig } from 'vite';
import path from 'path';
import fs from 'fs';

export default defineConfig({
    root: '.',
    base: './', // Relative paths for bucket hosting
    server: {
        fs: {
            allow: ['..'] // Allow serving files from project root
        }
    },
    // Custom middleware to serve ../output at /output
    plugins: [
        {
            name: 'serve-output-dir',
            configureServer(server) {
                server.middlewares.use('/output', (req, res, next) => {
                    if (!req.url) return next();

                    // Sanitize path (basic)
                    const safeUrl = req.url.split('?')[0];
                    const filePath = path.join(__dirname, '../output', safeUrl);

                    if (fs.existsSync(filePath)) {
                        const stat = fs.statSync(filePath);
                        console.log(`[Middleware] Serving: ${safeUrl} (${stat.size} bytes)`);

                        // Basic mime handling
                        if (safeUrl.endsWith('.json')) {
                            res.setHeader('Content-Type', 'application/json');
                        } else if (safeUrl.endsWith('.zip')) {
                            res.setHeader('Content-Type', 'application/zip');
                        } else {
                            res.setHeader('Content-Type', 'application/octet-stream');
                        }

                        res.setHeader('Content-Length', stat.size);

                        // Stream the file to prevent OOM on large Zips
                        const stream = fs.createReadStream(filePath);
                        stream.pipe(res);
                        return;
                    } else {
                        // Explicitly 404 if file missing, do NOT fallback to SPA index.html
                        console.log(`[Middleware] 404 Not Found: ${filePath}`);
                        res.statusCode = 404;
                        res.end('File not found in output directory');
                        return;
                    }
                    // next(); // Do not call next() for /output routes to avoid index.html fallback
                });
            }
        }
    ],
    build: {
        outDir: 'dist',
        emptyOutDir: true,
        target: 'esnext' // Top-level await support if needed
    }
});
