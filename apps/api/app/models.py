from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AssistantMode(str, Enum):
    jarvis = "JARVIS"
    friday = "FRIDAY"
    veronica = "VERONICA"
    sentinel = "SENTINEL"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: AssistantMode = AssistantMode.jarvis
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    developer_mode: bool = False


class ToolCallPlan(BaseModel):
    tool: str
    purpose: str
    risk: RiskLevel = RiskLevel.low
    requires_confirmation: bool = False
    input_preview: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    mode: AssistantMode
    response: str
    protocol: str | None = None
    provider_status: str | None = None
    memory_updates: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    tool_plan: list[ToolCallPlan] = Field(default_factory=list)


class ProtocolRequest(BaseModel):
    command: str
    mode: AssistantMode = AssistantMode.jarvis


class ActionLog(BaseModel):
    actor: str = "VERONICA"
    action: str
    risk: RiskLevel
    confirmed: bool
    result: str


_TASK_STATUSES = {"pending", "done", "cancelled"}
_REMINDER_STATUSES = {"pending", "done", "dismissed"}
_PRIORITIES = {"low", "medium", "high"}


class NoteCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class TaskCreateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    priority: str = "medium"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in _PRIORITIES:
            raise ValueError(f"priority must be one of {_PRIORITIES}")
        return v


class TaskUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _TASK_STATUSES:
            raise ValueError(f"status must be one of {_TASK_STATUSES}")
        return v


class ReminderCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    due_at: str | None = None


class ReminderUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _REMINDER_STATUSES:
            raise ValueError(f"status must be one of {_REMINDER_STATUSES}")
        return v
