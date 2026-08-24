from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


Priority = Literal["P0", "P1", "P2", "P3", "P4", "P5"]
Lane = Literal["now", "protect", "delegate", "monitor"]


class ActionSpec(BaseModel):
    label: str
    kind: Literal["eli_agent_queue", "composio"] = "eli_agent_queue"
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


class CalendarItem(BaseModel):
    id: str
    title: str
    start: str
    end: str | None = None
    all_day: bool = False
    source: str
    kind: Literal["calendar", "priority"] = "calendar"
    priority_id: str | None = None


class DashboardPayload(BaseModel):
    generated_at: datetime
    live: bool
    greeting: str
    focus: str
    cards: list[PriorityCard]
    calendar_items: list[CalendarItem] = Field(default_factory=list)
    admin_count: int = 0
    integrations: dict[str, bool | str]
    warnings: list[str] = Field(default_factory=list)


FeedbackCategory = Literal["priority_correction", "dashboard_change", "positive_reinforcement"]
FeedbackDisposition = Literal["dismiss", "not_relevant", "modify", "complete"]


class FeedbackRequest(BaseModel):
    category: FeedbackCategory
    feedback: str = Field(min_length=1, max_length=2000)
    item_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    disposition: FeedbackDisposition | None = None

    @model_validator(mode="after")
    def validate_association(self):
        if self.disposition and not self.item_id:
            raise ValueError("A disposition requires an associated dashboard item")
        return self


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: Literal["recorded", "queued"]
    eli_agent_writeback: bool
    retriable: bool
    next_brief_refresh: bool
    detail: str


class ApprovalRequest(BaseModel):
    item: PriorityCard


class ExecuteRequest(BaseModel):
    approval_id: str
    payload_hash: str


class VoiceRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
