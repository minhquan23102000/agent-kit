# Reading the user's meaning before committing to it

Use when you are about to derive a `standard` from the user's words and those words leave more
than one reading open.

## Why this exists

The Goal link records the user's words. Recording is not understanding. The user says "make it
faster"; the agent records those three words correctly, derives "reduce API latency to under
200ms" — and the user meant build time. Every link traces cleanly, every check passes, and the
output is wrong. Nothing downstream catches it, because everything downstream is checked against
the words, and the words are right there.

## The question, verbatim

This wording is the one that ran. Do not paraphrase it without re-running the cases.

```
"type": "score"
"instructions": "The operationalization claims to be what the user's words mean.
                 If that reading is WRONG, how much of the work already committed
                 downstream does it invalidate?"
"criteria": ["one word or a phrasing",
             "one section or one paragraph",
             "the structure of the whole thing"]
```

The state is `user_words` and `operationalization` (the reading the agent is about to commit to),
plus `rival_reading` when one exists.

Read `probabilities["2"]` — the probability of the "structure" level. **That is the discriminating
signal**, not the mean score.

## How to read it

High `structure` means: if this reading is wrong, it invalidates the structure of what is being
built — so stop, and ask the user the one question that separates the readings, before anything
is built on top.

Four cases observed while this question was being tested, as a scale:

| case | level | `structure` |
| --- | --- | --- |
| phase names in English vs Vietnamese | 0.53 | **0.07** |
| a control reading that turned out to be genuinely ambiguous too | 0.94 | 0.28 |
| "make it faster" read as API latency | 1.01 | 0.35 |
| "model nhỏ gọi model lớn" read as delegation | 1.21 | **0.44** |

The cheapest case cost one word. The most expensive invalidated an architecture. Six-fold
separation, and the order matched the real damage of that session.

**The line is provisional, and no constant is frozen anywhere.** Four points draw a line, they do
not calibrate one. Read it as a pointer: `structure` near 0.1, carry on; near 0.4, ask the user
first.

## Two formulations that died, and why

Kept because this is the expensive part:

- *"Does this reading follow necessarily from the user's words?"* — the answer is **always no**.
  Natural language never entails a single reading.
- *"Would the rival reading produce a different artifact?"* — the answer is **always yes**. The
  cheapest case of that session scored *higher* than the most expensive one.

Both died the same way: a question about a **hypothetical alternative** is always answerable, so
it measures nothing. The wording that ran asks about **consequences already committed**, and a
consequence has a size.

The rule this generalises to, for any question sent to Jev: **a question whose answer is
self-evident is not a check.**

## Checking the criteria you wrote: complete and traced

The question above asks whether you read the user right. Once you have written criteria, two more
things can be wrong: a demand has no criterion (incomplete), or a criterion is not something the
user asked for (invented, contradicting, too vague). Give each criterion the user's own phrase as a
`quote`, and check in code that the quote really is in their words. That part is exact, so it does
not go to Jev. Then ask Jev two things:

```python
# completeness: one question per user message, over criteria that carry their quote
state_c = {"user_words": messages, "criteria": [f"{c} ('{q}')" for c, q in pairs]}
f"m{j}": {"type": "bool", "instructions": f"Everything the user wants in `user_words[{j}]` (a request, a complaint that something is missing, a question why it is not there) has an entry in `criteria` that states it. If `user_words[{j}]` wants nothing, this is true."}
# integrity: one question per criterion, over the plain criteria, NO quotes
state_t = {"user_words": messages, "criteria": [c for c, _ in pairs]}
f"t{i}": {"type": "bool", "instructions": f"The user wants `criteria[{i}]`, as `user_words` shows: they ask for it, complain it is missing, or ask why it is not there. It does not contradict them."}
```

Across 15 English and Vietnamese cases (full, missing, invented, contradicting, vague, wrong
format), every bad set was rejected at 0.03-0.45 and every full set passed at 0.64-0.96. Asking per
message lets a rejection say which message went uncovered: missing demands scored 0.04-0.10.

Two lessons about building the state came out of these runs:

- **A quote in the state vouches for whatever sits next to it.** When each criterion carried its
  quote in the trace state, *"checks spelling ('check tính toàn vẹn hay đầy đủ')"* passed at 0.74.
  The quote helps coverage, because it shows which words a criterion answers. It hurts trace,
  because the question becomes whether the quote exists, not whether the criterion matches it. So
  the two questions get two different states.
- **Name the kinds of demand.** The first trace wording asked what the user "asked for". It
  scored the user's own demand, written as a complaint (*"sao không có check…?"*), at 0.18, because a
  question does not read as a request. Once the wording listed complaints and why-questions as
  kinds of demand, the same criterion scored 0.66-0.88.

Vietnamese margins stay thin. A correct but literal criterion (*"checks it for completeness and
integrity"*) scored 0.45 on coverage. It passed (0.64) only once it said concretely what it demands.
A rejection here usually means the criterion is too vague, not that Jev misread.
