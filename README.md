# Jev Agent-Kit R&amp;D for OMP

Agent make dozens of silent judgments a turn: is this done, is this correct, do I have enough to decide, which way now. Made inside your own text stream, those judgments are uncalibrated and biased toward finishing, you tend to certify your own work. judge hands one such judgment to Jev.

Jev extension, a subagent and skills for [omp](https://github.com/can1357/oh-my-pi), shared from a
working setup. The main piece is **pilot mode** (`/pilot`): it stops your coding agent from
certifying its own work at the three points where a mistake costs the most. Nothing personal
is included: no profile, no model config.

## Install

```bash
git clone https://github.com/minhquan23102000/agent-kit.git ~/agent-kit
~/agent-kit/install.sh            # link everything into ~/.omp
~/agent-kit/install.sh --status   # show what is linked
```

Then tell omp where the skills are. The kit installs them into `~/.omp/.agents/skills`, and omp
does not scan that folder by default. Add it to `~/.omp/agent/config.yml`:

```yaml
skills:
  customDirectories:
    - ~/.omp/.agents/skills
```

The oracle runs on the model you assign to the `advisor` role. Pick a strong one, since its job is to catch what your main model missed:

```yaml
modelRoles:
  advisor: <a strong reasoning model you have access to>
```

Restart omp. Inside omp, run `/login typesafe` once: pilot mode and both skills call TypeSafe's
Jev model, and the key is kept in omp's own credential store.

`install.sh` creates symlinks instead of copies, so `git -C ~/agent-kit pull` plus a restart is
the whole update. If a real file already sits where a link should go, the script leaves it
alone and reports a conflict. Set `OMP_HOME` to install somewhere other than `~/.omp`. To
uninstall, delete the links it created.

## What's inside


| Path                                 | What it does                                                                                                                                                                                                            |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent/extensions/jev-pilot.ts`      | Pilot mode, the `/pilot` command                                                                                                                                                                                        |
| `agent/agents/oracle.md`             | Read-only oracle subagent for a second opinion on consequential decisions. Pilot mode requires it: edits stay blocked until the oracle has reviewed the approach                                                        |
| `.agents/skills/calibrated-judgment` | Turns the agent's gut checks ("is this done?", "does the evidence support this?", "do I know enough to decide?") into calibrated judgments through omp's `judge`. Pilot mode reads its reference files, so install both |
| `.agents/skills/browser-autopilot`   | Drives or checks a browser flow (log in, fill a form, click through steps), with Jev choosing each step instead of a large-model turn per click. Hands control back when unsure. Not for visual or pixel checks         |


## Pilot mode

### The problem

An agent grades itself at three points: what you meant, which approach to take, and whether
it's done. A rule in a skill doesn't hold at those points, because nothing makes the agent read
it or follow it. While this was being built, the agent, which knew the design and was trying to
follow it, skipped the reference file, started new work without updating the goal, and wrote
"all criteria met" without checking any of them. Pilot mode turns the three points into gates.
It uses Jev (a fast, cheap model that answers typed questions with probabilities) only where
Jev measures something real.

### What you see

Type your task and turn on `/pilot`. The agent can't edit files yet. First it shows you:

- the goal, in one sentence
- numbered criteria
- questions D1..Dn, each with two readings, for example: *D1. What does "faster" mean?
(a) the query runs faster (b) finance gets the file earlier*

It decides cheap questions itself and lists them in one line, so you can overrule them. Reply
with `ok`, `D1 b`, or `change criterion 2 to ...`. Only a clear yes moves on. A reply that only
asks a question keeps the draft waiting.

Next, an oracle agent reviews the approach, and only then does the agent edit anything. When it
stops, it must quote real tool output for each criterion. The pilot checks that every quote
appears word for word in the session, and Jev judges each criterion against its own quotes.

The status bar shows one chip: `goal · 1 to you`, `execution · Jev ✓3/3` (or `[WARN]2/3`),
`completion ✓4/4`. A widget above the editor appears only when Jev says no, one line per
criterion, and each line tells you which kind of no it is:

- `x export fast 1% · cited: "real 0m31.2s"`: a real failure. The quoted evidence shows the
criterion is not met.
- `x file in finance 4% · no citation`: the agent gave no evidence for this criterion.
- `[WARN] report live 38% · plan only`: a doubt about the plan. It clears once the work is done.

`/pilot` toggles pilot mode on and off. `/pilot show` lists the goal and criteria.

### Phases


| Phase      | What the pilot does                                                                                                          | What Jev does                                                                                                                          |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Goal       | Blocks edits. The agent reads `goal-comprehension.md`, then drafts the goal, criteria and questions                          | Scores how costly a wrong guess is for each question (costly ones go to you), and sorts your reply into agree, change, reject or other |
| Solution   | Blocks edits until an oracle has answered and the agent has submitted its approach. Saying "done" here sends the agent back  | Warns about the plan, never blocks. Checks only criteria about the result, not about the process                                       |
| Execution  | Detects a stuck agent (repeated tools, errors in a row)                                                                      | Nothing                                                                                                                                |
| Review     | Every stop that isn't a question for you lands here. The agent quotes evidence per criterion, and the code checks the quotes | Nothing                                                                                                                                |
| Completion | Hard gate. After 3 blocks it lets the work through marked UNVERIFIED and tells you which criteria failed                     | Judges each criterion against its quotes and the final message                                                                         |


The goal, criteria and approach are added to the system prompt on every turn, so they survive
compaction. They're also added to every `task` call, so subagents and the oracle see them too.

### When to use it

Use pilot mode when a wrong reading or a wrong approach is expensive: vague requirements,
structural changes, work you can only check at the end. Skip it for small, clear tasks, where
the agreement round and the oracle call are pure overhead.

Write any threshold in a criterion as an absolute number ("20s or less"), never a relative one
("twice as fast"). Jev doesn't do arithmetic, and a relative threshold lets a failing result
pass.

Limits: pilot mode has been tested on small real tasks, not yet measured against a run without
it on a hard task. It can't find unknowns ahead of time. When execution runs into one, it brings
it back to you.

### Showing the chip in the status bar

The chip needs the `status` segment in your status line. In `~/.omp/agent/config.yml`:

```yaml
statusLine:
  preset: custom
  leftSegments: [pi, model, mode, status, path, git, context_pct, cost]
  showHookStatus: false
```

