"""Small SQL-script helpers shared by schema loading and transform discovery."""

from __future__ import annotations

import re
from typing import List


def split_sql_statements(text: str) -> List[str]:
    """Split a ClickHouse SQL script at semicolons outside literals/comments."""
    def contains_sql(statement: str) -> bool:
        without_leading_comments = re.sub(
            r"(?s)^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*",
            "",
            statement,
        )
        return bool(without_leading_comments.strip())

    statements: List[str] = []
    current: List[str] = []
    in_single = in_double = in_backtick = in_line_comment = in_block_comment = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_single or in_double or in_backtick:
            current.append(ch)
            quote = "'" if in_single else '"' if in_double else "`"
            if ch == "\\" and nxt:
                current.append(nxt)
                i += 2
                continue
            if ch == quote:
                if nxt == quote:
                    current.append(nxt)
                    i += 2
                    continue
                in_single = in_double = in_backtick = False
            i += 1
            continue

        if ch == "-" and nxt == "-":
            current.extend((ch, nxt))
            in_line_comment = True
            i += 2
        elif ch == "/" and nxt == "*":
            current.extend((ch, nxt))
            in_block_comment = True
            i += 2
        elif ch == "'":
            current.append(ch)
            in_single = True
            i += 1
        elif ch == '"':
            current.append(ch)
            in_double = True
            i += 1
        elif ch == "`":
            current.append(ch)
            in_backtick = True
            i += 1
        elif ch == ";":
            statement = "".join(current).strip()
            if statement and contains_sql(statement):
                statements.append(statement)
            current = []
            i += 1
        else:
            current.append(ch)
            i += 1

    trailing = "".join(current).strip()
    if trailing and contains_sql(trailing):
        statements.append(trailing)
    return statements
