from random import Random

from love_letter.engine.cards import CARD_COUNTS
from love_letter.engine.rules import build_deck


def test_deck_composition() -> None:
    deck = build_deck(Random(0))
    assert len(deck) == sum(CARD_COUNTS.values())
    for card, count in CARD_COUNTS.items():
        assert deck.count(card) == count
