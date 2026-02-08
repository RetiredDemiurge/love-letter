from __future__ import annotations

from pathlib import Path
from random import Random
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from love_letter.engine.cards import CardType
from love_letter.engine.rules import (
    RulesError,
    advance_turn,
    apply_action,
    check_round_end,
    game_over,
    new_game,
    setup_round,
    start_turn,
)
from love_letter.engine.state import Action, GameState, PlayerState, RoundState

CARD_ID_BY_TYPE: dict[CardType, str] = {
    CardType.GUARD: "guard",
    CardType.PRIEST: "priest",
    CardType.BARON: "baron",
    CardType.HANDMAID: "handmaid",
    CardType.PRINCE: "prince",
    CardType.KING: "king",
    CardType.COUNTESS: "countess",
    CardType.PRINCESS: "princess",
}
CARD_TYPE_BY_ID = {v: k for k, v in CARD_ID_BY_TYPE.items()}


class NewGameIn(BaseModel):
    names: list[str] | None = None


class StartTurnIn(BaseModel):
    player_id: int


class ActionIn(BaseModel):
    player_id: int
    card: str
    target_id: int | None = None
    guess: str | None = None


class GameSession:
    def __init__(self) -> None:
        self.rng = Random()
        self.lock = Lock()
        self.game_state = new_game(["Player 1", "Player 2"])
        self.round_state = setup_round(self.game_state, self.rng)

    def reset(self, names: list[str] | None = None) -> None:
        self.game_state = new_game(names or ["Player 1", "Player 2"])
        self.round_state = setup_round(self.game_state, self.rng)

    def state(self, player_id: int | None = None) -> dict[str, Any]:
        round_state = self.round_state
        players = []
        for player in round_state.players:
            players.append(_serialize_player(player, include_hand=player_id == player.id))

        player_lookup = {player.id: player.name for player in round_state.players}
        recent_events = round_state.events[-40:]
        public_log = [_format_public_event(event, player_lookup) for event in recent_events]
        private_log = []
        if player_id is not None:
            private_log = [
                message
                for message in (_format_private_event(event, player_lookup, player_id) for event in recent_events)
                if message is not None
            ]

        return {
            "players": players,
            "current_player_id": round_state.players[round_state.current_player_idx].id,
            "round_over": round_state.round_over,
            "round_number": self.game_state.round_number,
            "target_tokens": self.game_state.target_tokens,
            "deck_count": len(round_state.deck),
            "burned_count": len(round_state.burned),
            "face_up": [_card_id(card) for card in round_state.face_up],
            "events": [_serialize_public_event(event) for event in recent_events],
            "public_log": public_log,
            "private_log": private_log,
            "game_over": game_over(self.game_state),
        }

    def start_turn(self, player_id: int) -> None:
        round_state = self.round_state
        current = round_state.players[round_state.current_player_idx]
        if current.id != player_id:
            raise RulesError("Not your turn.")
        can_play = start_turn(round_state, player_id, self.rng)
        if not can_play:
            check_round_end(self.game_state, round_state, self.rng)

    def play(self, action_in: ActionIn) -> None:
        round_state = self.round_state
        current = round_state.players[round_state.current_player_idx]
        if current.id != action_in.player_id:
            raise RulesError("Not your turn.")
        action = Action(
            player_id=action_in.player_id,
            card=_card_type(action_in.card),
            target_id=action_in.target_id,
            guess=_card_type(action_in.guess) if action_in.guess else None,
        )
        apply_action(round_state, action, self.rng)
        check_round_end(self.game_state, round_state, self.rng)
        if not round_state.round_over:
            advance_turn(round_state)

    def next_round(self) -> None:
        if not self.round_state.round_over:
            raise RulesError("Round is not over.")
        self.round_state = setup_round(self.game_state, self.rng)


app = FastAPI(title="Love Letter Prototype")
ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "assets"
WEB_DIR = ROOT / "web"

app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

SESSION = GameSession()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/web/index.html")


@app.get("/api/state")
def api_state(player_id: int | None = None) -> dict[str, Any]:
    with SESSION.lock:
        return SESSION.state(player_id=player_id)


@app.post("/api/new")
def api_new(payload: NewGameIn) -> dict[str, Any]:
    with SESSION.lock:
        SESSION.reset(payload.names)
        return SESSION.state(player_id=0)


@app.post("/api/start")
def api_start(payload: StartTurnIn) -> dict[str, Any]:
    with SESSION.lock:
        try:
            SESSION.start_turn(payload.player_id)
        except RulesError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return SESSION.state(player_id=payload.player_id)


@app.post("/api/play")
def api_play(payload: ActionIn) -> dict[str, Any]:
    with SESSION.lock:
        try:
            SESSION.play(payload)
        except RulesError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return SESSION.state(player_id=payload.player_id)


@app.post("/api/next_round")
def api_next_round() -> dict[str, Any]:
    with SESSION.lock:
        try:
            SESSION.next_round()
        except RulesError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return SESSION.state(player_id=0)


def _card_id(card: CardType) -> str:
    return CARD_ID_BY_TYPE[card]


def _card_type(card_id: str) -> CardType:
    if card_id not in CARD_TYPE_BY_ID:
        raise RulesError("Unknown card.")
    return CARD_TYPE_BY_ID[card_id]


def _serialize_player(player: PlayerState, include_hand: bool) -> dict[str, Any]:
    return {
        "id": player.id,
        "name": player.name,
        "tokens": player.tokens,
        "protected": player.protected,
        "eliminated": player.eliminated,
        "discard": [_card_id(card) for card in player.discard],
        "hand": [_card_id(card) for card in player.hand] if include_hand else None,
        "hand_count": len(player.hand),
    }


def _serialize_event_data(data: Any) -> Any:
    if isinstance(data, CardType):
        return _card_id(data)
    if isinstance(data, list):
        return [_serialize_event_data(item) for item in data]
    if isinstance(data, dict):
        return {key: _serialize_event_data(value) for key, value in data.items()}
    return data


def _serialize_event(event: Any) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "data": _serialize_event_data(event.data),
    }


def _serialize_public_event(event: Any) -> dict[str, Any]:
    kind = event.kind
    data = event.data
    if kind == "draw":
        return {"kind": kind, "data": {"player_id": data.get("player_id"), "reason": data.get("reason")}}
    if kind == "reveal":
        return {
            "kind": kind,
            "data": {"viewer_id": data.get("viewer_id"), "target_id": data.get("target_id")},
        }
    if kind == "baron_compare":
        return {
            "kind": kind,
            "data": {"player_id": data.get("player_id"), "target_id": data.get("target_id")},
        }
    return _serialize_event(event)


def _format_public_event(event: Any, lookup: dict[int, str]) -> str:
    kind = event.kind
    data = event.data

    if kind == "round_start":
        return f"Round {data.get('round')} begins. Start player: {lookup.get(data.get('start_player_id'), 'Unknown')}."
    if kind == "face_up":
        cards = ", ".join(_card_id(card) for card in data.get("cards", []))
        return f"Face-up removed cards: {cards}."
    if kind == "draw":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} draws a card."
    if kind == "play":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} plays {_card_id(data.get('card'))}."
    if kind == "guard_guess":
        return (
            f"{lookup.get(data.get('player_id'), 'Unknown')} guesses {_card_id(data.get('guess'))} "
            f"on {lookup.get(data.get('target_id'), 'Unknown')}."
        )
    if kind == "reveal":
        return (
            f"{lookup.get(data.get('viewer_id'), 'Unknown')} looked at "
            f"{lookup.get(data.get('target_id'), 'Unknown')}'s hand."
        )
    if kind == "baron_compare":
        return (
            f"{lookup.get(data.get('player_id'), 'Unknown')} compares hand with "
            f"{lookup.get(data.get('target_id'), 'Unknown')}."
        )
    if kind == "protected":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} is protected."
    if kind == "protection_ended":
        return f"{lookup.get(data.get('player_id'), 'Unknown')}'s protection ends."
    if kind == "discard":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} discards {_card_id(data.get('card'))}."
    if kind == "eliminated":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} is eliminated."
    if kind == "swap":
        return (
            f"{lookup.get(data.get('player_id'), 'Unknown')} swaps hands with "
            f"{lookup.get(data.get('target_id'), 'Unknown')}."
        )
    if kind == "countess_no_effect":
        return f"{lookup.get(data.get('player_id'), 'Unknown')}'s countess has no effect."
    if kind == "round_end":
        winners = ", ".join(lookup.get(player_id, "Unknown") for player_id in data.get("winners", []))
        return f"Round ends. Winner(s): {winners}."
    if kind == "token_awarded":
        return f"{lookup.get(data.get('player_id'), 'Unknown')} gains a token."
    if kind == "deck_empty":
        return "Deck is empty. Round ends now."
    return f"{kind}: {_serialize_event_data(data)}"


def _format_private_event(event: Any, lookup: dict[int, str], viewer_id: int) -> str | None:
    kind = event.kind
    data = event.data
    if kind == "reveal" and data.get("viewer_id") == viewer_id:
        return (
            f"You looked at {lookup.get(data.get('target_id'), 'Unknown')}'s hand: "
            f"{_card_id(data.get('card'))}."
        )
    if kind == "baron_compare" and viewer_id in {data.get("player_id"), data.get("target_id")}:
        return (
            "Baron compare details: "
            f"{lookup.get(data.get('player_id'), 'Unknown')} ({_card_id(data.get('player_card'))}) vs "
            f"{lookup.get(data.get('target_id'), 'Unknown')} ({_card_id(data.get('target_card'))})."
        )
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("love_letter.server:app", host="127.0.0.1", port=8000, reload=True)
