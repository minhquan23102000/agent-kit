"""The clerk: enumerate the behaviour points of an artifact, mechanically.

Reads the artifact so the agent does not have to, and returns one row per behaviour it
can exhibit, with the line number it lives on. Those rows are the raw material for the
`facts` field; naming each row as a fact and giving it a probe is the agent's work.

Parsing is tree-sitter, via `tree-sitter-language-pack`, which carries grammars for the
languages below and fetches any other on first use. No hand-written pattern table decides
what parses; the grammar does. What remains hand-written is the only thing a grammar
cannot supply: **what counts as a behaviour point in this language**. In a control-flow
language it is a return, a throw, a branch. In SQL it is a predicate: rows that match are
included, rows that do not are not. In a data language it is a key.

Three tiers:

  treesitter  the grammar parsed it. Preferred, and the only tier with SQL.
  astgrep     no grammar here, but the ast_grep tool can read it.
  none        neither. This tier REFUSES rather than returning an empty list, because an
              empty list reads as "nothing to check" and that is the lie this skill exists
              to prevent.

    python clerk.py src/router.py
    python clerk.py query.sql
    python clerk.py schema.yaml --json

    import sys; sys.path.insert(0, r".../decompose-facts/scripts")
    from clerk import paths
    rows = await paths("src/app.ts")
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tree_sitter_language_pack as _pack
except ImportError:  # the ast_grep tier and the refusal tier still work
    _pack = None

# Node types that mean "the artifact can behave differently here", in the great majority
# of grammars. Verified against javascript, typescript, python, go, java, c and others.
DEFAULT_NODES = frozenset({
    "return_statement", "throw_statement", "raise_statement",
    "if_statement", "catch_clause", "except_clause",
    "switch_statement", "case_clause", "match_statement",
    "yield_statement", "try_statement", "assert_statement",
})

# Where a language names the same idea differently, or expresses it as an expression.
LANGUAGE_NODES: dict[str, frozenset[str]] = {
    "rust": frozenset({"return_expression", "if_expression", "match_expression",
                       "try_expression", "panic_expression"}),
    "ruby": frozenset({"return", "if", "if_modifier", "unless", "unless_modifier",
                       "case", "rescue"}),
    "yaml": frozenset({"block_mapping_pair"}),
    "json": frozenset({"pair"}),
    "toml": frozenset({"pair"}),
    "bash": frozenset({"if_statement"}),
}

# Behaviours that are a call, not a keyword, so they need a query rather than a node type.
# Each captures the whole construct as @hit, not just the name: "exit 2" is the behaviour,
# "exit" on its own is not.
LANGUAGE_QUERIES: dict[str, list[str]] = {
    "go": ['(call_expression function: (identifier) @n (#eq? @n "panic")) @hit'],
    "rust": ['(macro_invocation macro: (identifier) @n (#eq? @n "panic")) @hit'],
    "bash": ['(command name: (command_name) @n (#eq? @n "exit")) @hit'],
    "ruby": ['(call method: (identifier) @n (#eq? @n "raise")) @hit'],
}

# SQL carries no control flow. Its paths are predicates, and the tree marks them as such.
SQL_PREDICATE_NODES = frozenset({"where", "having", "join"})
SQL_CONJUNCTIONS = frozenset({"keyword_and", "keyword_or"})

EXTENSION_LANGUAGE = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".sql": "sql",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "c_sharp", ".php": "php", ".kt": "kotlin", ".swift": "swift",
    ".scala": "scala", ".lua": "lua", ".ex": "elixir", ".exs": "elixir",
    ".hs": "haskell", ".dart": "dart", ".html": "html", ".css": "css",
}

# The ast_grep fallback, for a language tree-sitter has no grammar for here.
ASTGREP_PATTERNS: dict[str, list[str]] = {
    "javascript": ["return $X", "throw $X", "if ($C) { $$$B }", "catch ($E) { $$$B }"],
    "typescript": ["return $X", "throw $X", "if ($C) { $$$B }", "catch ($E) { $$$B }"],
    "java": ["return $X", "throw $X", "if ($C) { $$$B }", "catch ($E) { $$$B }"],
    "go": ["return $X", "panic($X)", "if $C { $$$B }"],
}


class NoClerk(Exception):
    """No parser for this artifact; enumerate it by hand and carry the raw span."""


def _text(source: bytes, node) -> str:
    return re.sub(r"\s+", " ", source[node.start_byte:node.end_byte].decode("utf-8", "replace")).strip()


def _walk(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children)


def _sql_rows(source: bytes, root) -> list[dict]:
    """Each predicate is one fact: rows matching it are included, rows that do not are not."""
    rows = []

    def leaves(node):
        """Descend through AND/OR to the individual predicates, which are the real facts."""
        operator = node.child_by_field_name("operator")
        if operator is not None and operator.type in SQL_CONJUNCTIONS:
            for side in ("left", "right"):
                child = node.child_by_field_name(side)
                if child is not None:
                    yield from leaves(child)
        else:
            yield node

    for node in _walk(root):
        if node.type not in SQL_PREDICATE_NODES:
            continue
        predicate = node.child_by_field_name("predicate")
        if predicate is None:
            continue
        for leaf in leaves(predicate):
            rows.append({
                "function": "-",
                "line": leaf.start_point[0] + 1,
                "kind": "predicate",
                "text": _text(source, leaf)[:120],
                "clause": node.type,
            })
    return sorted(rows, key=lambda r: r["line"])


def _treesitter_rows(source: bytes, language: str) -> list[dict] | None:
    """None means this grammar is not available, which is not the same as no behaviour."""
    if _pack is None:
        return None
    try:
        parser = _pack.get_parser(language)
    except Exception:
        return None
    tree = parser.parse(source)
    root = tree.root_node
    if root.has_error and root.child_count == 0:
        return None

    if language == "sql":
        return _sql_rows(source, root)

    nodes = LANGUAGE_NODES.get(language, DEFAULT_NODES)
    rows = []
    for node in _walk(root):
        if node.type in nodes:
            rows.append({"function": "-", "line": node.start_point[0] + 1,
                         "kind": "path", "text": _text(source, node)[:120],
                         "node": node.type})

    for pattern in LANGUAGE_QUERIES.get(language, []):
        try:
            from tree_sitter import Query, QueryCursor
            query = Query(_pack.get_language(language), pattern)
            for hit in QueryCursor(query).captures(root).get("hit", []):
                rows.append({"function": "-", "line": hit.start_point[0] + 1,
                             "kind": "path", "text": _text(source, hit)[:120],
                             "node": hit.type})
        except Exception:
            pass

    seen, unique = set(), []
    for row in sorted(rows, key=lambda r: r["line"]):
        key = (row["line"], row["text"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _find_grep():
    """The eval kernel exposes `tool` in the calling namespace, not in builtins."""
    import inspect
    frame = inspect.currentframe()
    while frame is not None:
        found = frame.f_globals.get("tool")
        if found is not None:
            return found.ast_grep
        frame = frame.f_back
    raise NoClerk("cannot reach the ast_grep tool from here; pass grep= explicitly.")


_MATCH_RE = re.compile(r"^\*(\d+)\|(.*)$")


def _parse_display(text: str, pattern: str) -> list[dict]:
    """The ast_grep tool reports '*<line>|<text>' per match, then indented meta lines."""
    rows: list[dict] = []
    current = None
    for line in text.splitlines():
        match = _MATCH_RE.match(line)
        if match:
            current = {"function": "-", "line": int(match.group(1)), "kind": "path",
                       "text": match.group(2).strip()[:120], "pattern": pattern}
            rows.append(current)
        elif current is not None and line[:1] in (" ", "\t") and not line.strip().startswith("meta:"):
            current["text"] = (current["text"] + " " + re.sub(r"^\s*\d+\|", "", line).strip())[:120]
    return rows


async def paths(target: str | Path, language: str | None = None, grep=None) -> dict:
    """Return {"tier": ..., "rows": [...], "note": ...} for one artifact."""
    path = Path(target)
    lang = language or EXTENSION_LANGUAGE.get(path.suffix.lower())
    source = path.read_bytes()

    if lang is None:
        raise NoClerk(
            f"no language for {path.suffix or path.name!r}. Pass language= explicitly rather than "
            "letting the clerk guess, because a wrong grammar parses into silent nonsense."
        )

    rows = _treesitter_rows(source, lang)
    if rows is not None:
        note = "via tree-sitter" if rows else (
            "0 behaviour points. Check this against the file: a grammar that parses cleanly and a "
            "set of node types that do not match is indistinguishable from an artifact that does "
            "nothing, and this note is the only thing separating the two."
        )
        return {"tier": "treesitter", "language": lang, "rows": rows, "note": note}

    if lang in ASTGREP_PATTERNS:
        grep = grep or _find_grep()
        collected: list[dict] = []
        for pattern in ASTGREP_PATTERNS[lang]:
            found = await grep({"pat": pattern, "path": str(path), "lang": lang})
            collected.extend(_parse_display(found.get("text", ""), pattern))
        seen, unique = set(), []
        for row in sorted(collected, key=lambda r: r["line"]):
            key = (row["line"], row["text"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return {"tier": "astgrep", "language": lang, "rows": unique,
                "note": "via ast_grep; no tree-sitter grammar here"}

    raise NoClerk(
        f"no grammar for language {lang!r} (file {path.name!r}) and no ast_grep patterns either. "
        "This is the tier that refuses: enumerate it by hand, and carry the raw span with each "
        "fact, because a clerk that returns an empty list here would read as 'nothing to check'."
    )


def _render(result: dict) -> None:
    rows = result["rows"]
    print(f"tier={result['tier']} language={result['language']} rows={len(rows)}  ({result['note']})")
    for row in rows:
        extra = f" [{row.get('clause') or row.get('node')}]" if row.get("clause") or row.get("node") else ""
        print(f"  line {row['line']:>4}  {row['kind']:<9}  {row['text']}{extra}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--language")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = args.path
    lang = args.language or EXTENSION_LANGUAGE.get(path.suffix.lower())
    if lang is None:
        print(f"no language for {path.name}; pass --language rather than letting the clerk guess",
              file=sys.stderr)
        return 3

    rows = _treesitter_rows(path.read_bytes(), lang)
    if rows is None:
        print(f"{lang} needs the ast_grep tool, which this offline CLI cannot reach. Run these "
              f"from the eval kernel:", file=sys.stderr)
        for pattern in ASTGREP_PATTERNS.get(lang, []):
            print(f'  ast_grep  pat="{pattern}"  lang="{lang}"  path="{path}"', file=sys.stderr)
        if lang not in ASTGREP_PATTERNS:
            print(f"  no clerk for {lang}: enumerate by hand and carry the raw span", file=sys.stderr)
        return 3

    result = {"tier": "treesitter", "language": lang, "rows": rows, "note": "via tree-sitter"}
    print(json.dumps(result, indent=2)) if args.json else _render(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
