from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Scope = Literal["category", "merchant", "customer", "trigger"]


class WireModel(BaseModel):
    # Unknown envelope keys are rejected; new payload fields are retained.
    model_config = ConfigDict(extra="forbid")


class ContextPush(WireModel):
    scope: Scope
    context_id: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00-\x1f]+$")
    version: int = Field(strict=True, ge=1)
    payload: dict[str, Any]
    delivered_at: AwareDatetime

    @field_validator("payload")
    @classmethod
    def bounded_depth(cls, v: dict) -> dict:
        def visit(x: Any, depth: int = 0) -> None:
            if depth > 25:
                raise ValueError("Payload nested too deeply")
            if isinstance(x, dict):
                for value in x.values():
                    visit(value, depth + 1)
            elif isinstance(x, list):
                for value in x:
                    visit(value, depth + 1)
            elif isinstance(x, float):
                import math
                if not math.isfinite(x):
                    raise ValueError("Non-finite numbers are invalid JSON")
        visit(v)
        return v


class Tick(WireModel):
    now: AwareDatetime
    available_triggers: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("available_triggers")
    @classmethod
    def ids(cls, values: list[str]) -> list[str]:
        if any(not v or len(v) > 256 for v in values):
            raise ValueError("Invalid trigger ID")
        return values


class Reply(WireModel):
    conversation_id: str = Field(min_length=1, max_length=256)
    merchant_id: str | None = Field(default=None, max_length=256)
    customer_id: str | None = Field(default=None, max_length=256)
    from_role: Literal["merchant", "customer"]
    message: str = Field(min_length=1, max_length=8000)
    received_at: AwareDatetime
    turn_number: int = Field(strict=True, ge=1, le=10000)

    @field_validator("message")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value


class Action(WireModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str = Field(min_length=1, max_length=4000)
    cta: Literal["binary_yes_stop", "open_ended", "none"]
    suppression_key: str
    rationale: str


class ReplyResult(WireModel):
    action: Literal["send", "wait", "end"]
    body: str | None = None
    cta: Literal["binary_yes_stop", "open_ended", "none"] | None = None
    wait_seconds: int | None = None
    rationale: str
    # Extra template fields are used only if a reply is outside the 24-hour window.
    template_name: str | None = None
    template_params: list[str] | None = None


class Preview(WireModel):
    category: dict[str, Any]
    merchant: dict[str, Any]
    trigger: dict[str, Any]
    customer: dict[str, Any] | None = None
    now: AwareDatetime

    @field_validator("category", "merchant", "trigger", "customer")
    @classmethod
    def safe_depth(cls, value):
        return ContextPush.bounded_depth(value) if value is not None else None
