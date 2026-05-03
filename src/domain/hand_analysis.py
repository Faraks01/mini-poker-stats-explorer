"""
Разбор раздач для извлечения контекста:
- тип спота (SRP / 3BP)
- формация (BB_SB, BB_BTN и т.д.)
- роли игроков (PFR / PFC)
- относительные позиции (IP / OOP)
- линии действий (B, X, B-B-B, X-X-B и т.д.)
"""

from dataclasses import dataclass, field
from typing import Optional

from src.domain.models import (
    Hand,
    Action,
    Position,
    ActionType,
    Street,
    SpotType,
    PlayerRole,
    RelativePosition,
)


POSITION_ORDER = [
    Position.SB,
    Position.BB,
    Position.UTG,
    Position.HJ,
    Position.CO,
    Position.BTN,
]


@dataclass
class PlayerContext:
    name: str
    position: Position
    role: Optional[PlayerRole] = None
    relative_position: Optional[RelativePosition] = None
    line: str = ""
    actions_by_street: dict[Street, list[ActionType]] = field(default_factory=dict)


@dataclass
class HandContext:
    hand_id: str
    spot: Optional[SpotType] = None
    formation: Optional[str] = None
    players_in_pot: list[PlayerContext] = field(default_factory=list)
    streets_seen: list[Street] = field(default_factory=list)
    board: list[str] = field(default_factory=list)


class HandAnalyzer:
    def analyze(self, hand: Hand) -> HandContext:
        ctx = HandContext(hand_id=hand.hand_id, board=hand.board)

        preflop_actions = [a for a in hand.actions if a.street == Street.PREFLOP]

        ctx.spot = self._determine_spot(preflop_actions)
        players_in_pot = self._find_players_in_pot(hand, preflop_actions)
        ctx.players_in_pot = players_in_pot

        if len(players_in_pot) == 2:
            ctx.formation = self._determine_formation(players_in_pot)
            self._assign_roles(players_in_pot, preflop_actions)
            self._assign_relative_positions(players_in_pot)

        self._build_lines(players_in_pot, hand.actions)
        ctx.streets_seen = self._get_streets_seen(hand.actions)

        return ctx

    def _determine_spot(self, preflop_actions: list[Action]) -> SpotType:
        raise_count = sum(
            1 for a in preflop_actions if a.action_type == ActionType.RAISE
        )
        return SpotType.THREE_BET_POT if raise_count >= 2 else SpotType.SRP

    def _find_players_in_pot(
        self, hand: Hand, preflop_actions: list[Action]
    ) -> list[PlayerContext]:
        folded = set()
        acted = set()

        for action in preflop_actions:
            if action.action_type == ActionType.FOLD:
                folded.add(action.player)
            else:
                acted.add(action.player)

        player_map = {p.name: p for p in hand.players}
        in_pot = []

        for name in acted:
            if name not in folded and name in player_map:
                p = player_map[name]
                in_pot.append(
                    PlayerContext(
                        name=name,
                        position=p.position,
                        actions_by_street={},
                    )
                )

        in_pot.sort(
            key=lambda x: POSITION_ORDER.index(x.position)
            if x.position in POSITION_ORDER
            else 99
        )
        return in_pot

    def _determine_formation(self, players: list[PlayerContext]) -> str:
        if len(players) != 2:
            return "MULTIWAY"

        positions = sorted(
            [p.position for p in players],
            key=lambda x: POSITION_ORDER.index(x) if x in POSITION_ORDER else 99,
        )
        return f"{positions[0].value}_{positions[1].value}"

    def _assign_roles(
        self, players: list[PlayerContext], preflop_actions: list[Action]
    ) -> None:
        last_raiser = None
        for action in preflop_actions:
            if action.action_type == ActionType.RAISE:
                last_raiser = action.player

        player_names = {p.name for p in players}
        for p in players:
            if p.name == last_raiser:
                p.role = PlayerRole.PFR
            elif last_raiser in player_names:
                p.role = PlayerRole.PFC

    def _assign_relative_positions(self, players: list[PlayerContext]) -> None:
        if len(players) != 2:
            return

        idx0 = (
            POSITION_ORDER.index(players[0].position)
            if players[0].position in POSITION_ORDER
            else 99
        )
        idx1 = (
            POSITION_ORDER.index(players[1].position)
            if players[1].position in POSITION_ORDER
            else 99
        )

        if idx0 < idx1:
            players[0].relative_position = RelativePosition.OOP
            players[1].relative_position = RelativePosition.IP
        else:
            players[0].relative_position = RelativePosition.IP
            players[1].relative_position = RelativePosition.OOP

    def _build_lines(
        self, players: list[PlayerContext], all_actions: list[Action]
    ) -> None:
        player_names = {p.name for p in players}
        player_map = {p.name: p for p in players}

        for p in players:
            p.actions_by_street = {
                Street.FLOP: [],
                Street.TURN: [],
                Street.RIVER: [],
            }

        postflop_actions = [a for a in all_actions if a.street != Street.PREFLOP]

        for action in postflop_actions:
            if action.player in player_names:
                p = player_map[action.player]
                if action.street in p.actions_by_street:
                    p.actions_by_street[action.street].append(action.action_type)

        for p in players:
            p.line = self._encode_line(p.actions_by_street)

    def _encode_line(self, actions_by_street: dict[Street, list[ActionType]]) -> str:
        parts = []
        for street in [Street.FLOP, Street.TURN, Street.RIVER]:
            actions = actions_by_street.get(street, [])
            if not actions:
                break
            parts.append(self._encode_street_actions(actions))
        return "-".join(parts) if parts else ""

    def _encode_street_actions(self, actions: list[ActionType]) -> str:
        if not actions:
            return ""

        codes = []
        for a in actions:
            if a == ActionType.BET:
                codes.append("B")
            elif a == ActionType.RAISE:
                codes.append("R")
            elif a == ActionType.CHECK:
                codes.append("X")
            elif a == ActionType.CALL:
                codes.append("C")
            elif a == ActionType.FOLD:
                codes.append("F")

        return "".join(codes)

    def _get_streets_seen(self, actions: list[Action]) -> list[Street]:
        streets = []
        seen = set()
        for a in actions:
            if a.street not in seen:
                seen.add(a.street)
                streets.append(a.street)
        return streets

    def get_player_context(
        self, ctx: HandContext, position: RelativePosition
    ) -> Optional[PlayerContext]:
        for p in ctx.players_in_pot:
            if p.relative_position == position:
                return p
        return None

    def get_player_by_role(
        self, ctx: HandContext, role: PlayerRole
    ) -> Optional[PlayerContext]:
        for p in ctx.players_in_pot:
            if p.role == role:
                return p
        return None
