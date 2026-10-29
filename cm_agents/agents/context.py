"""Per-run dependencies. They are not stored in the checkpoint."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import Settings


@dataclass
class AgentContext:
    settings: Settings
    client: ServiceNowClient
    policy: dict[str, Any]
    fixtures: dict[str, Any]


_current: contextvars.ContextVar[AgentContext] = contextvars.ContextVar("cm_agent_context")


def activate(ctx: AgentContext) -> contextvars.Token[AgentContext]:
    return _current.set(ctx)


def reset(token: contextvars.Token[AgentContext]) -> None:
    _current.reset(token)


def current() -> AgentContext:
    return _current.get()
