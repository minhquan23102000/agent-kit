# The done gate: judging finished work against the standard

Use when you are about to yield, or to tell the user the work is finished. Two things decide
whether this gate means anything, and both were measured: where the standard comes from, and
whether it is asked as one question or one per criterion.

## The standard comes from the user's words, never your restatement

By the end of a task you usually hold a restated standard: the goal and acceptance criteria you
wrote down at the start. It is the most natural thing to check against, and it is a derived
artifact. Any criterion it dropped is invisible at this gate, because the work is judged against
the restatement and the restatement no longer contains it.

One request: *"add CSV export to the report page. the file has to contain only the rows for the
date filter I applied, and the file name should carry the report date"*. The restatement kept the
first clause and lost the other two. The work exported every row into `report.csv`.

| `standard` field | "the work meets `standard`" |
| --- | --- |
| restatement: "Export button produces a CSV of the report" | **0.68** |
| the user's words, verbatim | **0.06** |

Same evidence. Against the restatement, the work passes. So put the user's own request, quoted
from the session, in the `standard` field. Use your restatement only to enumerate criteria, and
check each one traces to a phrase in those words.

## One question per criterion, never one for the whole standard

A single "does the work meet the standard?" question blurs a failed criterion into a middling
number. Same request; the work now filters correctly but names the file `report-final.csv`:

| question | work with the wrong file name | work that meets all three |
| --- | --- | --- |
| one composite question | **0.50** | 0.91 |
| criterion: CSV export exists | 0.93 | 0.95 |
| criterion: only the filtered rows | 0.90 | 0.93 |
| criterion: file name carries the date | **0.12** | 0.95 |

The composite landed on a coin flip, which passes any gate that blocks only below 0.5. The
per-criterion questions name the one that failed. The gate is the **lowest** criterion, not the
mean, because a single unmet criterion is unmet work.

## The procedure

1. **Quote the user's request** from the session into `standard`. If the user amended the goal
   during the work, quote the amendment too; the latest words win.
2. **Enumerate the criteria**, one line each, each traceable to a phrase in those words. A
   criterion you cannot trace is one you inferred; mark it.
3. **Produce the evidence for each.** Run it and carry the raw output, with what you did to get
   it. A criterion you cannot produce evidence for is not met.
4. **Judge every criterion in one call over one state**, `{"standard", "criteria", "evidence"}`,
   with one question per criterion that points at it by path:

   ```python
   f"c{i}": {"type": "bool",
       "instructions": f"The `evidence` shows that `criteria[{i}]` is met.",
       "criteria": {"true":  "the evidence shows this criterion is met",
                    "false": "the evidence shows it is not met, or does not establish it"}}
   ```

   One shared state gave the same separation as a state per criterion (wrong file name:
   0.95 / 0.82 / **0.13**), and it keeps every criterion judged against the same world. Skip
   the call where code settles it exactly (a test exit code, a row count compared to a row
   count) and use the check itself.
5. **Add the Goodhart tripwire** from the main skill to the same fan-out.
6. **Fix any low criterion before you claim done.** Do not report partial work as finished.

## What this gate cannot catch

It catches a criterion you forgot or failed. It does not catch a criterion you misunderstood: if
you read "the report date" as today's date and the user meant the filter's end date, every
question above passes. That misreading has to be caught before the work is built, with the
comprehension check.
