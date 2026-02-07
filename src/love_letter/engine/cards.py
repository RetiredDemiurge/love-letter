from __future__ import annotations

from enum import IntEnum
from typing import Iterable


class CardType(IntEnum):
    GUARD = 1
    PRIEST = 2
    BARON = 3
    HANDMAID = 4
    PRINCE = 5
    KING = 6
    COUNTESS = 7
    PRINCESS = 8


CARD_NAMES: dict[CardType, str] = {
    CardType.GUARD: "Guard",
    CardType.PRIEST: "Priest",
    CardType.BARON: "Baron",
    CardType.HANDMAID: "Handmaid",
    CardType.PRINCE: "Prince",
    CardType.KING: "King",
    CardType.COUNTESS: "Countess",
    CardType.PRINCESS: "Princess",
}

CARD_COUNTS: dict[CardType, int] = {
    CardType.GUARD: 5,
    CardType.PRIEST: 2,
    CardType.BARON: 2,
    CardType.HANDMAID: 2,
    CardType.PRINCE: 2,
    CardType.KING: 1,
    CardType.COUNTESS: 1,
    CardType.PRINCESS: 1,
}


def card_name(card: CardType) -> str:
    return CARD_NAMES[card]


def all_cards() -> Iterable[CardType]:
    return list(CardType)
