from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.master import MasterAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.config import Settings
from novel_flow.events import EventBus, PipelineEvent, RunCancelledError, check_cancelled
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.models.schemas import CharacterCard, ChapterPlan, PatchInstruction, PatchOperation, StoryPremise, WorkflowStage, WorkflowState
from novel_flow.services.crawler import MockTrendCrawler
from novel_flow.services.patcher import PatchExecutor

if TYPE_CHECKING:
    from novel_flow.storage.sqlite_store import SQLiteStore


@dataclass
class AppStores:
    formal: SQLiteStore
    test: SQLiteStore
    settings: Settings


@dataclass
class RunHandle:
    run_id: str
    mode: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class NovelApp:
    def __init__(self, stores: AppStores) -> None:
        self.stores = stores
        self._run_handles: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

    def list_novels(self, mode: str) -> list[dict[str, Any]]:
        store = self._store(mode)
        novels = store.list_books()
        for item in novels:
            item["latest_run_id"] = store.latest_run_for_book(item["book_id"])
        return novels

    def get_novel(self, mode: str, book_id: str) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            return {}
        latest_run_id = store.latest_run_for_book(book_id)
        latest_stage = None
        if latest_run_id:
            state = store.load_workflow_state(latest_run_id)
            if state is not None:
                latest_stage = state.stage.value
        blueprint_review = None
        if latest_run_id:
            for row in reversed(store.list_run_outputs(latest_run_id)):
                if row["output_type"] == "blueprint_review":
                    blueprint_review = self._parse_json(row["payload_json"])
                    break
        critic = store.load_latest_critic_report(book_id)
        return {
            "book": book.model_dump(mode="json"),
            "critic": critic.model_dump(mode="json") if critic else None,
            "blueprint_review": blueprint_review,
            "latest_run_id": latest_run_id,
            "latest_stage": latest_stage,
            "runs": self.list_runs(mode, book_id),
        }

    def list_runs(self, mode: str, book_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._store(mode).list_runs(book_id=book_id, limit=50)
        for row in rows:
            handle = self._handle(str(row["run_id"]))
            row["is_running"] = bool(handle and handle.is_running)
            row["cancel_requested"] = bool(handle and handle.cancel_event.is_set())
        return rows

    def get_run(self, mode: str, run_id: str) -> dict[str, Any]:
        store = self._store(mode)
        state = store.load_workflow_state(run_id)
        handle = self._handle(run_id)
        outputs = [
            {
                "id": row["id"],
                "agent": row["agent"],
                "output_type": row["output_type"],
                "title": row["title"],
                "created_at": row["created_at"],
                "payload": self._parse_json(row["payload_json"]),
            }
            for row in store.list_run_outputs(run_id)
        ]
        events = []
        for row in store.list_events(run_id, after_id=0, limit=500):
            item = dict(row)
            item["payload"] = self._parse_json(item["payload_json"])
            events.append(item)
        return {
            "run_id": run_id,
            "stage": state.stage.value if state else None,
            "current_book_id": state.current_book_id if state else None,
            "updated_at": state.updated_at.isoformat() if state else None,
            "is_running": bool(handle and handle.is_running),
            "cancel_requested": bool(handle and handle.cancel_event.is_set()),
            "outputs": outputs,
            "events": events,
        }

    def delete_novel(self, mode: str, book_id: str) -> None:
        self._store(mode).delete_book(book_id)

    def update_novel_concept(
        self,
        mode: str,
        *,
        book_id: str,
        title: str | None,
        premise: dict[str, Any] | None,
        characters: list[dict[str, Any]] | None,
        chapter_plans: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")

        if premise is not None:
            book.premise = StoryPremise.model_validate(premise)
        if title:
            book.title = title
        elif premise is not None:
            book.title = book.premise.title
        if characters is not None:
            book.characters = [CharacterCard.model_validate(item) for item in characters]
        if chapter_plans is not None:
            plans = [ChapterPlan.model_validate(item) for item in chapter_plans]
            book.metadata["chapter_plans"] = [plan.model_dump(mode="json") for plan in plans]
            next_index = int(book.metadata.get("next_chapter_index", 0))
            book.metadata["next_chapter_index"] = min(next_index, len(plans))
            completed = set(book.metadata.get("completed_chapter_ids", []))
            book.metadata["completed_chapter_ids"] = [plan.chapter_id for plan in plans if plan.chapter_id in completed]
        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return book.model_dump(mode="json")

    def stop_run(self, mode: str, run_id: str) -> None:
        handle = self._handle(run_id)
        if handle and handle.mode == mode and handle.is_running:
            handle.cancel_event.set()
        self._store(mode).delete_run(run_id)

    def ai_update_concept(self, mode: str, *, book_id: str, scope: str, target_id: str | None, guidance: str) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "ai_update_concept", "scope": scope, "target_id": target_id or ""})
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                updated_book = blueprint_agent.revise_concept(book, scope=scope, target_id=target_id, guidance=guidance)
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "BlueprintAgent", "concept_updated", "AI concept update", updated_book.model_dump(mode="json"))
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def ai_update_text(self, mode: str, *, book_id: str, scope: str, target_id: str, guidance: str) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PATCHING, current_book_id=book.id, context={"action": "ai_update_text", "scope": scope, "target_id": target_id})
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                if scope == "block":
                    updated_book = writer.rewrite_unit(book=book, block_id=target_id, guidance=guidance)
                elif scope == "chapter":
                    updated_book = writer.rewrite_chapter(book=book, chapter_id=target_id, guidance=guidance)
                else:
                    raise ValueError(f"Unsupported text update scope: {scope}")
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "text_updated", "AI text update", updated_book.model_dump(mode="json"))
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def start_formal_novel(self, query: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            master = self._build_master(store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                master.start_new_novel(query=query, run_id=run_id, mode="formal")

        return self._launch_run("formal", run_id, task)

    def continue_formal_novel(self, *, book_id: str | None = None, title: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            master = self._build_master(store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                master.continue_novel(book_id=book_id, title=title, run_id=run_id, mode="formal")

        return self._launch_run("formal", run_id, task)

    def test_blueprint(self, query: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, context={"query": query, "action": "blueprint"})
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                blueprint = blueprint_agent.build_blueprint(research_query=query)
                check_cancelled()
                writer = self._build_writer()
                book = writer.create_book(blueprint=blueprint, source_query=query)
                check_cancelled()
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "blueprint", "Blueprint", blueprint.model_dump(mode="json"))
                self._save_output(memory, run_id, "WriterAgent", "book_shell", "Book shell", book.model_dump(mode="json"))
                state.current_book_id = book.id
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_write_chapter(self, query: str | None = None, book_id: str | None = None) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                if book_id:
                    book = memory.load_book(book_id)
                    if book is None:
                        raise ValueError(f"Book not found: {book_id}")
                else:
                    if not query:
                        raise ValueError("Query is required when starting a new test novel.")
                    blueprint = self._build_blueprint_agent().build_blueprint(research_query=query)
                    check_cancelled()
                    book = writer.create_book(blueprint=blueprint, source_query=query)
                    check_cancelled()
                    memory.save_book(book)
                    self._save_output(memory, run_id, "BlueprintAgent", "blueprint", "Blueprint", blueprint.model_dump(mode="json"))
                updated_book, chapter = writer.write_next_chapter(book)
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "chapter_written", f"Chapter written: {chapter.title}", chapter.model_dump(mode="json"))
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.WRITING, current_book_id=updated_book.id, context={"action": "write_chapter"})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_critique(self, book_id: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            critic = self._build_critic()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                report = critic.review_book(book=book)
                check_cancelled()
                memory.save_critic_report(report, book_id=book.id)
                self._save_output(memory, run_id, "CriticAgent", "critic_report", "Critic report", report.model_dump(mode="json"))
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.CRITIQUE, current_book_id=book.id, latest_critic_report_id=report.report_id, context={"action": "critique"})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_patch(self, *, book_id: str, block_id: str, operation: str, patch_content: str, reason: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            instruction = PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation(operation),
                reason=reason,
                content=patch_content,
            )
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                patched_book, payload = writer.patch_block(book=book, instruction=instruction)
                check_cancelled()
                memory.save_book(patched_book)
                self._save_output(memory, run_id, "WriterAgent", "patch_version", f"Patch applied: {instruction.target_block_id}", payload["patch_version"])
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.PATCHING, current_book_id=patched_book.id, context={"action": "patch", "block_id": block_id})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def _launch_run(self, mode: str, run_id: str, task: Callable[[SQLiteStore, RunHandle], None]) -> str:
        store = self._store(mode)
        handle = RunHandle(run_id=run_id, mode=mode)
        store.save_event(
            PipelineEvent(
                run_id=run_id,
                event_type="run_created",
                agent="Server",
                title="Run created",
                payload={"mode": mode, "summary": "运行已启动，正在准备请求模型。"},
            )
        )

        def runner() -> None:
            try:
                task(store, handle)
            except RunCancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                store.save_event(PipelineEvent(run_id=run_id, event_type="error", agent="Server", title="Run failed", payload={"error": str(exc)}))
            finally:
                if handle.cancel_event.is_set():
                    store.delete_run(run_id)
                with self._lock:
                    self._run_handles.pop(run_id, None)

        thread = threading.Thread(target=runner, daemon=True)
        handle.thread = thread
        with self._lock:
            self._run_handles[run_id] = handle
        thread.start()
        return run_id

    def _save_output(self, memory: MemoryAgent, run_id: str, agent: str, output_type: str, title: str, payload: dict[str, Any]) -> None:
        memory.save_run_output(
            run_id=run_id,
            agent=agent,
            output_type=output_type,
            title=title,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _handle(self, run_id: str) -> RunHandle | None:
        with self._lock:
            return self._run_handles.get(run_id)

    def _store(self, mode: str) -> SQLiteStore:
        return self.stores.test if mode == "test" else self.stores.formal

    def _build_llm(self) -> DoubaoLLMClient:
        settings = self.stores.settings
        if not settings.doubao_api_key or not settings.doubao_model:
            raise ValueError("Missing DOUBAO_API_KEY or DOUBAO_MODEL. Check your .env file.")
        return DoubaoLLMClient(api_key=settings.doubao_api_key, model=settings.doubao_model, base_url=settings.doubao_base_url)

    def _build_writer(self) -> WriterAgent:
        return WriterAgent(llm_client=self._build_llm(), patch_executor=PatchExecutor())

    def _build_blueprint_agent(self) -> BlueprintAgent:
        return BlueprintAgent(llm_client=self._build_llm())

    def _build_critic(self) -> CriticAgent:
        return CriticAgent(llm_client=self._build_llm())

    def _build_master(self, store: SQLiteStore) -> MasterAgent:
        llm_client = self._build_llm()
        return MasterAgent(
            memory_agent=MemoryAgent(store=store),
            research_agent=ResearchAgent(crawler=MockTrendCrawler()),
            blueprint_agent=BlueprintAgent(llm_client=llm_client),
            writer_agent=WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor()),
            critic_agent=CriticAgent(llm_client=llm_client),
        )

    @staticmethod
    def _parse_json(data: str) -> dict[str, Any]:
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": data}


class _Handler(BaseHTTPRequestHandler):
    app: NovelApp

    def log_message(self, *args: object) -> None:
        pass

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/":
            self._html(_HTML_PAGE)
            return
        if parsed.path == "/api/novels":
            self._json(self.app.list_novels(qs.get("mode", ["formal"])[0]))
            return
        if parsed.path == "/api/novel":
            self._json(self.app.get_novel(qs.get("mode", ["formal"])[0], qs.get("book_id", [""])[0]))
            return
        if parsed.path == "/api/runs":
            self._json(self.app.list_runs(qs.get("mode", ["formal"])[0], qs.get("book_id", [None])[0]))
            return
        if parsed.path == "/api/run":
            self._json(self.app.get_run(qs.get("mode", ["formal"])[0], qs.get("run_id", [""])[0]))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        try:
            if parsed.path == "/api/novels/start":
                self._json({"ok": True, "run_id": self.app.start_formal_novel(str(payload.get("query", "")))})
                return
            if parsed.path == "/api/novels/continue":
                self._json({"ok": True, "run_id": self.app.continue_formal_novel(book_id=payload.get("book_id"), title=payload.get("title"))})
                return
            if parsed.path == "/api/novels/delete":
                self.app.delete_novel(str(payload.get("mode", "formal")), str(payload.get("book_id", "")))
                self._json({"ok": True})
                return
            if parsed.path == "/api/novels/update_concept":
                book = self.app.update_novel_concept(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    title=payload.get("title"),
                    premise=payload.get("premise"),
                    characters=payload.get("characters"),
                    chapter_plans=payload.get("chapter_plans"),
                )
                self._json({"ok": True, "book": book})
                return
            if parsed.path == "/api/novels/ai_update_concept":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.ai_update_concept(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            scope=str(payload.get("scope", "all")),
                            target_id=payload.get("target_id"),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/ai_update_text":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.ai_update_text(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            scope=str(payload.get("scope", "block")),
                            target_id=str(payload.get("target_id", "")),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/runs/stop":
                self.app.stop_run(str(payload.get("mode", "formal")), str(payload.get("run_id", "")))
                self._json({"ok": True})
                return
            if parsed.path == "/api/test/blueprint":
                self._json({"ok": True, "run_id": self.app.test_blueprint(str(payload.get("query", "")))})
                return
            if parsed.path == "/api/test/write":
                self._json({"ok": True, "run_id": self.app.test_write_chapter(query=payload.get("query"), book_id=payload.get("book_id"))})
                return
            if parsed.path == "/api/test/critique":
                self._json({"ok": True, "run_id": self.app.test_critique(str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/test/patch":
                self._json({"ok": True, "run_id": self.app.test_patch(book_id=str(payload.get("book_id", "")), block_id=str(payload.get("block_id", "")), operation=str(payload.get("operation", "replace")), patch_content=str(payload.get("patch_content", "")), reason=str(payload.get("reason", "manual test patch")))})
                return
            self.send_response(404)
            self.end_headers()
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, status=400)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def _html(self, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def start_server(*, formal_store: SQLiteStore, test_store: SQLiteStore, settings: Settings, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    _Handler.app = NovelApp(AppStores(formal=formal_store, test=test_store, settings=settings))
    server = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_HTML_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='UTF-8'><title>Novel Flow</title><style>
*{box-sizing:border-box}body{margin:0;font-family:"Microsoft YaHei",sans-serif;background:#0f1115;color:#e6e9ef;height:100vh;display:flex;flex-direction:column}
#hdr{display:flex;gap:8px;align-items:center;padding:10px 16px;background:#141923;border-bottom:1px solid #232834}#hdr h1{margin:0;font-size:15px;color:#89a6ff}
select,button,input,textarea{background:#1b2130;color:#eef2ff;border:1px solid #323b52;border-radius:6px;padding:6px 10px;font-size:12px}button{cursor:pointer}.danger{border-color:#6a2b3b;color:#ffcad5}.ghost{background:transparent}
#stage-pill{padding:4px 10px;border-radius:999px;border:1px solid #34405f;color:#9fb2eb;font-size:11px}#main{display:flex;flex:1;overflow:hidden}#left{width:42%;border-right:1px solid #232834;display:flex;flex-direction:column}#right{flex:1;display:flex;flex-direction:column}
#subhdr{padding:8px 14px;border-bottom:1px solid #232834;color:#8390ad;font-size:12px}#evs{flex:1;overflow:auto;padding:10px}.run{background:#151a23;border:1px solid #242b3b;border-radius:10px;margin-bottom:10px;overflow:hidden}.head{display:flex;gap:8px;align-items:center;padding:10px 12px;background:#171d29;cursor:pointer}.ts{margin-left:auto;color:#6f7a95;font-size:10px}
.tag{font-size:10px;padding:2px 6px;border-radius:999px;background:#222a3d;color:#b9c8ff}.live{background:#253b2c;color:#9fe2b0}.stop{background:#4a2230;color:#ffc4d2}.body{padding:10px 12px;border-top:1px solid #242b3b}.box{background:#121722;border:1px solid #242b3b;border-radius:8px;margin-bottom:8px;overflow:hidden}.box summary{list-style:none;cursor:pointer;padding:10px;color:#eef2ff;font-size:12px;display:flex;align-items:center;gap:8px}.box summary::-webkit-details-marker{display:none}.box .payload{padding:0 10px 10px 10px}.title{font-size:12px;color:#eef2ff;margin-bottom:0}.payload{font-size:11px;color:#93a0bf;white-space:pre-wrap;word-break:break-word;line-height:1.65}.empty{padding:50px 20px;text-align:center;color:#7f8aa3}
#tabs{display:flex;border-bottom:1px solid #232834;background:#141923}.tab{padding:10px 14px;cursor:pointer;color:#8b96af;font-size:12px;border-bottom:2px solid transparent}.tab.active{color:#dfe6ff;border-bottom-color:#7ea2ff}
#tc{flex:1;overflow:auto;padding:14px}.pnl{display:none}.pnl.active{display:block}.card{background:#151a23;border:1px solid #242b3b;border-radius:10px;padding:14px;margin-bottom:10px}.sec{font-size:11px;color:#7e8ba8;text-transform:uppercase;letter-spacing:.08em;margin:12px 0 8px}.row{margin:6px 0;font-size:13px;color:#dce3fb}.row strong{color:#8ea1d8;margin-right:6px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}.mini{background:#121722;border:1px solid #242b3b;border-radius:8px;padding:10px}.mini h4{margin:0 0 6px 0;color:#eef2ff;font-size:13px}.chapter,.issue{background:#121722;border:1px solid #242b3b;border-radius:8px;padding:10px;margin-bottom:8px}.block{background:#0f131c;border-left:2px solid #4e628f;border-radius:6px;padding:10px;margin:6px 0;white-space:pre-wrap;line-height:1.8}.editor label{display:block;margin:10px 0 6px;color:#8ea1d8;font-size:12px}.editor textarea{width:100%;min-height:140px;resize:vertical}.editor input{width:100%}.editor .hint{color:#7f8aa3;font-size:11px;margin-top:6px}
</style></head><body>
<div id='hdr'><h1>Novel Flow</h1><select id='modeSel' onchange='changeMode()'><option value='formal'>正式模式</option><option value='test'>测试模式</option></select><select id='novelSel' onchange='selectNovel(this.value)'><option value=''>选择小说</option></select><span id='stage-pill'>未开始</span><button id='btnNew' onclick='startFormal()'>新建小说</button><button id='btnContinue' onclick='continueFormal()'>续写小说</button><button id='btnBlueprint' onclick='testBlueprint()' style='display:none'>测试大纲</button><button id='btnWrite' onclick='testWrite()' style='display:none'>测试写章节</button><button id='btnCritique' onclick='testCritique()' style='display:none'>测试评价</button><button id='btnPatch' onclick='testPatch()' style='display:none'>测试修改</button><button id='btnStop' class='ghost' onclick='stopCurrentRun()' style='display:none'>停止运行</button><button class='danger' onclick='deleteNovel()'>删除小说</button></div>
<div id='main'><div id='left'><div id='subhdr'>左侧显示当前小说的历史运行记录，当前运行默认展开</div><div id='evs'><div class='empty'>选择小说或发起一次运行后查看过程</div></div></div><div id='right'><div id='tabs'><div class='tab active' onclick="showTab('blueprint')">小说信息</div><div class='tab' onclick="showTab('text')">小说正文</div><div class='tab' onclick="showTab('critic')">评价结果</div></div><div id='tc'><div id='pnl-blueprint' class='pnl active'><div class='empty'>等待加载小说信息</div></div><div id='pnl-text' class='pnl'><div class='empty'>等待加载小说正文</div></div><div id='pnl-critic' class='pnl'><div class='empty'>等待加载评价结果</div></div></div></div></div>
<script>
let mode='formal',bookId='',pendingRunId='',runsCache=[],expandedRuns=new Set(),boxStates={},currentBook=null;
let refreshPaused=false,refreshPauseReason='',refreshPauseTimer=null,isMouseSelecting=false;
const STAGES={research:'调研中',planning:'大纲中',writing:'写作中',critique:'评价中',patching:'修改中',complete:'已完成'};
const stageText=v=>STAGES[v]||v||'未开始',esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),shortTs=v=>v?String(v).replace('T',' ').slice(0,19):'';
async function api(path,opt){const r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json'}},opt||{}));return await r.json();}
function toggleButtons(){const t=mode==='test';btnNew.style.display=t?'none':'inline-block';btnContinue.style.display=t?'none':'inline-block';btnBlueprint.style.display=t?'inline-block':'none';btnWrite.style.display=t?'inline-block':'none';btnCritique.style.display=t?'inline-block':'none';btnPatch.style.display=t?'inline-block':'none';}
function updateStopButton(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);btnStop.style.display=a?'inline-block':'none';}
async function loadNovels(){const novels=await api('/api/novels?mode='+mode);novelSel.innerHTML="<option value=''>选择小说</option>";novels.forEach(n=>{const o=document.createElement('option');o.value=n.book_id;o.textContent=`${n.title} (${n.book_id})`;novelSel.appendChild(o);});if(bookId)novelSel.value=bookId;}
async function loadRuns(){if(!bookId){runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];return renderRuns();}runsCache=await api(`/api/runs?mode=${mode}&book_id=${bookId}`);const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();}
async function changeMode(){mode=modeSel.value;bookId='';pendingRunId='';runsCache=[];expandedRuns=new Set();boxStates={};evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";stagePill.textContent='未开始';toggleButtons();updateStopButton();await loadNovels();}
async function selectNovel(id){bookId=id;pendingRunId='';expandedRuns=new Set();boxStates={};if(!bookId){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";updateStopButton();return;}await refreshNovel();}
async function refreshNovel(){if(!bookId)return;const d=await api(`/api/novel?mode=${mode}&book_id=${bookId}`);if(!d.book)return;currentBook=d.book;renderBlueprint(d.book,d.blueprint_review);renderText(d.book);renderCritic(d.critic);stagePill.textContent=stageText(d.latest_stage);runsCache=d.runs||[];const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();await loadNovels();}
async function refreshPendingRun(){if(!pendingRunId)return;const d=await api(`/api/run?mode=${mode}&run_id=${pendingRunId}`);stagePill.textContent=stageText(d.stage||'writing');if(d.current_book_id){bookId=d.current_book_id;pendingRunId='';novelSel.value=bookId;return refreshNovel();}runsCache=[{run_id:pendingRunId,is_running:d.is_running!==false,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),pending_message:'运行中，等待模型返回更多内容。'}];expandedRuns.add(pendingRunId);await renderRuns({[pendingRunId]:d});updateStopButton();}
function boxHtml(key,title,payload,isOpen){return `<details class='box' ${isOpen?'open':''} ontoggle="toggleBox('${key}', this.open)"><summary><span class='title'>${title}</span></summary><div class='payload'>${payload}</div></details>`}
function toggleBox(key,isOpen){boxStates[key]=isOpen;}
function setRefreshPaused(paused,reason=''){refreshPaused=paused;refreshPauseReason=paused?reason:'';if(refreshPauseTimer){clearTimeout(refreshPauseTimer);refreshPauseTimer=null;}}
function pauseRefreshFor(ms,reason=''){setRefreshPaused(true,reason);refreshPauseTimer=setTimeout(()=>{if(!isMouseSelecting)setRefreshPaused(false,'');},ms);}
function isEditingElement(el){return !!(el&&(el.tagName==='TEXTAREA'||el.tagName==='INPUT'||el.isContentEditable));}
function hasUserSelection(){const sel=window.getSelection&&window.getSelection();return !!(sel&&String(sel).trim().length);}
document.addEventListener('mousedown',()=>{isMouseSelecting=true;setRefreshPaused(true,'selecting');});
document.addEventListener('mouseup',()=>{isMouseSelecting=false;if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isEditingElement(document.activeElement))setRefreshPaused(false,'');});
document.addEventListener('selectionchange',()=>{if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isMouseSelecting&&!isEditingElement(document.activeElement)&&refreshPauseReason==='selection')setRefreshPaused(false,'');});
document.addEventListener('focusin',event=>{if(isEditingElement(event.target))setRefreshPaused(true,'editing');});
document.addEventListener('focusout',event=>{if(isEditingElement(event.target)){setTimeout(()=>{if(!hasUserSelection()&&!isEditingElement(document.activeElement)&&!isMouseSelecting)setRefreshPaused(false,'');},0);}});
async function renderRuns(pref){if(!runsCache.length){evs.innerHTML="<div class='empty'>当前还没有运行记录</div>";return;}const cache=pref||{};for(const r of runsCache){if(expandedRuns.has(r.run_id)&&!cache[r.run_id])cache[r.run_id]=await api(`/api/run?mode=${mode}&run_id=${r.run_id}`);}let h='';runsCache.forEach(r=>{const ex=expandedRuns.has(r.run_id),d=cache[r.run_id],outs=(d&&d.outputs)||[],evts=(d&&d.events)||[];const streamText=evts.filter(e=>e.event_type==='llm_stream').map(e=>e.payload?.preview||'').join('');const normalEvents=evts.filter(e=>e.event_type!=='llm_stream');const items=[];if(r.pending_message)items.push({key:`${r.run_id}:pending`,title:'系统提示',payload:esc(r.pending_message),sortTs:r.updated_at||''});if(streamText){const lastStream=evts.filter(e=>e.event_type==='llm_stream').slice(-1)[0];items.push({key:`${r.run_id}:stream`,title:'DoubaoLLM · 流式输出',payload:esc(streamText),sortTs:(lastStream&&lastStream.ts)||r.updated_at||''});}outs.forEach((o,i)=>items.push({key:`${r.run_id}:out:${i}`,title:`${esc(o.agent)} · ${esc(o.title)}`,payload:esc(JSON.stringify(o.payload,null,2)),sortTs:o.created_at||''}));normalEvents.forEach((e,i)=>{const p=e.payload?.error||e.payload?.summary||e.payload?.preview||e.payload?.premise_title||e.payload?.chapter_id||e.payload?.block_id||'';items.push({key:`${r.run_id}:evt:${i}`,title:`${esc(e.agent||'System')} · ${esc(e.title||'')}`,payload:esc(p),sortTs:e.ts||''})});items.sort((a,b)=>String(a.sortTs).localeCompare(String(b.sortTs)));h+=`<div class='run'><div class='head' onclick="toggleRun('${r.run_id}')"><span class='tag'>${esc(stageText(r.stage))}</span>${r.is_running?"<span class='tag live'>运行中</span>":''}${r.cancel_requested?"<span class='tag stop'>停止中</span>":''}<span>${esc(r.run_id)}</span><span class='ts'>${esc(shortTs(r.updated_at))}</span></div>`;if(ex){h+="<div class='body'>";if(r.is_running)h+=`<div style='margin-bottom:8px'><button class='ghost' onclick="event.stopPropagation();stopRun('${r.run_id}')">停止并删除这次运行</button></div>`;if(!items.length)h+="<div class='payload'>当前还没有过程数据。</div>";items.forEach((item,index)=>{const isLatest=index===items.length-1;const isOpen=(item.key in boxStates)?boxStates[item.key]:isLatest;h+=boxHtml(item.key,item.title,item.payload,isOpen);});h+='</div>';}h+='</div>';});evs.innerHTML=h;}
function toggleRun(id){expandedRuns.has(id)?expandedRuns.delete(id):expandedRuns.add(id);renderRuns();}
async function stopCurrentRun(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);if(!a)return alert('当前没有正在运行的流程。');await stopRun(a.run_id);}
async function stopRun(id){if(!confirm('确认停止并删除这次运行过程吗？'))return;await api('/api/runs/stop',{method:'POST',body:JSON.stringify({mode,run_id:id})});expandedRuns.delete(id);if(pendingRunId===id)pendingRunId='';runsCache=runsCache.filter(x=>x.run_id!==id);bookId?await refreshNovel():renderRuns();updateStopButton();}
async function startFormal(){const q=prompt('输入新建小说的题材/需求：');if(!q)return;const r=await api('/api/novels/start',{method:'POST',body:JSON.stringify({query:q})});pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);boxStates={};stagePill.textContent='启动中';runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];await renderRuns();updateStopButton();}
async function continueFormal(){if(!bookId)return alert('请先选择一部小说再续写。');const r=await api('/api/novels/continue',{method:'POST',body:JSON.stringify({book_id:bookId})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'续写任务已启动，正在准备请求模型。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function deleteNovel(){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除这部小说吗？此操作不可撤销。'))return;await api('/api/novels/delete',{method:'POST',body:JSON.stringify({mode,book_id:bookId})});bookId='';pendingRunId='';runsCache=[];expandedRuns=new Set();evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";stagePill.textContent='未开始';await loadNovels();updateStopButton();}
async function testBlueprint(){const q=prompt('输入测试题材，生成大纲：');if(!q)return;const r=await api('/api/test/blueprint',{method:'POST',body:JSON.stringify({query:q})});pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'测试大纲任务已启动，正在准备请求模型。'}]:[];await renderRuns();updateStopButton();}
async function testWrite(){let r;if(bookId)r=await api('/api/test/write',{method:'POST',body:JSON.stringify({book_id:bookId})});else{const q=prompt('当前未选择测试小说。输入题材后会新建一本测试小说并写第一章：');if(!q)return;r=await api('/api/test/write',{method:'POST',body:JSON.stringify({query:q})});}pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'测试写章节任务已启动，正在准备请求模型。'}]:[];await renderRuns();updateStopButton();}
async function testCritique(){if(!bookId)return alert('请先选择一部测试小说。');const r=await api('/api/test/critique',{method:'POST',body:JSON.stringify({book_id:bookId})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'critique',updated_at:new Date().toISOString(),pending_message:'测试评价任务已启动，正在准备请求模型。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function testPatch(){if(!bookId)return alert('请先选择一部测试小说。');const blockId=prompt('输入要修改的 block_id：');if(!blockId)return;const operation=prompt('输入操作类型 replace / append / prepend：','replace')||'replace';const patchContent=prompt('输入修改内容：');if(!patchContent)return;const reason=prompt('输入修改原因：','manual test patch')||'manual test patch';const r=await api('/api/test/patch',{method:'POST',body:JSON.stringify({book_id:bookId,block_id:blockId,operation,patch_content:patchContent,reason})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'测试修改任务已启动，正在准备执行补丁。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseConcept(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你想怎么修改构思：');if(!guidance)return;const r=await api('/api/novels/ai_update_concept',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'AI 正在修改小说构思。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseText(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt(scope==='chapter'?'描述你想怎么修改这一章：':'描述你想怎么修改这个 block：');if(!guidance)return;const r=await api('/api/novels/ai_update_text',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'AI 正在修改正文。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
function renderBlueprint(book, blueprintReview){let h=`<div class='card'><div class='sec'>Story Spine</div><div class='row'><strong>书名</strong>${esc(book.title||'')}</div><div class='row'><strong>题材</strong>${esc(book.premise?.genre||'')}</div><div class='row'><strong>风格</strong>${esc(book.premise?.target_style||'')}</div><div class='row'><strong>高概念</strong>${esc(book.premise?.high_concept||'')}</div><div class='row'><strong>情绪钩子</strong>${esc(book.premise?.emotional_hook||'')}</div><div class='row'><strong>核心冲突</strong>${esc(book.premise?.central_conflict||'')}</div><div class='row'><strong>核心看点</strong>${esc(book.premise?.core_hook||'')}</div><div class='row'><strong>结尾兑现</strong>${esc(book.premise?.ending_payoff||'')}</div><div class='row'><strong>已完成章节</strong>${(book.metadata?.completed_chapter_ids||[]).length}</div><div class='row'><strong>下一章索引</strong>${book.metadata?.next_chapter_index??'-'}</div><div style='margin-top:10px'><button onclick="aiReviseConcept('all','')">AI 全量修改构思</button><button style='margin-left:8px' onclick="aiReviseConcept('premise','')">AI 修改核心设定</button></div></div>`;const escList=v=>(Array.isArray(v)&&v.length)?v.map(item=>`<div class='row'>- ${esc(item)}</div>`).join(''):`<div class='row'>- 暂无</div>`;h+=`<div class='card'><div class='sec'>Long Arc</div><div class='row'><strong>升级路径</strong></div>${escList(book.premise?.escalation_path)}<div class='row'><strong>反转蓝图</strong></div>${escList(book.premise?.twist_blueprint)}<div class='row'><strong>阶段兑现</strong></div>${escList(book.premise?.stage_payoffs)}<div class='row'><strong>卖点</strong></div>${escList(book.premise?.selling_points)}</div>`;const chars=book.characters||[];if(chars.length){h+="<div class='card'><div class='sec'>Character Bible</div><div class='grid'>";chars.forEach(c=>h+=`<div class='mini'><h4>${esc(c.name||'')}</h4><div><strong>角色</strong> ${esc(c.role||'')}</div><div><strong>表层目标</strong> ${esc(c.goal||'')}</div><div><strong>缺陷</strong> ${esc(c.flaw||'')}</div><div><strong>外显人格</strong> ${esc(c.public_persona||'')}</div><div><strong>隐藏动机</strong> ${esc(c.hidden_motive||'')}</div><div><strong>恐惧</strong> ${esc(c.fear||'')}</div><div><strong>软肋</strong> ${esc(c.soft_spot||'')}</div><div><strong>底线</strong> ${esc(c.bottom_line||'')}</div><div><strong>前史</strong> ${esc(c.backstory||'')}</div><div><strong>行为逻辑</strong> ${esc(c.behavior_logic||'')}</div><div><strong>成长弧线</strong> ${esc(c.arc||'')}</div><div><strong>关系钩子</strong> ${(c.relationship_hooks||[]).map(item=>esc(item)).join(' / ')}</div><div style='margin-top:8px'><button onclick="aiReviseConcept('character','${esc(c.name||'')}')">AI 修改这个角色</button></div></div>`);h+='</div></div>';}const plans=book.metadata?.chapter_plans||[];if(plans.length){h+="<div class='card'><div class='sec'>Chapter Roadmap</div>";plans.forEach(p=>h+=`<div class='chapter'><div class='row'><strong>${esc(p.chapter_id||'')}</strong> ${esc(p.title||'')}</div><div class='row'><strong>阶段</strong> ${esc(p.phase||'')}</div><div class='row'><strong>本章任务</strong> ${esc(p.objective||'')}</div><div class='row'><strong>功能</strong> ${esc(p.story_function||'')}</div><div class='row'><strong>关键转折</strong> ${esc(p.key_turn||'')}</div><div class='row'><strong>兑现</strong> ${esc(p.payoff||'')}</div><div class='row'><strong>张力</strong> ${esc(p.tension||'')}</div><div class='row'><strong>悬念</strong> ${esc(p.cliffhanger||'')}</div><div class='row'><strong>续写路线</strong> ${esc(p.next_route_hint||'')}</div><div style='margin-top:8px'><button onclick="aiReviseConcept('chapter_plan','${esc(p.chapter_id||'')}')">AI 修改这个大纲</button></div></div>`);h+='</div>';}if(blueprintReview){h+=`<div class='card'><div class='sec'>Blueprint Review</div><div class='row'><strong>总结</strong>${esc(blueprintReview.summary||'')}</div>${(blueprintReview.issues||[]).map(item=>`<div class='issue'><div class='row'><strong>${esc(item.title||'')}</strong>${esc(item.problem_type||'')}</div><div class='row'><strong>证据</strong>${esc(item.evidence||'')}</div><div class='row'><strong>影响</strong>${esc(item.impact||'')}</div><div class='row'><strong>建议</strong>${esc(item.recommendation||'')}</div></div>`).join('')||"<div class='row'>当前没有大纲问题。</div>"}</div>`;}h+=`<div class='card editor'><div class='sec'>修改小说构思</div><label>书名</label><input id='concept-title' value='${esc(book.title||'')}' /><label>Premise JSON</label><textarea id='concept-premise'>${esc(JSON.stringify(book.premise||{},null,2))}</textarea><label>角色设定 JSON 数组</label><textarea id='concept-characters'>${esc(JSON.stringify(book.characters||[],null,2))}</textarea><label>章节规划 JSON 数组</label><textarea id='concept-plans'>${esc(JSON.stringify(book.metadata?.chapter_plans||[],null,2))}</textarea><div style='margin-top:10px'><button onclick='saveConcept()'>保存构思</button></div><div class='hint'>支持直接修改标题、核心设定、角色和章节规划。保存后会直接回写到当前小说。</div></div>`;document.getElementById('pnl-blueprint').innerHTML=h;}
async function saveConcept(){if(!bookId)return alert('请先选择一部小说。');try{const title=document.getElementById('concept-title').value.trim();const premise=JSON.parse(document.getElementById('concept-premise').value);const characters=JSON.parse(document.getElementById('concept-characters').value);const chapter_plans=JSON.parse(document.getElementById('concept-plans').value);const result=await api('/api/novels/update_concept',{method:'POST',body:JSON.stringify({mode,book_id:bookId,title,premise,characters,chapter_plans})});if(!result.ok)return alert(result.error||'保存失败');currentBook=result.book;renderBlueprint(currentBook);renderText(currentBook);await loadNovels();alert('小说构思已保存');}catch(err){alert('保存失败：'+err.message);}}
function renderText(book){let h='';(book.volumes||[]).forEach(v=>{h+=`<div class='card'><div class='row'><strong>卷</strong>${esc(v.title||v.id)}</div>`;(v.chapters||[]).forEach(ch=>{h+=`<div class='sec'>${esc(ch.title||ch.id)} <button style='margin-left:8px' onclick="aiReviseText('chapter','${esc(ch.id||'')}')">AI 修改本章</button></div>`;(ch.scenes||[]).forEach(sc=>{h+=`<div class='row'><strong>场景</strong>${esc(sc.id||'')}</div>`;(sc.blocks||[]).forEach(bl=>{h+=`<div class='row'><strong>${esc(bl.id||'')}</strong>${esc(bl.purpose||'')} <button style='margin-left:8px' onclick="aiReviseText('block','${esc(bl.id||'')}')">AI 修改这个 Block</button></div><div class='block'>${esc(bl.text||'')}</div>`;});});});h+='</div>';});document.getElementById('pnl-text').innerHTML=h||"<div class='empty'>当前还没有正文</div>";}
function renderCritic(c){if(!c){document.getElementById('pnl-critic').innerHTML="<div class='empty'>当前还没有评价结果</div>";return;}let h=`<div class='card'><div class='row'><strong>摘要</strong>${esc(c.summary||'')}</div><div class='row'><strong>问题数</strong>${(c.issues||[]).length}</div></div>`;(c.issues||[]).forEach(i=>h+=`<div class='issue'><div class='row'><strong>${esc(i.severity||'')}</strong>${esc(i.title||'')}</div><div class='row'><strong>位置</strong>${esc(i.location?.block_id||'')}</div><div class='row'><strong>证据</strong>${esc(i.evidence||'')}</div><div class='row'><strong>影响</strong>${esc(i.impact||'')}</div><div class='row'><strong>建议</strong>${esc(i.recommendation||'')}</div></div>`);document.getElementById('pnl-critic').innerHTML=h;}
function showTab(name){document.querySelectorAll('.tab').forEach((e,i)=>e.classList.toggle('active',['blueprint','text','critic'][i]===name));document.querySelectorAll('.pnl').forEach(e=>e.classList.remove('active'));document.getElementById('pnl-'+name).classList.add('active');}
const btnNew=document.getElementById('btnNew'),btnContinue=document.getElementById('btnContinue'),btnBlueprint=document.getElementById('btnBlueprint'),btnWrite=document.getElementById('btnWrite'),btnCritique=document.getElementById('btnCritique'),btnPatch=document.getElementById('btnPatch'),btnStop=document.getElementById('btnStop'),stagePill=document.getElementById('stage-pill'),novelSel=document.getElementById('novelSel'),modeSel=document.getElementById('modeSel'),evs=document.getElementById('evs');
toggleButtons();loadNovels();updateStopButton();setInterval(async()=>{if(refreshPaused)return;if(bookId)await refreshNovel();if(pendingRunId)await refreshPendingRun();},1500);
</script></body></html>"""
