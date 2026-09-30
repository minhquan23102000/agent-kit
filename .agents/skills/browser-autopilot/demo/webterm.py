# A one-client web terminal for recording: runs one command in a real pseudo-terminal and shows it
# in xterm.js, so a browser tab (and Chrome's screencast of it) sees exactly what a terminal would.
# View-only: output streams to the page, no keyboard input goes back.
#
#   python3 webterm.py --port 7681 -- zsh -lc 'omp "…"'
#
# The command starts when the page first connects, at the page's own size (cols x rows), so a
# recording that opens the page captures the command from its first frame. xterm.js is read from
# ~/.omp/vendor/xterm (bun add @xterm/xterm@5 @xterm/addon-fit there once).
import argparse, base64, fcntl, os, pty, select, signal, struct, sys, termios, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

XTERM = os.path.expanduser("~/.omp/vendor/xterm/node_modules/@xterm")
FILES = {"/xterm.js": (f"{XTERM}/xterm/lib/xterm.js", "text/javascript"),
         "/xterm.css": (f"{XTERM}/xterm/css/xterm.css", "text/css"),
         "/addon-fit.js": (f"{XTERM}/addon-fit/lib/addon-fit.js", "text/javascript")}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>%(title)s</title>
<link rel="stylesheet" href="/xterm.css">
<style>html,body{margin:0;height:100%%;background:%(bg)s}#t{position:absolute;inset:14px}</style>
</head><body><div id="t"></div>
<script src="/xterm.js"></script><script src="/addon-fit.js"></script>
<script>
const term = new Terminal({fontSize: %(size)d, fontFamily: '"JetBrainsMonoNL Nerd Font", "JetBrainsMono Nerd Font", Menlo, monospace',
  theme: {background: '%(bg)s'}, cursorBlink: false, scrollback: 2000, allowProposedApi: true});
const fit = new FitAddon.FitAddon(); term.loadAddon(fit); term.open(document.getElementById('t')); fit.fit();
const es = new EventSource(`/stream?cols=${term.cols}&rows=${term.rows}`);
es.onmessage = e => term.write(Uint8Array.from(atob(e.data), c => c.charCodeAt(0)));
es.addEventListener('end', () => { es.close(); window.__webterm_ended = true; });
</script></body></html>"""

class Term:
    def __init__(self, argv):
        self.argv, self.pid, self.fd, self.lock = argv, None, None, threading.Lock()

    def start(self, cols, rows):
        with self.lock:
            if self.pid: return False
            pid, fd = pty.fork()
            if pid == 0:
                os.environ.update(TERM="xterm-256color", COLORTERM="truecolor")
                os.execvp(self.argv[0], self.argv)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.kill(pid, signal.SIGWINCH)
            self.pid, self.fd = pid, fd
            return True

    def stop(self):
        if self.pid:
            try: os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            except Exception:
                try: os.kill(self.pid, signal.SIGTERM)
                except Exception: pass

def serve(port, argv, title, size, bg):
    term = Term(argv)

    class H(BaseHTTPRequestHandler):
        def log_message(self, format, *args): pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                body = (PAGE % {"title": title, "size": size, "bg": bg}).encode()
                return self._send(200, "text/html; charset=utf-8", body)
            if u.path in FILES:
                path, ctype = FILES[u.path]
                with open(path, "rb") as f: return self._send(200, ctype, f.read())
            if u.path == "/stream":
                q = parse_qs(u.query)
                if not term.start(int(q.get("cols", ["100"])[0]), int(q.get("rows", ["40"])[0])):
                    return self._send(409, "text/plain", b"already running")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        r, _, _ = select.select([term.fd], [], [], 15)
                        if not r:
                            self.wfile.write(b": keepalive\n\n"); self.wfile.flush(); continue
                        try: chunk = os.read(term.fd, 65536)
                        except OSError: chunk = b""
                        if not chunk: break
                        self.wfile.write(b"data: " + base64.b64encode(chunk) + b"\n\n"); self.wfile.flush()
                    self.wfile.write(b"event: end\ndata: \n\n"); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    term.stop()
                return
            self._send(404, "text/plain", b"not found")

        def _send(self, code, ctype, body):
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    def bye(*_):
        term.stop(); os._exit(0)
    signal.signal(signal.SIGTERM, bye); signal.signal(signal.SIGINT, bye)
    srv.serve_forever()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7681)
    ap.add_argument("--title", default="terminal")
    ap.add_argument("--font-size", type=int, default=15)
    ap.add_argument("--bg", default="#0f172a")
    ap.add_argument("argv", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    argv = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
    if not argv: sys.exit("usage: webterm.py [--port N] -- command args…")
    serve(a.port, argv, a.title, a.font_size, a.bg)
