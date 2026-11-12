"""Shared transform-file parsing and ``xform_*`` view registration/invocation.

Transforms are authored as parameterized views under ``sql/schema/``:

.. code-block:: sql

    -- target schema SQL file, e.g. 50-schema-relative_strength.sql
    CREATE OR REPLACE VIEW xform_relative_strength (ticker, date, ...)
    COMMENT '{"order":50,"target":"relative_strength","sources":["relative_strength_ranks"],"chunk_size":"1m"}'
    AS
    WITH ...
    SELECT ... WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}

The view DDL carries the schedule metadata (``COMMENT`` JSON); the SELECT body
is byte-identical to the historical ``INSERT INTO`` transform text.

Registration must go through the HTTP ``clickhouse-connect`` client
(``client.command``) — ``clickhouse-client`` performs client-side
``{param:Type}`` substitution that corrupts parameterized view placeholders.

Populate then schedules off the registered objects (``transform_catalog``) and
per chunk executes ``INSERT INTO <target> (cols) SELECT * FROM xform_*(...)``.

Legacy ``INSERT INTO`` transforms (``sql/transform/metrics/*.sql``) remain
supported: they parse to ``shape='insert'`` and keep the ``@transform-config``
comment header as their config carrier.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from sigmarail.config import app_config, get_database_config, get_schema_dir, get_schema_files
from sigmarail.sql_script import split_sql_statements

logger = logging.getLogger(__name__)

XFORM_VIEW_PREFIX = "xform_"

_TRANSFORM_PARAMS = re.compile(r"\{(\w+):(\w+)\}")

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

_CREATE_VIEW_HEAD = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>(?:`?db`?\.)?`?name`?|(?P<vname>" + _IDENT + r"))",
    re.IGNORECASE,
)

_INSERT_HEAD = re.compile(
    r"^\s*INSERT\s+INTO\s+(?:(?P<db>" + _IDENT + r")\.)?(?P<target>" + _IDENT + r")",
    re.IGNORECASE,
)

_COMMENT_LITERAL = re.compile(
    r"COMMENT\s+'((?:[^'\\]|\\.|'')*)'", re.IGNORECASE
)


@dataclass
class TransformSpec:
    """A parsed transform — either a parameterized view or a legacy INSERT."""

    shape: str                      # 'view' | 'insert'
    name: str                       # metric slug (e.g. 'relative-strength')
    view_name: Optional[str]        # 'xform_relative_strength' for view shape
    target: Optional[str]           # populate target table
    columns: Optional[List[str]]    # output column list (view paren / INSERT cols)
    param_names: List[str]          # declared {name:Type} placeholders, in order
    param_types: Dict[str, str]     # name -> declared ClickHouse type
    config: Dict[str, Any]          # COMMENT JSON (view) or @transform-config (insert)
    create_ddl: Optional[str]       # full CREATE VIEW statement (view shape)
    body: str                       # SELECT body (view) or full INSERT text (insert)
    path: Optional[Path] = None

    @property
    def order(self) -> int:
        """Execution order from config; filename numeric prefix as fallback."""
        order = self.config.get("order")
        if isinstance(order, int):
            return order
        if order is not None:
            try:
                return int(order)
            except (TypeError, ValueError):
                pass
        if self.path is not None:
            m = re.match(r"^(\d+)-", self.path.name)
            if m:
                return int(m.group(1)) % 400 if int(m.group(1)) >= 400 else int(m.group(1))
        return 999999

    @property
    def chunk_size(self) -> Optional[str]:
        value = self.config.get("chunk_size")
        return str(value).strip().lower() if value is not None else None

    @property
    def sources(self) -> List[str]:
        sources = self.config.get("sources") or []
        return [str(s) for s in sources]

    @property
    def deprecated(self) -> bool:
        return bool(self.config.get("deprecated"))


def _rewrite_sql_database_qualifier(sql_content: str) -> str:
    """Rewrite the SigmaRail database qualifier for isolated test databases."""
    if app_config.mode != "test":
        return sql_content
    db = get_database_config().database
    if not db or db == "sigmarail":
        return sql_content
    return sql_content.replace("sigmarail.", f"{db}.")


def _first_statement_start(text: str) -> Optional[str]:
    """First keyword of the first non-comment statement (CREATE / INSERT / WITH...)."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        m = re.match(r"([A-Za-z]+)", stripped)
        return m.group(1).upper() if m else None
    return None


def _paren_block(text: str, open_idx: int) -> Optional[str]:
    """Text between the parens starting at ``open_idx`` (``text[open_idx] == '('``)."""
    depth = 0
    in_squote = False
    i = open_idx
    while i < len(text):
        ch = text[i]
        if in_squote:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
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
                return text[open_idx + 1 : i]
        i += 1
    return None


def _split_top_level(block: str) -> List[str]:
    """Split on commas at paren-depth 0 (quote aware)."""
    items: List[str] = []
    depth = 0
    in_squote = False
    buf: List[str] = []
    i = 0
    while i < len(block):
        ch = block[i]
        if in_squote:
            buf.append(ch)
            if ch == "'":
                if i + 1 < len(block) and block[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_squote = False
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
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        items.append("".join(buf).strip())
    return [c for c in items if c]


def _strip_sql_comments(text: str) -> str:
    """Remove ``--`` and ``/* */`` comments outside string/backtick literals."""
    out: List[str] = []
    in_squote = in_btick = in_line = in_block = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_line:
            if ch == "\n":
                in_line = False
                out.append(ch)
            i += 1
            continue
        if in_block:
            if ch == "*" and i + 1 < len(text) and text[i + 1] == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if in_squote:
            out.append(ch)
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue
        if in_btick:
            out.append(ch)
            if ch == "`":
                in_btick = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
        elif ch == "`":
            in_btick = True
        elif ch == "-" and i + 1 < len(text) and text[i + 1] == "-":
            in_line = True
            i += 2
            continue
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            in_block = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_column_list(block: Optional[str]) -> Optional[List[str]]:
    """Column names from a paren block — comments stripped, quoting preserved."""
    if block is None:
        return None
    cols = [item.strip() for item in _split_top_level(_strip_sql_comments(block))]
    return [c for c in cols if c] or None


def _unescape_sql_string(raw: str) -> str:
    """Unescape a single-quoted SQL string body ('' -> ', \\' -> ')."""
    return raw.replace("''", "'").replace("\\'", "'").replace("\\\\", "\\")


def _parse_comment_config(ddl: str) -> Dict[str, Any]:
    """JSON dict from the ``COMMENT '<json>'`` clause on a CREATE VIEW."""
    m = _COMMENT_LITERAL.search(ddl)
    if not m:
        return {}
    try:
        parsed = json.loads(_unescape_sql_string(m.group(1)))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Transform view COMMENT is not valid JSON config")
        return {}


def parse_header_config(text: str) -> Optional[Dict[str, Any]]:
    """Parse the ``-- @transform-config`` YAML header (legacy insert-shape files)."""
    config_lines: List[str] = []
    in_config = False
    for line in text.split("\n"):
        if line.strip().startswith("-- @transform-config"):
            in_config = True
            continue
        if in_config:
            if line.strip().startswith("--"):
                config_line = line[2:].strip()
                if config_line:
                    if config_line.startswith("@") and config_line != "@transform-config":
                        break
                    if config_line.replace("=", "").replace("-", "").strip() == "":
                        break
                    if config_line and not config_line.startswith("-") and ":" not in config_line:
                        if config_line[0].isupper() or config_line.startswith("#"):
                            break
                    config_lines.append(config_line)
            elif line.strip():
                break
    if not config_lines:
        return None
    try:
        config = yaml.safe_load("\n".join(config_lines))
        return config if isinstance(config, dict) else None
    except yaml.YAMLError:
        return None


def _scan_params(body: str) -> tuple[List[str], Dict[str, str]]:
    names: List[str] = []
    types: Dict[str, str] = {}
    for name, ptype in _TRANSFORM_PARAMS.findall(body):
        if name not in types:
            names.append(name)
            types[name] = ptype
    return names, types


def view_name_for(path: Path) -> str:
    """``NNN-xform-<slug>.sql`` -> ``xform_<slug>``; bare ``NN-<slug>.sql`` -> ``xform_<slug>``."""
    stem = path.stem
    stem = re.sub(r"^\d+-", "", stem)
    stem = re.sub(r"^xform[-_]", "", stem)
    return XFORM_VIEW_PREFIX + stem.replace("-", "_")


def slug_for_name(view_name: str) -> str:
    """``xform_relative_strength`` -> ``relative-strength`` (filename slug form)."""
    return view_name.removeprefix(XFORM_VIEW_PREFIX).replace("_", "-")


def _strip_leading_comments(text: str) -> str:
    lines = text.splitlines()
    idx = 0
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith("--")):
        idx += 1
    return "\n".join(lines[idx:])


def parse_transform(text: str, *, path: Optional[Path] = None, name: Optional[str] = None) -> TransformSpec:
    """Parse a transform file (or stored ``create_table_query``) into a spec."""
    sql = _strip_leading_comments(text)
    first = _first_statement_start(text)
    starts_managed_view = bool(re.match(
        r"(?is)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:`?[A-Za-z_][\w]*`?\.)?`?xform_[A-Za-z0-9_]+`?\b",
        _strip_sql_comments(sql),
    ))
    if first != "CREATE" or not starts_managed_view:
        # Co-located schema files may begin with table DDL before a single
        # managed transform view. Resolve that view for callers that pass a
        # schema-file path; multi-view files must use discover_transform_specs
        # so each view remains unambiguous.
        views = []
        for statement in split_sql_statements(text):
            candidate = _strip_sql_comments(statement).strip()
            if re.match(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                r"(?:`?[A-Za-z_][\w]*`?\.)?`?xform_[A-Za-z0-9_]+`?\b",
                candidate,
                re.IGNORECASE,
            ):
                views.append(candidate)
        if len(views) == 1:
            view_match = re.search(r"\b(xform_[A-Za-z0-9_]+)\b", views[0], re.IGNORECASE)
            resolved_name = name or (slug_for_name(view_match.group(1)) if view_match else None)
            return parse_transform(views[0], path=path, name=resolved_name)
        if len(views) > 1:
            raise ValueError(
                "schema file contains multiple managed views; select one with discover_transform_specs()"
            )
    if name:
        slug = name
    elif path:
        slug = re.sub(r"^\d+-(?:xform-)?", "", path.stem)
    else:
        slug = "transform"

    if first == "CREATE":
        head = re.search(
            r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(?:`?" + _IDENT + r"`?\.)?`?(?P<vname>" + _IDENT + r")`?",
            sql,
            re.IGNORECASE,
        )
        if not head:
            raise ValueError("unparseable CREATE VIEW transform header")
        vname = head.group("vname")
        rest = sql[head.end() :]
        columns: Optional[List[str]] = None
        rest_l = rest.lstrip()
        if rest_l.startswith("("):
            offset = len(rest) - len(rest_l)
            block = _paren_block(rest, offset)
            if block is not None:
                columns = _parse_column_list(block)
                rest = rest[offset + len(block) + 2 :]
                # Stored DDL may emit a second paren list: typed columns first
                # `(`name` Type, ...)` then the output aliases `(a, b, ...)`.
                rest_l = rest.lstrip()
                if rest_l.startswith("("):
                    offset = len(rest) - len(rest_l)
                    alias_block = _paren_block(rest, offset)
                    if alias_block is not None:
                        columns = _parse_column_list(alias_block)
                        rest = rest[offset + len(alias_block) + 2 :]
                elif columns is not None:
                    # Single list may still be typed (`name` Type) — strip types.
                    columns = [
                        re.sub(r"^(`[^`]+`|[A-Za-z_][\w.]*)\s+.*$", r"\1", c)
                        for c in columns
                    ]
        config = _parse_comment_config(rest)
        as_match = re.search(r"\bAS\b", rest, re.IGNORECASE)
        body = rest[as_match.end() :].strip() if as_match else ""
        param_names, param_types = _scan_params(body or rest)
        target = config.get("target") or None
        return TransformSpec(
            shape="view",
            name=slug,
            view_name=vname,
            target=target,
            columns=columns,
            param_names=param_names,
            param_types=param_types,
            config=config,
            create_ddl=sql.strip(),
            body=body,
            path=path,
        )

    if first == "INSERT":
        m = _INSERT_HEAD.search(sql)
        if not m:
            raise ValueError("unparseable INSERT transform header")
        target = m.group("target")
        columns = None
        rest = sql[m.end() :].lstrip()
        if rest.startswith("("):
            block = _paren_block(rest, 0)
            columns = _parse_column_list(block)
        config = parse_header_config(text) or {}
        if "target" in config and config["target"]:
            target = str(config["target"]).split(".")[-1]
        param_names, param_types = _scan_params(sql)
        return TransformSpec(
            shape="insert",
            name=slug,
            view_name=None,
            target=target,
            columns=columns,
            param_names=param_names,
            param_types=param_types,
            config=config,
            create_ddl=None,
            body=sql.strip(),
            path=path,
        )

    raise ValueError(f"unrecognized transform shape (first statement: {first!r})")


def statement_semicolons(body: str) -> List[int]:
    """Positions of ``;`` outside comments and string literals."""
    positions: List[int] = []
    in_squote = in_line_comment = in_block_comment = False
    i = 0
    while i < len(body):
        ch = body[i]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and i + 1 < len(body) and body[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
        elif in_squote:
            if ch == "'":
                if i + 1 < len(body) and body[i + 1] == "'":
                    i += 2
                    continue
                in_squote = False
        elif ch == "'":
            in_squote = True
        elif ch == "-" and i + 1 < len(body) and body[i + 1] == "-":
            in_line_comment = True
            i += 2
            continue
        elif ch == "/" and i + 1 < len(body) and body[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        elif ch == ";":
            positions.append(i)
        i += 1
    return positions


def insert_select_body(spec: TransformSpec) -> str:
    """The ``WITH ... SELECT`` body of an insert-shape transform (after the INSERT header).

    Statement-terminating ``;`` is removed (a view's ``AS`` clause carries no
    terminator); trailing ``--`` comments after it are kept — ClickHouse parses
    them out of the stored definition while the file stays documented.
    """
    if spec.shape != "insert":
        raise ValueError("insert_select_body requires an insert-shape spec")
    m = _INSERT_HEAD.search(spec.body)
    if not m:
        raise ValueError("unparseable INSERT header")
    rest = spec.body[m.end() :].lstrip()
    if rest.startswith("("):
        block = _paren_block(rest, 0)
        if block is not None:
            rest = rest[len(block) + 2 :].lstrip()
    semis = statement_semicolons(rest)
    if semis:
        for pos in reversed(semis):
            rest = rest[:pos] + rest[pos + 1 :]
    return rest.strip("\n").rstrip()


def transform_files_dir(project_root: Optional[Path] = None) -> Path:
    if project_root is not None:
        return Path(project_root) / "sql" / "schema"
    return get_schema_dir()


def legacy_transform_files_dir(project_root: Optional[Path] = None) -> Path:
    root = Path(project_root) if project_root else Path(__file__).resolve().parent
    return root / "sql" / "transform" / "metrics"


def discover_transform_files(project_root: Optional[Path] = None) -> List[Path]:
    """Schema SQL files containing one or more managed ``xform_*`` views."""
    return sorted({spec.path for spec in discover_transform_specs(project_root) if spec.path})


def discover_transform_specs(project_root: Optional[Path] = None) -> List[TransformSpec]:
    """Parse managed views from any SQL file under ``sql/schema``.

    A schema script may contain table DDL and multiple managed views. Each
    ``xform_*`` CREATE VIEW is parsed independently; filename conventions do
    not determine the transform identity or its populate configuration.
    """
    schema_dir = transform_files_dir(project_root)
    if not schema_dir.is_dir():
        return []
    specs: List[TransformSpec] = []
    schema_files = get_schema_files() if project_root is None else sorted(
        schema_dir.glob("*.sql"), key=_metric_sql_sort_key
    )
    for path in sorted(schema_files, key=_metric_sql_sort_key):
        for statement in split_sql_statements(path.read_text(encoding="utf-8")):
            sql = _strip_sql_comments(statement).strip()
            head = re.match(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                r"(?:`?[A-Za-z_][\w]*`?\.)?`?(?P<name>xform_[A-Za-z0-9_]+)`?\b",
                sql,
                re.IGNORECASE,
            )
            if not head:
                continue
            view_name = head.group("name")
            try:
                spec = parse_transform(sql, path=path, name=slug_for_name(view_name))
                spec.view_name = view_name
                specs.append(spec)
            except Exception as e:
                logger.warning("Could not parse managed view %s in %s: %s", view_name, path.name, e)
    return specs


def discover_legacy_transform_files(project_root: Optional[Path] = None) -> List[Path]:
    """Legacy insert-shape files under ``sql/transform/metrics``."""
    legacy_dir = legacy_transform_files_dir(project_root)
    if not legacy_dir.is_dir():
        return []
    return sorted(legacy_dir.glob("[0-9]*-*.sql"))


def _metric_sql_sort_key(path: Path) -> tuple[int, str]:
    m = re.match(r"^(\d+)-", path.name)
    order = int(m.group(1)) if m else 999999
    return (order, path.name)


def register_transform_view(client, spec: TransformSpec, *, name: Optional[str] = None) -> None:
    """Explicitly (re)register one view via HTTP; never use clickhouse-client.

    Schema DDL is create-if-missing. This explicit operational path remains
    replace-capable so ``--register-views`` can refresh a stored definition.
    """
    ddl = spec.create_ddl
    if ddl is None:
        raise ValueError(f"spec {spec.name} has no CREATE VIEW DDL to register")
    ddl = re.sub(
        r"(?is)^CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?",
        "CREATE OR REPLACE VIEW ",
        ddl,
        count=1,
    )
    if name and name != spec.view_name:
        ddl = re.sub(
            r"\bVIEW\s+" + re.escape(spec.view_name or "") + r"\b",
            f"VIEW {name}",
            ddl,
            count=1,
            flags=re.IGNORECASE,
        )
    client.command(_rewrite_sql_database_qualifier(ddl))


def register_all_transform_views(
    client, project_root: Optional[Path] = None
) -> tuple[List[str], List[tuple[str, str]]]:
    """Register every managed view found in schema SQL. Returns (registered, errors)."""
    registered: List[str] = []
    errors: List[tuple[str, str]] = []
    for spec in discover_transform_specs(project_root):
        try:
            register_transform_view(client, spec)
            registered.append(spec.view_name or spec.name)
        except Exception as e:
            name = spec.view_name or (spec.path.name if spec.path else spec.name)
            logger.warning("Failed to register transform view %s: %s", name, e)
            errors.append((name, str(e)))
    return registered, errors


def _param_literal(value: Any, ptype: Optional[str]) -> str:
    """Render a parameter value as an inline SQL literal for view invocation."""
    t = (ptype or "").lower()
    if t.startswith(("uint", "int", "float", "decimal")):
        return str(value)
    return "'" + str(value).replace("'", "\\'") + "'"


def chunk_insert_sql(spec: TransformSpec, params: Dict[str, Any], *, view_name: Optional[str] = None) -> str:
    """``INSERT INTO <target> [(cols)] SELECT * FROM <view>(name=literal, ...)``.

    Only parameters actually declared in the view body are passed.
    """
    if not spec.target:
        raise ValueError(f"transform {spec.name} has no target")
    vname = view_name or spec.view_name
    if not vname:
        raise ValueError(f"transform {spec.name} has no view to select from")
    args = ", ".join(
        f"{name}={_param_literal(params[name], spec.param_types.get(name))}"
        for name in spec.param_names
        if name in params
    )
    invocation = f"{vname}({args})" if args else vname
    cols = f" ({', '.join(spec.columns)})" if spec.columns else ""
    return f"INSERT INTO {spec.target}{cols} SELECT * FROM {invocation}"


def transform_catalog(client) -> List[TransformSpec]:
    """Registered transform views as specs, ordered by ``config.order``.

    This is populate's schedule source: ordering, chunk size, sources and the
    deprecated flag all come from the ``COMMENT`` JSON stored in the database.
    """
    result = client.query(
        """
        SELECT name, comment, create_table_query
        FROM system.tables
        WHERE database = currentDatabase()
          AND engine = 'View'
          AND startsWith(name, 'xform_')
        ORDER BY name
        """
    )
    specs: List[TransformSpec] = []
    for name, comment, create_ddl in result.result_rows:
        try:
            spec = parse_transform(create_ddl, name=slug_for_name(name))
            if not spec.config and comment:
                try:
                    parsed = json.loads(comment)
                    if isinstance(parsed, dict):
                        spec.config.update(parsed)
                        if parsed.get("target") and not spec.target:
                            spec.target = str(parsed["target"]).split(".")[-1]
                except json.JSONDecodeError:
                    pass
            spec.view_name = name
            specs.append(spec)
        except Exception as e:
            logger.warning("Could not parse registered transform %s: %s", name, e)
    specs.sort(key=lambda s: (s.order, s.view_name or ""))
    return specs


def stale_transform_views(client, project_root: Optional[Path] = None) -> List[str]:
    """Registered ``xform_*`` views with no matching file — candidates for DROP."""
    expected = {spec.view_name for spec in discover_transform_specs(project_root) if spec.view_name}
    result = client.query(
        """
        SELECT name FROM system.tables
        WHERE database = currentDatabase()
          AND engine = 'View'
          AND startsWith(name, 'xform_')
        """
    )
    return [name for (name,) in result.result_rows if name not in expected]


def run_transform_file(
    client,
    path_or_text,
    params: Dict[str, Any],
    *,
    settings: Optional[Dict[str, Any]] = None,
    view_name: Optional[str] = None,
) -> None:
    """Parse → register → single-chunk INSERT. Shared by populate, healer, tests.

    ``view_name`` lets callers register under a scoped name (e.g. the healer's
    ``xform_heal_<slug>``) without mutating the on-disk file.
    """
    if isinstance(path_or_text, Path):
        path = path_or_text
    else:
        s = str(path_or_text)
        path = Path(s) if "\n" not in s and len(s) < 4096 else None
    if path is not None and path.is_file():
        text = path.read_text()
    else:
        path, text = None, str(path_or_text)
    spec = parse_transform(text, path=path)
    if spec.shape == "insert":
        client.command(
            _rewrite_sql_database_qualifier(spec.body),
            parameters=params,
            settings=settings or {},
        )
        return
    register_transform_view(client, spec, name=view_name)
    client.command(
        chunk_insert_sql(spec, params, view_name=view_name),
        settings=settings or {},
    )
