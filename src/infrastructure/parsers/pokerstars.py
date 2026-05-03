import re
from typing import Optional

from src.domain.models import (
    Hand, PlayerState, Action, Position, ActionType, Street
)
from src.infrastructure.parsers.base import BaseHandHistoryParser


class PokerStarsParser(BaseHandHistoryParser):
    """Парсер историй в стиле PokerStars (данные GTO-ботов)."""

    HAND_PATTERN = re.compile(
        r"PokerStars Game #(\d+):\s+Hold'em No Limit \(\$?([\d.]+)/\$?([\d.]+)\)"
        r"\s*-\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
    )
    TABLE_PATTERN = re.compile(
        r"Table '([^']+)'\s+(\d+)-max\s+Seat #(\d+) is the button"
    )
    SEAT_PATTERN = re.compile(
        r"Seat (\d+): (\w+) \(\$?([\d.]+) in chips\)"
    )
    DEALT_PATTERN = re.compile(
        r"Dealt to (\w+) \[([^\]]+)\]"
    )
    ACTION_PATTERN = re.compile(
        r"^(\w+): (folds|checks|calls|bets|raises)(?: \$?([\d.]+))?(?: to \$?([\d.]+))?"
        r"( and is all-in)?",
        re.MULTILINE
    )
    BOARD_PATTERN = re.compile(
        r"\*\*\* (FLOP|TURN|RIVER) \*\*\* \[([^\]]+)\](?: \[([^\]]+)\])?"
    )
    UNCALLED_PATTERN = re.compile(
        r"Uncalled bet \(\$?([\d.]+)\) returned to (\w+)"
    )
    COLLECTED_PATTERN = re.compile(
        r"(\w+) collected \$?([\d.]+) from pot"
    )

    POSITION_MAP = {
        "UTG": Position.UTG,
        "HJ": Position.HJ,
        "CO": Position.CO,
        "BU": Position.BTN,
        "BTN": Position.BTN,
        "SB": Position.SB,
        "BB": Position.BB,
    }

    def can_parse(self, content: str) -> bool:
        return "PokerStars Game #" in content

    def parse(self, content: str) -> list[Hand]:
        hands = []
        raw_hands = self._split_hands(content)

        for raw in raw_hands:
            try:
                hand = self._parse_single(raw)
                if hand:
                    hands.append(hand)
            except Exception:
                continue

        return hands

    def _split_hands(self, content: str) -> list[str]:
        parts = re.split(r"(?=PokerStars Game #)", content)
        return [p.strip() for p in parts if p.strip() and "PokerStars Game #" in p]

    def _parse_single(self, raw: str) -> Optional[Hand]:
        header = self.HAND_PATTERN.search(raw)
        if not header:
            return None

        hand_id = header.group(1)
        sb = float(header.group(2))
        bb = float(header.group(3))
        timestamp = header.group(4)

        table_match = self.TABLE_PATTERN.search(raw)
        if not table_match:
            return None

        table_name = table_match.group(1)
        max_players = int(table_match.group(2))
        button_seat = int(table_match.group(3))

        players = self._parse_players(raw)
        self._assign_positions(players, button_seat, max_players)
        self._parse_hole_cards(raw, players)

        actions = self._parse_actions(raw, players)
        board = self._parse_board(raw)

        return Hand(
            hand_id=hand_id,
            timestamp=timestamp,
            table_name=table_name,
            max_players=max_players,
            button_seat=button_seat,
            small_blind=sb,
            big_blind=bb,
            players=players,
            actions=actions,
            board=board,
        )

    def _parse_players(self, raw: str) -> list[PlayerState]:
        players = []
        for match in self.SEAT_PATTERN.finditer(raw):
            seat = int(match.group(1))
            name = match.group(2)
            stack = float(match.group(3))

            position = self.POSITION_MAP.get(name, None)

            players.append(PlayerState(
                name=name,
                position=position or Position.UTG,
                stack=stack,
            ))
        return players

    def _names_are_positions(self, players: list[PlayerState]) -> bool:
        return all(p.name in self.POSITION_MAP for p in players)

    def _assign_positions(
        self, players: list[PlayerState], button_seat: int, max_players: int
    ) -> None:
        if self._names_are_positions(players):
            return

        n = len(players)
        if n == 0:
            return

        if n == 2:
            positions = [Position.SB, Position.BB]
        elif n == 3:
            positions = [Position.BTN, Position.SB, Position.BB]
        elif n == 4:
            positions = [Position.CO, Position.BTN, Position.SB, Position.BB]
        elif n == 5:
            positions = [Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB]
        else:
            positions = [Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB]

        btn_idx = (button_seat - 1) % n
        for i, player in enumerate(players):
            pos_idx = (i - btn_idx - 1) % n
            if pos_idx < len(positions):
                player.position = positions[-(pos_idx + 1)]

    def _parse_hole_cards(self, raw: str, players: list[PlayerState]) -> None:
        player_map = {p.name: p for p in players}
        for match in self.DEALT_PATTERN.finditer(raw):
            name = match.group(1)
            cards = match.group(2)
            if name in player_map:
                player_map[name].cards = cards

    def _parse_actions(self, raw: str, players: list[PlayerState]) -> list[Action]:
        actions = []
        player_map = {p.name: p for p in players}

        current_street = Street.PREFLOP
        lines = raw.split("\n")

        for line in lines:
            line = line.strip()

            if "*** FLOP ***" in line:
                current_street = Street.FLOP
                continue
            elif "*** TURN ***" in line:
                current_street = Street.TURN
                continue
            elif "*** RIVER ***" in line:
                current_street = Street.RIVER
                continue
            elif "*** SUMMARY ***" in line:
                break

            match = self.ACTION_PATTERN.match(line)
            if match:
                name = match.group(1)
                action_str = match.group(2)
                amount = float(match.group(3)) if match.group(3) else None
                to_amount = float(match.group(4)) if match.group(4) else None
                is_allin = bool(match.group(5))

                if to_amount:
                    amount = to_amount

                action_type = self._map_action(action_str)
                position = player_map.get(name, PlayerState(name=name, position=Position.UTG, stack=0)).position

                actions.append(Action(
                    player=name,
                    position=position,
                    action_type=action_type,
                    amount=amount,
                    street=current_street,
                    is_all_in=is_allin,
                ))

        return actions

    def _map_action(self, action_str: str) -> ActionType:
        mapping = {
            "folds": ActionType.FOLD,
            "checks": ActionType.CHECK,
            "calls": ActionType.CALL,
            "bets": ActionType.BET,
            "raises": ActionType.RAISE,
        }
        return mapping.get(action_str, ActionType.FOLD)

    def _parse_board(self, raw: str) -> list[str]:
        cards = []
        for match in self.BOARD_PATTERN.finditer(raw):
            board_cards = match.group(2).split()
            cards.extend(board_cards)
            if match.group(3):
                cards.extend(match.group(3).split())
        return cards
