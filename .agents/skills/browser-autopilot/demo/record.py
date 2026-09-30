# Record one take of the browser-autopilot demo without macOS Screen Recording permission.
#
# The same shop task is done by an omp session either WITH the browser-autopilot skill (Jev drives,
# the agent writes the plan) or WITHOUT it (the agent drives the browser itself, one action per
# model turn). Same model, same site, same setup.
#
# Nothing is captured from the screen. The agent's terminal is a real zsh running omp in a
# pseudo-terminal, shown as a web page by webterm.py (xterm.js); both it and the agent's shop tab
# are pages of omp's shared Chromium, so each is recorded through Chrome's own screencast. The two
# recordings are then put side by side: shop on the left, terminal on the right, 1920x1080.
#
# In an omp Python eval kernel (it needs omp's `browser`):
#   exec(read(".agents/skills/browser-autopilot/demo/record.py"))
#   r = await record_take("with")      # or "without"
# Output in ~/Desktop/autopilot-demo/: <mode>.mp4 and <mode>.stats.txt (model turns, tool calls,
# model cost and time, read from the take's omp session file). Needs xterm.js in
# ~/.omp/vendor/xterm (bun add @xterm/xterm@5 @xterm/addon-fit there once).
import os, sys, json, time, shlex, socket, subprocess
from datetime import datetime, timezone

DEMO = os.path.expanduser("~/.omp/.agents/skills/browser-autopilot/demo")
OUT = os.path.expanduser("~/Desktop/autopilot-demo")
SHOP_PORT, TERM_PORT = 8765, 7681
MODEL = "anthropic/claude-opus-5-5"

TASK = """On the Harbor Supply shop (http://127.0.0.1:8765/shop.html): sign in as demo_user with password harbor-2026, \
buy one Red Jacket in size M and one Green Bottle, ship Express to Nguyen Van A, 12 Ly Thuong Kiet, Hanoi, Vietnam, \
email nguyenvana@example.com, agree to the terms of sale and place the order. Then tell me the order number.
Start by running this in Python eval: exec(read("__DEMO__/setup.py")); tab = await open_shop()
It opens the shop in a tab named "shop"; do the task in that tab.""".replace("__DEMO__", DEMO)

PROMPTS = {
    "with": TASK + """
Use the browser-autopilot skill in demo mode: autopilot.run(None, ..., tab_name="shop", demo=True) \
with a step-by-step plan, the facts, and done_when.""",
    "without": TASK + """
Drive the browser yourself with the eval browser helpers, one action at a time, checking the page \
as you go. Do not use the browser-autopilot skill.""",
}

# omp runs one Chrome per working folder, so the take runs from ~/.omp, the folder of the session
# that records it: otherwise its shop tab lives in another Chrome and the recorder never sees it.
HOME_OMP = os.path.expanduser("~/.omp")
# omp keeps sessions under sessions/<cwd relative to home, "/" written as "-">, each file named by
# its start time; the take's file is the one that started after `mark`.
SESSIONS = os.path.expanduser("~/.omp/agent/sessions/-" + os.path.relpath(HOME_OMP, os.path.expanduser("~")).replace("/", "-"))

def _started(name):
    try: return datetime.strptime(name[:23], "%Y-%m-%dT%H-%M-%S-%f").replace(tzinfo=timezone.utc).timestamp()
    except ValueError: return 0

# Runs in the terminal tab's JS runtime for the whole take: records the terminal page, starts
# recording the shop page the moment the agent opens it, and stops once the agent's turn is over
# (its last session message is an assistant message with no tool call).
_RECORDER_JS = """
const fs = require('fs'), path = require('path');
const P = __PARAMS__;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const turnOver = () => {
  if (!fs.existsSync(P.sessions)) return false;
  const started = f => { const m = f.match(/^(\\d{4}-\\d\\d-\\d\\d)T(\\d\\d)-(\\d\\d)-(\\d\\d)-(\\d{3})Z/);
    return m ? Date.parse(`${m[1]}T${m[2]}:${m[3]}:${m[4]}.${m[5]}Z`) : 0; };
  const files = fs.readdirSync(P.sessions).filter(f => f.endsWith('.jsonl') && started(f) >= P.mark * 1000)
    .map(f => path.join(P.sessions, f)).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  if (!files.length) return false;
  const lines = fs.readFileSync(files[0], 'utf8').trim().split('\\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    let d; try { d = JSON.parse(lines[i]); } catch { continue; }
    if (d.type !== 'message') continue;
    const m = d.message || {};
    return m.role === 'assistant' && !(m.content || []).some(c => c.type === 'toolCall');
  }
  return false;
};
const t0 = Date.now();
const termRec = await page.screencast({ path: P.term });
let shop = null, shopRec = null, t1 = null, doneAt = null, over = false;
while (Date.now() - t0 < P.timeout * 1000) {
  if (!shop) {
    for (const t of browser.targets()) {
      if (t.type() === 'page' && t.url().includes(P.shopPath)) { shop = await t.page(); break; }
    }
    // A page taken from another connection has no viewport of its own here, so the screencast
    // takes the window at the screen's scale (1200x1350, page in the corner, black around it).
    if (shop) {
      await shop.setViewport({ width: 960, height: 1080, deviceScaleFactor: 1 });
      shopRec = await shop.screencast({ path: P.shop }); t1 = Date.now();
    }
  } else if (!doneAt && shop.url().includes('#done')) doneAt = Date.now();
  if (turnOver()) { over = true; break; }
  await sleep(1000);
}
await sleep(3000);
await termRec.stop();
if (shopRec) await shopRec.stop();
if (shop) await shop.close().catch(() => {});
return { offset: t1 ? (t1 - t0) / 1000 : null, order_placed_at: doneAt ? (doneAt - t0) / 1000 : null,
         turn_over: over, seconds: (Date.now() - t0) / 1000 };
"""

def _wait_port(port, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0: return True
        time.sleep(0.2)
    return False

def _free(port):
    pids = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True).stdout.split()
    for p in pids: subprocess.run(["kill", p])
    time.sleep(0.5)

def _stats(session, mode):
    turns = tools = 0; cost = 0.0; ts = []
    for line in open(session):
        d = json.loads(line)
        if d.get("timestamp"): ts.append(datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")))
        m = d.get("message") or {}
        if d.get("type") == "message" and m.get("role") == "assistant":
            turns += 1
            tools += sum(1 for c in m.get("content", []) if c.get("type") == "toolCall")
            cost += ((m.get("usage") or {}).get("cost") or {}).get("total", 0)
    secs = (ts[-1] - ts[0]).total_seconds() if len(ts) > 1 else 0
    return (f"take: {mode} autopilot\n"
            f"model turns: {turns}, tool calls: {tools}, model cost: ${cost:.2f} (Jev judge calls not included)\n"
            f"session time: {int(secs // 60)}m{int(secs % 60):02d}s\nsession file: {session}\n")

async def record_take(mode, *, out=OUT, timeout=1500):
    assert mode in PROMPTS, "mode is 'with' or 'without'"
    os.makedirs(out, exist_ok=True)
    term_v, shop_v, final = (os.path.join(out, f"{mode}.{k}") for k in ("terminal.webm", "shop.webm", "mp4"))
    for f in (term_v, shop_v, final):
        if os.path.exists(f): os.remove(f)
    for p in (SHOP_PORT, TERM_PORT): _free(p)
    null = subprocess.DEVNULL
    # A sleeping display stops Chrome painting: screencast frames stop with no error. Keep it on.
    awake = subprocess.Popen(["caffeinate", "-d", "-u"], stdout=null, stderr=null)
    shop = subprocess.Popen(["python3", "-m", "http.server", str(SHOP_PORT), "--bind", "127.0.0.1"],
                            cwd=DEMO, stdout=null, stderr=null)
    # Both takes on one pinned model: a new session's default model is not a stable choice.
    cmd = (f"cd {shlex.quote(HOME_OMP)} && omp --no-extensions --approval-mode=yolo --model {MODEL} "
           f"{shlex.quote(PROMPTS[mode])}")
    # The command starts when the terminal page first connects, so the recording has it from frame one.
    term = subprocess.Popen([sys.executable, os.path.join(DEMO, "webterm.py"), "--port", str(TERM_PORT),
                             "--title", f"omp · {mode} autopilot", "--", "zsh", "-lc", cmd],
                            stdout=null, stderr=null, start_new_session=True)
    tab = None
    try:
        if not (_wait_port(SHOP_PORT) and _wait_port(TERM_PORT)):
            raise RuntimeError("shop server or web terminal did not start")
        mark = time.time()
        tab = await browser.open(name="demo-term", url=f"http://127.0.0.1:{TERM_PORT}",  # noqa: F821
                                 viewport={"width": 960, "height": 1080}, persist=True)
        params = {"term": term_v, "shop": shop_v, "sessions": SESSIONS, "mark": mark,
                  "shopPath": "/shop.html", "timeout": timeout}
        rec = await tab.run(_RECORDER_JS.replace("__PARAMS__", json.dumps(params)), timeout=timeout + 120)
    finally:
        try: await browser.close(name="demo-term")  # noqa: F821
        except Exception: pass
        for p in (term, shop, awake):
            p.terminate()
            try: p.wait(5)
            except Exception: p.kill()
    # Side by side: the shop is blank (page colour) until the agent opens it, then plays in step
    # with the terminal because its recording started `offset` seconds later.
    off = rec.get("offset")
    if off is not None and os.path.exists(shop_v):
        left = (f"[0:v]scale=960:1080:force_original_aspect_ratio=decrease,pad=960:1080:(ow-iw)/2:0:color=0xf6f5f2,"
                f"tpad=start_duration={off:.2f}:color=0xf6f5f2,fps=30[l]")
        ins = ["-i", shop_v, "-i", term_v]
    else:  # no shop recording: a plain left half, as long as the terminal's
        left = f"color=c=0xf6f5f2:s=960x1080:r=30:d={rec['seconds']:.2f}[l]"
        ins = ["-i", term_v]
    right = f"[{1 if len(ins) == 4 else 0}:v]scale=960:1080:force_original_aspect_ratio=decrease,pad=960:1080:0:0:color=0x0f172a,fps=30[r]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex",
                    f"{left};{right};[l][r]hstack=inputs=2:shortest=0,format=yuv420p[v]",
                    "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", final], check=True)
    sessions = sorted((os.path.join(SESSIONS, f) for f in os.listdir(SESSIONS) if f.endswith(".jsonl")
                       and _started(f) >= mark), key=os.path.getmtime)
    stats = _stats(sessions[-1], mode) if sessions else "no session file found\n"
    open(os.path.join(out, f"{mode}.stats.txt"), "w").write(stats)
    print(stats + f"video: {final}")
    return {**rec, "video": final, "stats": stats}
