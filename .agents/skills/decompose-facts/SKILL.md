---
name: decompose-facts
description: >-
  Splits anything that has to be checked (code, a diff, a spec, a scoring rule, a research
  claim, a plan, a story canon, a user's request) into atomic facts that can each be verified
  one at a time, plus an explicit list of the parts that cannot become such a fact. Use before
  judging, testing, reviewing or verifying anything bigger than one sentence; when a single
  "is this right / done / correct?" question would have to average over several things; when
  writing acceptance criteria or a test list; and when a check came back green but you are not
  sure it checked the thing that matters. Not for a one-line change a single command proves.
---

# Decompose facts

A verifier answers whatever it is asked. Jev, a reviewer, a test: none of them abstain. Ask one
question about three things and it averages them; the broken one disappears. So verification
is decided before the verifier runs, by how the material was split.

## Output: two lists

- **atoms**: one line each: the `fact`, the `span` it comes from (path and lines, or the quoted
  words), and the `probe` that would settle it.
- **not_atoms**: parts no probe of any kind could settle ("the reader feels the loss", "the design
  hangs together"), each with why. Never drop them silently and never dress them up as facts. They
  tell the person holding the goal what stays with them.

## A fact is small enough when

1. **One demand.** Not "exports, filtered, and named by date"; three facts.
2. **One way to settle it.** Arithmetic goes to code; write thresholds as absolute numbers
   ("20s or less", not "half of 40s"). What only a run or a transcript can show is still a fact;
   its probe is the run or the transcript.
3. **Self-contained.** No "as before", "as in attempt 2".
4. **Applies here.** If it presupposes something ("the root cause"), that presupposition is a fact
   of its own, checked first.
5. **Can be false.** You can name a world where it fails. "The file exists" padding proves nothing.

A fact states what the thing **does or says**, never what a standard requires.

## How

1. **List from the bytes.** For code run `scripts/clerk.py` (`python clerk.py path`): one row per
   branch, return, raise, SQL predicate or key, with its line. Otherwise walk the material in
   order: sentence, clause, rule, scene.
2. **Split** each piece until it meets the five conditions, or move it to `not_atoms`.
3. **Check both directions.** Every atom against its span: does the source say that? Every part of
   the source against the list: is it covered by an atom or a `not_atoms` entry?
4. **Name the whole.** All atoms can be true and the whole still wrong. Put that whole-level
   property in `not_atoms` so someone checks it by running everything or by looking.

Choosing who checks each atom (code, Jev, a person, a full run) belongs to the caller.
`calibrated-judgment` uses the atoms as its `facts`.
