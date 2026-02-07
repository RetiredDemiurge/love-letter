from __future__ import annotations

from typing import Iterable

from love_letter.engine.cards import CardType, card_name
from love_letter.engine.state import Event, PlayerState


def render_event(event: Event, players: Iterable[PlayerState]) -> str:
    lookup = {player.id: player.name for player in players}
    kind = event.kind
    data = event.data

    if kind == "round_start":
        player_name = lookup.get(data.get("start_player_id"), "Unknown")
        return f"Round {data.get('round')} begins. Start player: {player_name}."
    if kind == "face_up":
        cards = ", ".join(card_name(card) for card in data.get("cards", []))
        return f"Face-up removed cards: {cards}."
    if kind == "draw":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        reason = data.get("reason")
        if reason == "prince":
            return f"{player_name} draws a replacement card."
        return f"{player_name} draws a card."
    if kind == "play":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        card = card_name(data["card"])
        return f"{player_name} plays {card}."
    if kind == "guard_guess":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        target_name = lookup.get(data.get("target_id"), "Unknown")
        guess = card_name(data["guess"])
        return f"{player_name} guesses {guess} on {target_name}."
    if kind == "reveal":
        viewer = lookup.get(data.get("viewer_id"), "Unknown")
        target = lookup.get(data.get("target_id"), "Unknown")
        card = card_name(data["card"])
        return f"{viewer} sees {target}'s hand: {card}."
    if kind == "baron_compare":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        target_name = lookup.get(data.get("target_id"), "Unknown")
        player_card = card_name(data["player_card"])
        target_card = card_name(data["target_card"])
        return f"Baron compare: {player_name} ({player_card}) vs {target_name} ({target_card})."
    if kind == "protected":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        return f"{player_name} is protected until their next turn."
    if kind == "protection_ended":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        return f"{player_name}'s protection ends."
    if kind == "discard":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        card = card_name(data["card"])
        return f"{player_name} discards {card}."
    if kind == "eliminated":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        return f"{player_name} is eliminated."
    if kind == "swap":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        target_name = lookup.get(data.get("target_id"), "Unknown")
        return f"{player_name} swaps hands with {target_name}."
    if kind == "countess_no_effect":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        return f"{player_name}'s Countess has no effect."
    if kind == "round_end":
        winners = ", ".join(lookup.get(pid, "Unknown") for pid in data.get("winners", []))
        return f"Round ends. Winner(s): {winners}."
    if kind == "token_awarded":
        player_name = lookup.get(data.get("player_id"), "Unknown")
        tokens = data.get("tokens")
        return f"{player_name} gains a token (total: {tokens})."
    if kind == "deck_empty":
        return "Deck is empty. Round ends now."

    return f"{kind}: {data}"


def render_hand(hand: list[CardType]) -> str:
    return ", ".join(f"{idx + 1}:{card_name(card)}" for idx, card in enumerate(hand))
