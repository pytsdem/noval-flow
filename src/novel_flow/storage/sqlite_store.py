from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from novel_flow.exceptions import StorageError
from novel_flow.models.schemas import BlockPatchVersion, BookDocument, CriticReport, ResearchReport, WorkflowState


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pe_run_id ON pipeline_events(run_id);

                CREATE TABLE IF NOT EXISTS workflow_states (
                    run_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    current_book_id TEXT,
                    mode TEXT NOT NULL DEFAULT 'formal',
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_reports (
                    report_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS books (
                    book_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS critic_reports (
                    report_id TEXT PRIMARY KEY,
                    book_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS patch_versions (
                    version_id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL,
                    block_id TEXT NOT NULL,
                    patch_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_outputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    output_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_run_outputs_run_id ON run_outputs(run_id);
                """
            )
            self._ensure_column(connection, "workflow_states", "current_book_id", "TEXT")
            self._ensure_column(connection, "workflow_states", "mode", "TEXT NOT NULL DEFAULT 'formal'")
            self._ensure_column(connection, "critic_reports", "book_id", "TEXT")

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _to_json(model: BaseModel) -> str:
        return model.model_dump_json(indent=2)

    @staticmethod
    def _from_json(data: str) -> dict[str, Any]:
        return json.loads(data)

    def save_workflow_state(self, state: WorkflowState, mode: str = "formal") -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workflow_states (run_id, stage, current_book_id, mode, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        stage = excluded.stage,
                        current_book_id = excluded.current_book_id,
                        mode = excluded.mode,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        state.run_id,
                        state.stage.value,
                        state.current_book_id,
                        mode,
                        self._to_json(state),
                        state.updated_at.isoformat(),
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save workflow state: {exc}") from exc

    def load_workflow_state(self, run_id: str) -> WorkflowState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflow_states WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return WorkflowState.model_validate(self._from_json(row["payload_json"]))

    def save_research_report(self, report: ResearchReport) -> None:
        self._save_simple(
            table="research_reports",
            key_name="report_id",
            key_value=report.report_id,
            payload=report,
            title=None,
            created_at=report.created_at.isoformat(),
            updated_at=None,
        )

    def load_research_report(self, report_id: str) -> ResearchReport | None:
        return self._load_simple("research_reports", "report_id", report_id, ResearchReport)

    def save_book(self, book: BookDocument) -> None:
        self._save_simple(
            table="books",
            key_name="book_id",
            key_value=book.id,
            payload=book,
            title=book.title,
            created_at=book.created_at.isoformat(),
            updated_at=book.updated_at.isoformat(),
        )

    def load_book(self, book_id: str) -> BookDocument | None:
        return self._load_simple("books", "book_id", book_id, BookDocument)

    def list_books(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT book_id, title, payload_json, created_at, updated_at
                FROM books
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = self._from_json(row["payload_json"])
            results.append(
                {
                    "book_id": row["book_id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "chapter_count": sum(len(volume.get("chapters", [])) for volume in payload.get("volumes", [])),
                    "next_chapter_index": payload.get("metadata", {}).get("next_chapter_index"),
                }
            )
        return results

    def find_books_by_title(self, title: str, limit: int = 10) -> list[BookDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM books
                WHERE title LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (f"%{title}%", limit),
            ).fetchall()
        return [BookDocument.model_validate(self._from_json(row["payload_json"])) for row in rows]

    def delete_book(self, book_id: str) -> None:
        with self._connect() as connection:
            run_rows = connection.execute(
                "SELECT run_id FROM workflow_states WHERE current_book_id = ?",
                (book_id,),
            ).fetchall()
            run_ids = [row["run_id"] for row in run_rows]
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                connection.execute(f"DELETE FROM pipeline_events WHERE run_id IN ({placeholders})", run_ids)
                connection.execute(f"DELETE FROM run_outputs WHERE run_id IN ({placeholders})", run_ids)
                connection.execute(f"DELETE FROM workflow_states WHERE run_id IN ({placeholders})", run_ids)
            connection.execute("DELETE FROM patch_versions WHERE book_id = ?", (book_id,))
            connection.execute("DELETE FROM critic_reports WHERE book_id = ?", (book_id,))
            connection.execute("DELETE FROM books WHERE book_id = ?", (book_id,))

    def delete_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM pipeline_events WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_outputs WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM workflow_states WHERE run_id = ?", (run_id,))

    def save_critic_report(self, report: CriticReport, book_id: str | None = None) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO critic_reports (report_id, book_id, payload_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        report.report_id,
                        book_id,
                        self._to_json(report),
                        report.created_at.isoformat(),
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save record into critic_reports: {exc}") from exc

    def load_critic_report(self, report_id: str) -> CriticReport | None:
        return self._load_simple("critic_reports", "report_id", report_id, CriticReport)

    def load_latest_critic_report(self, book_id: str) -> CriticReport | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM critic_reports
                WHERE book_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (book_id,),
            ).fetchone()
        if row is None:
            return None
        return CriticReport.model_validate(self._from_json(row["payload_json"]))

    def save_patch_version(self, version: BlockPatchVersion) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO patch_versions
                    (version_id, book_id, block_id, patch_id, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version.version_id,
                        version.book_id,
                        version.block_id,
                        version.patch_id,
                        self._to_json(version),
                        version.created_at.isoformat(),
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save patch version: {exc}") from exc

    def list_patch_versions(self, book_id: str, block_id: str) -> list[BlockPatchVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM patch_versions
                WHERE book_id = ? AND block_id = ?
                ORDER BY created_at ASC
                """,
                (book_id, block_id),
            ).fetchall()
        return [BlockPatchVersion.model_validate(self._from_json(row["payload_json"])) for row in rows]

    def _save_simple(
        self,
        table: str,
        key_name: str,
        key_value: str,
        payload: BaseModel,
        title: str | None,
        created_at: str,
        updated_at: str | None,
    ) -> None:
        try:
            with self._connect() as connection:
                if table == "books":
                    connection.execute(
                        f"""
                        INSERT INTO {table} ({key_name}, title, payload_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT({key_name}) DO UPDATE SET
                            title = excluded.title,
                            payload_json = excluded.payload_json,
                            updated_at = excluded.updated_at
                        """,
                        (key_value, title, self._to_json(payload), created_at, updated_at),
                    )
                else:
                    connection.execute(
                        f"""
                        INSERT OR REPLACE INTO {table} ({key_name}, payload_json, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (key_value, self._to_json(payload), created_at),
                    )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save record into {table}: {exc}") from exc

    def _load_simple(self, table: str, key_name: str, key_value: str, model_type: type[BaseModel]) -> Any:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE {key_name} = ?",
                (key_value,),
            ).fetchone()
        if row is None:
            return None
        return model_type.model_validate(self._from_json(row["payload_json"]))

    def save_event(self, event: Any) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO pipeline_events (run_id, event_type, agent, title, payload_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event.event_type,
                        event.agent,
                        event.title,
                        json.dumps(event.payload, ensure_ascii=False),
                        event.ts,
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save event: {exc}") from exc

    def list_events(self, run_id: str, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, agent, title, payload_json, ts
                FROM pipeline_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (run_id, after_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_events(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, agent, title, payload_json, ts
                FROM (
                    SELECT id, event_type, agent, title, payload_json, ts
                    FROM pipeline_events
                    WHERE run_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_run_output(
        self,
        *,
        run_id: str,
        agent: str,
        output_type: str,
        title: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO run_outputs (run_id, agent, output_type, title, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        agent,
                        output_type,
                        title,
                        json.dumps(payload, ensure_ascii=False),
                        created_at,
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Failed to save run output: {exc}") from exc

    def list_run_outputs(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, agent, output_type, title, payload_json, created_at
                FROM run_outputs
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_runs(self, limit: int = 30, book_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT run_id, stage, current_book_id, mode, updated_at FROM workflow_states"
        params: list[Any] = []
        if book_id:
            query += " WHERE current_book_id = ?"
            params.append(book_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def latest_run_for_book(self, book_id: str) -> str | None:
        runs = self.list_runs(limit=1, book_id=book_id)
        if not runs:
            return None
        return str(runs[0]["run_id"])
