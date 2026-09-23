# agent-kit

Shared extensions and skills for [omp](https://github.com/can1357/oh-my-pi). Only generic,
reusable pieces are here; personal agent config (profile, preferences, model roles) is not.

## Install

```bash
git clone <this repo> ~/agent-kit
~/agent-kit/install.sh            # links everything into ~/.omp
~/agent-kit/install.sh --status   # shows what is linked
```

Everything is linked, not copied, so `git pull` updates your install. A real file already at a
target is left untouched and reported as a conflict. Set `OMP_HOME` to install somewhere other
than `~/.omp`. Restart omp after installing.

## What's inside

| Path | What it is |
|---|---|
| `agent/extensions/jev-pilot.ts` | Pilot mode (`/pilot`) |
| `.agents/skills/calibrated-judgment` | Turns an agent's gut-check judgments ("is this done?", "does the evidence support this?") into calibrated typed decisions through omp's `judge` (TypeSafe Jev). Pilot mode reads its references |
| `.agents/skills/browser-autopilot` | Drives or verifies a browser flow step by step with Jev, instead of spending a large-model turn on every click |

## Pilot mode

An agent certifies its own work at the three points where mistakes cost the most: reading
what you meant, choosing the approach, and declaring the work done. Advice in a skill doesn't
hold at those points, because nothing forces the agent to follow it. Pilot mode turns them
into gates the agent can't talk its way past.

| Phase | What the pilot does | Where Jev is used |
|---|---|---|
| Goal | Blocks edits. The agent reads `goal-comprehension.md`, then shows the goal, numbered criteria and open questions D1..Dn | Scores each question by how costly a wrong guess is: costly ones go to you, cheap ones the agent decides in one line. Classifies your reply: only an explicit yes counts as agreement, and a message that only asks a question doesn't |
| Solution | Blocks edits until an oracle has reviewed the approach and `pilot_propose` is called | Warns, never blocks. Scores only criteria about the product, not about the process |
| Execution | Detects a stuck agent (repeated tools, consecutive errors) | Not used |
| Review | Every stop that isn't a question for you lands here. The agent quotes tool output for each criterion with `pilot_report`; the code checks every quote appears verbatim | Not used |
| Completion | Hard gate. After 3 blocks it lets the work through, marked unverified | Checks each criterion against its own quotes and the final message |

The goal, criteria and approach are added to the system prompt every turn, so they survive
compaction. They're also added to every `task` call, so subagents don't start blank. The
status bar shows one chip with Jev's latest result (`goal · 1 to you`,
`execution · Jev ✓3/3`, `completion ✓4/4`). A widget appears only when Jev says no, one line
per criterion with what it judged (`cited: "…"`, `no citation`, `plan only`), so you can tell
noise from a real failure. `/pilot` toggles it; `/pilot show` lists the goal and criteria.

Turn it on when a wrong reading or a wrong approach is expensive: ambiguous requirements,
structural changes, work you can only check at the end. For small, clear tasks it's overhead.

It needs a TypeSafe credential in omp's credential store (`/login typesafe`).

To show the status chip inside the bar, your status line needs the `status` segment, e.g. in
`~/.omp/agent/config.yml`:

```yaml
statusLine:
  preset: custom
  leftSegments: [pi, model, mode, status, path, git, context_pct, cost]
  showHookStatus: false
```
