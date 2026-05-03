"""
Реализация StatsEngine — расчёт статистик по данным раздач.
"""

from typing import Optional

from src.domain.hand_analysis import HandContext, PlayerContext
from src.domain.models import (
    Hand,
    StatDefinition,
    StatResult,
    ActionType,
    Street,
)
from src.application.engines import StatsEngine, HandStatContextPort


class DefaultStatsEngine(StatsEngine):
    def __init__(self, hand_context: HandStatContextPort):
        self._ctx = hand_context

    def calculate(self, hands: list[Hand], stat: StatDefinition) -> StatResult:
        if stat.state in ("NO_STAT", "INVALID_CONTEXT"):
            return StatResult(
                stat_id=stat.id,
                label=stat.label,
                numerator=0,
                denominator=0,
                value=None,
                state=stat.state,
                min_sample=stat.min_sample,
            )

        denominator, numerator = self._opportunity_and_success_counts(hands, stat)

        value = None
        state = stat.state

        if denominator > 0:
            value = numerator / denominator
        else:
            state = "NO_DATA"

        if denominator < stat.min_sample and state == "AVAILABLE":
            state = "LOW_SAMPLE"

        return StatResult(
            stat_id=stat.id,
            label=stat.label,
            numerator=numerator,
            denominator=denominator,
            value=value,
            state=state,
            min_sample=stat.min_sample,
        )

    def calculate_opportunity(self, hands: list[Hand], stat: StatDefinition) -> int:
        d, _ = self._opportunity_and_success_counts(hands, stat)
        return d

    def calculate_success(self, hands: list[Hand], stat: StatDefinition) -> int:
        _, n = self._opportunity_and_success_counts(hands, stat)
        return n

    def _opportunity_and_success_counts(
        self, hands: list[Hand], stat: StatDefinition
    ) -> tuple[int, int]:
        if not stat.opportunity:
            return 0, 0

        has_success = bool(stat.success)
        denom = 0
        num = 0

        for hand in hands:
            if not self._ctx.matches_stat(hand, stat):
                continue
            ctx = self._ctx.analyze_hand(hand)
            player = self._ctx.find_target_player(ctx, stat)
            if not player or not self._matches_opportunity(ctx, player, stat):
                continue
            denom += 1
            if has_success and self._matches_success(ctx, player, stat):
                num += 1

        return denom, num

    def _matches_opportunity(
        self, ctx: HandContext, player: PlayerContext, stat: StatDefinition
    ) -> bool:
        opp = stat.opportunity
        if not opp:
            return True

        opp_street = opp.get("street")
        if opp_street:
            street_map = {
                "flop": Street.FLOP,
                "turn": Street.TURN,
                "river": Street.RIVER,
            }
            target = street_map.get(opp_street)
            if target and target not in ctx.streets_seen:
                return False

        if opp.get("canAct"):
            if not self._player_can_act(ctx, player, opp_street):
                return False

        line_prefix = opp.get("linePrefix")
        if line_prefix:
            if not player.line.startswith(line_prefix):
                return False

        # facingAction в каталоге пока не поддерживается (игнорируется).

        return True

    def _matches_success(
        self, ctx: HandContext, player: PlayerContext, stat: StatDefinition
    ) -> bool:
        success = stat.success
        if not success:
            return True

        action = success.get("action")
        street = success.get("street")
        target_line = success.get("line")

        if target_line:
            if player.line != target_line and not player.line.startswith(target_line):
                actual_prefix = (
                    player.line[: len(target_line)]
                    if len(player.line) >= len(target_line)
                    else player.line
                )
                if actual_prefix != target_line:
                    return False

        if action and street:
            street_map = {
                "flop": Street.FLOP,
                "turn": Street.TURN,
                "river": Street.RIVER,
            }
            target_street = street_map.get(street)
            if target_street:
                actions = player.actions_by_street.get(target_street, [])
                action_map = {
                    "bet": ActionType.BET,
                    "check": ActionType.CHECK,
                    "call": ActionType.CALL,
                    "raise": ActionType.RAISE,
                    "fold": ActionType.FOLD,
                }
                target_action = action_map.get(action)
                if target_action and target_action not in actions:
                    return False
        elif action and not street:
            action_map = {
                "bet": ActionType.BET,
                "check": ActionType.CHECK,
                "call": ActionType.CALL,
                "raise": ActionType.RAISE,
                "fold": ActionType.FOLD,
            }
            target_action = action_map.get(action)
            if target_action:
                all_actions = []
                for acts in player.actions_by_street.values():
                    all_actions.extend(acts)
                if target_action not in all_actions:
                    return False

        return True

    def _player_can_act(
        self, ctx: HandContext, player: PlayerContext, street: Optional[str]
    ) -> bool:
        if not street:
            return True

        street_map = {
            "flop": Street.FLOP,
            "turn": Street.TURN,
            "river": Street.RIVER,
        }
        target = street_map.get(street)
        if not target:
            return True

        return target in ctx.streets_seen
