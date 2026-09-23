# Judging an approach before you execute it

Use when you have diagnosed a problem, proposed how to fix it, and are about to spend the
execution on that proposal. Choosing the approach is the most expensive decision in the work: a
wrong one wastes everything built on it, and nothing downstream says so, because every later check
asks whether the execution matches the approach.

## Two standards at this gate: the diagnosis and the criteria

At the done gate the standard is the user's requirement. Here there are two, and each catches
what the other misses:

- the **diagnosis**: the raw observation of what is actually wrong, or for a feature, of what
  exists now (the stack trace, the failing row, the file and function the change must touch).
  An approach is sound when it acts on what that observation shows.
- the **criteria**: what the user asked for, one line each, traceable to their words. An
  approach is sound when executing it as written would deliver each one.

```python
state = {
    "goal":      "...",           # the user's words, verbatim
    "criteria":  ["...", "..."],  # one per demand in those words
    "diagnosis": "...",           # the raw observation, with file:line, never paraphrased
    "solution":  "...",           # the approach you are about to execute
}
```

If you have no diagnosis yet, you do not have an approach to judge. Reproduce, or read the code
the change has to touch, first.

## The questions, verbatim

These wordings are the ones that ran. Do not paraphrase them without re-running the cases.

```python
"at_cause": {"type": "bool",
    "instructions": "The change in `solution` acts on the cause shown in `diagnosis`, rather than "
                    "suppressing, avoiding, or working around the symptom.",
    "criteria": {"true":  "it changes the code at the cause the diagnosis shows",
                 "false": "it hides the symptom, or changes something the diagnosis does not implicate"}},
f"c{i}": {"type": "bool",                     # one per criterion
    "instructions": f"Executing `solution` as written would satisfy `criteria[{i}]`.",
    "criteria": {"true":  "the approach as written delivers this criterion",
                 "false": "the approach misses it, contradicts it, or does not say enough to tell"}},
"waste": {"type": "score",
    "instructions": "If the approach in `solution` turns out to be WRONG, how much of the execution "
                    "it commits would be wasted?",
    "criteria": ["one line or one function",
                 "one module or one feature",
                 "the structure of the whole application"]},
```

Ask `at_cause` with its negation in the same call (the pair is in the table below). The gate is
the lowest of `at_cause` and every criterion.

## How to read them

One problem (a login form throws `TypeError` at `validate.ts:42` when the email field is empty)
and five proposed approaches:

| approach | `concrete` | `at_cause` | negation | `waste` | P(`structure`) |
| --- | --- | --- | --- | --- | --- |
| guard empty input at line 42, add a test | 0.98 | **0.88** | 0.18 | 0.20 | 0.00 |
| wrap submit in try/catch, ignore the error | 0.93 | **0.03** | 0.97 | 0.52 | 0.00 |
| upgrade the regex library, four detailed steps | 0.97 | **0.18** | 0.85 | 0.95 | 0.02 |
| "refactor validation to be more robust" | 0.07 | 0.51 | 0.64 | 0.96 | 0.01 |
| migrate all six forms to a new form library | 0.96 | 0.28 | 0.89 | 1.96 | **0.97** |

- `at_cause` low: the approach is not aimed at the cause. Rework it before executing.
- `at_cause` near 0.5, with a pair summing above 1.1: the proposal is too vague to judge. Make it
  concrete, then ask again. A vague proposal is not "half right".
- P(`structure`) high: if this approach is wrong, it costs the architecture. That is when a second
  agent (an oracle review of the approach) or the user earns its cost. Near 0, carry on.

Five cases on one problem draw a pointer, not a calibration. No threshold here is frozen.

## Why the diagnosis must be in the state

The same `at_cause` question with the `diagnosis` field removed:

| approach | with diagnosis | without |
| --- | --- | --- |
| guard at line 42 | 0.88 | 0.86 |
| try/catch | 0.03 | 0.04 |
| upgrade the regex library | **0.18** | **0.42** |
| migrate six forms | 0.28 | 0.56 |

The obvious workaround is caught either way, by general taste. The approach that is concrete,
plausible, and aimed at the wrong cause (the expensive one) is only caught when the raw diagnosis is
in the state. Without it Jev judges whether the approach sounds reasonable, not whether it fixes
this problem.

## Why the criteria questions are needed too

`at_cause` alone is weak on a feature, where there is no symptom to work around. A CSV-export
request (only the filtered rows; file name carries the report date) and three approaches:

| approach | `at_cause` | criteria (export / filtered rows / file name) |
| --- | --- | --- |
| export via the existing filtered query, name `report-<to>.csv` | 0.91 | 0.92 / 0.91 / 0.84 |
| dump the whole database table to CSV | **0.69** | 0.61 / **0.12** / **0.09** |
| "implement CSV export for reports" | **0.84** | 0.32 / 0.21 / 0.11 |

`at_cause` passed the approach that ignores the filter, and passed the vague one. The criteria
caught both. The reverse holds on the bug: the try/catch satisfies "no longer throws" at 0.78,
and only `at_cause` (0.03) sees it hides the crash. Lowest of all, on the bug cases: guard at line
42 0.60, try/catch 0.03, regex upgrade 0.17, vague 0.11, six-form migration 0.28.

## The formulation that died

*"Has the agent proposed a concrete approach?"* It scored 0.93 to 0.98 on every approach with
steps in it, including the try/catch that hides the crash and the library upgrade that changes the
wrong thing. It measures form. It only tells you that a proposal exists, which you already know.
