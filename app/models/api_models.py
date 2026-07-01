from dataclasses import dataclass
from typing import Any


@dataclass
class InitRequest:
    condition_id: str
    free_text: str | None


@dataclass
class InitResponse:
    runtime_id: str
    version: int
    client_state: dict


@dataclass
class UpdateRequest:
    runtime_id: str
    base_version: int
    answers: dict[str, Any]


@dataclass
class SafetyMessage:
    rule_id: str
    message: str


@dataclass
class UpdateResponse:
    runtime_id: str
    version: int
    client_state: dict
    safety_messages: list[SafetyMessage]


@dataclass
class FinishRequest:
    runtime_id: str
    version: int


@dataclass
class FinishResponse:
    submission_id: str
