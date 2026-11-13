"""Backpressured Parquet and gzip CSV streaming from ClickHouse Arrow batches."""

from __future__ import annotations

import gzip
import hashlib
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from starlette.responses import JSONResponse, StreamingResponse


class _QueueSink:
    """Minimal non-seekable output consumed by Arrow encoders."""

    def __init__(
        self, chunks: queue.Queue[bytes | None], cancel: threading.Event, max_bytes: int
    ):
        self.chunks = chunks
        self.cancel = cancel
        self.max_bytes = max_bytes
        self.written = 0
        self.closed = False
        self.discard_writes = False
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        if self.discard_writes:
            return len(data)
        if self.cancel.is_set():
            raise BrokenPipeError("client disconnected")
        self.written += len(data)
        if self.written > self.max_bytes:
            raise ValueError("export exceeded the configured byte limit")
        self.digest.update(data)
        view = memoryview(data)
        for start in range(0, len(view), 64 * 1024):
            chunk = bytes(view[start : start + 64 * 1024])
            while not self.cancel.is_set():
                try:
                    self.chunks.put(chunk, timeout=0.25)
                    break
                except queue.Full:
                    continue
            if self.cancel.is_set():
                raise BrokenPipeError("client disconnected")
        return len(data)

    def tell(self) -> int:
        return self.written

    def flush(self) -> None:
        return None

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


def _arrow_stream_response(
    *,
    client: Any,
    sql: str,
    parameters: dict[str, object],
    export_id: str,
    max_rows: int,
    max_bytes: int,
    timeout_seconds: int,
    query_fingerprint: str,
    provenance: dict[str, Any],
    output_format: str,
    on_complete: Callable[[dict[str, Any]], None],
    on_error: Callable[[str], None],
) -> StreamingResponse | JSONResponse:
    """Stream Arrow batches through a bounded Parquet or gzip CSV byte queue."""
    if output_format not in {"parquet", "csv"}:
        raise ValueError("output_format must be 'parquet' or 'csv'")
    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=8)
    ready = threading.Event()
    cancel = threading.Event()
    state: dict[str, Any] = {
        "error": None,
        "rows": 0,
        "schema": None,
        "stream_ready": False,
    }

    def mark_failed(message: str) -> None:
        try:
            on_error(message)
        except Exception:  # noqa: BLE001 - lifecycle callbacks cannot strand a stream
            pass

    def produce() -> None:
        writer: Any | None = None
        gzip_output: gzip.GzipFile | None = None
        sink = _QueueSink(chunks, cancel, max_bytes)
        started = time.monotonic()
        try:
            with client.query_arrow_stream(
                sql,
                parameters=parameters,
                settings={
                    "max_execution_time": timeout_seconds,
                    "max_result_rows": max_rows,
                    "result_overflow_mode": "throw",
                },
            ) as batches:
                for batch in batches:
                    if cancel.is_set():
                        return
                    if time.monotonic() - started > timeout_seconds:
                        raise TimeoutError(
                            "export query exceeded the configured runtime limit"
                        )
                    if not isinstance(batch, pa.RecordBatch):
                        raise TypeError("ClickHouse returned a non-Arrow record batch")
                    state["rows"] += batch.num_rows
                    if state["rows"] > max_rows:
                        raise ValueError("export exceeded the configured row limit")
                    if writer is None:
                        state["schema"] = [
                            {
                                "name": field.name,
                                "type": str(field.type),
                                "nullable": field.nullable,
                            }
                            for field in batch.schema
                        ]
                        if output_format == "parquet":
                            writer = pq.ParquetWriter(
                                sink, batch.schema, compression="zstd"
                            )
                        else:
                            gzip_output = gzip.GzipFile(
                                fileobj=sink, mode="wb", mtime=0
                            )
                            writer = pacsv.CSVWriter(
                                gzip_output,
                                batch.schema,
                                write_options=pacsv.WriteOptions(include_header=True),
                            )
                        state["stream_ready"] = True
                        ready.set()
                    if output_format == "parquet":
                        writer.write_batch(batch)
                    else:
                        writer.write(batch)
            if writer is None:
                state["error"] = ValueError(
                    "query returned no rows; schema cannot be inferred"
                )
            else:
                writer.close()
                writer = None
                if gzip_output is not None:
                    gzip_output.close()
                    gzip_output = None
                state["manifest"] = {
                    "export_id": export_id,
                    "status": "completed",
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "row_count": state["rows"],
                    "size_bytes": sink.written,
                    "sha256": sink.digest.hexdigest(),
                    "format": output_format,
                    "compression": "zstd" if output_format == "parquet" else "gzip",
                    "schema": state["schema"],
                    "query_fingerprint": query_fingerprint,
                    "provenance": provenance,
                }
        except Exception as exc:  # noqa: BLE001 - query and encoder failures must terminate the stream
            state["error"] = exc
        finally:
            if writer is not None:
                if state["error"] is None:
                    try:
                        writer.close()
                    except Exception as exc:  # noqa: BLE001 - cleanup must always release the stream
                        state["error"] = exc
                if state["error"] is not None:
                    # Drain encoder state without finalizing a failed partial file.
                    sink.discard_writes = True
                    try:
                        writer.close()
                    except Exception:  # noqa: BLE001 - abort cleanup is best effort
                        pass
                writer = None
            if gzip_output is not None:
                if state["error"] is not None:
                    sink.discard_writes = True
                try:
                    gzip_output.close()
                except Exception:  # noqa: BLE001 - abort cleanup is best effort
                    pass
                gzip_output = None
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001 - ensure a client-close failure reaches the stream
                if state["error"] is None and "manifest" not in state:
                    state["error"] = exc
            ready.set()
            while not cancel.is_set():
                try:
                    chunks.put(None, timeout=0.25)
                    break
                except queue.Full:
                    continue

    worker = threading.Thread(
        target=produce, name=f"vera-export-{export_id[:8]}", daemon=True
    )
    worker.start()
    ready.wait(timeout=timeout_seconds)
    if not ready.is_set():
        cancel.set()
        mark_failed("export query timed out")
        try:
            client.close()
        except Exception:  # noqa: BLE001, S110 - timeout response takes precedence
            pass
        return JSONResponse(
            {"error": "export query timed out", "code": "query_timeout"},
            status_code=504,
        )
    if state["error"] is not None and not state["stream_ready"]:
        cancel.set()
        mark_failed(str(state["error"]))
        return JSONResponse(
            {"error": str(state["error"]), "code": "export_failed"}, status_code=422
        )

    def body() -> Iterator[bytes]:
        completed = False
        try:
            while True:
                chunk = chunks.get()
                if chunk is None:
                    if state["error"] is not None:
                        raise RuntimeError(
                            "ClickHouse export stream ended before completion"
                        )
                    break
                yield chunk
            worker.join(timeout=1)
            manifest = state.get("manifest")
            if manifest is None:
                raise RuntimeError("export stream ended without a manifest")
            on_complete(manifest)
            completed = True
        except Exception as exc:  # noqa: BLE001 - ensure incomplete downloads fail their ticket
            mark_failed(str(exc))
            raise
        finally:
            if not completed and state["error"] is None:
                mark_failed("client disconnected before export completed")
            cancel.set()
            if worker.is_alive():
                try:
                    client.close()
                except Exception:  # noqa: BLE001, S110 - disconnect cleanup is best effort
                    pass

    return StreamingResponse(
        body(),
        media_type=(
            "application/vnd.apache.parquet"
            if output_format == "parquet"
            else "application/gzip"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="vera-research-{export_id}.parquet"'
                if output_format == "parquet"
                else f'attachment; filename="vera-research-{export_id}.csv.gz"'
            ),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
        },
    )


def parquet_stream_response(**kwargs: Any) -> StreamingResponse | JSONResponse:
    """Stream ClickHouse Arrow batches as Zstandard-compressed Parquet."""
    return _arrow_stream_response(output_format="parquet", **kwargs)


def csv_gzip_stream_response(**kwargs: Any) -> StreamingResponse | JSONResponse:
    """Stream ClickHouse Arrow batches as a gzip-compressed CSV file."""
    return _arrow_stream_response(output_format="csv", **kwargs)
