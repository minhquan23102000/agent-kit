---
name: browser-autopilot
description: >-
  Drive or verify a real browser flow with Jev instead of spending a big-model turn on every
  click. Use when a task means navigating a website to a goal - log in, search, fill a form,
  open a result, click through a multi-step flow - and when you want to check that a web page
  actually reached a goal (structural/behavioral verification over the DOM). A Jev fan-out call
  picks one operation and one element per step from the page's accessibility table; a small
  model writes text only for typing. It runs on omp's own browser (no second Chrome stack) and
  hands control back to you on low confidence, a block, an unverified "done", or an error. Not
  for visual/pixel design checks (layout, spacing, color, does-it-match-the-mockup) - those need
  a vision model or a screenshot diff, since Jev reads the accessibility tree, not pixels. Not a
  deterministic CI test runtime on its own: use it to explore/verify, then pin a fixed script.
---

# Browser autopilot

You (the big model, the professor) are expensive per step. Deciding "which button next" one click
at a time burns a full turn each time. `judge` (Jev) makes that same decision in ~150 ms, calibrated,
for a fraction of the cost. This tool hands the mechanical driving to Jev and keeps you as the
reviewer: you give a goal, it runs the loop, you inspect the result.

## Two jobs, kept separate

- **Drive** - run a flow toward a goal (`autopilot.run`). Jev picks the operation and target; a
  small model supplies text for typing.
- **Verify** - check that a page satisfies a goal (`autopilot.verify_done`, read-only). This is the
  `calibrated-judgment` skill applied to browser state: raw DOM/text as evidence, a claim and its
  negation. Read that skill for the judgment doctrine; this tool only wires it to a live page.

Verify handles **structural/behavioral** truth (is the button there, is the form in the right state,
is the content present). It does **not** handle **visual** truth (does it look right). For visual
design verification use a vision model on a screenshot, not this.

## How to call it

```python
exec(read(".agents/skills/browser-autopilot/autopilot.py"))
r = await autopilot.run(
    "https://en.wikipedia.org/wiki/Main_Page",
    "Find and open the Wikipedia article about Gödel's incompleteness theorems.",
)
# r: {status, reason, needs_professor, final_url, final_title, steps, tab, trace,
#     capture_dir?, screenshots?}
```

- **You own the goal and the review.** When `r["needs_professor"]` is true (status `escalate`,
  `blocked`, `error`, or `budget`), the run stopped and left the tab open (`r["tab"]`) for you to
  take over with the ordinary `browser` helpers. On a clean `done` the tab is closed.
- **A `done` is verified independently** before it is trusted: a separate read-only `judge` call
  re-scoops the page and asks whether the goal is truly met (plus its negation). A `done` the
  verifier rejects becomes an `escalate`, not a success. Never trust the loop's own `DONE`.
- Tune with `conf_floor` (escalate below this operation confidence), `max_steps`, `verify=False`,
  `close="keep"|"auto"`, `wait_timeout` (seconds for explicit WAIT, default 5.0).
- **Capture mode**: `capture=True` saves a viewport screenshot at every step to an auto-created
  temp dir; `capture="/path/to/dir"` saves to that directory. `capture_full_page=True` captures
  the full scrollable page (slower). The result gets `capture_dir` and `screenshots` list; each
  trace record gets a `screenshot` field with the file path.
- **Attach to an open tab** with `url=None` to act on the page already loaded (named by
  `tab_name`) instead of navigating — needed for a stateful, multi-goal session on one page.

## How much to hand over per call

The goal length is the real design choice, and it is not "long vs short" — it is how far
autopilot can go before a decision only you can make.

Default to the **longest goal it can carry and self-verify**: a whole login, a form, "find and
open X", a known multi-step flow. Let its escalation contract cut the run for you — it hands back
on low confidence, a block, or an unverified done. Do not pre-chop a mechanical stretch into
one-click goals; that wastes turns and buys nothing.

Pre-cut the goal yourself at exactly one kind of seam: where autopilot would go on **confidently
but wrong** because the knowledge that step needs lives in *you*, not on the page — a strategy
call, a fact to extract and reason on, the choice of the next target from what a page just
revealed. There the confidence is high, so the tool will *not* hand back (it only escalates on
*low* confidence): a wrong step passes silently and, in a chain, poisons every step after it.
That boundary — "a wrong step here is high-confidence and corrupts the rest" — is where you keep
the wheel, never a fixed step count.

The loop, concretely: mark where your knowledge is required (those seams are the goal cuts) →
hand the longest self-verifying stretch between seams → read the **actual page**, never the run's
word for it, and make the decision it could not → feed the next goal, or drive one step by hand
when it must be exact → at the end verify the whole against the real goal, not the per-step DONE.

## Waiting

The loop handles waiting at two layers, both automatic:

1. **Post-action settle** (`_settle`): after every CLICK, TYPE_TEXT, SELECT, or SCROLL_DOWN, the
   loop waits until the page visibly stabilizes (two consecutive identical DOM observations) or a
   4 s timeout. This catches SPA navigations, XHR-driven re-renders, autocomplete dropdowns, and
   redirect chains without a fixed sleep. No configuration needed.

2. **Explicit WAIT** (`_smart_wait`): when Jev chooses WAIT ("the needed control is absent or
   results are loading"), the loop blocks until the page changes or `wait_timeout` elapses
   (default 5 s, configurable). Progressive backoff avoids hammering observe. Three consecutive
   WAITs without a page change → `blocked: wait_timeout`.

You do not call either function directly; they run inside `autopilot.run`. If you need a
condition wait while driving manually (wait for a selector, specific text, or network idle), use
the ordinary `tab.waitForSelector` / `tab.waitForText` / `tab.waitForUrl` helpers.

## What it does not do (hand back to yourself)

- Shadow DOM, iframes, canvas, file uploads, pop-up tabs, nested scrolling, and arbitrary keyboard
  widgets are outside it - it will `block` or stall; take over manually.
- It is a probabilistic policy. For a **repeatable CI regression**, use a run to discover the flow,
  then emit a deterministic selector script (e.g. Playwright) and, where a step is semantic, drop in
  a `verify_done`-style Jev assertion. Do not make the probabilistic policy the CI oracle.
- Pixel/visual comparison - use a vision model or screenshot diff.
- For **e2e evidence** (PR proof, audit trail), use `capture=True` to get a screenshot at every
  step. The screenshots + trace together form a visual record of the flow. To compare runs, diff
  the screenshots or feed them to a vision model.

## Why it is a module, not an omp extension

omp extensions are TypeScript in the omp process and do not get the eval kernel's `browser`/`judge`;
an extension would have to drive its own Chrome and call TypeSafe itself - a second browser stack.
This module is Python in the eval kernel, so it reuses omp's browser and `judge` directly. Graduate
it to a TS extension only to make it a first-class, shareable tool, and only then pay for its own
browser layer (or attach over CDP to omp's Chromium).
