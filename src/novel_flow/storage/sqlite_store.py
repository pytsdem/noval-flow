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
                CREATE TABLE IF NOT EXISTS workflow_states (
                    run_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
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
                """
            )

    @staticmethod
    def _to_json(model: BaseModel) -> str:
        return model.model_dump_json(indent=2)

    @staticmethod
    def _from_json(data: str) -> dict[str, Any]:
        return json.loads(data)

    def save_workflow_state(self, state: WorkflowState) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workflow_states (run_id, stage, payload_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        stage = excluded.stage,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (state.run_id, state.stage.value, self._to_json(state), state.updated_at.isoformat()),
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

    def save_critic_report(self, report: CriticReport) -> None:
        self._save_simple(
            table="critic_reports",
            key_name="report_id",
            key_value=report.report_id,
            payload=report,
            title=None,
            created_at=report.created_at.isoformat(),
            updated_at=None,
        )

    def load_critic_report(self, report_id: str) -> CriticReport | None:
        return self._load_simple("critic_reports", "report_id", report_id, CriticReport)

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
