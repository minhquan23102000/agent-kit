"""Gatekeeper for a calibrated-judgment state.

`judge` takes any dict, so an agent can leave out whichever field it forgot. This
wrapper makes the shape non-optional: the call does not happen until every field is
present, the fact list has more than one entry, and the counter names where it looked.
It runs in the omp eval kernel, the only place `judge` exists, and takes it as an argument;
it is not a standalone script.

    import sys
    sys.path.insert(0, "<calibrated-judgment skill dir>/scripts")
    from verify import verify

    result = await verify(
        judge,
        facts=["normalize(None) raises TypeError", "normalize('0...') returns '+84...'"],
        claim="normalize returns E.164 for a local-prefix number",
        evidence="ran normalize('090 123 4567') -> returned '+84901234567' (msisdn.py:14-19)",
        standard="R1 (SPEC-7): normalize must accept spaces or dashes inside the number",
        rule="Behavior is shown by a run on the input the requirement names, not by the source.",
        counter="searched docs/**, config/**, CHANGELOG for a supersession of SPEC-7: none",
        questions={"correct": {"type": "bool", "instructions": "..."}},
    )
    print(result["warnings"])
    print(result["answers"])
    print(result["pairs"])

`rule` is optional because not every claim needs one, but a claim that asserts a cause
(fixed, prevents, works) without it is warned about: Jev has no causal model of its own
and, given no rule, passes a diff read as proof of a fix (0.65 without, 0.06 with).

`questions` may include a pair written as `x` and `not_x`; the sums are reported so a
contradictory pair (both sides endorsed, or a total far from 1) is visible without the
caller having to remember to check.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

# A counter is evidence only when it says where the search happened, so the check is for
# a location, not for a search verb: "searched nothing" and "looked in the obvious places"
# name no place, while "docs/**: none" does. A location is a path or glob, a file with an
# extension, or a named source that has no path of its own.
_LOCATION = re.compile(
    r"[\w.*-]*[/\\*][\w.*/\\-]*"                      # docs/**, src\auth, *.md
    r"|\b[\w-]+\.[A-Za-z][A-Za-z0-9]{0,4}\b"           # validate.ts, SPEC-31.md
    r"|\b(?:git log|git blame|CHANGELOG|README|ADR[\w-]*|commit [0-9a-f]{6,})\b",
    re.IGNORECASE,
)

# Evidence is clean when every value in it came from code that ran or from a verbatim cut, so
# the check is for a trace of either: an output verb or marker, or coordinates. "Handles
# separators correctly, all tests pass" has neither; it is the claim restated. Measured: that
# summary scored 0.47 in the world where the claim was true and 0.49 where it was false.
_OBSERVED = re.compile(
    r"\b(?:returned|raised|exit(?:ed)? (?:code|with)|stdout|stderr|Traceback|wrote|printed)\b"
    r"|\b(?:PASSED|FAILED|ERROR)\b|\$ |->|:\d+|\blines? \d+",
)

# A claim about cause needs a rule saying what observation shows that cause. Warning only.
_CAUSAL = re.compile(
    r"\b(?:fix(?:es|ed)?|caus(?:e|es|ed)|prevent(?:s|ed)?|resolv(?:e|es|ed)|broke|breaks?"
    r"|because|works?|makes?|made)\b",
    re.IGNORECASE,
)

# Warning only, never a refusal. Provisional: a state holding a whole document was seen to
# pin a judgment near the top and stop moving when the document moved; this cut-off was
# not calibrated. Print it with the warning so it can be argued with.
MAX_STATE_CHARS = 6000

# Observed pair sums: clear cases sat at 1.00-1.06; proposals too vague to judge at
# 1.15-1.17; a real contradiction (the SPEC-31 gate) at 1.57. The upper edge sits on the
# vague cases on purpose: a vague state should be flagged too. Override per call.
PAIR_TOLERANCE = (0.85, 1.15)


class Incomplete(Exception):
    """The state is missing something the call is not allowed to proceed without."""


def build(facts: Iterable[str], claim: str, evidence: Any, standard: str,
          counter: str, rule: str | None = None) -> dict[str, Any]:
    facts = list(facts or [])
    fields = {
        "facts": facts,
        "claim": claim,
        "evidence": evidence,
        "standard": standard,
        "counter": counter,
    }
    empty = [name for name, value in fields.items() if not value]
    if empty:
        raise Incomplete(
            "state is missing: " + ", ".join(empty)
            + ". Every field is load-bearing; a blank one is the failure this call exists to stop."
        )
    if len(facts) < 2:
        raise Incomplete(
            "facts has one entry, so the artifact was not decomposed. One path is never the "
            "whole bundle; if you believe there is only one, name the second as the reason "
            "there is no other."
        )
    if not _LOCATION.search(counter):
        raise Incomplete(
            "counter names no location. Write where you looked, e.g. "
            "\"searched docs/**, config/**, CHANGELOG: none\". An absence with no place is not "
            "an empty counter, it is the hole wearing a label."
        )
    if rule is not None:
        if not rule.strip():
            raise Incomplete("rule was passed empty. Leave it out, or write the rule.")
        fields["rule"] = rule
    return fields


def _pairs(questions: dict[str, Any], declared: dict[str, str] | None = None) -> dict[str, str]:
    """Complementary question pairs. Declared pairs win; `not_<id>` is the free convention.

    Auto-detection cannot work by itself: the natural naming for a pair is anything
    (`claim_holds` / `claim_fails`), and no mechanical rule recognises an antonym.
    """
    found = dict(declared or {})
    for key in questions:
        if key.startswith("not_") and key[4:] in questions:
            found.setdefault(key[4:], key)
    missing = [p for p, n in found.items() if p not in questions or n not in questions]
    if missing:
        raise Incomplete(
            f"declared pair(s) {missing} name questions that were not asked. A pair is only "
            "checkable when both sides are in `questions`."
        )
    return found


def _warnings(state: dict[str, Any], questions: dict[str, Any],
              declared: dict[str, str] | None = None) -> list[str]:
    out = []
    size = len(json.dumps(state))
    if size > MAX_STATE_CHARS:
        out.append(
            f"state is {size} chars, past {MAX_STATE_CHARS}: judgments over a state this large "
            "have been measured to stop moving when the artifact moves. Cut it to the span."
        )
    evidence = state["evidence"]
    evidence_text = evidence if isinstance(evidence, str) else json.dumps(evidence)
    if not (_OBSERVED.search(evidence_text) or _LOCATION.search(evidence_text)):
        out.append(
            "evidence names no command, output, or coordinates, so it reads as your own summary. "
            "Carry what code produced (with the command) or a verbatim cut (with path:lines); "
            "a summary is judged as your belief, not as the world."
        )
    if "rule" not in state and _CAUSAL.search(state["claim"]):
        out.append(
            "the claim asserts a cause but the state has no rule. Say what observation shows a "
            "claim of this kind (for a fix: the same input fails before and passes after), or Jev "
            "falls back on what sounds plausible."
        )
    bools = [k for k, q in questions.items() if q.get("type") == "bool"]
    if bools and not _pairs(questions, declared):
        out.append(
            "no complementary pair among the bool questions, so a contradictory pair cannot be "
            "detected. Declare one with pairs={positive: negative}, or name the negative side "
            "'not_<id>'."
        )
    return out


async def verify(judge: Callable, facts: Iterable[str], claim: str, evidence: Any,
                 standard: str, counter: str, questions: dict[str, Any],
                 rule: str | None = None,
                 pairs: dict[str, str] | None = None,
                 tolerance: tuple[float, float] = PAIR_TOLERANCE) -> dict[str, Any]:
    """Check the shape, then judge. Raises Incomplete before any call is made.

    `pairs` maps a positive question id to its negative, e.g.
    `pairs={"claim_holds": "claim_fails"}`. Declare it whenever the two ids do not follow
    the `not_<id>` convention, because nothing mechanical can recognise an antonym.
    """
    state = build(facts, claim, evidence, standard, counter, rule)
    warnings = _warnings(state, questions, pairs)
    answers = await judge(state, questions)

    pair_sums = {}
    for positive, negative in _pairs(questions, pairs).items():
        left = answers.get(positive, {}).get("bool")
        right = answers.get(negative, {}).get("bool")
        if left is None or right is None:
            continue
        total = left + right
        low, high = tolerance
        pair_sums[positive] = {"sum": round(total, 3), "contradictory": not (low <= total <= high)}
        if pair_sums[positive]["contradictory"]:
            warnings.append(
                f"'{positive}' and '{negative}' sum to {total:.2f}, outside {low}-{high}. A "
                "complementary pair should sit near 1; look again rather than believing either number."
            )

    return {"state": state, "answers": answers, "pairs": pair_sums, "warnings": warnings}
