"""Prove each rule's why by breaking the rule in a scratch copy and watching the harm.

A rule's `why` says what breaks, for whom, when the rule is violated. If nobody can make that
break happen, the why is not understood, and a rule nobody understands is wrong. For every rule
whose harm is runnable, this script:

  1. checks HEAD out into a temporary git worktree (the user's own tree is never touched),
  2. writes `harm.files` into it (probe scripts that are not part of the repository),
  3. runs `harm.run` there: the control,
  4. applies `harm.edit`, the violation (each `old` must occur exactly once in its file),
  5. runs `harm.run` again.

The why is proven when `harm.expect` matches the second run's output and not the control's:
the same command, the same tree, one difference, and the harm appears only with it.

    python prove_harm.py rulebook.yaml                    # every rule with a runnable harm
    python prove_harm.py rulebook.yaml CHUNK-001 LINK-002 # only these
    python prove_harm.py rulebook.yaml --repo path/to/repo

One JSON line per rule, with `result`:

    proven          the harm appears with the violation and not without it
    already_broken  the control shows the harm too: HEAD already breaks the rule (report it),
                    or `expect` is loose enough to match healthy output
    no_harm         the violation changed nothing `expect` looks for: the why is wrong, the rule
                    sits where the guarantee is not made, or it is a habit, not a rule
    error           the probe could not run as written (an edit that does not apply, a timeout)
    reader          the harm lands in a person; the user confirms it, no code can

Exit code 0 when every probed rule is proven, 1 otherwise, 2 for an invalid rulebook. HEAD is
what gets probed: commit or stash work in progress first if the probe should see it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_states import RulebookError, load_rulebook  # noqa: E402

TIMEOUT = 300
TAIL = 1500


class ProbeError(Exception):
    pass


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def run(command: str, cwd: Path) -> str:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"`{command}` ran past {TIMEOUT}s") from exc
    return p.stdout + p.stderr


def apply_edit(tree: Path, edit: dict[str, Any]) -> None:
    path = tree / edit["path"]
    if not path.is_file():
        raise ProbeError(f"harm.edit: {edit['path']} does not exist at HEAD")
    text = path.read_bytes().decode("utf-8")
    old, new = edit["old"], edit["new"]
    if text.count(old) == 0 and "\r\n" in text:  # a checkout with CRLF line endings
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    found = text.count(old)
    if found != 1:
        raise ProbeError(f"harm.edit: the old text occurs {found} times in {edit['path']}, not once")
    path.write_bytes(text.replace(old, new).encode("utf-8"))


def probe(repo: Path, harm: dict[str, Any]) -> dict[str, Any]:
    scratch = Path(tempfile.mkdtemp(prefix="harm-"))
    tree = scratch / "tree"
    try:
        git(repo, "worktree", "add", "--detach", "--quiet", str(tree), "HEAD")
        for rel, content in (harm.get("files") or {}).items():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_text(content, encoding="utf-8")
        control = run(harm["run"], tree)
        for edit in harm["edit"]:
            apply_edit(tree, edit)
        violated = run(harm["run"], tree)
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
                       capture_output=True)
        shutil.rmtree(scratch, ignore_errors=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    expect = re.compile(harm["expect"])
    in_control, in_violated = bool(expect.search(control)), bool(expect.search(violated))
    result = "already_broken" if in_control else "proven" if in_violated else "no_harm"
    return {"result": result, "control": control[-TAIL:], "violation": violated[-TAIL:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rulebook", type=Path)
    ap.add_argument("rule_ids", nargs="*", metavar="RULE_ID")
    ap.add_argument("--repo", type=Path, default=Path("."))
    args = ap.parse_args(argv)
    try:
        book = load_rulebook(args.rulebook)
    except RulebookError as exc:
        print(exc, file=sys.stderr)
        return 2
    wanted = set(args.rule_ids)
    unknown = wanted - {r["id"] for r in book["rules"]}
    if unknown:
        print(f"no such rule: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    all_proven = True
    for rule in book["rules"]:
        harm = rule.get("harm")
        if not harm or (wanted and rule["id"] not in wanted):
            continue
        out: dict[str, Any] = {"rule_id": rule["id"], "protects": rule.get("protects")}
        if harm.get("reader"):
            out.update(result="reader", detail=f"{harm['reader']}: {harm['misled']}")
        else:
            try:
                out.update(probe(args.repo, harm))
            except (ProbeError, subprocess.CalledProcessError) as exc:
                out.update(result="error", detail=str(exc) if isinstance(exc, ProbeError)
                           else (exc.stderr or str(exc)).strip())
            all_proven &= out["result"] == "proven"
        print(json.dumps(out, ensure_ascii=False))
    return 0 if all_proven else 1


if __name__ == "__main__":
    sys.exit(main())
