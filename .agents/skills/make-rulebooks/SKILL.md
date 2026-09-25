---
name: make-rulebooks
description: >-
  Writes down a codebase's rules (conventions, invariants, architectural constraints, the "we
  always" and "we never" of a project) into a rulebook a pre-commit hook or CI step can enforce
  with Jev, another model, or a linter. Starts from what the project is for: who it serves, what
  it promises them, what it refuses. Every rule names the promise it protects and proves its why
  by breaking the rule in a scratch copy and watching the harm appear; model-checked rules also
  carry the state to send (which code unit to cut from a diff), which units they govern, and
  questions calibrated on real examples and on the merged code. Use when asked to list or extract
  project rules, coding conventions, or code patterns; to generate rules for a hook, CI gate, or
  AI code reviewer; or to decide what state a judge should see for a code change instead of raw
  code. Not for reviewing one diff right now, and not for a human-only style guide.
---

# Make rulebooks

A judge without the project's law falls back on general taste. Asked whether a commit fixed a
crash, Jev passed a plain reading of the diff at 0.65 when its state held no rule, and at 0.06
once one sentence said what shows a fix. A reviewer model stands in the same place with a
repository: it knows what good code looks like in general and nothing about why this project
forbids what it forbids. The rulebook supplies that law, one rule at a time, in a form a hook can
hand to any judge. The change supplies the case. Neither half works without the other.

## What a rule is, and what it is not

A rule has four parts: a **scope** (where it applies), a **statement** (one condition that can be
broken: you can write a change that violates it), a **why** (what breaks, for whom, when it is
violated), and the **promise it protects**, one of the commitments the project makes to the people
it serves. The why is the causal half. It tells a judge what the rule protects, so a boundary case
is judged by purpose; and it tells a maintainer when the rule has outlived its reason.

A why counts only once you have watched it happen. Break the rule in a scratch copy, run the
thing, and see the harm the why names. If you cannot make it appear, you do not understand the
rule, and a rule you do not understand is wrong, however faithfully the code happens to follow it.
A regularity whose harm nobody has made visible is a **pattern**. Forty functions returning
`path:start-end` may be law or an accident of who wrote them. Record it with `status: pattern` and
your hypothesis, labelled as yours. It is never enforced, because enforcing a pattern freezes an
accident, and a rule nobody understands breaks silently the day its context changes.

A rule is also not general good practice restated ("keep functions small"). If a model would judge
it the same way without your project, it adds cost to every call and nothing else. A rulebook
holds what is true *here*, in this project and not in every other.

## Start from what the project is for

Rules are not found by reading code for regularities. They fall out of what the project promises.
Before mining anything, write the `purpose` block from the project's own words: the first
paragraphs of the README, the problem statement of a design doc, the main module's docstring.

- **serves**: who uses it, and to do what.
- **promises**: what it guarantees those people. Inventio says it "tells you where it lives
  (`path:start-end`), so a person or an agent can open the exact lines". The promise is that every
  hit opens on exactly its passage, and every coordinate rule descends from that one sentence.
- **refuses**: what it deliberately does not do, and what that buys. "It uses no embeddings" is a
  refusal, and it binds as hard as a promise: a change that adds a vector index breaks no test and
  still betrays the design.

Each rule answers to one of these through `protects`, and that is the test of whether a candidate
belongs at all. A regularity that protects no promise and no refusal is a habit. Some habits are
law all the same, because their harm lands on the people who work on the project rather than the
ones who use it: updating the README in the same commit as the behavior it describes protects the
promise that the README tells the truth. Write that promise down with its evidence, and the habit
becomes a rule like any other. A habit that protects nothing written anywhere is taste, and taste
is not the rulebook's business.

The purpose is also what a harm is measured against. "Something broke" is not a harm; "the hit
opens on a blank line, so the promised coordinate is wrong" is.

## Where rules live

Read in this order, which is also the order of authority when two sources disagree; within a tier,
the latest explicit decision wins.

1. **Explicit**: README, CONTRIBUTING, AGENTS.md or CLAUDE.md, ADRs and design docs, comments that
   state a constraint (`never`, `must`, `do not`), `pyproject.toml` or `package.json`, lint and
   type-checker config, CI workflows, schemas and migrations.
2. **Enforced**: tests that assert an invariant rather than one example, runtime `assert`s and
   validation, types that make a state unrepresentable.
3. **Historical**: commits that fixed or reverted a violation (`git log --grep` for fix, revert,
   never, must, regression) and the review comments behind them. History tells you where to look,
   never that a rule holds: a commit message is someone's account of a break, and the harm probe
   is how you see it yourself.
4. **Implicit**: a structure repeated across the code. Count it with code, never by impression:
   "31 of 33 public functions return coordinates; the two others are `cli.py:88` and `:140`." The
   exceptions matter as much as the count. Each one is either a violation or the rule's real
   boundary, and you need to know which before the rule goes into a hook.

Keep a candidate only with verbatim evidence and its coordinates. Evidence you paraphrase is your
opinion of the repository, and the rulebook is meant to be the repository's own voice.

## The procedure

Everything goes into `rulebook.yaml` as you go, at the repository root unless the user names
another place. Both scripts validate it before they do anything else.

1. **Write the purpose**: serves, promises, refuses, each with verbatim located evidence.
2. **Inventory the sources** with code: list the files in each tier, read configs and docs whole,
   run the git log searches.
3. **Mine candidates**, one line each, evidence quoted and located.
4. **Find the why and the promise** for each. Source the why (the sentence that gives the reason,
   the code path that depends on the invariant) and name the promise or refusal it protects. No
   promise means a habit (see above); no source means `status: pattern`, with your hypothesis
   labelled as a hypothesis.
5. **Make each rule atomic and breakable.** One condition per rule; a statement with an "and" in
   it is two rules. The change that violates it is the next step's input.
6. **Prove the why** with the harm probe (next section). A rule keeps `status: rule` only when its
   probe comes back `proven`, or, for a harm that lands in a person, when the user has confirmed
   the reader and the wrong decision.
7. **Give each rule the cheapest checker that settles it.**
   - `deterministic`: the condition is syntactic or computable (an import that must not appear, a
     name, a config key, a file that must exist). Prefer a rule the project's own linter already
     has; otherwise a short script, an ast-grep rule, or a regex. A model spent here buys a
     probability where code gives a fact, and on numbers and dates a model is close to useless:
     judging retry spacing from a raw log gave 0.37 when the rule held and 0.29 when it did not.
   - `semantic`: the condition needs reading for meaning (an error message tells the user the next
     step; a test asserts behavior rather than only that nothing raised; a docstring states the
     unit its return value is in). Only these go to a model.
   - `human`: the condition lives in a person (the design fits the architecture's intent). List it
     for reviewers; no hook runs it.
8. **For each semantic rule, write the unit, `applies_when`, and the two criteria** (see "The
   state is never the raw repository" and "Which units a rule governs").
9. **Calibrate each semantic rule** on three units: one that passes, one that fails, and one in
   scope that the rule does not govern (`skip`), the nearest neighbour you can find. The fail is
   the unit the harm probe broke, as it reads after the edit: the violation whose consequence you
   have watched. Keep the rule only when pass and fail both apply well above skip, and pass
   complies well above fail; record the numbers. The runner's thresholds sit between them and stay
   provisional until real changes have been judged. A rule that cannot separate its own examples
   blocks good commits, and a team that gets blocked for nothing turns the hook off, taking every
   good rule with it.
10. **Sweep the code already merged** and explain every flag (see "The sweep" below) before the
    rule goes into a hook.

## Prove the why: break it and watch

The why is a causal claim: this violation causes that harm. The one way to know a causal claim in
the present is to intervene, so the probe makes exactly one intervention and nothing else.
`scripts/prove_harm.py` checks HEAD out into a temporary git worktree (the user's working tree is
never touched), runs the rule's command there as a control, applies the violation as literal
edits, and runs the same command again. The why is proven when `expect` matches the violated run
and not the control: one difference, and the harm appears only with it.

```yaml
harm:
  files: {probe_chunk.py: "<a probe script, written into the scratch tree only>"}
  run: python probe_chunk.py
  edit:
    - {path: inventio/ingest.py, old: "s, ls = _trimmed(s, ls)", new: "s, ls = s, ls"}
  expect: COORD_BROKEN                                  # a regex that names the harm
  observed: "section 1 5 COORD_BROKEN '# A\\n\\nalpha\\n\\n'"  # copied from the probe's output
```

Make the probe print the harm in the promise's own terms rather than a pass or a fail: open the
coordinate and say whether it lands on the text, count the judgments before and after, list what a
fake client was handed. Never let the probe do the harm for real: a privacy rule's probe records
what would have been sent instead of sending it.

The result is one of four, and each teaches something different:

- **proven**: the harm appears with the violation and not without it. Copy the decisive line of
  the violated output into `observed`; that line is the rule's receipt. Dropping one trim call in
  the chunker turned `section 1 3 ok '# A\n\nalpha'` into
  `section 1 5 COORD_BROKEN '# A\n\nalpha\n\n'`.
- **no_harm**: breaking the rule did not produce what the why predicted, so the why is wrong. One
  rulebook said re-chunking would "churn chunk ids, which orphans every judgment and link keyed
  to them". The probe showed the ids coming back identical (SQLite reuses freed row ids) and the
  judgment simply gone, 1 before and 0 after. The rule was right and its why was not, and the why
  is what a judge reads when it decides a boundary case. Another said that cutting a long span
  away from a blank line breaks coordinates; the coordinates stayed exact, and the probe's own
  output showed the real harm, a paragraph cut at its seventh line. Rewrite the why to what you
  watched, or demote the rule to a pattern.
- **already_broken**: the control shows the harm too. Either HEAD already breaks the rule (the
  same probe over a large class printed a head chunk ending on a blank line, a real defect) and
  you report it to the user, or `expect` is so loose that healthy output matches it and you
  tighten it.
- **error**: the probe could not run as written, usually because an `old` text does not occur
  exactly once.

Some harms land in a person, and no command can show them: a documented number with no scope
misleads whoever plans from it. Write those as `reader` (who reads it), `violation` (the text that
breaks the rule), and `misled` (the decision they get wrong). If you cannot name a real reader and
a real wrong decision, you do not understand that rule either. The script lists reader harms for
the user to confirm and never counts them as proven.

## The state is never the raw repository

The unit of judgment is one rule against one piece of code. Everything between the repository and
that pair is done by code, so the state carries nobody's opinion and can be rebuilt from the
rulebook and the diff alone:

```
diff ─► changed files in rule.scope ─► units the change touches, cut by syntax ─► one state per (rule, unit)
```

- **unit**: the smallest syntactic piece the rule speaks about (`function`, `class`, `module`, or
  `hunk` for a language the script cannot parse), with its path and lines. Only units whose lines
  the change touched are judged.
- **rule**: the statement, the why, `applies_when`, `pass_when`, and `fail_when`, verbatim from the
  rulebook. `pass_when` and `fail_when` are where boundary cases go. When a calibration example
  comes back wrong and you catch yourself explaining what the rule really meant, that explanation
  is the missing half of these two lines.
- **questions**: the same two for every rule, in one request. `applies`: "`unit.code` is a case
  `rule.applies_when` describes". `complies`: "`unit.code` satisfies `rule.statement`", with
  criteria pointing at `rule.pass_when` and `rule.fail_when`. A unit is a violation only when it
  applies and does not comply. Because the questions never change, a runner can send every state
  of a change in one batch.

Why not the file, or the whole diff? Because a judge settles about one hop reliably. One
requirement with its defect two calls deep: the whole 18k-character file scored 0.89 when the code
complied and 0.27 when it did not; the three functions of the call chain, 0.85 against 0.08. The
violating case creeps upward as unrelated code fills the state, which is exactly the direction
that lets a bad change through. And a rule that can only be judged by following calls across files
is several rules, or a deterministic one. Split it rather than widening the unit.

## Which units a rule governs

A change touches units a rule has nothing to say about, and `complies` cannot tell them from
violations: its false means both "breaks the rule" and "nothing here to judge". A coordinate rule
run over the sixteen functions of a chunking module flagged thirteen, ten of which never compute
a coordinate; asking `applies` beside it in the same request cut the flags to three. Choosing the
units is a judgment in its own right, so it goes to the model, stated in `applies_when`.

A list of names looks like the cheaper answer and fails in the direction that matters. In one
extraction, 22 of 24 function and class rules were scoped by a name pattern, 18 of them a bare
list of the names that existed that day. A cloud ranker class written afterwards applied at 0.95
and complied at 0.01, a plain violation the list would never have cut, and new code is what a
hook exists to catch. Keep `name` only for a naming convention the tooling itself relies on
(pytest collects `test_*`); the script refuses a pattern that is nothing but literal names.

Word `applies_when` by what the unit handles, never by what the rule demands of it. "Decides which
files a re-run reads again" stopped applying to the very code that skipped the decision: 0.44 on
the violating example against 0.95 on the compliant one. "Goes over a source's files during an
index run and passes them on to be read" applied to both (0.88 and 0.95), because a violation
changes how a unit does its job, not which job it has. Then name the nearest thing the rule does
not cover. A local-model ranker applied to a cloud-privacy rule at 0.77 until one sentence said a
model downloaded once and run on this machine does not count; after it, below 0.4.

## The rulebook

```yaml
project: <name>
purpose:
  serves: <who uses the project, and to do what, in its own words>
  promises:
    - {id: P1, promise: <what it guarantees them>, evidence: "<path>:<line>: '<verbatim quote>'"}
  refuses:
    - {id: R1, choice: <what it deliberately does not do, and what that buys>, evidence: "..."}
rules:
  - id: <PREFIX-NNN>
    statement: <one condition a change could break>
    why: <what breaks, for whom, when it is violated>
    scope: ["<glob>", ...]
    status: rule              # or pattern: no watched harm yet, never enforced
    protects: P1              # a promise or refusal id; required for status: rule
    evidence:
      - "<path>:<line>: '<verbatim quote>'"
      - "<a count computed by code, with the exceptions located>"
    check:
      kind: semantic          # deterministic | semantic | human
      unit: function          # semantic: function | class | module | hunk
      applies_when: <which units the rule governs, by what they handle; then the nearest case it does not>
      name: "^test_"          # optional: only a naming convention the tooling itself relies on
      pass_when: <what a compliant unit looks like>
      fail_when: <what a violating unit looks like>
      # deterministic instead: command: "ruff check --select D103 {files}"
    examples:                 # semantic: at least one pass, one fail, one skip
      - {expect: pass, ref: "<path>:<start>-<end>"}
      - {expect: fail, ref: "<path>:<start>-<end>", note: "<the commit that fixed it>"}
      # or: {expect: fail, path: "<path>", code: "<mutated unit>", note: "synthetic: <what changed>"}
      - {expect: skip, ref: "<path>:<start>-<end>", note: "<why the rule does not govern it>"}
    calibration:
      pass: {applies: <p>, complies: <p>}
      fail: {applies: <p>, complies: <p>}
      skip: {applies: <p>}
      sweep: {units: <n>, flags: <n>}   # every flag explained, see "The sweep"
      model: <model id>
    harm:                     # required for status: rule; see "Prove the why"
      files: {<probe path>: <probe script>}
      run: <command, run in the scratch tree before and after the edit>
      edit:
        - {path: <path>, old: <text that occurs once>, new: <the violation>}
      expect: <regex on the output that names the harm>
      observed: <the decisive line of the violated output>
      # or, for a harm that lands in a person: reader, violation, misled
```

## The bundled scripts

`scripts/build_states.py` validates the rulebook and does the cut; `scripts/prove_harm.py` runs
the harm probes. Run them; do not paste them.

```sh
python <skill-dir>/scripts/build_states.py rulebook.yaml --examples                # calibration set
python <skill-dir>/scripts/build_states.py rulebook.yaml --sweep                   # all merged code in scope
python <skill-dir>/scripts/build_states.py rulebook.yaml --staged                  # pre-commit hook
python <skill-dir>/scripts/build_states.py rulebook.yaml --diff origin/main...HEAD # CI
python <skill-dir>/scripts/build_states.py rulebook.yaml --files src/a.py          # audit a file
python <skill-dir>/scripts/prove_harm.py rulebook.yaml                             # every harm probe
python <skill-dir>/scripts/prove_harm.py rulebook.yaml CHUNK-001                   # one rule
```

Each output line is `{"meta", "request"}` for a semantic rule, or `{"meta", "command"}` for a
deterministic rule, with the changed files in scope put in place of `{files}`. Patterns and human
checks are never emitted. Python is cut by syntax; other languages fall back to the changed hunk
with three lines of context, marked `"kind": "hunk"`.

Where the verdict comes from depends on where the check runs, because `judge` and `judge_batch`
exist only inside the omp eval kernel. No script, git hook, or CI job can import them, and the
script never calls a model.

- **Inside omp** (calibrating the rulebook, or an agent checking its own change before it
  commits): run the script, then feed its states to `judge_batch` in the eval kernel. The kernel
  names a Noul `bool`.

  ```python
  import json, subprocess
  SCRIPT = "<skill-dir>/scripts/build_states.py"
  out = subprocess.run(["python", SCRIPT, "rulebook.yaml", "--examples"],
                       capture_output=True, text=True, check=True).stdout
  rows = [r for r in map(json.loads, out.splitlines()) if "request" in r]
  questions = {k: dict(q, type="bool") for k, q in rows[0]["request"]["questions"].items()}
  batch = judge_batch({i: r["request"]["state"] for i, r in enumerate(rows)}, questions,
                      intent="calibrating rules")
  results = {}
  async for i, item in batch.drain_iter(120):
      results[i] = (rows[i]["meta"], item.answers["applies"]["bool"], item.answers["complies"]["bool"])
  ```

- **Outside omp** (a git hook, a CI job): `request` is already a TypeSafe `POST
  https://api.typesafe.ai/v1/systemone` body with both questions in it. The runner sends it with
  its own key (`Authorization: Bearer $TYPESAFE_API_KEY`), since omp's credential does not travel
  into a hook, or sends the same `state` and questions to another model.

Either way the gate is the runner's code: flag a unit when `applies >= A and complies < C`, with
`A` and `C` set between the calibration numbers (0.5 each until they exist). The runner also owns
whether a flag blocks or warns; a rule without `calibration` should only warn.

Read each rule's three examples side by side. A fail that complies high usually means `fail_when`
describes the violation too loosely, or the unit is too large for the violation to stand out; a
pass that complies low usually means `pass_when` asks for more than the rule does. A fail that
stops applying means `applies_when` was worded by what the rule demands instead of what the unit
handles; a skip that applies means `applies_when` never named its boundary.

## The sweep: merged code is the second calibration set

Three examples prove a rule can separate its own cases. They say nothing about how often it will
cry wolf, and the code already merged does, because the team accepted it. Run `--sweep`, judge
every state, and read every flag. Each is one of three things, with a different fix:

- **A violation that was already there.** Report it to the user with the unit and the rule; never
  weaken the rule to make it pass. On one repository the sweep flagged the two chunkers that build
  a large class's head chunk themselves, and running them showed that chunk ending on a blank
  line: the exact wrong coordinate the rule exists to prevent.
- **A check that lives one call away.** Units that hand the work to a helper are flagged because
  the judge cannot see the helper. Do not write the helper into `pass_when`: tried on those
  chunkers, it lifted the violating example to 0.58 and hid the real defect from the sweep. Split
  the rule instead. The semantic rule judges the helper, where the guarantee is made, and a
  deterministic rule checks that every path goes through it; there, that the chunk constructor is
  called only inside the helper, which finds exactly the two defective sites.
- **A boundary the criteria never stated.** A test that builds the real cloud ranker with a fake
  key, only to prove it refuses before any call, reads as a breach of "never constructs a real
  ranker". The explanation you would give a reviewer is the missing sentence of `pass_when`; write
  it there and calibrate again.

Record the unit and flag counts in `calibration.sweep`. A rule goes into a hook only when every
flag is one of these three and has been handled, because a rule that flags accepted code blocks the
next person who touches that code, for nothing they did.

## Keeping the rulebook true

- Re-extract when a source changes: a doc edited, a lint rule added, an ADR superseding another.
  Before keeping an old rule, grep for supersession (`supersedes`, `deprecated`, `no longer`,
  `removed in`). A rule still on the books after its reason is gone is the most expensive kind,
  because it blocks correct work with the project's own authority.
- A rule that keeps failing on changes reviewers accept is wrong or mis-scoped, not the
  reviewers. Fix its criteria or scope and calibrate again.
- Re-run the harm probes when the code a rule protects changes shape. A probe that starts
  erroring means its `old` text moved; one that turns `no_harm` means the guarantee now lives
  somewhere else, and the rule has to follow it there.

## Done means

- The purpose names who the project serves, its promises, and its refusals, each with verbatim
  located evidence.
- Every rule has one breakable statement, a why, the promise or refusal it `protects`, verbatim
  located evidence, and a check kind.
- Every `status: rule` entry has a harm: a probe that came back `proven` with its `observed` line
  copied in, or a reader harm the user has confirmed. Every `already_broken` result is reported to
  the user as a defect in the code.
- Every semantic rule has an `applies_when` worded by what the unit handles, and calibration
  numbers from a real pass, a real or marked-synthetic fail, and a skip: pass and fail apply well
  above skip, and pass complies well above fail.
- Every semantic rule has been swept over the merged code, and every flag is reported as a
  violation, split out as a helper-plus-routing pair, or closed with a `pass_when` sentence.
- `build_states.py --examples` runs on the rulebook without a validation error.
- The user is told which entries are patterns waiting on their confirmation and which are human
  checks: the parts of the project's law that only they can settle.
