---
name: calibrated-judgment
description: >-
  Turns an agent's own gut-check judgments into calibrated typed decisions with omp's
  judge/judge_batch (the Jev System-One model), and builds the state Jev needs: evidence
  preprocessed so it can be settled in one step, plus the standard and the causal rule it is
  judged under. Use when about to assert "done", "this works", "fixed", or "enough context" and a
  calibrated second opinion beats self-certifying; when deciding what goes into a judge's state or
  how to preprocess logs, code, or diffs for it; when verifying a claim against evidence, checking
  sufficiency before acting, testing whether your questions test the real goal, scoring against a
  rubric, or gating a ship; and when the user mentions Jev, judge, TypeSafe, calibrated judgment,
  noul, or LLM-as-judge. Not for multi-step reasoning or planning (it answers atomic gut-checks
  only), and not for checks code can compute exactly.
---

# Calibrated judgment

You make dozens of silent judgments a turn: is this done, is this correct, do I have enough to
decide, which way now. Made inside your own text stream, those judgments are uncalibrated and
biased toward finishing — you tend to certify your own work. `judge` hands one such judgment to
Jev, a model trained to return a *calibrated* typed answer over a state you give it.

Know what Jev is before you feed it. It is a structured predictor: it reads the state you wrote and
spreads probability over the answers you declared. It holds no model of the world and no causal
model in its weights, it reads your words literally, and it is reliable for about one step of
inference. It cannot compute the gap between two timestamps, follow a defect two calls deep through
a large file, or know on its own that reading a diff is not the same as running the code.
Understanding did not vanish from this arrangement; it moved into the state, the question, and the
code that combines the answers. That address is you.

Four roles, and the middle two decide the outcome:

- **you generate**: you choose what to ask, and what to do with the answer.
- **you witness**: you go out into the environment and carry back what was there.
- **you compile**: you turn what you carried into a state Jev can settle in one literal step, and
  you bring the law it is judged under.
- **Jev discriminates**: it collapses that state into a typed answer with a probability. It cannot
  plan, cannot act, never visits the scene, and cannot supply a causal link you left out.

The judge sees your state, never the world it came from. So the ceiling on the verdict is set by
what you carried in and how you compiled it, not by how well you asked. Keep the reasoning and the
planning for yourself, and spend the real work on the state.

## What "complete" means for a state

A state is complete for one judgment when it is **closed under that judgment**: it contains every
fact in the environment that could change the answer. Not every fact there is.

The test is a counterfactual you run on yourself: name a fact outside the state that would flip the
verdict if Jev saw it. Name one and find it missing, and the state is not closed — which means the
number coming back is about your excerpt, not about the world.

So the thing to carry is the **decisive difference**, not the supporting pile. The environment is
always larger than any state; closing it never means including everything, only everything that can
move the answer.

"The environment" means everything around the judgment: the world itself (the runtime, the bytes,
what actually happened), the artifact under judgment, the process that produced it, the constraints
and standards it answers to, the decisions already taken, and your own beliefs about all of it. That
last part never shows up in a state and is the part most likely to be wrong. So put a belief of your
own into the state as the `claim`: a belief left in your head is the one field Jev never gets to
check.

Jev cannot volunteer what is missing. It sees a state that looks whole, and a hole is invisible from
inside. It can only point at a hole you name as a candidate, which is what the probe below does.
Closure is your work, and it is where the judgments actually go wrong.

Closure is half. The other half is **one hop**: the answer has to sit one literal step from the
fields. A state can hold every decisive fact and still fail, because the fact is in a form Jev
cannot read: two timestamps whose gap is the question, a defect buried in a file full of things
the question does not need, an agent's summary standing where the output should be. Measured on
three claims, each judged once in a world where it is true and once where it is false:

| claim | what the state carried | true world | false world |
|---|---|---|---|
| retries wait at least 2.0 s | the raw log, 49 lines, other hosts interleaved | 0.37 | 0.29 |
| retries wait at least 2.0 s | the same log, gaps computed by code | 0.86 | 0.02 |
| exports skip soft-deleted rows | the whole source file, 18k chars, defect two calls deep | 0.89 | 0.27 |
| exports skip soft-deleted rows | the three functions of the call chain, cut by code | 0.85 | 0.08 |
| exports skip soft-deleted rows | the export run on a fixture holding one deleted row | 0.83 | 0.01 |
| grouped amounts parse per spec | the agent's summary: "handles separators, all 12 tests pass" | 0.47 | 0.49 |

Read each pair as a gap. The raw log cannot tell the broken retry loop from the working one; the
computed gaps can, and at that point code can decide it outright, so the call is no longer needed.
Source code is readable, but the false world creeps upward as the file fills with things the
question does not need (0.08, then 0.27), and that is the direction a gate fails in. The summary
cannot separate the worlds at all: it is your belief, and Jev is judging your belief.

## Build the state: six moves

**1. Scoop from the environment, not from memory.** Re-read the actual bytes now: the file, the tool
output, the user's words. Retyping from memory is fabrication with a delay, and a field that
misreads the source becomes a confident wrong number — the one failure no calibration can catch for
you, because Jev never sees the source, only your field.

Clean has one operational meaning here: nothing in the evidence was written by the party whose work
is being judged. Every value in it came out of code you ran (keep the command beside it) or is a
verbatim cut (keep its coordinates). The only field you author is the `claim`, and it has its own
field so that your words never leak into the evidence. "Handles separators correctly, all tests
pass" is the claim again, filed under evidence.

Raw does not mean whole. When the decisive thing is larger than the state can hold — a 10,000-line
log, a whole chapter, a 400-file diff — carry the *span*, not the artifact, and carry its
coordinates with it: `"build.log lines 4182-4210"`, quoted verbatim. A located span is still raw and
still auditable; a summary is neither. If finding the span needs judgment rather than a grep, make
the locate its own question — a `choice` over the candidate spans you found in code — and put the
winner in the state.

**2. Break the artifact into facts, then find the decisive one.** The first field of the state is the
list, so a state without it is not a state. An artifact is a bundle of facts, and "is this
right?" asked of a bundle gets answered by averaging, which hides the one broken part. The split
itself (the five conditions a fact must meet, listing from the bytes, the two-way check, and the
list of parts that cannot become a fact) is the
`decompose-facts` skill. Read it and use its `atoms` as this field; its `not_atoms` are the part
of the judgment that stays with the human.

Two things it hands you that matter here. The fact list is an **index, not evidence**: the state
carries the evidence the decisive fact points at (the verbatim span, or the output code produced
for it), so Jev can see whether the fact matches it. And filter before you judge: a fact no
criterion touches is not judged, so only the handful that can move the answer needs its evidence
carried.

Then ask which of them can flip the answer. That one is the decisive difference, and it is what you
go get. What the claim asserts decides which receipt can carry it, and there are three rungs:

- **What the artifact says**: read it. A span of the file, the config, the doc.
- **What it does**: produce it. Behavior cannot be read out of source, however carefully; run the
  thing, then scoop the output. This is why a claim about behavior needs a receipt, not a source
  listing.
- **What the change caused**: the same input, run before the change and after it. "Fixed",
  "prevents", "broke", "made it faster" are claims about cause. A run after the change alone shows
  the behavior now, not that the change produced it, because the input may never have failed.

A receipt from a lower rung cannot carry a claim from a higher one, however well it is written.
This is Pearl's ladder (seeing, doing, imagining) in working clothes. For deterministic code the
before-and-after run on one input *is* the counterfactual, which is why the top rung is cheap in
software and expensive nearly everywhere else. Jev will not climb the ladder for you; it has no
causal model to climb with.

When the artifact is a **change** (a diff, a revision), the facts are about the delta, and the
standard is whatever the delta was supposed to accomplish.

**3. Compile the decisive fact down to one hop.** Before it enters the state, do to it everything
code can do:

- arithmetic, counts, time gaps, date order, sorting: compute them and carry the result, because
  Jev reads numbers and dates as text;
- behavior: run it (move 2), and carry the output of the run, not the source that would produce it;
- a defect spread across several places: cut out only the path that matters (the call chain, the
  changed hunk, the one config key), with coordinates;
- anything Jev would have to generate (a value, a span): find the candidates in code and let Jev
  choose among them.

Then look at what is left. Often nothing is: the gap is under 2.0 seconds or it is not, and code
has decided. There is no judgment to ask for. Jev earns its call on the residue that only reading
can settle: whether an error message tells the user what to do next, whether a test exercises the
path the bug lived on, whether a change acts on the cause the diagnosis shows.

**4. Fetch the law, verbatim, into its own fields.** The law has two parts, and a state usually
needs both.

The **standard** is what the artifact has to satisfy: the contract, spec, canon, policy, or the
user's words. It is a fact about the world, so it belongs in the **state**, not in your question.
Quote it from its source; do not paraphrase it into your own prose. Without it Jev does not
abstain: it substitutes its own general taste for your contract and answers a question you did not
ask. In the worked example below, the same raw receipt scores 0.72 without the standard and 0.06
with it.

The **rule** is what observation establishes a claim of this kind, and why: the causal link from
the evidence to the claim. Every claim you make about your own work is causal in the end (this
change fixed that, this test shows that, this run means that), and Jev brings no causal model of
its own. Leave the rule out and it falls back on common sense, which passes whatever sounds
plausible. One claim, "commit 4c1e fixed the crash `summarize()` raised on empty input", four
receipts, with and without one sentence of rule:

| evidence | no rule | with rule |
|---|---|---|
| the diff: a guard added before `rows[0]` | **0.65** | 0.06 |
| after the commit, `summarize([])` returned `{}` | 0.40 | 0.04 |
| same input: raised `IndexError` before, returned `{}` after | 0.87 | 0.92 |
| same input: returned `{}` before and after | 0.05 | 0.03 |

The rule was: *"A change is shown to have fixed a failure only by running the same input twice: the
failure occurs before the change and does not occur after it. Reading the diff shows what was
edited, not what it does. A successful run after the change alone does not show a fix, because
that input may never have failed."* Without it, reading your own diff passes as proof at 0.65,
which is the most common false "fixed" there is. With it, Jev applies the ladder from move 2
faithfully, because a stated rule is exactly what a literal reader follows well.

Take the rule from a source when one exists: the project's testing policy, a spec's definition of
done, the domain's own mechanism. When you write it yourself you are supplying causal structure, so
write it as a rule anyone could check against any case, never as a verdict on this one.

**5. Sweep for the counter.** A sweep is a search, not a glance at the file next door. Grep the
environment for the artifact's identifier, and for supersession language — `supersedes`,
`deprecated`, `no longer`, `removed in` — because a requirement can still be on the books after the
reason for it is gone, and a fact that obsoletes the standard is a counter too. Then write the scope
*inside* the field: `"searched docs/**, CHANGELOG, git log for a supersession of SPEC-31: none"`. An
absence is evidence only when it names where you looked. `"found none"` with no scope is not an
empty counter, it is the hole wearing a label. The sweep ends when what is left cannot flip the
answer, not when the hits run out: two hundred grep results are swept the moment none of the
remainder can move the verdict.

**6. Re-scoop if the environment moved.** The state is a snapshot of something moving. Any field
taken before your last edit, last tool call, or last thing the user said may already be false.

What falls out is six fields, and the names are the point:

```python
state = {
    "facts":    ["...", "..."],  # every path, one line each; the whole bundle
    "claim":    "...",           # the one fact from that list you are about to assert; the only field you write
    "evidence": "...",           # compiled: values code computed and verbatim spans, each with its command or coordinates
    "standard": "...",           # what the artifact must satisfy, quoted from its source
    "rule":     "...",           # what observation establishes a claim of this kind, and why
    "counter":  "...",           # the best disconfirming fact, or "searched X, Y: none"
}
```

The list goes in whole because its completeness is the thing you are worst at judging, and a list
you can see is a list you can check against the artifact. Everything else in the state is about the
one fact you pulled out of it.

Claim and evidence stay separate fields because Jev can only see the gap between them while they are
apart. Merged, there is nothing left to check. Standard and rule stay apart for the same reason: one
says what must be true, the other what would show it, and only while they are separate can Jev see
a receipt from the wrong rung.

Take one snapshot of the environment per gate, not one per question. Every criterion live at this
moment is judged against that snapshot, so no two criteria end up measured against different
worlds; a second scoop for the second criterion is a second world. When the snapshot is small, send
it whole to every question. When it is too large to be one hop from each of them, cut a projection
per criterion out of that same snapshot (move 3), never a fresh scoop.

## Close the state before you trust it

The sufficiency question everyone asks first — "is this enough to decide?" — is nearly useless,
because it is asked about a state that looks whole, so it comes back yes. Ask the referential
version instead, which is a judgment about the state's shape:

- "Does answering this require a fact that is not in this state?"
- Stronger: hand Jev a candidate list of the facts that could be decisive and let it point at the
  one that is. You generate the space — that is reasoning, and it cannot be offloaded — and Jev
  picks.

Run against a state with the standard removed, that probe answers `requirement 0.99`, `caller 0`,
`tests 0.01`, `impl 0`. It points straight at the hole, and you go fetch it. At a gate the sequence
becomes **scoop → probe for the hole → fetch → re-scoop → judge**, and it runs once, not
continuously.

## The call

`judge` is a native omp eval builtin — no import, no setup script. It needs a TypeSafe
credential; log in once (`omp auth-broker login typesafe`) and it resolves from omp's global
credential store in every session and directory, so no per-project `.env` and no extension are
required. With no credential it silently falls back to a smaller model, so treat results as less
calibrated. To confirm one is live, read the login screen or the credential store —
`omp auth-broker status` reports whether a broker *daemon* is running, not whether a key exists,
so it is not that check.

Runs in the eval kernel:

```python
ans = await judge(state, {
    "grounded": {"type": "bool",
        "instructions": "The evidence demonstrates the claim is true.",
        "criteria": {"true": "evidence shows the exact behavior claimed",
                     "false": "evidence is missing, tangential, or does not establish it"}},
})
# ans -> {"grounded": {"bool": 0.0 .. 1.0}}
```

- `state`: a string, or better the object built above. This is everything Jev sees.
- Three question types, mixed freely in one call, each answered in parallel and in isolation:
  - `bool` (Noul): probability 0..1 that a statement holds. Near 0.5 means genuinely unsure, not "medium intensity".
  - `choice`: pick one label from `criteria`; returns `choice`, `probabilities`, `confidence`. It
    settles *which* label wins, not how likely each one is: a coin stated as 60% heads came back
    heads 0.99 as a `choice` and 0.58 as a `bool` (Arcturus Labs, 401 requests). When you need how
    likely something is, ask a `bool`.
  - `score`: a level on an ordered rubric; returns `score`, `probabilities`, `confidence`.
- `confidence` measures how concentrated the distribution is, not whether the answer is correct and not permission to act. Several good options can spread it; ignore it on branches you never use.
- Many states at once: `judge_batch`. Adding questions to one call barely changes latency, so ask every independent question together rather than in a loop.
- **A verdict fanned over many items needs an applicability question beside it.** A `bool` asking
  whether an item meets a criterion returns false both for an item that breaks it and for one the
  criterion never governed, so a batch reads every bystander as a failure. One coding rule fanned
  over sixteen functions of a module flagged thirteen, ten of them functions it never governed; an
  `applies` question in the same call cut the flags to three. Gate on both in your own code, and word
  the applicability by what the item handles, not by what the criterion demands, or the violation
  that skips the demanded step stops applying (0.44 against 0.95 for the compliant item).
- **Do not ask what code decides exactly.** A count, a checksum, a parse, a threshold, a diff, a
  sort order — if a deterministic check can settle it, run that check instead. Jev is for the part
  where code cannot decide, and spending a judgment on arithmetic you could have executed buys a
  probability where you could have had a fact.
- Point a question at state fields by path, in backticks: "Does `evidence` satisfy `standard`?" A
  question that does not say which part of the state it means gets answered against whichever part
  reads most like an answer. Question IDs are for your code and are never sent to the model, so write
  the whole question in `instructions`.
- **Cheap sanity check, and its limit.** In the same call, also ask the claim's negation. A
  trustworthy pair is *roughly* complementary — near 1.0, not exactly, since each question is
  scored in isolation, so the red flag is a pair that endorses both sides or sums far from 1.
  This catches contradiction, not a biased state: wording a claim as "obvious" or "doubtful"
  measurably nudges the score (a plain false fact sat at 0.01; the same fact dressed in doubt
  drifted to 0.18). Keep the claim and evidence worded plainly.

## The script and three references

One script and three references ship with this skill. Reach for them instead of re-deriving them;
the script is executed, never pasted into context. Enumerating an artifact into facts (including
the `clerk.py` script for code) lives in `decompose-facts`.

- **The gatekeeper, always**: `from verify import verify`, then
  `await verify(judge, facts=..., claim=..., evidence=..., standard=..., rule=..., counter=...,
  questions=..., pairs={"claim_holds": "claim_fails"})`.
  It refuses a state with a blank field, a one-entry fact list, or a counter that names no scope,
  and it reports the sums of any declared pair so a contradictory pair cannot pass unnoticed. It
  warns when the evidence names no command, output, or coordinates (a summary wearing the evidence
  label), and when the claim asserts a cause (fixed, prevents, works) with no `rule`.
  Declare the pair whenever the two ids do not follow the `not_<id>` convention, because nothing
  mechanical recognises an antonym. Use it in place of calling `judge` directly.
- **The comprehension check, before you commit to what the user meant**:
  `references/goal-comprehension.md`. Read it when you are about to derive a standard from a
  request whose wording leaves more than one reading open. It holds the tested question wording,
  how to read the answer, and the two formulations that died and why. Recording the user's words
  is not understanding them — a session can trace every link perfectly and still produce the
  wrong thing, because the words were right there and the meaning was not.
- **The solution check, before you execute an approach**: `references/solution-confidence.md`.
  Read it when you have diagnosed a problem and proposed how to fix it, and are about to spend the
  execution on that proposal. It holds the tested question that sizes what a wrong approach would
  cost, and the formulation that died because it measured form instead of substance.
- **The done gate, before you claim the work is finished**: `references/review-verification.md`.
  Read it when you are about to yield or tell the user the work is done. It holds where the
  standard at that gate has to come from, and the measured reason a single "does it meet the
  standard?" question must be split one criterion per question.

## Ask the right question, not just ask it well

The six moves get a state *complete*. They do not make it the *right* state, and a clean answer
over the wrong state is the expensive failure. You choose what to ask and you write the `criteria`
inside the question, so a confident all-green can just mean you tried the artifact on the wrong
charges. You cannot repair this by asking Jev "is my question right?" — that is one more judgment
over a state you wrote, so it moves the problem up a level instead of ending it. The regress ends
only outside Jev, at the source of the goal.

- **Take the criteria from the source, and the standard into the state.** Each criterion the source
  demands becomes one atomic question; the standard they are judged against is a state field (move
  3). A criterion you cannot trace to a phrase in the source is *inferred* — mark it, because that
  is where you are projecting your own idea of the goal.
- **One question per criterion; drop nothing silently.** Enumerating the criteria is your reasoning,
  not Jev's: knowing every way the goal can fail *is* understanding the goal, and that is the part
  that cannot be offloaded. Set the criteria against the facts from move 2 as a grid and read the gaps
  on both sides: a criterion no fact covers is an untested requirement, and a fact no criterion
  covers is either surplus or a requirement nobody ever wrote down.
- **Compose the answers in your own code.** A judgment that turns on several factors is several
  questions, and the combination is arithmetic you own, with weights you can change and re-run
  without re-asking. Jev returns per-factor signals and never the composite, so "rate this pitch" is
  the wrong question and "market size, feasibility, differentiation" is three right ones. The
  causal structure between the factors lives here too, so write it as the logic it is: when one
  unmet factor sinks the whole, take the minimum or an AND; when two signals matter only together,
  test them together. A weighted sum quietly assumes the factors act independently, and it will
  average away exactly the combination that mattered.
- **Run the negative probe — the highest-value move.** Ask *yourself*, not Jev: if every one of
  these checks came back green, what is the most plausible way the real goal is still unmet? If you
  can name a scenario, you are missing a question; add it. It costs no call and catches the common
  failure — passing your own checks on a target you quietly picked wrong.
- **Keep one Goodhart tripwire.** Add a single `bool` to the fan-out: "could all these checks pass
  while the stated goal is still unmet?" High = stop and look again; low tells you *nothing* — it
  is never a pass. Worth one cheap question, no more meta-checking than that. Keep it inside the
  fan-out, over the same small state as the checks it guards: asked once over a whole document it
  pins near the top and stays there. A judgment that does not move when the artifact moves is
  broken, not reassuring, so measure it against a deliberately worse version of the same artifact
  before you believe either number.
- **Stable criteria, moving focus.** The criteria are fixed by the source; each time you pick only
  the ones live at the current step and re-derive their questions. Re-enumerate from scratch only
  when the *source* changes — the user amends the goal, the spec moves — not when your own
  understanding drifts.
- **On a hard gate, show the questions, not just the answers.** Whether you enumerated the right
  criteria is the one audit no self-check closes; the only reliable auditor is someone holding the
  true goal. At the gates below, surface *what you checked* to the human, not only the ticks.
- **Climb the ladder only as far as the stakes demand.** Defenses against the wrong question run
  cheap-and-inside to strong-and-outside: the negative probe (your own thinking) catches what you
  can imagine; re-checking (reflection) catches carelessness but never a blind spot and can harden
  a wrong answer; an oracle — a fresh, stronger, adversarial second agent — is a different set of
  eyes but still shares your training's blind spots; only an external check (a test that runs, the
  human holding the true goal) closes the blind spot. Small work stops low; irreversible work must
  reach the top. Measured: on a one-line bug fix (a CSV loader that left `qty` a string), agents
  told to run every gate took 87-102 s against 29-32 s for agents working plainly, and all eight
  runs fixed the same root cause. When the cause is visible in one read and a command proves the
  fix, the command is the gate; the calls add time and change nothing.

## When to fire: three gates, not a heartbeat

This is not a loop, and Jev is not a heartbeat. Nothing happens between the gates below — no polling,
no judging every step, no re-checking what has not moved. A gate opens when something is about to
leave your hands: a claim you are about to state, a plan you are about to commit to, an action you
cannot undo. If nothing is leaving, there is no gate, and you just work.

You will not notice you are "in phase 4". You will notice you just ran something, that you are
about to claim it works, or that you are about to hand the work over. Anchor the judgment to those
moments — the ones you already recognize from the inside — not to a place in a plan you have to
remember to consult. That is the difference between a skill that runs every time and one that gets
read once and dropped. Three moments, and one rule that rides across all of them.

**Between moments, Jev advises and you decide.** Surface the probability and keep moving; it is a
second opinion, not a verdict, and treating every step as a checkpoint just slows the work.

- **About to commit to a plan or design.** Fire a `bool` sufficiency: does the state hold enough to
  decide this without guessing? Low means read more or ask first — you are not ready to design yet.
  Planning is yours (Jev gates the entry, never writes the plan).
- **About to claim something you just produced works.** The instant before you write "tests pass",
  "the bug is fixed", "the data is clean" — fire a `bool` grounding on that one claim, over the raw
  receipt. Advise-weight, not a gate: low means the claim has no basis yet, so look again or run it
  again. It does not stop the work; it stops the false claim. This is the fire that keeps getting
  dropped, and it is what makes the judgment change the work instead of decorating the end.
- **About to declare done, or to do something irreversible** — deleting, overwriting, a production
  write, spending. Gate hard here; recovery is expensive or impossible. First run the negative
  probe (a confident all-green set of the *wrong* questions is exactly what this gate catches),
  then judge every live criterion with `judge_batch` against that one state, plus one Goodhart
  `bool`. A low result is a stop: fix, or climb toward an *external* check — never another
  self-probe, which cannot raise your own confidence. Set the bar by stakes, because what you are
  trading against the cost of the call is the cost of being wrong: higher for the destructive move
  than the read-only one.

**Across every moment — routing.** Whenever the next step is a choice among a fixed, known set,
hand it to Jev as a `choice` (see *Choose the next move*). This is not its own moment; it rides on
the three above.

**Before any of them — reconcile first.** Each of these fires on evidence you are about to trust.
Re-read the actual artifact and confirm the state matches what you are looking at now (move 6).
Skip it and a misread becomes a confident wrong number — the one failure a calibrated pass cannot
catch for you.

## Choose the next move (routing)

Verification tells you where you are; it does not tell you where to go. When the next move is a
choice among a fixed, known set — which tool, which handler, continue or escalate, which of three
files — ask it as a `choice` and let the calibrated pick and its confidence steer the next bounded
step. That is the whole circuit: judge the state, then choose the move.

The boundary that keeps this safe: an *open-ended* "what should I do next" is planning, and
planning is yours as the generator, not a gut-check. Hand routing to Jev only when you can already
enumerate the options; if you cannot list them, think, do not ask.

## Where Jev is weak

- **Typed is not true, and probes are not proof.** A clean type guarantees the answer's shape,
  never its truth. Self-probes on toy cases prove the *mechanism* works; only a with/without test
  on real work — the same task run with and without the judgment, outcomes compared — proves it
  changes the outcome. Earn a threshold on real cases; never read a pile of green probes as proof
  of value.
- **Jev is downstream of your perception.** It judges the state, never the world the state came
  from, so it cannot fix a misreading — only inherit it and lacquer it with a number. Open-ended
  discovery over an artifact bigger than you can hold in view (reviewing a large PR, auditing an
  unfamiliar codebase) is reasoning, not a gut-check: do the reading yourself, then hand Jev only
  the thin atomic verifications inside it, each over evidence you have actually read. Routed at the
  whole artifact, it returns a confident answer about your summary, not about the code.
- **How far you can close the state sets how far Jev may rule.** This is the honest ladder, and it
  is a property of the state you can build, not of the subject matter:
  - **Closable** — every decisive fact is reachable and readable, so the answer may gate an action.
    Code belongs here, with one constraint: behavior has to be *produced* before it can be scooped.
  - **Partly closable** — some axes are reachable, others live in a person. Prose is the case:
    canon can be checked, a reader's experience cannot, because it is not in the environment at all.
    Let Jev rule on the reachable axes and only point on the rest.
  - **Unclosable** — the standard itself sits in a person. Here Jev is a pointer to look again,
    never a verdict, and no quantity of evidence repairs it.
  Read a low score on taste as "look again here", and keep yourself or the human as the arbiter.
- **The circularity never fully closes.** The discipline above shrinks it; it does not remove it.
  For anything that matters, the human stays the final judge on the high-stakes call.
- **Self-agreement is not validity.** Jev endorsing your own questions is you checking your
  homework with a different pen. The only real reference is the external source — the user's
  words, the spec, the test — never your restatement of it, and never the fact that you liked the
  question you asked.

## Worked example (real output)

Same claim, same raw receipt, only the state fields differ. The claim is that `handle_empty()`
behaves correctly for empty input; the evidence is the run that was actually made; the standard is
the requirement the function has to meet; the counter is a fact found by sweeping the repo.

```python
EVIDENCE = ('Ran handle_empty([]); it returned [] and wrote "WARN empty input" to stderr. '
            'Exit code 0.')
CLAIM  = "handle_empty() behaves correctly for empty input."
REQ    = ("handle_empty must return [] for empty input AND must not write to stderr or log: "
          "it is called inside a hot loop where any I/O costs latency.")
COUNTER = ("Repo check: the hot-loop caller was removed in commit 4a1f2c last week; the only "
           "remaining caller runs once at process startup.")

states = {
    "S1_no_standard":  {"claim": CLAIM, "evidence": EVIDENCE},
    "S2_with_standard": {"claim": CLAIM, "evidence": EVIDENCE, "standard": REQ},
    "S3_with_counter": {"claim": CLAIM, "evidence": EVIDENCE, "standard": REQ,
                        "counter": COUNTER},
}

q = {
    "correct": {"type": "bool",
        "instructions": "Is the behavior observed in the evidence correct for this function?",
        "criteria": {"true": "the observed behavior is correct",
                     "false": "the observed behavior is not correct"}},
    "has_standard": {"type": "bool",
        "instructions": "Does this state say what the function is required to do?",
        "criteria": {"true": "the requirement is stated in the state",
                     "false": "the requirement is not stated in the state"}},
}
```

Real answers:

| state | `has_standard` | `correct` |
|---|---|---|
| S1 no standard | 0.12 | **0.72** |
| S2 with standard | 0.85 | **0.06** |
| S3 with counter | 0.91 | 0.20 |

Read the middle column first. Jev *knows* the state never says what the function must do — 0.12 —
and still answers 0.72. It does not abstain; it falls back on general taste ("it runs, a warning is
harmless") and returns a confident number to a question you did not ask. That is the whole reason
the standard is a state field: an incomplete state is usually not short of evidence, it is short of
the standard.

The last row is the counter axis: same standard, plus one disconfirming fact found by sweeping.
0.06 to 0.20. It does not overturn the answer, but it shows the environment holds facts that move
the verdict, and the state only knows the ones the witness went and looked for.

Note what the evidence field never becomes: a summary. "It works now" would have earned the same
confident number with none of the meaning.

The same machinery, asked as a `choice` over a whole skill file with the candidate list supplied by
hand, returned `big_slice` with `probabilities` spread 0.5 / 0.27 / 0.21 and `confidence` 0.40. Read
a spread pick as a pointer, not a verdict: it says look here first, and the trailing options were not
ruled out. `confidence` is concentration, so 0.40 on a four-way question is ordinary and means
nothing about whether the pick is right.

## One gate, end to end (real)

A reconstruction from that run's report and its transcript, not a line-by-line quote. The moment: an
agent was about to say "`normalize_msisdn` is ready to ship". A claim was leaving its hands, so a
gate opened. In order, what happened:

1. **Scoop.** `src/msisdn.py`, the three tests, `docs/SPEC-31-msisdn.md` — read now, quoted, not
   retyped from an earlier look.
2. **Facts — and this step was skipped.** The state went straight to claim / evidence / standard /
   counter with no path list, so no fact was ever named and none was probed. The one that mattered,
   `None` into `normalize`, surfaced only in the closing prose of the verdict, as a hunch with
   nothing behind it.
3. **Standard.** `SPEC-31 §3`: invalid input MUST return `None`. Verbatim, in its own field.
4. **Sweep — the step that failed first.** The first pass wrote `"Searched gateway.py: no superseding
   spec or commit found"` and stopped. That is a false negative: `gateway.py` was the file next door
   and no sweep had happened. The verdict that came out was "do not ship, the spec is violated" —
   wrong, and wrong because the counter was empty with a label on it.
5. **Re-scoop.** The sweep redone as a search: grep the tree for `SPEC-31` and for supersession
   language. `docs/adr/0017-msisdn-errors.md` supersedes §3 and requires exactly the `ValueError` the
   code already raises, and `docs/onboarding.md` states that an ADR beats a SPEC.
6. **Judge.** `ready_to_ship` 0.88 against `not_ready` 0.69 — a pair summing to 1.57, which is the
   contradiction the sanity check exists to catch. Look again, and the real gap was never the spec:
   it was one of the unprobed facts (`None` raises `TypeError`, not `ValueError`) plus a three-case
   test suite.

The shallow sweep cost a confidently backwards verdict with a number on it. The skipped
decomposition cost a real bug that stayed a hunch instead of becoming a probe. The gate cost one
extra grep and one path list. Both runs are the same agent on the same repository.
