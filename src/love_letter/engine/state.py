from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import CardType


@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    player_id: int
    card: CardType
    target_id: int | None = None
    guess: CardType | None = None


@dataclass
class PlayerState:
    id: int
    name: str
    hand: list[CardType] = field(default_factory=list)
    discard: list[CardType] = field(default_factory=list)
    tokens: int = 0
    protected: bool = False
    eliminated: bool = False


@dataclass
class RoundState:
    players: list[PlayerState]
    deck: list[CardType]
    burned: list[CardType]
    face_up: list[CardType]
    current_player_idx: int = 0
    events: list[Event] = field(default_factory=list)
    round_over: bool = False


@dataclass
class GameState:
    players: list[PlayerState]
    target_tokens: int
    round_number: int = 0
    round_state: RoundState | None = None
    next_start_player_id: int | None = None


@dataclass(frozen=True)
class SetupConfig:
    burn_face_down: int
    burn_face_up: int
