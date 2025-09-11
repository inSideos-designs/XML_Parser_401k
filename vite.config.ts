import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';
import { spawn } from 'child_process';
import { defineConfig } from 'vite';

// Ensure __dirname is available in ESM context
// @ts-ignore
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else { inQ = !inQ; }
    } else if (ch === ',' && !inQ) {
      out.push(cur); cur = '';
    } else { cur += ch; }
  }
  out.push(cur);
  return out;
}

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    }
  },
  server: {
    middlewareMode: false,
  },
  plugins: [
    {
      name: 'local-maps-endpoints',
      configureServer(server) {
        // Serve NPPG logo from user's Desktop as /nppg-logo
        server.middlewares.use('/nppg-logo', (req, res) => {
          try {
            const home = process.env.HOME || process.env.USERPROFILE || '';
            const p = path.join(home, 'Desktop', 'images.jpeg');
            if (!fs.existsSync(p)) {
              res.statusCode = 404; res.setHeader('Content-Type','application/json');
              res.end(JSON.stringify({ error: 'images.jpeg not found on Desktop' }));
              return;
            }
            const data = fs.readFileSync(p);
            res.setHeader('Content-Type','image/jpeg');
            res.end(data);
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });
        server.middlewares.use('/local-map', (req, res) => {
          try {
            const py = spawn('python3', [path.join(__dirname, 'server', 'get_local_map.py')]);
            let out = '';
            let err = '';
            let code: number | null = null;
            py.stdout.on('data', (d) => { out += d.toString(); });
            py.stderr.on('data', (d) => { err += d.toString(); });
            py.on('close', (c) => {
              code = c;
              if (code && code !== 0) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
              } else {
                res.setHeader('Content-Type','application/json');
                res.end(out);
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });

        server.middlewares.use('/local-options', (req, res) => {
          try {
            const py = spawn('python3', [path.join(__dirname, 'server', 'get_local_options.py')]);
            let out = '';
            let err = '';
            let code: number | null = null;
            py.stdout.on('data', (d) => { out += d.toString(); });
            py.stderr.on('data', (d) => { err += d.toString(); });
            py.on('close', (c) => {
              code = c;
              if (code && code !== 0) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
              } else {
                res.setHeader('Content-Type','application/json');
                res.end(out);
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });

        server.middlewares.use('/process-local', (req, res) => {
          try {
            let body = '';
            req.on('data', (chunk) => { body += chunk; });
            req.on('end', () => {
              try {
                const py = spawn('python3', [path.join(__dirname, 'server', 'run_process_local.py')]);
                let out = '';
                let err = '';
                py.stdout.on('data', (d) => { out += d.toString(); });
                py.stderr.on('data', (d) => { err += d.toString(); });
                py.on('close', (code) => {
                  if (code && code !== 0) {
                    res.statusCode = 500; res.setHeader('Content-Type','application/json');
                    res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
                  } else {
                    res.setHeader('Content-Type','application/json');
                    res.end(out);
                  }
                });
                py.stdin.write(body);
                py.stdin.end();
              } catch (e: any) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: String(e?.message || e) }));
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });
      },

      // Ensure endpoints also work in `vite preview`
      configurePreviewServer(server) {
        const add = (route: string, handler: any) => {
          // @ts-ignore
          server.middlewares.use(route, handler);
        };

        add('/nppg-logo', (req: any, res: any) => {
          try {
            const home = process.env.HOME || process.env.USERPROFILE || '';
            const p = path.join(home, 'Desktop', 'images.jpeg');
            if (!fs.existsSync(p)) {
              res.statusCode = 404; res.setHeader('Content-Type','application/json');
              res.end(JSON.stringify({ error: 'images.jpeg not found on Desktop' }));
              return;
            }
            const data = fs.readFileSync(p);
            res.setHeader('Content-Type','image/jpeg');
            res.end(data);
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });

        add('/local-map', (req: any, res: any) => {
          try {
            const py = spawn('python3', [path.join(__dirname, 'server', 'get_local_map.py')]);
            let out = '';
            let err = '';
            py.stdout.on('data', (d: any) => { out += d.toString(); });
            py.stderr.on('data', (d: any) => { err += d.toString(); });
            py.on('close', (code: number) => {
              if (code && code !== 0) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
              } else {
                res.setHeader('Content-Type','application/json');
                res.end(out);
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });

        add('/local-options', (req: any, res: any) => {
          try {
            const py = spawn('python3', [path.join(__dirname, 'server', 'get_local_options.py')]);
            let out = '';
            let err = '';
            py.stdout.on('data', (d: any) => { out += d.toString(); });
            py.stderr.on('data', (d: any) => { err += d.toString(); });
            py.on('close', (code: number) => {
              if (code && code !== 0) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
              } else {
                res.setHeader('Content-Type','application/json');
                res.end(out);
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });

        add('/process-local', (req: any, res: any) => {
          try {
            let body = '';
            req.on('data', (chunk: any) => { body += chunk; });
            req.on('end', () => {
              try {
                const py = spawn('python3', [path.join(__dirname, 'server', 'run_process_local.py')]);
                let out = '';
                let err = '';
                py.stdout.on('data', (d: any) => { out += d.toString(); });
                py.stderr.on('data', (d: any) => { err += d.toString(); });
                py.on('close', (code: number) => {
                  if (code && code !== 0) {
                    res.statusCode = 500; res.setHeader('Content-Type','application/json');
                    res.end(JSON.stringify({ error: `python exited ${code}`, stderr: err, stdout: out }));
                  } else {
                    res.setHeader('Content-Type','application/json');
                    res.end(out);
                  }
                });
                py.stdin.write(body);
                py.stdin.end();
              } catch (e: any) {
                res.statusCode = 500; res.setHeader('Content-Type','application/json');
                res.end(JSON.stringify({ error: String(e?.message || e) }));
              }
            });
          } catch (e: any) {
            res.statusCode = 500; res.setHeader('Content-Type','application/json');
            res.end(JSON.stringify({ error: String(e?.message || e) }));
          }
        });
      },
    },
  ],
});
