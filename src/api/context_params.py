"""
Сборка FilterContext из опциональных строк (query-параметры API/UI).
"""

from typing import Optional

from src.domain.models import (
    FilterContext,
    SpotType,
    RelativePosition,
    PlayerRole,
    Street,
)


def parse_filter_context(
    spot: Optional[str] = None,
    formation: Optional[str] = None,
    position: Optional[str] = None,
    role: Optional[str] = None,
    street: Optional[str] = None,
    line_prefix: Optional[str] = None,
) -> FilterContext:
    st: Optional[SpotType] = None
    if spot:
        for e in SpotType:
            if e.value == spot:
                st = e
                break

    rel: Optional[RelativePosition] = None
    if position:
        for e in RelativePosition:
            if e.value == position:
                rel = e
                break

    rl: Optional[PlayerRole] = None
    if role:
        for e in PlayerRole:
            if e.value == role:
                rl = e
                break

    strt: Optional[Street] = None
    if street:
        key = street.lower()
        street_map = {
            "preflop": Street.PREFLOP,
            "flop": Street.FLOP,
            "turn": Street.TURN,
            "river": Street.RIVER,
        }
        strt = street_map.get(key)

    return FilterContext(
        spot=st,
        formation=formation or None,
        position=rel,
        role=rl,
        street=strt,
        line_prefix=line_prefix or None,
    )
