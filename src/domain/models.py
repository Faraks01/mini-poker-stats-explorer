from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Position(str, Enum):
    UTG = "UTG"
    HJ = "HJ"
    CO = "CO"
    BTN = "BTN"
    SB = "SB"
    BB = "BB"


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "allin"


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class SpotType(str, Enum):
    SRP = "SRP"
    THREE_BET_POT = "3BP"


class PlayerRole(str, Enum):
    PFR = "PFR"
    PFC = "PFC"


class RelativePosition(str, Enum):
    IP = "IP"
    OOP = "OOP"


class Action(BaseModel):
    player: str
    position: Optional[Position] = None
    action_type: ActionType
    amount: Optional[float] = None
    street: Street
    is_all_in: bool = False


class PlayerState(BaseModel):
    name: str
    position: Position
    stack: float
    cards: Optional[str] = None


class Hand(BaseModel):
    hand_id: str
    timestamp: Optional[str] = None
    table_name: Optional[str] = None
    max_players: int = 6
    button_seat: int
    small_blind: float
    big_blind: float
    players: list[PlayerState]
    actions: list[Action]
    board: list[str] = Field(default_factory=list)
    pot: Optional[float] = None


class FilterContext(BaseModel):
    spot: Optional[SpotType] = None
    formation: Optional[str] = None
    position: Optional[RelativePosition] = None
    role: Optional[PlayerRole] = None
    street: Optional[Street] = None
    line_prefix: Optional[str] = None


class StatDefinition(BaseModel):
    id: str
    label: str
    description: str
    metric_family: str = Field(alias="metricFamily")
    spot: Optional[str] = None
    formation: Optional[str] = None
    position: Optional[str] = None
    role: Optional[str] = None
    line: Optional[str] = None
    street: Optional[str] = None
    size_bucket: Optional[str] = Field(default=None, alias="sizeBucket")
    state: str
    binding_mode: str = Field(alias="bindingMode")
    min_sample: int = Field(alias="minSample")
    opportunity: Optional[dict] = None
    success: Optional[dict] = None
    context_filters: Optional[dict] = Field(default=None, alias="contextFilters")
    target_line: Optional[str] = Field(default=None, alias="targetLine")
    target_size_bucket: Optional[str] = Field(default=None, alias="targetSizeBucket")

    class Config:
        populate_by_name = True


class StatResult(BaseModel):
    stat_id: str
    label: str
    numerator: int
    denominator: int
    value: Optional[float] = None
    state: str
    min_sample: int

    @property
    def is_valid(self) -> bool:
        return self.denominator > 0 and self.state == "AVAILABLE"

    @property
    def has_sufficient_sample(self) -> bool:
        return self.denominator >= self.min_sample


class ComparisonResult(BaseModel):
    stat_id: str
    label: str
    population_value: Optional[float] = None
    population_sample: int = 0
    population_numerator: int = 0
    gto_value: Optional[float] = None
    gto_sample: int = 0
    gto_numerator: int = 0
    delta: Optional[float] = None
    state: str
