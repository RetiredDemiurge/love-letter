from __future__ import annotations

from fastapi.testclient import TestClient

from love_letter.server import SESSION, app


client = TestClient(app)


CARD_META = {
    "guard": {"needs_target": True, "needs_guess": True},
    "priest": {"needs_target": True},
    "baron": {"needs_target": True},
    "handmaid": {},
    "prince": {"needs_target": True, "can_self": True},
    "king": {"needs_target": True},
    "countess": {},
    "princess": {},
}


def test_web_root_redirects() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"].endswith("/web/index.html")


def test_web_index_serves() -> None:
    response = client.get("/web/index.html")
    assert response.status_code == 200
    assert "Love Letter" in response.text


def test_assets_serve() -> None:
    response = client.get("/assets/cards/princess.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_api_flow_start_and_play() -> None:
    reset = client.post("/api/new", json={"names": ["A", "B"]})
    assert reset.status_code == 200

    response = client.get("/api/state?player_id=0")
    assert response.status_code == 200
    state = response.json()

    current_player = state["current_player_id"]

    response = client.post("/api/start", json={"player_id": current_player})
    assert response.status_code == 200
    state = response.json()

    player_state = next(p for p in state["players"] if p["id"] == current_player)
    hand = player_state["hand"]
    assert hand and len(hand) == 2

    card_id = _choose_card(hand)
    meta = CARD_META[card_id]

    target_id = None
    if meta.get("needs_target"):
        targets = _valid_targets(state, current_player, card_id)
        target_id = targets[0] if targets else None

    payload = {
        "player_id": current_player,
        "card": card_id,
        "target_id": target_id,
        "guess": "priest" if meta.get("needs_guess") else None,
    }

    response = client.post("/api/play", json=payload)
    assert response.status_code == 200
    next_state = response.json()
    assert "players" in next_state


def test_api_start_turn_rejects_multiple_draws() -> None:
    SESSION.rng.seed(0)
    response = client.post("/api/new", json={"names": ["A", "B"]})
    assert response.status_code == 200
    state = response.json()
    current_player = state["current_player_id"]

    first = client.post("/api/start", json={"player_id": current_player})
    assert first.status_code == 200

    second = client.post("/api/start", json={"player_id": current_player})
    assert second.status_code == 400
    assert "already drawn" in second.json()["detail"].lower()

    state_for_current = client.get("/api/state", params={"player_id": current_player}).json()
    current = next(player for player in state_for_current["players"] if player["id"] == current_player)
    assert len(current["hand"]) == 2


def test_api_priest_reveal_is_private() -> None:
    SESSION.rng.seed(16)
    response = client.post("/api/new", json={"names": ["A", "B"]})
    assert response.status_code == 200
    state = response.json()
    current_player = state["current_player_id"]
    target_player = 1 if current_player == 0 else 0

    state = client.post("/api/start", json={"player_id": current_player}).json()
    current = next(player for player in state["players"] if player["id"] == current_player)
    assert "priest" in current["hand"]

    play = client.post(
        "/api/play",
        json={"player_id": current_player, "card": "priest", "target_id": target_player, "guess": None},
    )
    assert play.status_code == 200
    current_view = play.json()

    reveal_events = [event for event in current_view["events"] if event["kind"] == "reveal"]
    assert reveal_events
    assert "card" not in reveal_events[-1]["data"]
    assert any("looked at" in line.lower() for line in current_view["public_log"])
    assert any("you looked at" in line.lower() for line in current_view["private_log"])

    other_view = client.get("/api/state", params={"player_id": target_player}).json()
    assert other_view["private_log"] == []


def _choose_card(hand: list[str]) -> str:
    # Prefer cards that require no target
    for card_id in ["handmaid", "countess", "princess"]:
        if card_id in hand:
            return card_id
    return hand[0]


def _valid_targets(state: dict, player_id: int, card_id: str) -> list[int]:
    targets = []
    for player in state["players"]:
        if player["eliminated"]:
            continue
        if card_id in {"guard", "priest", "baron", "king"}:
            if player["id"] == player_id:
                continue
            if player["protected"]:
                continue
            targets.append(player["id"])
            continue
        if card_id == "prince":
            if player["id"] == player_id:
                targets.append(player["id"])
                continue
            if player["protected"]:
                continue
            targets.append(player["id"])
    return targets
