from __future__ import annotations

import random

from fastapi.testclient import TestClient

from love_letter.server import app


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


def _create_table(name: str, seed: int | None = None) -> dict:
    payload = {"name": name}
    if seed is not None:
        payload["seed"] = seed
    response = client.post("/api/multi/create", json=payload)
    assert response.status_code == 200
    return response.json()


def _join_table(join_code: str, name: str) -> dict:
    response = client.post("/api/multi/join", json={"join_code": join_code, "name": name})
    assert response.status_code == 200
    return response.json()


def _state(game_id: str, seat_token: str) -> dict:
    response = client.get(
        "/api/multi/state",
        params={"game_id": game_id},
        headers={"X-Seat-Token": seat_token},
    )
    assert response.status_code == 200
    return response.json()


def _target_candidates(state: dict, player_id: int, card_id: str) -> list[int]:
    targets: list[int] = []
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


def _choose_card(hand: list[str]) -> str:
    if "countess" in hand and ("king" in hand or "prince" in hand):
        return "countess"
    for card_id in ["handmaid", "countess", "princess", "priest", "guard", "baron", "prince", "king"]:
        if card_id in hand:
            return card_id
    return hand[0]


def _assert_private_hand_visibility(view_state: dict) -> None:
    viewer_id = view_state["viewer_id"]
    for player in view_state["players"]:
        if player["id"] == viewer_id:
            assert player["hand"] is not None
            assert len(player["hand"]) == player["hand_count"]
        else:
            assert player["hand"] is None


def test_multiplayer_create_join_and_private_state() -> None:
    created = _create_table("Host", seed=7)
    game_id = created["game_id"]
    join_code = created["join_code"]
    host_token = created["seat_token"]

    host_state = created["state"]
    assert host_state["waiting_for_opponent"] is True
    assert host_state["connected_players"] == 1
    assert len(join_code) == 6

    not_ready = client.post(
        "/api/multi/start",
        json={"game_id": game_id},
        headers={"X-Seat-Token": host_token},
    )
    assert not_ready.status_code == 400
    assert "waiting for player 2" in not_ready.json()["detail"].lower()

    joined = _join_table(join_code, "Guest")
    guest_token = joined["seat_token"]
    guest_state = joined["state"]
    assert guest_state["waiting_for_opponent"] is False
    assert guest_state["connected_players"] == 2

    host_view = _state(game_id, host_token)
    guest_view = _state(game_id, guest_token)
    _assert_private_hand_visibility(host_view)
    _assert_private_hand_visibility(guest_view)
    assert host_view["players"][1]["name"] == "Guest"


def test_multiplayer_rejects_missing_or_invalid_token() -> None:
    created = _create_table("A", seed=3)
    game_id = created["game_id"]
    join_code = created["join_code"]
    host_token = created["seat_token"]
    joined = _join_table(join_code, "B")
    guest_token = joined["seat_token"]

    missing = client.get("/api/multi/state", params={"game_id": game_id})
    assert missing.status_code == 401

    invalid = client.get(
        "/api/multi/state",
        params={"game_id": game_id},
        headers={"X-Seat-Token": "bad-token"},
    )
    assert invalid.status_code == 401

    other_game = _create_table("C", seed=9)
    wrong_token = client.get(
        "/api/multi/state",
        params={"game_id": game_id},
        headers={"X-Seat-Token": other_game["seat_token"]},
    )
    assert wrong_token.status_code == 401

    # Control check that valid tokens still work.
    assert _state(game_id, host_token)["viewer_id"] == 0
    assert _state(game_id, guest_token)["viewer_id"] == 1


def test_multiplayer_priest_reveal_stays_private() -> None:
    created = _create_table("A", seed=16)
    game_id = created["game_id"]
    host_token = created["seat_token"]
    joined = _join_table(created["join_code"], "B")
    guest_token = joined["seat_token"]

    host_state = _state(game_id, host_token)
    guest_state = _state(game_id, guest_token)
    token_by_player = {
        host_state["viewer_id"]: host_token,
        guest_state["viewer_id"]: guest_token,
    }

    current_player = host_state["current_player_id"]
    current_token = token_by_player[current_player]
    target_player = 1 if current_player == 0 else 0

    started = client.post(
        "/api/multi/start",
        json={"game_id": game_id},
        headers={"X-Seat-Token": current_token},
    )
    assert started.status_code == 200
    start_state = started.json()
    hand = next(player for player in start_state["players"] if player["id"] == current_player)["hand"]
    assert "priest" in hand

    played = client.post(
        "/api/multi/play",
        json={"game_id": game_id, "card": "priest", "target_id": target_player, "guess": None},
        headers={"X-Seat-Token": current_token},
    )
    assert played.status_code == 200
    current_view = played.json()

    reveal_events = [event for event in current_view["events"] if event["kind"] == "reveal"]
    assert reveal_events
    assert "card" not in reveal_events[-1]["data"]
    assert any("you looked at" in line.lower() for line in current_view["private_log"])

    other_view = _state(game_id, token_by_player[target_player])
    assert not any("you looked at" in line.lower() for line in other_view["private_log"])


def test_multiplayer_randomized_two_client_simulation() -> None:
    random.seed(0)

    for seed in range(12):
        created = _create_table(f"H{seed}", seed=seed)
        game_id = created["game_id"]
        host_token = created["seat_token"]
        joined = _join_table(created["join_code"], f"G{seed}")
        guest_token = joined["seat_token"]

        token_by_player = {0: host_token, 1: guest_token}

        for _ in range(120):
            host_state = _state(game_id, host_token)
            guest_state = _state(game_id, guest_token)
            _assert_private_hand_visibility(host_state)
            _assert_private_hand_visibility(guest_state)
            assert host_state["current_player_id"] == guest_state["current_player_id"]

            current_player = host_state["current_player_id"]
            current_token = token_by_player[current_player]
            current_state = host_state if current_player == host_state["viewer_id"] else guest_state
            me = next(player for player in current_state["players"] if player["id"] == current_player)
            hand = me["hand"] or []

            if current_state["round_over"]:
                next_round = client.post(
                    "/api/multi/next_round",
                    json={"game_id": game_id},
                    headers={"X-Seat-Token": current_token},
                )
                if next_round.status_code not in {200, 400}:
                    assert False, next_round.text
                continue

            if len(hand) == 1:
                started = client.post(
                    "/api/multi/start",
                    json={"game_id": game_id},
                    headers={"X-Seat-Token": current_token},
                )
                if started.status_code not in {200, 400}:
                    assert False, started.text
                if started.status_code == 200:
                    current_state = started.json()
                    me = next(player for player in current_state["players"] if player["id"] == current_player)
                    hand = me["hand"] or []
                else:
                    continue

            if current_state["round_over"] or len(hand) != 2:
                continue

            card_id = _choose_card(hand)
            meta = CARD_META[card_id]
            target_id = None
            if meta.get("needs_target"):
                targets = _target_candidates(current_state, current_player, card_id)
                target_id = random.choice(targets) if targets else None

            played = client.post(
                "/api/multi/play",
                json={
                    "game_id": game_id,
                    "card": card_id,
                    "target_id": target_id,
                    "guess": "priest" if meta.get("needs_guess") else None,
                },
                headers={"X-Seat-Token": current_token},
            )
            if played.status_code not in {200, 400}:
                assert False, played.text
