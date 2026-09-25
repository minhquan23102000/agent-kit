"""Turn a project rulebook plus a change into judge requests and linter commands.

The state a judge sees for a code rule is never the raw repository. It is one rule and one
unit: the smallest piece of code the rule speaks about (a function, a class, a hunk), cut by
code from the files the change touched, with its path and lines. This script does that cut,
so every state is reproducible from the rulebook and the diff alone.

    python build_states.py rulebook.yaml --staged            # pre-commit hook
    python build_states.py rulebook.yaml --diff origin/main...HEAD
    python build_states.py rulebook.yaml --files inventio/search.py
    python build_states.py rulebook.yaml --examples          # calibration set
    python build_states.py rulebook.yaml --sweep             # every unit in scope, at HEAD

Output is JSONL on stdout, one line per check:

    {"meta": {...}, "request": {"state": ..., "model": ..., "questions": ...}}   semantic rule
    {"meta": {...}, "command": "ruff check --select D103 a.py b.py"}             deterministic rule

Every request asks the same two questions: `applies` (the unit is a case the rule governs)
and `complies` (the unit satisfies the rule). A unit is a violation only when it applies and
does not comply; `complies` alone reads "nothing here to judge" as a failure.

This script never calls a model. `request` is a TypeSafe `POST /v1/systemone` body as-is:
inside the omp eval kernel, pass its `state` to `judge_batch` (Noul is `bool` there); in a git
hook or CI job, where omp's `judge` does not exist, post it with your own `TYPESAFE_API_KEY` or
send the same state and questions to another model. The runner owns the call, the thresholds,
and what a failure blocks.
Rules with status `pattern` or check kind `human` are never emitted: a pattern has no watched
harm yet (see prove_harm.py), and a human check is for a reviewer, not a hook.

Python files are cut with `ast`. Any other language falls back to the changed hunk with a few
lines of context, marked `"kind": "hunk"` so the runner can see it was not a syntactic unit.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

UNIT_KINDS = {"function", "class", "module", "hunk"}
CHECK_KINDS = {"deterministic", "semantic", "human"}
HUNK_CONTEXT = 3
# Past this size a single unit stops being one hop from the rule (see the calibrated-judgment
# measurements: the false world crept from 0.08 to 0.27 as a file grew). Warned, not refused.
MAX_UNIT_CHARS = 6000
EXPECTS = {"pass", "fail", "skip"}
# A name pattern that is only a list of literal names enumerates the code that exists today.
NAME_LIST = re.compile(r"\^?\(?\w+(?:\|\w+)*\)?\$")
HARM_RUN = ("edit", "run", "expect")
HARM_READER = ("reader", "violation", "misled")


class RulebookError(Exception):
    pass


def load_rulebook(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        book = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise RulebookError("PyYAML is needed for a .yaml rulebook (pip install pyyaml), "
                                "or save the rulebook as .json") from exc
        book = yaml.safe_load(text)
    validate(book)
    return book


def commitments(book: dict[str, Any], problems: list[str]) -> set[str]:
    """Ids of the promises and refusals in `purpose`: what a rule may say it protects."""
    purpose = book.get("purpose") or {}
    if not purpose.get("serves"):
        problems.append("purpose.serves is missing: who the project is for, and to do what")
    if not purpose.get("promises"):
        problems.append("purpose.promises is empty: every rule has to protect one of them")
    ids: set[str] = set()
    for group, text in (("promises", "promise"), ("refuses", "choice")):
        for j, item in enumerate(purpose.get(group) or []):
            pid = item.get("id") or f"purpose.{group}[{j}]"
            for field in ("id", text, "evidence"):
                if not item.get(field):
                    problems.append(f"{pid}: missing {field}")
            if pid in ids:
                problems.append(f"{pid}: duplicate id")
            ids.add(pid)
    return ids


def harm_problems(rid: str, harm: dict[str, Any] | None) -> list[str]:
    if not harm:
        return [f"{rid}: no harm; a rule whose break nobody has watched stays a pattern until it has one"]
    runnable = any(harm.get(f) for f in HARM_RUN)
    reader = any(harm.get(f) for f in HARM_READER)
    if runnable and reader:
        return [f"{rid}: harm is either run (edit, run, expect) or reader (reader, violation, misled), "
                "not both"]
    out = [f"{rid}: harm needs {f}" for f in (HARM_READER if reader else HARM_RUN) if not harm.get(f)]
    for k, e in enumerate(harm.get("edit") or []):
        if not (isinstance(e, dict) and e.get("path") and e.get("old") and "new" in e):
            out.append(f"{rid}: harm.edit[{k}] needs path, old, and new")
    if harm.get("expect"):
        try:
            re.compile(harm["expect"])
        except re.error as exc:
            out.append(f"{rid}: harm.expect is not a regex: {exc}")
    return out


def validate(book: dict[str, Any]) -> None:
    problems: list[str] = []
    protectable, seen = commitments(book, problems), set()
    for i, rule in enumerate(book.get("rules") or []):
        rid = rule.get("id") or f"rules[{i}]"
        if rid in seen:
            problems.append(f"{rid}: duplicate id")
        seen.add(rid)
        for field in ("statement", "why", "scope", "status", "evidence", "check"):
            if not rule.get(field):
                problems.append(f"{rid}: missing {field}")
        if rule.get("status") not in {"rule", "pattern"}:
            problems.append(f"{rid}: status must be rule or pattern")
        if rule.get("status") == "rule":
            if rule.get("protects") not in protectable:
                problems.append(f"{rid}: protects must name a promise or refusal in purpose, "
                                f"not {rule.get('protects')!r}")
            problems += harm_problems(rid, rule.get("harm"))
        check = rule.get("check") or {}
        kind = check.get("kind")
        if kind not in CHECK_KINDS:
            problems.append(f"{rid}: check.kind must be one of {sorted(CHECK_KINDS)}")
        if kind == "deterministic" and not check.get("command"):
            problems.append(f"{rid}: a deterministic check needs a command")
        if kind == "semantic":
            if check.get("unit") not in UNIT_KINDS:
                problems.append(f"{rid}: check.unit must be one of {sorted(UNIT_KINDS)}")
            for field in ("applies_when", "pass_when", "fail_when"):
                if not check.get(field):
                    problems.append(f"{rid}: a semantic check needs {field}")
            if check.get("name") and NAME_LIST.fullmatch(check["name"]):
                problems.append(f"{rid}: check.name {check['name']!r} lists today's names, so code written "
                                "later under another name escapes the rule; say which units it governs in "
                                "applies_when, and keep name for a naming convention the tooling itself uses")
            expects = [e.get("expect") for e in rule.get("examples") or []]
            if set(expects) - EXPECTS:
                problems.append(f"{rid}: example expect must be one of {sorted(EXPECTS)}")
            if not EXPECTS <= set(expects):
                problems.append(f"{rid}: a semantic rule needs a pass, a fail, and a skip example "
                                "(skip: a unit in scope that the rule does not govern)")
    if not book.get("rules"):
        problems.append("rulebook has no rules")
    if problems:
        raise RulebookError("rulebook is invalid:\n  " + "\n  ".join(problems))


def in_scope(path: str, scope: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in scope)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def changed_lines(repo: Path, diff_args: list[str]) -> dict[str, set[int]]:
    """New-side line numbers each file's hunks touch. A pure deletion touches the line after it."""
    out: dict[str, set[int]] = {}
    current = None
    for line in git(repo, "diff", "-U0", "--no-color", *diff_args).splitlines():
        if line.startswith("+++ "):
            current = None if line[4:] == "/dev/null" else line[4:].removeprefix("b/")
            if current:
                out.setdefault(current, set())
        elif line.startswith("@@") and current:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            start, count = int(m.group(1)), int(m.group(2) or 1)
            out[current].update(range(start, start + count) if count else {start})
    return out


def new_side(diff_range: str) -> str | None:
    """The revision a range's new-side line numbers belong to; None is the working tree."""
    for dots in ("...", ".."):
        if dots in diff_range:
            return diff_range.split(dots, 1)[1] or "HEAD"
    return None


def read_source(repo: Path, path: str, rev: str | None) -> str:
    """The file the diff's line numbers refer to: None is the working tree, "" the index."""
    if rev is None:
        return (repo / path).read_text(encoding="utf-8")
    return git(repo, "show", f"{rev}:{path}")


def python_units(source: str, kind: str) -> Iterator[tuple[str, int, int]]:
    """(name, first line, last line) for top-level functions, methods, and classes."""
    tree = ast.parse(source)
    wanted = (ast.ClassDef,) if kind == "class" else (ast.FunctionDef, ast.AsyncFunctionDef)
    stack = list(tree.body)
    while stack:
        node = stack.pop(0)
        if isinstance(node, wanted):
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            yield node.name, first, node.end_lineno
        if isinstance(node, ast.ClassDef):
            stack.extend(node.body)


def cut(lines: list[str], first: int, last: int) -> str:
    return "\n".join(lines[first - 1:last])


def units_for(path: str, source: str, check: dict[str, Any],
              touched: set[int] | None) -> Iterator[dict[str, Any]]:
    """Units of the rule's kind; with `touched`, only the ones the change reaches."""
    kind, lines = check["unit"], source.splitlines()
    name_re = re.compile(check["name"]) if check.get("name") else None
    if kind == "module":
        if touched is None or touched:
            yield {"path": path, "lines": f"1-{len(lines)}", "kind": "module", "code": source}
        return
    if kind in {"function", "class"} and path.endswith(".py"):
        for name, first, last in python_units(source, kind):
            if name_re and not name_re.search(name):
                continue
            if touched is not None and not touched & set(range(first, last + 1)):
                continue
            yield {"path": path, "lines": f"{first}-{last}", "kind": kind, "name": name,
                   "code": cut(lines, first, last)}
        return
    if touched is None:  # no diff to anchor a hunk: the whole file is the only honest unit
        yield {"path": path, "lines": f"1-{len(lines)}", "kind": "module", "code": source}
        return
    for first, last in merge_ranges(touched, len(lines)):
        yield {"path": path, "lines": f"{first}-{last}", "kind": "hunk",
               "code": cut(lines, first, last)}


def merge_ranges(touched: set[int], length: int) -> Iterator[tuple[int, int]]:
    spans = sorted((max(1, n - HUNK_CONTEXT), min(length, n + HUNK_CONTEXT)) for n in touched)
    first, last = spans[0]
    for a, b in spans[1:]:
        if a <= last + 1:
            last = max(last, b)
        else:
            yield first, last
            first, last = a, b
    yield first, last


QUESTIONS = {
    "applies": {
        "type": "noul",
        "instructions": "`unit.code` is a case `rule.applies_when` describes.",
        "criteria": {
            "true": "`unit.code` does what `rule.applies_when` describes",
            "false": "`unit.code` does not do what `rule.applies_when` describes",
        },
    },
    "complies": {
        "type": "noul",
        "instructions": "`unit.code` satisfies `rule.statement`.",
        "criteria": {
            "true": "`unit.code` is as `rule.pass_when` describes",
            "false": "`unit.code` is as `rule.fail_when` describes, or is not as `rule.pass_when` describes",
        },
    },
}


def request(rule: dict[str, Any], unit: dict[str, Any], model: str) -> dict[str, Any]:
    """One rule against one unit. The questions are the same for every rule, so a runner can
    batch every state of a change into one call; what differs between rules lives in the state."""
    check = rule["check"]
    state = {
        "rule": {"id": rule["id"], "statement": rule["statement"], "why": rule["why"],
                 "applies_when": check["applies_when"],
                 "pass_when": check["pass_when"], "fail_when": check["fail_when"]},
        "unit": unit,
    }
    return {"state": state, "model": model, "questions": QUESTIONS}


def emit(meta: dict[str, Any], **body: Any) -> None:
    size = len(json.dumps(body.get("request", {}).get("state", {}).get("unit", {})))
    if size > MAX_UNIT_CHARS:
        meta = {**meta, "warning": f"unit is {size} chars; split the rule or narrow its unit"}
    print(json.dumps({"meta": meta, **body}, ensure_ascii=False))


def run_change(book: dict[str, Any], repo: Path, touched_by_file: dict[str, set[int]] | None,
               files: list[str], rev: str | None, model: str) -> None:
    for rule in book["rules"]:
        if rule["status"] != "rule" or rule["check"]["kind"] == "human":
            continue
        scoped = [f for f in files if in_scope(f, rule["scope"])]
        if not scoped:
            continue
        check = rule["check"]
        meta = {"rule_id": rule["id"], "kind": check["kind"],
                "calibrated": bool(rule.get("calibration"))}
        if check["kind"] == "deterministic":
            emit(meta, command=check["command"].replace("{files}", " ".join(scoped)))
            continue
        for path in scoped:
            try:
                source = read_source(repo, path, rev)
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue  # deleted by the change
            touched = touched_by_file.get(path) if touched_by_file is not None else None
            try:
                units = list(units_for(path, source, check, touched))
            except SyntaxError as exc:
                emit({**meta, "path": path, "error": f"cannot parse: {exc}"})
                continue
            for unit in units:
                emit({**meta, "path": unit["path"], "lines": unit["lines"], "unit_kind": unit["kind"],
                      "name": unit.get("name")}, request=request(rule, unit, model))


def run_examples(book: dict[str, Any], repo: Path, model: str) -> None:
    for rule in book["rules"]:
        if rule["check"]["kind"] != "semantic":
            continue
        for i, example in enumerate(rule.get("examples") or []):
            if "code" in example:
                unit = {"path": example.get("path", "synthetic"), "lines": "synthetic",
                        "kind": rule["check"]["unit"], "code": example["code"]}
            else:
                path, _, span = example["ref"].rpartition(":")
                first, _, last = span.partition("-")
                lines = (repo / path).read_text(encoding="utf-8").splitlines()
                unit = {"path": path, "lines": span, "kind": rule["check"]["unit"],
                        "code": cut(lines, int(first), int(last or first))}
            meta = {"rule_id": rule["id"], "example": i, "expect": example["expect"],
                    "note": example.get("note", "")}
            emit(meta, request=request(rule, unit, model))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rulebook", type=Path)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--diff", metavar="RANGE", help="git range, e.g. origin/main...HEAD")
    mode.add_argument("--staged", action="store_true", help="the index, for a pre-commit hook")
    mode.add_argument("--files", nargs="+", metavar="PATH", help="every unit in these files")
    mode.add_argument("--examples", action="store_true", help="each rule's calibration examples")
    mode.add_argument("--sweep", action="store_true",
                      help="every unit of every tracked file in scope: accepted code should raise no flags")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--model", default="jev-latest")
    args = ap.parse_args(argv)
    try:
        book = load_rulebook(args.rulebook)
    except RulebookError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.examples:
        run_examples(book, args.repo, args.model)
    elif args.files:
        files = [Path(f).as_posix() for f in args.files]
        run_change(book, args.repo, None, files, None, args.model)
    elif args.sweep:
        run_change(book, args.repo, None, git(args.repo, "ls-files").splitlines(), None, args.model)
    else:
        touched = changed_lines(args.repo, ["--cached"] if args.staged else [args.diff])
        rev = "" if args.staged else new_side(args.diff)
        run_change(book, args.repo, touched, sorted(touched), rev, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
