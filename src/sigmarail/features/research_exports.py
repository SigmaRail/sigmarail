"""Short-lived, owner-bound tickets for streamed Vera research queries.

Only ticket metadata and the validated query specification are persisted locally.
Query result rows are streamed from ClickHouse to Parquet and are never staged as
an export file on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sigmarail.features.signed_downloads import (
    issue_download_token as _issue_signed_download_token,
    verify_download_token as _verify_signed_download_token,
)

_TOKEN_AUDIENCE = "vera-research-export-stream"
_DOWNLOAD_TTL_SECONDS = 300
_EXPORT_ID_LENGTH = 32


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _positive_int(name: str, default: int, *, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


@dataclass(frozen=True)
class ExportConfig:
    """Local ticket catalog and streaming resource limits."""

    root: Path
    max_rows: int = 2_000_000
    max_bytes: int = 2_000_000_000
    max_tickets: int = 256
    max_principal_tickets: int = 32
    max_concurrent_exports: int = 4
    max_concurrent_principal_exports: int = 2
    export_ttl_seconds: int = 86_400
    query_timeout_seconds: int = 900

    @classmethod
    def from_env(cls) -> ExportConfig:
        root_value = os.environ.get("SIGMARAIL_MCP_EXPORT_ROOT", "").strip()
        if not root_value:
            raise ValueError(
                "SIGMARAIL_MCP_EXPORT_ROOT must be set to enable research exports"
            )
        return cls(
            root=Path(root_value).expanduser(),
            max_rows=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_ROWS", 2_000_000, maximum=50_000_000
            ),
            max_bytes=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_BYTES", 2_000_000_000, maximum=50_000_000_000
            ),
            max_tickets=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_TICKETS", 256, maximum=100_000
            ),
            max_principal_tickets=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_PRINCIPAL_TICKETS", 32, maximum=10_000
            ),
            max_concurrent_exports=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_CONCURRENT", 4, maximum=128
            ),
            max_concurrent_principal_exports=_positive_int(
                "SIGMARAIL_MCP_EXPORT_MAX_PRINCIPAL_CONCURRENT", 2, maximum=64
            ),
            export_ttl_seconds=_positive_int(
                "SIGMARAIL_MCP_EXPORT_TTL_SECONDS", 86_400, maximum=2_592_000
            ),
            query_timeout_seconds=_positive_int(
                "SIGMARAIL_MCP_EXPORT_QUERY_TIMEOUT_SECONDS", 900, maximum=86_400
            ),
        )


class ExportError(RuntimeError):
    """Expected export lifecycle failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _principal_key(principal_id: str) -> str:
    value = principal_id.strip()
    if not value or len(value) > 256:
        raise ValueError(
            "principal_id must be a non-empty identifier of at most 256 characters"
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ExportStore:
    """SQLite metadata store; contains no result rows or Parquet files."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.root = config.root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise ExportError(
                "unsafe_export_permissions",
                "export ticket root must be private (mode 0700)",
            )
        self.database = self.root / "exports.sqlite3"
        descriptor = os.open(
            self.database, os.O_CREAT | os.O_RDWR, 0o600
        )
        os.close(descriptor)
        self.database.chmod(0o600)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_stream_tickets (
                    export_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ready','running','completed','failed','revoked')),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    query_fingerprint TEXT NOT NULL,
                    query_spec_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT 'parquet',
                    manifest_json TEXT,
                    error_message TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_stream_owner_expiry "
                "ON research_stream_tickets(principal_id, expires_at, status)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS research_stream_token_uses "
                "(token_id TEXT PRIMARY KEY, expires_at TEXT NOT NULL)"
            )
            ticket_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(research_stream_tickets)"
                )
            }
            if "format" not in ticket_columns:
                connection.execute(
                    "ALTER TABLE research_stream_tickets "
                    "ADD COLUMN format TEXT NOT NULL DEFAULT 'parquet'"
                )
        self.database.chmod(0o600)

    def create_ticket(
        self,
        *,
        principal_id: str,
        query_fingerprint: str,
        query_spec: dict[str, Any],
        provenance: dict[str, Any],
        format: str = "parquet",
    ) -> dict[str, Any]:
        if format not in {"parquet", "csv"}:
            raise ValueError("format must be 'parquet' or 'csv'")
        owner = _principal_key(principal_id)
        if not query_fingerprint or len(query_fingerprint) > 128:
            raise ValueError(
                "query_fingerprint must be present and at most 128 characters"
            )
        now = _utc_now()
        created_at = _iso(now)
        expires_at = _iso(now + timedelta(seconds=self.config.export_ttl_seconds))
        export_id = secrets.token_hex(_EXPORT_ID_LENGTH // 2)
        spec_json = json.dumps(query_spec, sort_keys=True, separators=(",", ":"))
        provenance_json = json.dumps(provenance, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM research_stream_tickets WHERE expires_at <= ? OR status='revoked'",
                (created_at,),
            )
            connection.execute(
                "DELETE FROM research_stream_token_uses WHERE expires_at <= ?",
                (created_at,),
            )
            total = connection.execute(
                "SELECT count(*) FROM research_stream_tickets WHERE expires_at > ?",
                (created_at,),
            ).fetchone()[0]
            owned = connection.execute(
                "SELECT count(*) FROM research_stream_tickets "
                "WHERE principal_id = ? AND expires_at > ?",
                (owner, created_at),
            ).fetchone()[0]
            if (
                total >= self.config.max_tickets
                or owned >= self.config.max_principal_tickets
            ):
                connection.rollback()
                raise ExportError(
                    "export_ticket_quota_exceeded", "too many active export tickets"
                )
            connection.execute(
                "INSERT INTO research_stream_tickets("
                "export_id,principal_id,status,created_at,expires_at,query_fingerprint,"
                "query_spec_json,provenance_json,format) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    export_id,
                    owner,
                    "ready",
                    created_at,
                    expires_at,
                    query_fingerprint,
                    spec_json,
                    provenance_json,
                    format,
                ),
            )
            connection.commit()
        return self.get_ticket(export_id, owner=principal_id)

    def get_ticket(self, export_id: str, *, owner: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_stream_tickets WHERE export_id=? AND principal_id=?",
                (export_id, _principal_key(owner)),
            ).fetchone()
        if row is None:
            raise ExportError("export_not_found", "export not found")
        result = dict(row)
        result["query_spec"] = json.loads(result.pop("query_spec_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        manifest_json = result.pop("manifest_json")
        result["manifest"] = json.loads(manifest_json) if manifest_json else None
        if datetime.fromisoformat(result["expires_at"]) <= _utc_now():
            raise ExportError("export_expired", "export ticket has expired")
        return result

    def authorize_ticket(
        self, export_id: str, *, owner_hash: str, token_id: str, token_expires_at: str
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_stream_tickets "
                "WHERE export_id=? AND principal_id=? AND status='ready'",
                (export_id, owner_hash),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ExportError(
                    "export_not_found", "export ticket is absent or revoked"
                )
            result = dict(row)
            if datetime.fromisoformat(result["expires_at"]) <= _utc_now():
                connection.rollback()
                raise ExportError("export_expired", "export ticket has expired")
            now = _iso(_utc_now())
            active = connection.execute(
                "SELECT count(*) FROM research_stream_tickets "
                "WHERE status='running' AND expires_at > ?",
                (now,),
            ).fetchone()[0]
            active_owner = connection.execute(
                "SELECT count(*) FROM research_stream_tickets "
                "WHERE principal_id=? AND status='running' AND expires_at > ?",
                (owner_hash, now),
            ).fetchone()[0]
            if (
                active >= self.config.max_concurrent_exports
                or active_owner >= self.config.max_concurrent_principal_exports
            ):
                connection.rollback()
                raise ExportError(
                    "export_concurrency_limit",
                    "too many exports are currently running",
                )
            try:
                connection.execute(
                    "INSERT INTO research_stream_token_uses(token_id, expires_at) VALUES(?,?)",
                    (token_id, token_expires_at),
                )
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ExportError(
                    "download_token_replayed", "download token has already been used"
                ) from exc
            connection.execute(
                "UPDATE research_stream_tickets SET status='running' WHERE export_id=?",
                (export_id,),
            )
            connection.commit()
        result["status"] = "running"
        result["query_spec"] = json.loads(result.pop("query_spec_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def complete_ticket(self, export_id: str, manifest: dict[str, Any]) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE research_stream_tickets SET status='completed', manifest_json=? "
                "WHERE export_id=? AND status='running'",
                (
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                    export_id,
                ),
            )
        if cursor.rowcount != 1:
            raise ExportError(
                "export_state_conflict", "stream ticket is no longer running"
            )

    def fail_ticket(self, export_id: str, error_message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE research_stream_tickets SET status='failed', error_message=? "
                "WHERE export_id=? AND status='running'",
                (error_message[:500], export_id),
            )

    def revoke(self, export_id: str, *, owner: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE research_stream_tickets SET status='revoked' "
                "WHERE export_id=? AND principal_id=? AND status='ready'",
                (export_id, _principal_key(owner)),
            )
        if cursor.rowcount != 1:
            raise ExportError("export_not_found", "export not found")


class ExportJobManager:
    """Ticket signer and owner-scoped access to the streaming export policy."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.store = ExportStore(config)

    @classmethod
    def from_env(cls) -> ExportJobManager:
        secret = os.environ.get("SIGMARAIL_MCP_EXPORT_SIGNING_SECRET", "").encode("utf-8")
        if len(secret) < 32:
            raise ValueError(
                "SIGMARAIL_MCP_EXPORT_SIGNING_SECRET must contain at least 32 bytes"
            )
        public_url = os.environ.get("SIGMARAIL_MCP_PUBLIC_BASE_URL", "").strip()
        parsed = urlsplit(public_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError(
                "SIGMARAIL_MCP_PUBLIC_BASE_URL must be an HTTPS origin without a path"
            )
        return cls(ExportConfig.from_env())

    @staticmethod
    def principal_for_api_key(api_key: str) -> str:
        if not api_key:
            raise ExportError(
                "unauthorized", "an authenticated MCP principal is required"
            )
        return "api-key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def create_stream_ticket(
        self,
        *,
        principal_id: str,
        query_fingerprint: str,
        query_spec: dict[str, Any],
        provenance: dict[str, Any],
        format: str = "parquet",
    ) -> dict[str, Any]:
        return self.store.create_ticket(
            principal_id=principal_id,
            query_fingerprint=query_fingerprint,
            query_spec=query_spec,
            provenance=provenance,
            format=format,
        )

    def get_job(self, export_id: str, *, principal_id: str) -> dict[str, Any]:
        return self.store.get_ticket(export_id, owner=principal_id)

    def issue_download_token(
        self, export_id: str, *, principal_id: str
    ) -> dict[str, Any]:
        ticket = self.store.get_ticket(export_id, owner=principal_id)
        if ticket["status"] != "ready":
            raise ExportError(
                "export_not_ready", "export ticket is not ready for download"
            )
        secret = os.environ.get("SIGMARAIL_MCP_EXPORT_SIGNING_SECRET", "").encode("utf-8")
        if len(secret) < 32:
            raise ExportError(
                "export_signing_not_configured",
                "SIGMARAIL_MCP_EXPORT_SIGNING_SECRET must contain at least 32 bytes",
            )
        token, claims = _issue_signed_download_token(
            secret=secret,
            audience=_TOKEN_AUDIENCE,
            resource_id=export_id,
            principal_id=_principal_key(principal_id),
            ttl_seconds=_DOWNLOAD_TTL_SECONDS,
        )
        return {
            "token": token,
            "expires_in_seconds": _DOWNLOAD_TTL_SECONDS,
            "export_id": claims["resource_id"],
            "format": ticket["format"],
            "compression": "zstd" if ticket["format"] == "parquet" else "gzip",
        }

    def authorize_stream(self, export_id: str, token: str | None) -> dict[str, Any]:
        claims = self._validate_token(export_id, token)
        ticket = self.store.authorize_ticket(
            export_id,
            owner_hash=claims["principal_id"],
            token_id=claims["jti"],
            token_expires_at=_iso(datetime.fromtimestamp(claims["exp"], UTC)),
        )
        ticket["claims"] = claims
        return ticket

    def complete_stream(self, export_id: str, manifest: dict[str, Any]) -> None:
        self.store.complete_ticket(export_id, manifest)

    def fail_stream(self, export_id: str, message: str) -> None:
        self.store.fail_ticket(export_id, message)

    def _validate_token(self, export_id: str, token: str | None) -> dict[str, Any]:
        secret = os.environ.get("SIGMARAIL_MCP_EXPORT_SIGNING_SECRET", "").encode("utf-8")
        if len(secret) < 32 or not token:
            raise ExportError(
                "invalid_download_token", "download token is invalid or expired"
            )
        claims = _verify_signed_download_token(
            token,
            secret=secret,
            audience=_TOKEN_AUDIENCE,
            resource_id=export_id,
            max_ttl_seconds=_DOWNLOAD_TTL_SECONDS,
        )
        if claims is None:
            raise ExportError(
                "invalid_download_token", "download token is invalid or expired"
            )
        claims["export_id"] = claims.pop("resource_id")
        return claims
