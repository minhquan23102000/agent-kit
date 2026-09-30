# Jev Agent Kit

Skills, an extension and two subagents for [omp](https://github.com/can1357/oh-my-pi). They hand the
agent's small judgments (is this done, which element to click, does this rule hold) to Jev, a fast
model that answers typed questions with probabilities, so the big model stops grading its own work.
Nothing personal is included: no profile, no model config.

## Install

Paste this to your omp agent:

```text
Install agent-kit into my omp setup.
1. Clone https://github.com/minhquan23102000/agent-kit.git to ~/agent-kit (git pull if it is already
   there), run ~/agent-kit/install.sh and show me its output. If it reports a conflict, stop and tell
   me which file; do not move or delete anything.
2. In ~/.omp/agent/config.yml, add what is missing and keep everything already there:
   - skills.customDirectories contains ~/.omp/.agents/skills
   - modelRoles.advisor is set. If it is not, list the models I can use and ask me which strong
     reasoning model to pick. Do not choose for me.
   Show me the config.yml diff.
3. Ask me whether I want the pilot chip in my status line. Only if I say yes, add `status` to
   statusLine.leftSegments (with no custom status line yet: preset custom,
   leftSegments [pi, model, mode, status, path, git, context_pct, cost]).
4. Run ~/agent-kit/install.sh --status and check every line says "linked".
5. Tell me to run /login typesafe inside omp, then restart omp.
```

Update: `git -C ~/agent-kit pull`, then restart omp. The installer makes symlinks, so a pull updates
everything. Uninstall: delete the links that `install.sh --status` lists.

## What's inside

| Name | Kind | What it does | Needs |
|---|---|---|---|
| `jev-pilot` | extension | `/pilot` mode. Edits stay blocked until you agree the goal and criteria and the approach is recorded. Before "done", the agent must quote real tool output for each criterion, and Jev judges each one | TypeSafe login, both oracles |
| `oracle` | subagent | Read-only second opinion on an approach that could cost the architecture | `advisor` model role |
| `oracle-light` | subagent | Quick read-only check of a contained approach that Jev doubted | the `smol` model role |
| `calibrated-judgment` | skill | Turns gut checks ("is this done?", "is there enough evidence?") into calibrated Jev judgments. Pilot mode reads its reference files | `decompose-facts` |
| `decompose-facts` | skill | Splits code, a spec or a claim into small facts that can each be checked alone, and lists what cannot be checked. Makes no model calls | Python 3, `pip install tree-sitter-language-pack` for code |
| `make-rulebooks` | skill | Writes a repo's rules to `rulebook.yaml` for a hook or CI step. Each rule is kept only after breaking it in a scratch worktree shows the harm | Python 3, git, `pip install pyyaml` |
| `browser-autopilot` | skill | Drives a browser flow (log in, fill a form, check out). Your main model writes the plan once and Jev picks each click. Hands control back when unsure. Not for visual or pixel checks | — |

Skills that call Jev fall back to your small chat model when you are not logged in to TypeSafe.
Pilot mode does not fall back: it needs the login.

## Using it

| You want | Do this |
|---|---|
| A risky or vague task done without the agent grading itself | Type the task, then `/pilot`. Answer its questions with `ok`, `D1 b`, or `change criterion 2 to …`. `/pilot show` lists the goal and criteria; `/pilot` again turns it off |
| A browser flow done cheaply | Ask the agent to use browser-autopilot, with the steps and the values to type |
| To watch what Jev decides | Ask for browser-autopilot in demo mode. A visible browser draws a box around each candidate element, the chosen one in pink, and a panel with the plan |
| Rules for an AI reviewer or a CI gate | Ask the agent to extract the rules of the repo with make-rulebooks |
| To check something bigger than one sentence | Ask the agent to decompose it into facts before judging or testing it |

Put thresholds in criteria as absolute numbers ("20 s or less"), never relative ones ("twice as
fast"). Jev does not do arithmetic.

## Measured so far

| What | Result | Limit |
|---|---|---|
| browser-autopilot on the local demo shop (sign-in, options, cart, checkout form), 29/9, Opus 5.5 | With autopilot: 5 Opus turns, $0.07 of Opus. Without: 17 turns, $0.30. Both placed the right order | One run each. Jev's cost not counted. Demo mode pauses on purpose, so its time (2m09s against 1m18s) is not a speed comparison |
| make-rulebooks, one rule in the state | Jev passed "did this commit fix the crash" at 0.65 without the rule and 0.06 with it | One example |
| jev-pilot | Tested on small real tasks | Not yet compared against a run without it on a hard task |

Each skill's `SKILL.md` holds the details. To record the with/without demo yourself, see
`.agents/skills/browser-autopilot/demo/record.py` (needs `bun add @xterm/xterm@5 @xterm/addon-fit`
in `~/.omp/vendor/xterm` once).
