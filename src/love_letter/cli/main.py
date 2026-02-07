from __future__ import annotations

import argparse
import random
from typing import Iterable

from rich.console import Console
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from love_letter.engine.cards import CardType, card_name
from love_letter.engine.rules import (
    RulesError,
    advance_turn,
    apply_action,
    check_round_end,
    game_over,
    legal_play_cards,
    new_game,
    setup_round,
    start_turn,
    valid_targets,
)
from love_letter.engine.state import Action, PlayerState, RoundState
from love_letter.cli.render import render_event

console = Console()

CARD_STYLES: dict[CardType, str] = {
    CardType.GUARD: "bright_blue",
    CardType.PRIEST: "bright_cyan",
    CardType.BARON: "bright_magenta",
    CardType.HANDMAID: "bright_green",
    CardType.PRINCE: "bright_yellow",
    CardType.KING: "bright_red",
    CardType.COUNTESS: "white",
    CardType.PRINCESS: "bold red",
}


def main() -> None:
    args = _parse_args()
    names = args.names or _prompt_names()

    rng = random.Random()
    game_state = new_game(names)
    game_state.next_start_player_id = _prompt_start_player(game_state.players)

    console.print(
        Panel.fit(
            f"Love Letter — {len(names)} players\nFirst to {game_state.target_tokens} tokens wins.",
            title="Welcome",
            border_style="magenta",
        )
    )
    console.print("")

    while not game_over(game_state):
        round_state = setup_round(game_state, rng)
        _print_new_events(round_state, 0)

        while not round_state.round_over:
            current_player = round_state.players[round_state.current_player_idx]
            if current_player.eliminated:
                advance_turn(round_state)
                continue

            _wait_for_player(current_player)
            start_idx = len(round_state.events)
            can_play = start_turn(round_state, current_player.id, rng)
            _print_new_events(round_state, start_idx)

            if not can_play:
                start_idx = len(round_state.events)
                check_round_end(game_state, round_state, rng)
                _print_new_events(round_state, start_idx)
                break

            _play_turn(round_state, current_player, rng)

            start_idx = len(round_state.events)
            check_round_end(game_state, round_state, rng)
            _print_new_events(round_state, start_idx)

            if not round_state.round_over:
                advance_turn(round_state)

        _print_scoreboard(round_state.players)

    winners = [p for p in game_state.players if p.tokens >= game_state.target_tokens]
    if winners:
        winner_names = ", ".join(p.name for p in winners)
        console.print(Panel.fit(f"Winner(s): {winner_names}", title="Game Over", border_style="green"))


def _play_turn(round_state: RoundState, player: PlayerState, rng: random.Random) -> None:
    while True:
        console.print(
            Panel.fit(
                _hand_cards(player.hand),
                title=f"{player.name}'s Hand",
                border_style="cyan",
                box=box.ASCII,
            )
        )
        legal = legal_play_cards(player.hand)
        if len(legal) == 1:
            console.print(Text(f"Forced play: {card_name(legal[0])}", style="bold yellow"))
        chosen_card = _prompt_card_choice(player.hand, legal)

        target_id = None
        guess = None

        if chosen_card in {CardType.GUARD, CardType.PRIEST, CardType.BARON, CardType.PRINCE, CardType.KING}:
            targets = valid_targets(round_state, player.id, chosen_card)
            if not targets and chosen_card != CardType.PRINCE:
                console.print(Text("No valid targets. This card has no effect.", style="dim"))
            else:
                target_id = _prompt_target(targets)

        if chosen_card == CardType.GUARD and target_id is not None:
            guess = _prompt_guard_guess()

        action = Action(player_id=player.id, card=chosen_card, target_id=target_id, guess=guess)
        try:
            start_idx = len(round_state.events)
            apply_action(round_state, action, rng)
            _print_new_events(round_state, start_idx)
            break
        except RulesError as exc:
            console.print(Text(f"Invalid move: {exc}", style="bold red"))


def _prompt_card_choice(hand: list[CardType], legal: list[CardType]) -> CardType:
    while True:
        choice = _prompt_int("Choose a card to play (number): ")
        if 1 <= choice <= len(hand):
            card = hand[choice - 1]
            if card in legal:
                return card
        console.print(Text("That card cannot be played. Try again.", style="red"))


def _prompt_target(targets: list[PlayerState]) -> int:
    while True:
        console.print(Panel.fit(_targets_table(targets), title="Targets", border_style="blue"))
        choice = _prompt_int("Choose a target (number): ")
        if 1 <= choice <= len(targets):
            return targets[choice - 1].id
        console.print(Text("Invalid target.", style="red"))


def _prompt_guard_guess() -> CardType:
    options = [card for card in CardType if card != CardType.GUARD]
    while True:
        console.print(Panel.fit(_guess_table(options), title="Guard Guess", border_style="yellow"))
        choice = _prompt_int("Choose a card (number): ")
        if 1 <= choice <= len(options):
            return options[choice - 1]
        console.print(Text("Invalid choice.", style="red"))


def _prompt_names() -> list[str]:
    while True:
        count = _prompt_int("Number of players (2-4): ")
        if 2 <= count <= 4:
            break
        console.print(Text("Love Letter supports 2-4 players.", style="red"))
    names = []
    for idx in range(count):
        name = input(f"Player {idx + 1} name: ").strip() or f"Player {idx + 1}"
        names.append(name)
    return names


def _prompt_start_player(players: Iterable[PlayerState]) -> int:
    players = list(players)
    console.print(Text("Choose the starting player (rule: last on a date or youngest).", style="dim"))
    console.print(Panel.fit(_targets_table(players), title="Starting Player", border_style="magenta"))
    while True:
        choice = _prompt_int("Starting player (number): ")
        if 1 <= choice <= len(players):
            return players[choice - 1].id
        console.print(Text("Invalid choice.", style="red"))


def _wait_for_player(player: PlayerState) -> None:
    input(f"\n{player.name}, press Enter when ready (others look away). ")


def _print_new_events(round_state: RoundState, start_idx: int) -> None:
    for event in round_state.events[start_idx:]:
        style = _event_style(event.kind)
        console.print(Text(render_event(event, round_state.players), style=style))


def _print_scoreboard(players: Iterable[PlayerState]) -> None:
    table = Table(title="Scoreboard", header_style="bold magenta")
    table.add_column("Player", style="cyan")
    table.add_column("Tokens", justify="right")
    for player in players:
        table.add_row(player.name, str(player.tokens))
    console.print(table)
    console.print("")


def _prompt_int(prompt: str) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            return int(raw)
        console.print(Text("Enter a number.", style="red"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Love Letter in the console.")
    parser.add_argument("names", nargs="*", help="Player names")
    return parser.parse_args()


def _event_style(kind: str) -> str:
    return {
        "round_start": "bold magenta",
        "round_end": "bold magenta",
        "token_awarded": "green",
        "eliminated": "bold red",
        "protected": "blue",
        "protection_ended": "blue",
        "swap": "yellow",
        "reveal": "cyan",
        "baron_compare": "cyan",
        "guard_guess": "cyan",
    }.get(kind, "")


def _card_panel(card: CardType, index: int) -> Panel:
    label = card_name(card)
    lines = [
        f"#{index}",
        "",
        label,
        f"Value {card.value}",
    ]
    content = Text("\n".join(lines), justify="center")
    style = CARD_STYLES.get(card, "white")
    return Panel(content, border_style=style, box=box.ASCII)


def _hand_cards(hand: list[CardType]) -> Columns:
    panels = [_card_panel(card, idx) for idx, card in enumerate(hand, start=1)]
    return Columns(panels, equal=True, expand=True)


def _targets_table(targets: list[PlayerState]) -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Player", style="white")
    for idx, target in enumerate(targets, start=1):
        table.add_row(str(idx), target.name)
    return table


def _guess_table(options: list[CardType]) -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Card", style="white")
    table.add_column("Value", justify="right", style="magenta")
    for idx, card in enumerate(options, start=1):
        table.add_row(str(idx), card_name(card), str(card.value))
    return table


if __name__ == "__main__":
    main()
