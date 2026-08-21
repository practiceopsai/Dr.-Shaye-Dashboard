from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


Priority = Literal["P0", "P1", "P2", "P3", "P4"]
Lane = Literal["now", "protect", "delegate", "monitor"]


class ActionSpec(BaseModel):
    label: str
    kind: Literal["hermes_queue", "composio"] = "hermes_queue"
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    account: str = "personal"
    recipients: list[str] = Field(default_factory=list)
    reversible: bool = True


class PriorityCard(BaseModel):
    id: str
    priority: Priority
    lane: Lane
    category: str
    title: str
    context: str
    consequence: str
    deadline: str | None = None
    source: str
    mission_alignment: Literal["aligned", "mixed", "tension", "unknown"] = "unknown"
    action: ActionSpec


class DashboardPayload(BaseModel):
    generated_at: datetime
    live: bool
    greeting: str
    focus: str
    cards: list[PriorityCard]
    admin_count: int = 0
    integrations: dict[str, bool | str]
    warnings: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    item_id: str
    feedback: str = Field(min_length=1, max_length=2000)
    disposition: Literal["dismiss", "not_relevant", "modify", "complete"]


class ApprovalRequest(BaseModel):
    item: PriorityCard


class ExecuteRequest(BaseModel):
    approval_id: str
    payload_hash: str


class VoiceRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)

