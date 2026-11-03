"""Run one change thread. The SQLite file is closed before this function returns."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from cm_agents.agents.context import AgentContext, activate, reset
from cm_agents.clock import pin
from cm_agents.data.import_time import parse_utc
from cm_agents.enablement.policy import load_policy
from cm_agents.graphs.change_graph import build_change_graph
from cm_agents.graphs.release_graph import build_release_graph
from cm_agents.servicenow.changes import read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import Settings, repo_root


class RunError(RuntimeError):
    """The thread stopped and can be resumed after the cause is fixed."""


def load_request(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RunError("request file must be a mapping")
    for key in ("requester", "summary", "description"):
        if not str(loaded.get(key) or "").strip():
            raise RunError(f"request is missing {key}")
    return loaded


def new_thread_id() -> str:
    return "SYN-" + uuid.uuid4().hex[:12]


def new_release_thread_id() -> str:
    return "SYN-RUN-" + uuid.uuid4().hex[:12]


def is_release_thread(thread_id: str) -> bool:
    """Release checkpoints stay off the seed prefix SYN-REL-."""
    return thread_id.startswith("SYN-RUN-") or thread_id.startswith("SYN-S06-")


def start_change(settings: Settings, request: dict[str, Any], thread_id: str) -> int:
    _require_thread(thread_id)
    return _invoke(settings, thread_id, request, None)


def start_release(settings: Settings, thread_id: str) -> int:
    _require_release_thread(thread_id)
    return _invoke_release(settings, thread_id, None)


def create_release(
    settings: Settings,
    *,
    service: str,
    version: str,
    start: str,
    end: str,
    thread_id: str,
) -> int:
    """Create the release record and stop. The graph starts on release run."""
    from cm_agents.agents.release import create_release_change

    _require_release_thread(thread_id)
    with _client(settings) as client:
        record = create_release_change(
            client,
            service=service,
            version=version,
            start=start,
            end=end,
            thread_id=thread_id,
        )
    print(f"thread: {thread_id}")
    print("interrupt: none")
    print("step: created")
    print(f"change: {record.get('number') or ''}")
    print(f"state: {record.get('state') or ''}")
    return 0


def resume_change(settings: Settings, thread_id: str, resume: dict[str, Any]) -> int:
    _require_thread(thread_id)
    if is_release_thread(thread_id):
        return _invoke_release(settings, thread_id, resume)
    return _invoke(settings, thread_id, None, resume)


def show_status(settings: Settings, thread_id: str) -> int:
    _require_thread(thread_id)
    builder = build_release_graph if is_release_thread(thread_id) else build_change_graph
    with _graph(settings, builder) as (graph, client):
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        values = snap.values or {}
        if not values:
            print(f"thread: {thread_id}")
            print("interrupt: none")
            print("step: missing")
            print("change:")
            print("state:")
            return 1
        number = str(values.get("change_number") or "")
        state_value = ""
        if values.get("change_sys_id"):
            record = read_change(client, str(values["change_sys_id"]))
            number = str(record.get("number") or number)
            state_value = str(record.get("state") or "")
        kind, step = _interrupt_label(snap)
        print(f"thread: {thread_id}")
        print(f"interrupt: {kind}")
        print(f"step: {step}")
        print(f"change: {number}")
        print(f"state: {state_value}")
        _print_detail(snap)
        if values.get("error"):
            print(f"error: {values['error']}")
            return 1
    return 0


def _invoke(
    settings: Settings,
    thread_id: str,
    request: dict[str, Any] | None,
    resume: dict[str, Any] | None,
) -> int:
    try:
        if request and request.get("simulated_now"):
            pin(parse_utc(str(request["simulated_now"])))
        if resume and resume.get("simulated_now"):
            pin(parse_utc(str(resume["simulated_now"])))
        with _graph(settings) as (graph, _client):
            config = {"configurable": {"thread_id": thread_id}}
            if resume is None:
                graph.invoke(
                    {"thread_id": thread_id, "request": request or {}, "gaps": [], "error": ""},
                    config,
                )
            else:
                graph.invoke(Command(resume=resume), config)
            snap = graph.get_state(config)
        return _print_result(thread_id, snap)
    finally:
        pin(None)


def _invoke_release(
    settings: Settings,
    thread_id: str,
    resume: dict[str, Any] | None,
) -> int:
    try:
        if resume and resume.get("simulated_now"):
            pin(parse_utc(str(resume["simulated_now"])))
        with _graph(settings, build_release_graph) as (graph, _client):
            config = {"configurable": {"thread_id": thread_id}}
            if resume is None:
                graph.invoke({"thread_id": thread_id, "error": ""}, config)
            else:
                graph.invoke(Command(resume=resume), config)
            snap = graph.get_state(config)
        return _print_result(thread_id, snap)
    finally:
        pin(None)


class _ClientSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def __enter__(self) -> ServiceNowClient:
        self._client = ServiceNowClient(
            self.settings.sn_instance_url,
            self.settings.sn_agent_user,
            self.settings.sn_agent_password,
            secrets=self.settings.secret_values(),
            timeout=120,
        )
        return self._client

    def __exit__(self, *exc: object) -> None:
        if self._client is not None:
            self._client.close()


class _GraphSession:
    def __init__(self, settings: Settings, builder: Any) -> None:
        self.settings = settings
        self._builder = builder
        self._saver = None
        self._client = None
        self._token = None

    def __enter__(self):
        fixtures = json.loads(
            (repo_root() / "data" / "synthetic" / "fixtures.json").read_text(encoding="utf-8")
        )
        self._client = ServiceNowClient(
            self.settings.sn_instance_url,
            self.settings.sn_agent_user,
            self.settings.sn_agent_password,
            secrets=self.settings.secret_values(),
            timeout=120,
        )
        self._token = activate(
            AgentContext(self.settings, self._client, load_policy(), fixtures)
        )
        path = repo_root() / "var" / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._saver = SqliteSaver.from_conn_string(str(path))
        saver = self._saver.__enter__()
        graph = self._builder(saver)
        return graph, self._client

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            reset(self._token)
        if self._saver is not None:
            self._saver.__exit__(*exc)
        if self._client is not None:
            self._client.close()


def _graph(settings: Settings, builder: Any = build_change_graph) -> _GraphSession:
    return _GraphSession(settings, builder)


def _client(settings: Settings) -> _ClientSession:
    return _ClientSession(settings)


def _print_result(thread_id: str, snap: Any) -> int:
    values = snap.values or {}
    kind, step = _interrupt_label(snap)
    number = str(values.get("change_number") or "")
    state_value = ""
    if kind != "none":
        payload = snap.interrupts[0].value
        if isinstance(payload, dict):
            number = str(payload.get("change_number") or number)
            state_value = str(payload.get("state") or "")
    elif (values.get("review") or {}).get("change_state"):
        state_value = str(values["review"].get("change_state") or "")
        step = str(values["review"].get("route") or step)
    elif (values.get("deployment") or {}).get("change_state"):
        state_value = str(values["deployment"].get("change_state") or "")
        step = str(values["deployment"].get("outcome") or step)
    elif values.get("authorization"):
        state_value = str(values["authorization"].get("change_state") or "")
        step = str(values["authorization"].get("route") or step)
    print(f"thread: {thread_id}")
    print(f"interrupt: {kind}")
    print(f"step: {step}")
    print(f"change: {number}")
    print(f"state: {state_value}")
    _print_detail(snap)
    if values.get("error"):
        print(f"error: {values['error']}")
        return 1
    return 0


def _print_detail(snap: Any) -> None:
    interrupts = list(snap.interrupts or [])
    if not interrupts:
        return
    payload = interrupts[0].value
    if isinstance(payload, dict) and payload.get("detail"):
        print(f"detail: {payload['detail']}")


def _interrupt_label(snap: Any) -> tuple[str, str]:
    interrupts = list(snap.interrupts or [])
    if not interrupts:
        return "none", "done"
    payload = interrupts[0].value
    if isinstance(payload, dict):
        return str(payload.get("kind") or "interrupt"), str(payload.get("step") or "")
    return "interrupt", ""


def _require_thread(thread_id: str) -> None:
    if not thread_id.startswith("SYN-"):
        raise RunError("thread id must start with SYN-")


def _require_release_thread(thread_id: str) -> None:
    _require_thread(thread_id)
    if not is_release_thread(thread_id):
        raise RunError("release thread id must start with SYN-RUN- or SYN-S06-")
