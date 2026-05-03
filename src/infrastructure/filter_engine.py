"""
Реализация FilterEngine — отбор раздач по критериям контекста.
"""

from typing import Optional

from src.domain.hand_analysis import HandAnalyzer, HandContext, PlayerContext
from src.domain.models import (
    Hand,
    FilterContext,
    StatDefinition,
    SpotType,
    RelativePosition,
    PlayerRole,
    Street,
)
from src.application.engines import FilterEngine, HandStatContextPort


class DefaultFilterEngine(FilterEngine, HandStatContextPort):
    def __init__(self):
        self._analyzer = HandAnalyzer()
        self._context_cache: dict[str, HandContext] = {}

    def analyze_hand(self, hand: Hand) -> HandContext:
        if hand.hand_id not in self._context_cache:
            self._context_cache[hand.hand_id] = self._analyzer.analyze(hand)
        return self._context_cache[hand.hand_id]

    def clear_cache(self) -> None:
        self._context_cache.clear()

    def apply(self, hands: list[Hand], context: FilterContext) -> list[Hand]:
        return [h for h in hands if self.matches(h, context)]

    def matches(self, hand: Hand, context: FilterContext) -> bool:
        ctx = self.analyze_hand(hand)
        return self._matches_context(ctx, context)

    def matches_stat(self, hand: Hand, stat: StatDefinition) -> bool:
        if not stat.context_filters:
            return True

        ctx = self.analyze_hand(hand)
        return self._matches_stat_context(ctx, stat)

    def _matches_context(self, ctx: HandContext, filter_ctx: FilterContext) -> bool:
        if filter_ctx.spot and ctx.spot:
            if filter_ctx.spot.value != ctx.spot.value:
                return False

        if filter_ctx.formation and ctx.formation:
            if filter_ctx.formation != ctx.formation:
                return False

        if filter_ctx.street:
            street_map = {
                "flop": Street.FLOP,
                "turn": Street.TURN,
                "river": Street.RIVER,
            }
            target_street = street_map.get(
                filter_ctx.street.value
                if hasattr(filter_ctx.street, "value")
                else filter_ctx.street
            )
            if target_street and target_street not in ctx.streets_seen:
                return False

        if filter_ctx.role:
            if not any(p.role == filter_ctx.role for p in ctx.players_in_pot):
                return False

        if filter_ctx.position:
            if not any(
                p.relative_position == filter_ctx.position for p in ctx.players_in_pot
            ):
                return False

        if filter_ctx.line_prefix:
            if not any(
                p.line.startswith(filter_ctx.line_prefix) for p in ctx.players_in_pot
            ):
                return False

        return True

    def _matches_stat_context(self, ctx: HandContext, stat: StatDefinition) -> bool:
        cf = stat.context_filters
        if not cf:
            return True

        if cf.get("spot"):
            if not ctx.spot or cf["spot"] != ctx.spot.value:
                return False

        if cf.get("formation"):
            if not ctx.formation or cf["formation"] != ctx.formation:
                return False

        if cf.get("street"):
            street_map = {
                "flop": Street.FLOP,
                "turn": Street.TURN,
                "river": Street.RIVER,
            }
            target_street = street_map.get(cf["street"])
            if target_street and target_street not in ctx.streets_seen:
                return False

        return True

    def find_target_player(
        self, ctx: HandContext, stat: StatDefinition
    ) -> Optional[PlayerContext]:
        cf = stat.context_filters
        if not cf:
            return ctx.players_in_pot[0] if ctx.players_in_pot else None

        position = cf.get("position")
        role = cf.get("role")

        for p in ctx.players_in_pot:
            pos_match = (not position) or (
                p.relative_position and p.relative_position.value == position
            )
            role_match = (not role) or (p.role and p.role.value == role)
            if pos_match and role_match:
                return p

        return None
