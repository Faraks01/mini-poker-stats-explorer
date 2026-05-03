from typing import Optional

from src.domain.models import (
    StatDefinition,
    StatResult,
    ComparisonResult,
    FilterContext,
)
from src.application.ports import HandRepository, StatCatalogPort
from src.application.engines import StatsEngine, FilterEngine


class GetStatUseCase:
    def __init__(
        self,
        repository: HandRepository,
        catalog: StatCatalogPort,
        stats_engine: StatsEngine,
        filter_engine: FilterEngine,
    ):
        self.repository = repository
        self.catalog = catalog
        self.stats_engine = stats_engine
        self.filter_engine = filter_engine

    def execute(
        self, stat_id: str, hand_filter: FilterContext
    ) -> Optional[StatResult]:
        stat = self.catalog.get_by_id(stat_id)
        if not stat:
            return None

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

        hands = self.repository.get_all()
        filtered = self.filter_engine.apply(hands, hand_filter)
        return self.stats_engine.calculate(filtered, stat)


class CompareWithGTOUseCase:
    def __init__(
        self,
        population_repo: HandRepository,
        gto_repo: HandRepository,
        catalog: StatCatalogPort,
        stats_engine: StatsEngine,
        filter_engine: FilterEngine,
    ):
        self.population_repo = population_repo
        self.gto_repo = gto_repo
        self.catalog = catalog
        self.stats_engine = stats_engine
        self.filter_engine = filter_engine

    def execute(
        self, stat_id: str, hand_filter: FilterContext
    ) -> Optional[ComparisonResult]:
        stat = self.catalog.get_by_id(stat_id)
        if not stat:
            return None

        if stat.state in ("NO_STAT", "INVALID_CONTEXT"):
            return ComparisonResult(
                stat_id=stat.id,
                label=stat.label,
                state=stat.state,
            )

        pop_hands = self.filter_engine.apply(
            self.population_repo.get_all(), hand_filter
        )
        gto_hands = self.filter_engine.apply(self.gto_repo.get_all(), hand_filter)

        pop_result = self.stats_engine.calculate(pop_hands, stat)
        gto_result = self.stats_engine.calculate(gto_hands, stat)

        delta = None
        if pop_result.value is not None and gto_result.value is not None:
            delta = pop_result.value - gto_result.value

        state = stat.state
        if pop_result.denominator == 0 and gto_result.denominator == 0:
            state = "NO_DATA"
        elif not pop_result.has_sufficient_sample:
            state = "LOW_SAMPLE"

        return ComparisonResult(
            stat_id=stat.id,
            label=stat.label,
            population_value=pop_result.value,
            population_sample=pop_result.denominator,
            population_numerator=pop_result.numerator,
            gto_value=gto_result.value,
            gto_sample=gto_result.denominator,
            gto_numerator=gto_result.numerator,
            delta=delta,
            state=state,
        )


class ListStatsUseCase:
    def __init__(self, catalog: StatCatalogPort):
        self.catalog = catalog

    def execute(
        self,
        available_only: bool = False,
        spot: Optional[str] = None,
        formation: Optional[str] = None,
        position: Optional[str] = None,
        role: Optional[str] = None,
        stat_state: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> tuple[list[StatDefinition], int]:
        if available_only:
            stats = self.catalog.get_available()
        else:
            stats = self.catalog.get_all()

        filtered: list[StatDefinition] = []
        for s in stats:
            if spot and s.spot != spot:
                continue
            if formation and s.formation != formation:
                continue
            if position and s.position != position:
                continue
            if role and s.role != role:
                continue
            if stat_state and s.state != stat_state:
                continue
            filtered.append(s)

        total = len(filtered)
        if limit is not None and limit > 0:
            filtered = filtered[offset : offset + limit]
        elif offset > 0:
            filtered = filtered[offset:]

        return filtered, total
