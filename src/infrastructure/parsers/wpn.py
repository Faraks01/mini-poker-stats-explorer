import re
from typing import Optional

from src.domain.models import (
    Hand, PlayerState, Action, Position, ActionType, Street
)
from src.infrastructure.parsers.base import BaseHandHistoryParser


class WPNParser(BaseHandHistoryParser):
    """Парсер историй раздач WPN (Winning Poker Network), данные популяции."""

    HAND_PATTERN = re.compile(
        r"Hand #(\d+)\s*-\s*Holdem\(No Limit\)\s*-\s*\$?([\d.]+)/\$?([\d.]+)"
        r"\s*-\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
    )
    TABLE_PATTERN = re.compile(
        r"^(.+?)\s+(\d+)-max\s+Seat #(\d+) is the button",
        re.MULTILINE
    )
    SEAT_PATTERN = re.compile(
        r"Seat (\d+): ([^\(]+) \(\$?([\d.,]+)\)"
    )
    BLIND_PATTERN = re.compile(
        r"^([^\s]+) posts (?:the )?(small blind|big blind|ante) \$?([\d.,]+)",
        re.MULTILINE
    )
    ACTION_PATTERN = re.compile(
        r"^([^\s]+) (folds|checks|calls|bets|raises)(?: \$?([\d.,]+))?"
        r"(?: to \$?([\d.,]+))?( and is all-in)?",
        re.MULTILINE
    )
    BOARD_PATTERN = re.compile(
        r"\*\*\* (FLOP|TURN|RIVER) \*\*\*\s*\[([^\]]+)\](?: \[([^\]]+)\])?"
    )
    SHOWS_PATTERN = re.compile(
        r"^([^\s]+) shows \[([^\]]+)\]",
        re.MULTILINE
    )

    def can_parse(self, content: str) -> bool:
        return "Hand #" in content and "Holdem(No Limit)" in content

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
        parts = re.split(r"(?=Hand #\d+\s*-\s*Holdem)", content)
        return [p.strip() for p in parts if p.strip() and "Hand #" in p]

    def _parse_single(self, raw: str) -> Optional[Hand]:
        header = self.HAND_PATTERN.search(raw)
        if not header:
            return None

        hand_id = header.group(1)
        sb = self._parse_amount(header.group(2))
        bb = self._parse_amount(header.group(3))
        timestamp = header.group(4)

        table_match = self.TABLE_PATTERN.search(raw)
        if not table_match:
            return None

        table_name = table_match.group(1).strip()
        max_players = int(table_match.group(2))
        button_seat = int(table_match.group(3))

        players, seat_map = self._parse_players(raw)
        self._assign_positions(players, seat_map, button_seat, max_players)
        self._parse_shown_cards(raw, players)

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

    def _parse_amount(self, amount_str: str) -> float:
        return float(amount_str.replace(",", ""))

    def _parse_players(self, raw: str) -> tuple[list[PlayerState], dict[str, int]]:
        players = []
        seat_map = {}

        for match in self.SEAT_PATTERN.finditer(raw):
            seat = int(match.group(1))
            name = match.group(2).strip()
            stack = self._parse_amount(match.group(3))

            players.append(PlayerState(
                name=name,
                position=Position.UTG,
                stack=stack,
            ))
            seat_map[name] = seat

        return players, seat_map

    def _assign_positions(
        self,
        players: list[PlayerState],
        seat_map: dict[str, int],
        button_seat: int,
        max_players: int,
    ) -> None:
        n = len(players)
        if n == 0:
            return

        seats = sorted([(seat_map[p.name], p) for p in players], key=lambda x: x[0])

        btn_idx = 0
        for i, (seat, _) in enumerate(seats):
            if seat == button_seat:
                btn_idx = i
                break

        if n == 2:
            positions = [Position.SB, Position.BB]
            seats[btn_idx][1].position = Position.SB
            seats[(btn_idx + 1) % n][1].position = Position.BB
        else:
            position_order = self._get_position_order(n)
            for i in range(n):
                idx = (btn_idx + 1 + i) % n
                seats[idx][1].position = position_order[i]

    def _get_position_order(self, n: int) -> list[Position]:
        if n == 2:
            return [Position.SB, Position.BB]
        elif n == 3:
            return [Position.SB, Position.BB, Position.BTN]
        elif n == 4:
            return [Position.SB, Position.BB, Position.CO, Position.BTN]
        elif n == 5:
            return [Position.SB, Position.BB, Position.HJ, Position.CO, Position.BTN]
        elif n == 6:
            return [Position.SB, Position.BB, Position.UTG, Position.HJ, Position.CO, Position.BTN]
        elif n >= 7:
            base = [Position.SB, Position.BB, Position.UTG, Position.UTG, Position.HJ, Position.CO, Position.BTN]
            return base[:n]
        return [Position.UTG] * n

    def _parse_shown_cards(self, raw: str, players: list[PlayerState]) -> None:
        player_map = {p.name: p for p in players}
        for match in self.SHOWS_PATTERN.finditer(raw):
            name = match.group(1)
            cards = match.group(2)
            if name in player_map:
                player_map[name].cards = cards

    def _parse_actions(self, raw: str, players: list[PlayerState]) -> list[Action]:
        actions = []
        player_map = {p.name: p for p in players}
        player_names = set(p.name for p in players)

        current_street = Street.PREFLOP
        lines = raw.split("\n")

        in_action_section = False

        for line in lines:
            line = line.strip()

            if "*** HOLE CARDS ***" in line:
                in_action_section = True
                continue
            elif "*** FLOP ***" in line:
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

            if not in_action_section:
                if " posts " in line:
                    blind_match = self.BLIND_PATTERN.match(line)
                    if blind_match:
                        name = blind_match.group(1)
                        blind_type = blind_match.group(2)
                        amount = self._parse_amount(blind_match.group(3))

                        if name in player_names:
                            action_type = ActionType.BET
                            actions.append(Action(
                                player=name,
                                position=player_map[name].position,
                                action_type=action_type,
                                amount=amount,
                                street=Street.PREFLOP,
                                is_all_in=False,
                            ))
                continue

            match = self.ACTION_PATTERN.match(line)
            if match:
                name = match.group(1)
                if name not in player_names:
                    continue

                action_str = match.group(2)
                amount = self._parse_amount(match.group(3)) if match.group(3) else None
                to_amount = self._parse_amount(match.group(4)) if match.group(4) else None
                is_allin = bool(match.group(5))

                if to_amount:
                    amount = to_amount

                action_type = self._map_action(action_str)
                position = player_map[name].position

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
