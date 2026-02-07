from random import Random

import pytest

from love_letter.engine.cards import CardType
from love_letter.engine.rules import (
    RulesError,
    apply_action,
    check_round_end,
    legal_play_cards,
    new_game,
    setup_round,
    start_turn,
    valid_targets,
)
from love_letter.engine.state import Action, PlayerState, RoundState


def _round_with_players(players: list[PlayerState]) -> RoundState:
    return RoundState(players=players, deck=[], burned=[], face_up=[], current_player_idx=0)


def test_two_player_setup_face_up_removed() -> None:
    game_state = new_game(["A", "B"])
    rng = Random(0)
    round_state = setup_round(game_state, rng)

    assert len(round_state.players) == 2
    assert len(round_state.face_up) == 3
    assert len(round_state.burned) == 1
    assert len(round_state.deck) == 16 - 3 - 1 - 2


def test_countess_forced_play() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.COUNTESS, CardType.PRINCE])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD])
    round_state = _round_with_players([player, target])

    assert legal_play_cards(player.hand) == [CardType.COUNTESS]

    action = Action(player_id=0, card=CardType.PRINCE, target_id=1)
    with pytest.raises(RulesError):
        apply_action(round_state, action, Random(0))


def test_guard_guess_eliminates_on_match() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.GUARD, target_id=1, guess=CardType.PRIEST)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is True


def test_guard_guess_no_elimination_on_miss() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.GUARD, target_id=1, guess=CardType.BARON)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is False


def test_guard_no_targets_when_all_protected() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST], protected=True)
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.GUARD, target_id=None, guess=None)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is False


def test_king_no_targets_when_all_protected() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.KING])
    target = PlayerState(id=1, name="B", hand=[CardType.PRINCE], protected=True)
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.KING, target_id=None)
    apply_action(round_state, action, Random(0))

    assert player.hand == []
    assert target.hand == [CardType.PRINCE]


def test_prince_draws_burned_when_deck_empty() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.PRINCE])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD])
    round_state = _round_with_players([player, target])
    round_state.burned = [CardType.PRIEST]
    round_state.face_up = [CardType.BARON]

    action = Action(player_id=0, card=CardType.PRINCE, target_id=1)
    apply_action(round_state, action, Random(0))

    assert target.hand == [CardType.PRIEST]
    assert round_state.burned == []
    assert round_state.face_up == [CardType.BARON]


def test_prince_forces_self_target_when_all_others_protected() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.PRINCE])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD], protected=True)
    round_state = _round_with_players([player, target])

    targets = valid_targets(round_state, player.id, CardType.PRINCE)
    assert [p.id for p in targets] == [player.id]

    invalid_action = Action(player_id=0, card=CardType.PRINCE, target_id=1)
    with pytest.raises(RulesError):
        apply_action(round_state, invalid_action, Random(0))


def test_tie_breaker_uses_discard_sum() -> None:
    game_state = new_game(["A", "B"])
    player_a, player_b = game_state.players
    player_a.hand = [CardType.PRINCE]
    player_b.hand = [CardType.PRINCE]
    player_a.discard = [CardType.GUARD]
    player_b.discard = [CardType.KING]

    round_state = RoundState(
        players=game_state.players,
        deck=[],
        burned=[],
        face_up=[],
        current_player_idx=0,
    )

    check_round_end(game_state, round_state, Random(0))

    assert player_b.tokens == 1
    assert player_a.tokens == 0


def test_princess_played_eliminates_self() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.PRINCESS])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.PRINCESS)
    apply_action(round_state, action, Random(0))

    assert player.eliminated is True
    assert player.hand == []
    assert player.discard == [CardType.PRINCESS]


def test_prince_discards_princess_eliminates_target() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.PRINCE])
    target = PlayerState(id=1, name="B", hand=[CardType.PRINCESS])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.PRINCE, target_id=1)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is True
    assert target.hand == []
    assert target.discard[-1] == CardType.PRINCESS


def test_guard_cannot_guess_guard() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.GUARD, target_id=1, guess=CardType.GUARD)
    with pytest.raises(RulesError):
        apply_action(round_state, action, Random(0))


def test_elimination_discards_hand() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.GUARD, target_id=1, guess=CardType.PRIEST)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is True
    assert target.hand == []
    assert target.discard == [CardType.PRIEST]


def test_baron_eliminates_lower_card() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.BARON, CardType.PRINCESS])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.BARON, target_id=1)
    apply_action(round_state, action, Random(0))

    assert target.eliminated is True
    assert player.eliminated is False


def test_priest_reveal_no_state_change() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.PRIEST])
    target = PlayerState(id=1, name="B", hand=[CardType.GUARD])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.PRIEST, target_id=1)
    apply_action(round_state, action, Random(0))

    assert target.hand == [CardType.GUARD]
    assert target.eliminated is False


def test_king_swaps_hands() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.KING, CardType.GUARD])
    target = PlayerState(id=1, name="B", hand=[CardType.PRINCESS])
    round_state = _round_with_players([player, target])

    action = Action(player_id=0, card=CardType.KING, target_id=1)
    apply_action(round_state, action, Random(0))

    assert player.hand == [CardType.PRINCESS]
    assert target.hand == [CardType.GUARD]


def test_handmaid_protection_ends_on_turn_start() -> None:
    player = PlayerState(id=0, name="A", hand=[CardType.GUARD], protected=True)
    target = PlayerState(id=1, name="B", hand=[CardType.PRIEST])
    round_state = _round_with_players([player, target])
    round_state.deck = [CardType.BARON]

    can_play = start_turn(round_state, player.id, Random(0))

    assert can_play is True
    assert player.protected is False
    assert len(player.hand) == 2


def test_round_ends_when_deck_empty_after_turn() -> None:
    game_state = new_game(["A", "B"])
    player_a, player_b = game_state.players
    player_a.hand = [CardType.PRINCE]
    player_b.hand = [CardType.GUARD]
    round_state = RoundState(
        players=game_state.players,
        deck=[],
        burned=[],
        face_up=[],
        current_player_idx=0,
    )

    check_round_end(game_state, round_state, Random(0))

    assert round_state.round_over is True
    assert player_a.tokens == 1
