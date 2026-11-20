"""Git-only SQL parsing for the entity registry (F2/F5).

This module never opens a ClickHouse client. It extracts ``CREATE TABLE`` column
lists + ``COMMENT`` strings from ``sql/schema/*.sql`` and provides locality
checks ("does this column/symbol resolve inside this sibling source?") used by
the compiler, the ``explain_column`` enricher, and the platform gate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# Leading column identifier of a DDL column definition (backticked or bare).
_COL_HEAD = re.compile(r"^\s*(?:`(?P<bt>[^`]+)`|(?P<bare>" + _IDENT + r"))\s+\S")
# COMMENT 'text' (single quotes may be doubled to escape).
_COMMENT = re.compile(r"COMMENT\s+'((?:[^']|'')*)'", re.IGNORECASE)
# Optional concept tag inside a COMMENT body: ``| concept:<id>``.
_CONCEPT_TAG = re.compile(r"\|\s*concept:\s*(\S+)")
# Non-column DDL items we skip when scanning a CREATE block.
_NON_COLUMN_HEAD = re.compile(
    r"^\s*(INDEX|CONSTRAINT|PRIMARY\s+KEY|PROJECTION)\b", re.IGNORECASE
)


def strip_sql_comments(sql_text: str) -> str:
    """Remove ``--`` line and ``/* */`` block comments, preserving string literals.

    Column ``COMMENT '...| concept:<id>'`` tags live inside quoted strings and are
    therefore retained.
    """
    out: list[str] = []
    i = 0
    n = len(sql_text)
    in_squote = False
    while i < n:
        ch = sql_text[i]
        if in_squote:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql_text[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and sql_text[i + 1] == "-":
            while i < n and sql_text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and sql_text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql_text[i] == "*" and sql_text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level(block: str) -> list[str]:
    """Split a CREATE-block body on commas at paren-depth 0 (quote aware)."""
    items: list[str] = []
    depth = 0
    in_squote = False
    buf: list[str] = []
    i = 0
    while i < len(block):
        ch = block[i]
        if in_squote:
            if ch == "'":
                # Doubled '' is an escaped quote, stay in string.
                if i + 1 < len(block) and block[i + 1] == "'":
                    buf.append("''")
                    i += 2
                    continue
                in_squote = False
            buf.append(ch)
        elif ch == "'":
            in_squote = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        items.append("".join(buf))
    return items


def _create_block(sql_text: str, open_paren_idx: int) -> str | None:
    """Return the body between the matching parens starting at ``open_paren_idx``."""
    depth = 0
    in_squote = False
    i = open_paren_idx
    start = open_paren_idx + 1
    while i < len(sql_text):
        ch = sql_text[i]
        if in_squote:
            if ch == "'":
                if i + 1 < len(sql_text) and sql_text[i + 1] == "'":
                    i += 2
                    continue
                in_squote = False
        elif ch == "'":
            in_squote = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return sql_text[start:i]
        i += 1
    return None


def parse_create_tables(sql_text: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Map ``table -> {column: {"comment": str|None, "concept": str|None}}``."""
    sql_text = strip_sql_comments(sql_text)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for m in re.finditer(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(" + _IDENT + r")`?\s*\(",
        sql_text,
        re.IGNORECASE,
    ):
        table = m.group(1)
        body = _create_block(sql_text, m.end() - 1)
        if body is None:
            continue
        cols: dict[str, dict[str, Any]] = {}
        for item in _split_top_level(body):
            if _NON_COLUMN_HEAD.match(item):
                continue
            head = _COL_HEAD.match(item)
            if not head:
                continue
            name = head.group("bt") or head.group("bare")
            cm = _COMMENT.search(item)
            comment = cm.group(1).replace("''", "'") if cm else None
            concept = None
            if comment:
                tag = _CONCEPT_TAG.search(comment)
                if tag:
                    concept = tag.group(1)
            cols[name] = {"comment": comment, "concept": concept}
        out[table] = cols
    return out


def insert_target(sql_text: str) -> str | None:
    """Target table of an ``INSERT INTO <table>`` transform, if present."""
    m = re.search(r"INSERT\s+INTO\s+`?(" + _IDENT + r")`?", sql_text, re.IGNORECASE)
    return m.group(1) if m else None


def transform_config_target(sql_text: str) -> str | None:
    """``target: <table>`` from a ``@transform-config`` comment block."""
    m = re.search(r"^\s*--\s*target:\s*(" + _IDENT + r")", sql_text, re.IGNORECASE | re.MULTILINE)
    return m.group(1) if m else None


def table_for_source(source_path: Path) -> str | None:
    """Best-effort table name a source file defines/populates.

    schema ``*.sql`` -> first ``CREATE TABLE`` name; transform ``*.sql`` ->
    ``@transform-config target`` or ``INSERT INTO`` target. ``*.py`` -> None.
    """
    if not source_path.is_file() or source_path.suffix.lower() != ".sql":
        return None
    text = source_path.read_text(encoding="utf-8")
    tables = parse_create_tables(text)
    if tables:
        return next(iter(tables))
    return transform_config_target(text) or insert_target(text)


def column_exists_in_source(source_path: Path, column: str) -> bool:
    """Locality check: ``column`` is defined/produced inside ``source_path``.

    For schema files this is an exact ``CREATE TABLE`` column match; for
    transforms / Python the column appears as a whole-word identifier (covers
    INSERT targets, CTE aliases, and override keys).
    """
    if not source_path.is_file():
        return False
    text = source_path.read_text(encoding="utf-8")
    if source_path.suffix.lower() == ".sql":
        for cols in parse_create_tables(text).values():
            if column in cols:
                return True
    return re.search(r"\b" + re.escape(column) + r"\b", text) is not None


def iter_schema_files(repo_root: Path):
    schema_dir = repo_root / "sql" / "schema"
    if not schema_dir.is_dir():
        return
    for f in sorted(schema_dir.glob("*.sql")):
        yield f


def column_comment(repo_root: Path, table: str, column: str) -> str | None:
    """Find a column's ``COMMENT`` by scanning ``sql/schema/*.sql`` (git-only)."""
    for f in iter_schema_files(repo_root):
        tables = parse_create_tables(f.read_text(encoding="utf-8"))
        cols = tables.get(table)
        if cols and column in cols:
            return cols[column].get("comment")
    return None
