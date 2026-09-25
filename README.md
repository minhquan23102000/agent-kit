# Jev Agent-Kit R&amp;D 

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

Restart omp. Inside omp, run `/login typesafe` once: pilot mode and the skills that call Jev
(everything below except `decompose-facts`) use TypeSafe's Jev model, and the key is kept in
omp's own credential store.

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
| `.agents/skills/decompose-facts`     | Splits anything that has to be checked (code, a spec, a rule, a claim, a request) into small facts that can each be verified alone, plus a list of the parts that cannot. `calibrated-judgment` points to it, so install both. No model calls |
| `.agents/skills/make-rulebooks`      | Extracts a project's rules into a `rulebook.yaml` that a pre-commit hook or CI step can enforce with Jev, another model, or a linter. Every rule is proven by breaking it in a scratch worktree and watching the harm appear |
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


## Decompose facts

A verifier answers whatever it is asked. Ask a judge, a reviewer or a test one question about
three things and it averages them, and the broken one disappears. This skill does the split
before anything is checked, and nothing else: it does not decide who checks each fact and it
does not call a model.

It returns two lists. `atoms`: one fact per line, with the span it comes from (path and lines,
or quoted words) and the probe that would settle it. `not_atoms`: the parts no probe could
settle ("the design hangs together", "the reader feels the loss"), each with a reason. These
are listed on purpose, so the person holding the goal knows what is left to them.

A fact is small enough when it makes one demand, has one way to be settled (arithmetic goes to
code, thresholds are absolute numbers), stands on its own ("as before" is not allowed), applies
to the thing being checked, and could turn out false. For code, `scripts/clerk.py` lists every
branch, return, raise, SQL predicate or key with its line number (`python clerk.py <file>`;
needs `pip install tree-sitter-language-pack`, and the first run for a language downloads its
grammar). Then each atom is checked against its span, and the source against the list.

Use it before judging, testing or reviewing anything bigger than one sentence, or when a check
came back green and you are not sure it checked the right thing. Skip it for a one-line change a
single command already proves. Limits: tried on a handful of cases from its own development and
on one self-audit of a design document, where it found five stale citations; not yet tested on
other kinds of material.

## Make rulebooks

### The problem

A model reviewing a change knows what good code looks like in general and nothing about why your
project forbids what it forbids. Asked whether a commit fixed a crash, Jev passed a plain reading
of the diff at 0.65 with no rule in its state, and at 0.06 once one sentence said what shows a
fix. The skill writes that project law down, one rule at a time, in a form a hook can hand to any
judge.

### What you see

Ask the agent to extract the rules of a repository. It writes `rulebook.yaml` at the repo root:

- a `purpose` block first: who the project serves, what it promises, what it refuses, each quoted
  from the README or docs with `path:line`
- rules, each with a breakable statement, a why, the promise it protects, verbatim evidence, and
  a check kind: `deterministic` (a linter or script), `semantic` (goes to a model), or `human`
  (listed for reviewers)
- a harm probe per rule: `scripts/prove_harm.py` checks HEAD out into a temporary git worktree
  (your working tree is never touched), applies the violation, and runs a command before and
  after. A rule stays a rule only if the harm shows up with the violation and not without it;
  otherwise it is demoted to `status: pattern` and never enforced
- calibration numbers for each semantic rule, from one passing, one failing and one out-of-scope
  example, plus a sweep over the code already merged. Every flag in the sweep is reported as an
  existing defect or fixed in the rule

At the end it tells you which entries are patterns waiting on your confirmation and which are
human checks.

### Running the rulebook

`scripts/build_states.py` never calls a model. It cuts a change into one state per (rule, code
unit touched) and prints one JSON line each:

```sh
python <skill-dir>/scripts/build_states.py rulebook.yaml --staged                  # pre-commit hook
python <skill-dir>/scripts/build_states.py rulebook.yaml --diff origin/main...HEAD # CI
python <skill-dir>/scripts/build_states.py rulebook.yaml --examples                # calibration set
```

Inside omp, the agent feeds those states to `judge_batch`. In a git hook or CI job, where omp's
`judge` does not exist, each line's `request` is a ready body for
`POST https://api.typesafe.ai/v1/systemone`; send it with your own `TYPESAFE_API_KEY`, or send the
same state to another model. The runner decides whether a flag blocks or warns; a rule without
calibration numbers should only warn. Python code is cut by function and class; other languages
fall back to the changed hunk.

### When to use it

Use it to build or refresh a rule set for an AI reviewer, a hook or a CI gate. Skip it for
reviewing one diff right now, or for a style guide only humans will read.

Needs Python 3 and git; PyYAML (`pip install pyyaml`) for a `.yaml` rulebook, or save it as
`.json`.
