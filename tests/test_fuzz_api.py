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
    "prince": {"needs_target": True},
    "king": {"needs_target": True},
    "countess": {},
    "princess": {},
}


def _safe_json(response):
    try:
        return response.json()
    except Exception:
        return None


def test_fuzz_api_state_machine() -> None:
    random.seed(0)

    for player_count in [2, 3, 4]:
        response = client.post("/api/new", json={"names": [f"P{i+1}" for i in range(player_count)]})
        assert response.status_code == 200
        state = response.json()

        for _ in range(250):
            state = client.get("/api/state?player_id=0").json()
            current = state["current_player_id"]
            # Re-fetch state for current player to obtain their hand
            state = client.get("/api/state", params={"player_id": current}).json()

            # Invariants: deck/burned counts non-negative
            assert state["deck_count"] >= 0
            assert state["burned_count"] >= 0

            current_player = next(p for p in state["players"] if p["id"] == current)
            hand = current_player["hand"] or []

            # Invariant: hand size should be 1 or 2 for current player unless round is over
            if not state["round_over"]:
                assert len(hand) in {1, 2}

            # Randomly decide to start turn
            if len(hand) == 1 and random.random() < 0.8:
                start = client.post("/api/start", json={"player_id": current})
                if start.status_code != 200:
                    assert start.status_code in {400, 422}
                else:
                    state = start.json()

            # refresh hand after potential draw
            state = client.get("/api/state", params={"player_id": current}).json()
            current_player = next(p for p in state["players"] if p["id"] == current)
            hand = current_player["hand"] or []

            # If we have 2 cards, try a play (sometimes invalid)
            if len(hand) == 2 and random.random() < 0.9:
                card_id = random.choice(hand)
                meta = CARD_META.get(card_id, {})
                target_id = None
                if meta.get("needs_target"):
                    targets = [
                        p["id"]
                        for p in state["players"]
                        if not p["eliminated"] and p["id"] != current and not p["protected"]
                    ]
                    target_id = random.choice(targets) if targets else None
                payload = {
                    "player_id": current,
                    "card": card_id,
                    "target_id": target_id,
                    "guess": "priest" if meta.get("needs_guess") else None,
                }
                play = client.post("/api/play", json=payload)
                if play.status_code != 200:
                    assert play.status_code in {400, 422}
                else:
                    state = play.json()

            # Randomly attempt next round if over
            if state.get("round_over") and random.random() < 0.3:
                nxt = client.post("/api/next_round")
                if nxt.status_code == 200:
                    state = nxt.json()
