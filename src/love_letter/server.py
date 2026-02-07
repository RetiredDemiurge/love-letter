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
        return {
            "players": players,
            "current_player_id": round_state.players[round_state.current_player_idx].id,
            "round_over": round_state.round_over,
            "round_number": self.game_state.round_number,
            "target_tokens": self.game_state.target_tokens,
            "deck_count": len(round_state.deck),
            "burned_count": len(round_state.burned),
            "face_up": [_card_id(card) for card in round_state.face_up],
            "events": [_serialize_event(event) for event in round_state.events[-20:]],
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("love_letter.server:app", host="127.0.0.1", port=8000, reload=True)
