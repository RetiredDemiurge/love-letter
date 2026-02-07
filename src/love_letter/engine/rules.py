from __future__ import annotations

from random import Random
from typing import Iterable

from .cards import CARD_COUNTS, CardType
from .state import Action, Event, GameState, PlayerState, RoundState, SetupConfig

DEFAULT_SETUP_BY_PLAYERS: dict[int, SetupConfig] = {
    2: SetupConfig(burn_face_down=1, burn_face_up=3),
    3: SetupConfig(burn_face_down=1, burn_face_up=0),
    4: SetupConfig(burn_face_down=1, burn_face_up=0),
}

TARGET_TOKENS_BY_PLAYERS: dict[int, int] = {
    2: 7,
    3: 5,
    4: 4,
}


class RulesError(ValueError):
    pass


def default_target_tokens(num_players: int) -> int:
    if num_players not in TARGET_TOKENS_BY_PLAYERS:
        raise RulesError("Love Letter supports 2-4 players.")
    return TARGET_TOKENS_BY_PLAYERS[num_players]


def default_setup(num_players: int) -> SetupConfig:
    if num_players not in DEFAULT_SETUP_BY_PLAYERS:
        raise RulesError("Love Letter supports 2-4 players.")
    return DEFAULT_SETUP_BY_PLAYERS[num_players]


def new_game(player_names: list[str], target_tokens: int | None = None) -> GameState:
    players = [PlayerState(id=i, name=name) for i, name in enumerate(player_names)]
    tokens_goal = target_tokens if target_tokens is not None else default_target_tokens(len(players))
    return GameState(players=players, target_tokens=tokens_goal)


def build_deck(rng: Random) -> list[CardType]:
    deck: list[CardType] = []
    for card, count in CARD_COUNTS.items():
        deck.extend([card] * count)
    rng.shuffle(deck)
    return deck


def emit(round_state: RoundState, kind: str, **data) -> Event:
    event = Event(kind=kind, data=data)
    round_state.events.append(event)
    return event


def setup_round(game_state: GameState, rng: Random, setup: SetupConfig | None = None) -> RoundState:
    setup = setup or default_setup(len(game_state.players))
    for player in game_state.players:
        player.hand.clear()
        player.discard.clear()
        player.protected = False
        player.eliminated = False

    deck = build_deck(rng)
    burned = [deck.pop() for _ in range(setup.burn_face_down)]
    face_up = [deck.pop() for _ in range(setup.burn_face_up)]

    for player in game_state.players:
        player.hand.append(deck.pop())

    start_player_idx = _choose_start_player_index(game_state, rng)
    round_state = RoundState(
        players=game_state.players,
        deck=deck,
        burned=burned,
        face_up=face_up,
        current_player_idx=start_player_idx,
    )
    game_state.round_number += 1
    game_state.round_state = round_state
    emit(round_state, "round_start", round=game_state.round_number, start_player_id=round_state.players[start_player_idx].id)
    if face_up:
        emit(round_state, "face_up", cards=list(face_up))
    return round_state


def _choose_start_player_index(game_state: GameState, rng: Random) -> int:
    if game_state.next_start_player_id is None:
        return rng.randrange(len(game_state.players))
    for idx, player in enumerate(game_state.players):
        if player.id == game_state.next_start_player_id:
            return idx
    return 0


def start_turn(round_state: RoundState, player_id: int, rng: Random) -> bool:
    player = _find_player(round_state, player_id)
    if player.eliminated:
        raise RulesError("Eliminated players cannot take turns.")

    if player.protected:
        player.protected = False
        emit(round_state, "protection_ended", player_id=player_id)

    if not round_state.deck:
        emit(round_state, "deck_empty")
        return False

    drawn = round_state.deck.pop()
    player.hand.append(drawn)
    emit(round_state, "draw", player_id=player_id, card=drawn)
    return True


def legal_play_cards(hand: list[CardType]) -> list[CardType]:
    if CardType.COUNTESS in hand and (CardType.KING in hand or CardType.PRINCE in hand):
        return [CardType.COUNTESS]
    return list(hand)


def validate_action(round_state: RoundState, action: Action) -> str | None:
    player = _find_player(round_state, action.player_id)
    if player.eliminated:
        return "You are eliminated."
    if action.card not in player.hand:
        return "You must play a card from your hand."

    legal_cards = legal_play_cards(player.hand)
    if action.card not in legal_cards:
        return "You must play the Countess when holding it with King or Prince."

    if action.card in {CardType.GUARD, CardType.PRIEST, CardType.BARON, CardType.KING}:
        valid = _valid_targets(round_state, player, action.card)
        if not valid:
            if action.target_id is not None:
                return "No valid targets."
        else:
            if action.target_id is None:
                return "This card requires a target."
            if action.target_id not in {p.id for p in valid}:
                return "Target is not valid."

        if action.card == CardType.GUARD and valid:
            if action.guess is None:
                return "Guard requires a guess."
            if action.guess == CardType.GUARD:
                return "Guard cannot guess Guard."

    if action.card == CardType.PRINCE:
        valid = _valid_targets(round_state, player, action.card)
        if action.target_id is None:
            return "Prince requires a target."
        if action.target_id not in {p.id for p in valid}:
            return "Target is not valid."

    if action.card == CardType.PRIEST and action.target_id == action.player_id:
        return "You must target another player."
    if action.card == CardType.BARON and action.target_id == action.player_id:
        return "You must target another player."
    if action.card == CardType.GUARD and action.target_id == action.player_id:
        return "You must target another player."
    if action.card == CardType.KING and action.target_id == action.player_id:
        return "You must target another player."

    return None


def apply_action(round_state: RoundState, action: Action, rng: Random) -> list[Event]:
    error = validate_action(round_state, action)
    if error:
        raise RulesError(error)

    player = _find_player(round_state, action.player_id)
    target = _find_player(round_state, action.target_id) if action.target_id is not None else None

    player.hand.remove(action.card)
    player.discard.append(action.card)
    emit(round_state, "play", player_id=player.id, card=action.card)

    if action.card == CardType.GUARD:
        _resolve_guard(round_state, player, target, action.guess)
    elif action.card == CardType.PRIEST:
        _resolve_priest(round_state, player, target)
    elif action.card == CardType.BARON:
        _resolve_baron(round_state, player, target)
    elif action.card == CardType.HANDMAID:
        player.protected = True
        emit(round_state, "protected", player_id=player.id)
    elif action.card == CardType.PRINCE:
        _resolve_prince(round_state, player, target, rng)
    elif action.card == CardType.KING:
        _resolve_king(round_state, player, target)
    elif action.card == CardType.COUNTESS:
        emit(round_state, "countess_no_effect", player_id=player.id)
    elif action.card == CardType.PRINCESS:
        _eliminate_player(round_state, player, reason="played_princess")

    return round_state.events


def advance_turn(round_state: RoundState) -> None:
    if round_state.round_over:
        return
    num_players = len(round_state.players)
    idx = round_state.current_player_idx
    for _ in range(num_players):
        idx = (idx + 1) % num_players
        if not round_state.players[idx].eliminated:
            round_state.current_player_idx = idx
            return


def check_round_end(game_state: GameState, round_state: RoundState, rng: Random) -> list[Event]:
    if round_state.round_over:
        return round_state.events

    active = [p for p in round_state.players if not p.eliminated]
    winners: list[PlayerState] = []

    if len(active) <= 1:
        winners = active
    elif not round_state.deck:
        winners = _determine_highest_hand(active)
    else:
        return round_state.events

    round_state.round_over = True
    emit(round_state, "round_end", winners=[p.id for p in winners])
    for winner in winners:
        winner.tokens += 1
        emit(round_state, "token_awarded", player_id=winner.id, tokens=winner.tokens)

    if winners:
        game_state.next_start_player_id = rng.choice([p.id for p in winners])
    return round_state.events


def game_over(game_state: GameState) -> bool:
    return any(player.tokens >= game_state.target_tokens for player in game_state.players)


def valid_targets(round_state: RoundState, player_id: int, card: CardType) -> list[PlayerState]:
    player = _find_player(round_state, player_id)
    return _valid_targets(round_state, player, card)


def _resolve_guard(round_state: RoundState, player: PlayerState, target: PlayerState | None, guess: CardType | None) -> None:
    if target is None or guess is None:
        return
    emit(round_state, "guard_guess", player_id=player.id, target_id=target.id, guess=guess)
    if target.hand and target.hand[0] == guess:
        _eliminate_player(round_state, target, reason="guard_guess")


def _resolve_priest(round_state: RoundState, player: PlayerState, target: PlayerState | None) -> None:
    if target is None:
        return
    if target.hand:
        emit(round_state, "reveal", viewer_id=player.id, target_id=target.id, card=target.hand[0])


def _resolve_baron(round_state: RoundState, player: PlayerState, target: PlayerState | None) -> None:
    if target is None:
        return
    if not player.hand or not target.hand:
        return
    player_card = player.hand[0]
    target_card = target.hand[0]
    emit(round_state, "baron_compare", player_id=player.id, target_id=target.id, player_card=player_card, target_card=target_card)
    if player_card > target_card:
        _eliminate_player(round_state, target, reason="baron")
    elif target_card > player_card:
        _eliminate_player(round_state, player, reason="baron")


def _resolve_prince(round_state: RoundState, player: PlayerState, target: PlayerState | None, rng: Random) -> None:
    if target is None:
        return
    if target.hand:
        discarded = target.hand.pop()
        target.discard.append(discarded)
        emit(round_state, "discard", player_id=target.id, card=discarded, reason="prince")
        if discarded == CardType.PRINCESS:
            _eliminate_player(round_state, target, reason="prince_princess")
            return

    if not target.eliminated:
        replacement = _draw_replacement(round_state, rng)
        if replacement is not None:
            target.hand.append(replacement)
            emit(round_state, "draw", player_id=target.id, card=replacement, reason="prince")


def _resolve_king(round_state: RoundState, player: PlayerState, target: PlayerState | None) -> None:
    if target is None:
        return
    if not player.hand or not target.hand:
        return
    player.hand, target.hand = target.hand, player.hand
    emit(round_state, "swap", player_id=player.id, target_id=target.id)


def _eliminate_player(round_state: RoundState, player: PlayerState, reason: str) -> None:
    if player.eliminated:
        return
    player.eliminated = True
    player.protected = False
    if player.hand:
        discarded = player.hand.pop()
        player.discard.append(discarded)
        emit(round_state, "discard", player_id=player.id, card=discarded, reason="elimination")
    emit(round_state, "eliminated", player_id=player.id, reason=reason)


def _draw_replacement(round_state: RoundState, rng: Random) -> CardType | None:
    if round_state.deck:
        return round_state.deck.pop()
    if round_state.burned:
        return round_state.burned.pop()
    return None


def _determine_highest_hand(players: Iterable[PlayerState]) -> list[PlayerState]:
    best_value = max(p.hand[0] for p in players if p.hand)
    candidates = [p for p in players if p.hand and p.hand[0] == best_value]
    if len(candidates) <= 1:
        return candidates

    best_discard = max(sum(card for card in p.discard) for p in candidates)
    winners = [p for p in candidates if sum(card for card in p.discard) == best_discard]
    return winners


def _find_player(round_state: RoundState, player_id: int) -> PlayerState:
    for player in round_state.players:
        if player.id == player_id:
            return player
    raise RulesError("Player not found.")


def _valid_targets(round_state: RoundState, player: PlayerState, card: CardType) -> list[PlayerState]:
    targets: list[PlayerState] = []
    for candidate in round_state.players:
        if candidate.eliminated:
            continue
        if card in {CardType.GUARD, CardType.PRIEST, CardType.BARON, CardType.KING}:
            if candidate.id == player.id:
                continue
            if candidate.protected:
                continue
            targets.append(candidate)
            continue
        if card == CardType.PRINCE:
            if candidate.id == player.id:
                targets.append(candidate)
                continue
            if candidate.protected:
                continue
            targets.append(candidate)
    return targets
