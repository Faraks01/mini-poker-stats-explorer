"""
Маршруты REST API обозревателя покерной статистики.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.application.use_cases import (
    GetStatUseCase,
    CompareWithGTOUseCase,
    ListStatsUseCase,
)
from src.infrastructure.data_loader import DataLoader, LoadingState
from src.infrastructure.hand_sync import sync_repository_from_loader
from src.api.dependencies import (
    get_catalog,
    get_stats_engine,
    get_filter_engine,
    get_loader,
    get_hand_repository,
    GTO_SOURCE,
    POPULATION_SOURCE,
)
from src.api.context_params import parse_filter_context


router = APIRouter()


class DataStatusResponse(BaseModel):
    sources: dict[str, dict]


class StatListResponse(BaseModel):
    stats: list[dict]
    total: int
    offset: int
    limit: Optional[int] = None


class StatResultResponse(BaseModel):
    stat_id: str
    label: str
    numerator: int
    denominator: int
    value: Optional[float]
    value_percent: Optional[str]
    state: str
    min_sample: int
    source: str


class CompareResponse(BaseModel):
    stat_id: str
    label: str
    population_value: Optional[float]
    population_value_percent: Optional[str]
    population_sample: int
    population_numerator: int
    gto_value: Optional[float]
    gto_value_percent: Optional[str]
    gto_sample: int
    gto_numerator: int
    delta: Optional[float]
    delta_percent: Optional[str]
    state: str


@router.get("/data/status", response_model=DataStatusResponse)
def get_data_status(loader: DataLoader = Depends(get_loader)):
    """Статус загрузки всех источников данных."""
    return DataStatusResponse(sources=loader.get_all_sources_status())


@router.post("/data/load/{source}")
def start_loading(source: str, loader: DataLoader = Depends(get_loader)):
    """Запуск фоновой загрузки источника данных."""
    if source not in (GTO_SOURCE, POPULATION_SOURCE):
        raise HTTPException(404, f"Неизвестный источник: {source}")

    state = loader.get_state(source)
    if state == LoadingState.LOADED:
        return {"message": "Уже загружено", "state": state.value}

    if state == LoadingState.LOADING:
        progress = loader.get_progress(source)
        return {
            "message": "Загрузка выполняется",
            "state": state.value,
            "progress": f"{progress[0]}/{progress[1]}",
        }

    loader.start_loading(source)
    return {"message": "Загрузка запущена", "state": "loading"}


@router.get("/stats", response_model=StatListResponse)
def list_stats(
    available_only: bool = Query(False, description="Только доступные статы"),
    spot: Optional[str] = Query(None),
    formation: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    state: Optional[str] = Query(None, description="Фильтр по stat.state каталога"),
    offset: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    catalog=Depends(get_catalog),
):
    """Список статистик из каталога с фильтрами и пагинацией."""
    use_case = ListStatsUseCase(catalog)
    stats, total = use_case.execute(
        available_only=available_only,
        spot=spot,
        formation=formation,
        position=position,
        role=role,
        stat_state=state,
        offset=offset,
        limit=limit,
    )

    return StatListResponse(
        stats=[
            {
                "id": s.id,
                "label": s.label,
                "description": s.description,
                "metric_family": s.metric_family,
                "spot": s.spot,
                "formation": s.formation,
                "position": s.position,
                "role": s.role,
                "street": s.street,
                "state": s.state,
            }
            for s in stats
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/stats/{stat_id}", response_model=StatResultResponse)
def get_stat(
    stat_id: str,
    source: str = Query("gto", description="Источник данных: gto или population"),
    loader: DataLoader = Depends(get_loader),
    catalog=Depends(get_catalog),
    stats_engine=Depends(get_stats_engine),
    filter_engine=Depends(get_filter_engine),
    hf_spot: Optional[str] = Query(None, alias="hf_spot", description="Фильтр рук: спот"),
    hf_formation: Optional[str] = Query(None, alias="hf_formation"),
    hf_position: Optional[str] = Query(None, alias="hf_position"),
    hf_role: Optional[str] = Query(None, alias="hf_role"),
    hf_street: Optional[str] = Query(None, alias="hf_street"),
    hf_line_prefix: Optional[str] = Query(None, alias="hf_line_prefix"),
):
    """Расчёт конкретной статистики."""
    if source not in (GTO_SOURCE, POPULATION_SOURCE):
        raise HTTPException(400, f"Некорректный источник: {source}")

    stat = catalog.get_by_id(stat_id)
    if not stat:
        raise HTTPException(404, f"Статистика не найдена: {stat_id}")

    hands = loader.get_hands(source)
    if not hands:
        st = loader.get_state(source)
        if st == LoadingState.LOADING:
            raise HTTPException(202, "Данные ещё загружаются")
        raise HTTPException(404, f"Нет данных для источника: {source}")

    repo = get_hand_repository(source)
    sync_repository_from_loader(loader, source, repo)

    hand_filter = parse_filter_context(
        spot=hf_spot,
        formation=hf_formation,
        position=hf_position,
        role=hf_role,
        street=hf_street,
        line_prefix=hf_line_prefix,
    )

    use_case = GetStatUseCase(repo, catalog, stats_engine, filter_engine)
    result = use_case.execute(stat_id, hand_filter)
    if not result:
        raise HTTPException(404, f"Статистика не найдена: {stat_id}")

    return StatResultResponse(
        stat_id=result.stat_id,
        label=result.label,
        numerator=result.numerator,
        denominator=result.denominator,
        value=result.value,
        value_percent=f"{result.value:.2%}" if result.value is not None else None,
        state=result.state,
        min_sample=result.min_sample,
        source=source,
    )


@router.get("/compare/{stat_id}", response_model=CompareResponse)
def compare_stat(
    stat_id: str,
    loader: DataLoader = Depends(get_loader),
    catalog=Depends(get_catalog),
    stats_engine=Depends(get_stats_engine),
    filter_engine=Depends(get_filter_engine),
    hf_spot: Optional[str] = Query(None, alias="hf_spot"),
    hf_formation: Optional[str] = Query(None, alias="hf_formation"),
    hf_position: Optional[str] = Query(None, alias="hf_position"),
    hf_role: Optional[str] = Query(None, alias="hf_role"),
    hf_street: Optional[str] = Query(None, alias="hf_street"),
    hf_line_prefix: Optional[str] = Query(None, alias="hf_line_prefix"),
):
    """Сравнение популяции с GTO для статистики."""
    stat = catalog.get_by_id(stat_id)
    if not stat:
        raise HTTPException(404, f"Статистика не найдена: {stat_id}")

    pop_hands = loader.get_hands(POPULATION_SOURCE)
    gto_hands = loader.get_hands(GTO_SOURCE)
    if not pop_hands and not gto_hands:
        st_pop = loader.get_state(POPULATION_SOURCE)
        st_gto = loader.get_state(GTO_SOURCE)
        if st_pop == LoadingState.LOADING or st_gto == LoadingState.LOADING:
            raise HTTPException(202, "Данные ещё загружаются")
        raise HTTPException(404, "Нет загруженных данных для сравнения")

    pop_repo = get_hand_repository(POPULATION_SOURCE)
    gto_repo = get_hand_repository(GTO_SOURCE)
    sync_repository_from_loader(loader, POPULATION_SOURCE, pop_repo)
    sync_repository_from_loader(loader, GTO_SOURCE, gto_repo)

    hand_filter = parse_filter_context(
        spot=hf_spot,
        formation=hf_formation,
        position=hf_position,
        role=hf_role,
        street=hf_street,
        line_prefix=hf_line_prefix,
    )

    use_case = CompareWithGTOUseCase(
        pop_repo, gto_repo, catalog, stats_engine, filter_engine
    )
    cmp_res = use_case.execute(stat_id, hand_filter)
    if not cmp_res:
        raise HTTPException(404, f"Статистика не найдена: {stat_id}")

    return CompareResponse(
        stat_id=cmp_res.stat_id,
        label=cmp_res.label,
        population_value=cmp_res.population_value,
        population_value_percent=(
            f"{cmp_res.population_value:.2%}"
            if cmp_res.population_value is not None
            else None
        ),
        population_sample=cmp_res.population_sample,
        population_numerator=cmp_res.population_numerator,
        gto_value=cmp_res.gto_value,
        gto_value_percent=(
            f"{cmp_res.gto_value:.2%}" if cmp_res.gto_value is not None else None
        ),
        gto_sample=cmp_res.gto_sample,
        gto_numerator=cmp_res.gto_numerator,
        delta=cmp_res.delta,
        delta_percent=f"{cmp_res.delta:+.2%}" if cmp_res.delta is not None else None,
        state=cmp_res.state,
    )


@router.get("/hands/sample")
def get_sample_hands(
    source: str = Query("gto"),
    limit: int = Query(5, ge=1, le=50),
    loader: DataLoader = Depends(get_loader),
):
    """Пример раздач для отладки."""
    hands = loader.get_hands_if_loaded(source)
    if not hands:
        return {"hands": [], "message": "Данные ещё не загружены"}

    sample = hands[:limit]
    return {
        "hands": [
            {
                "hand_id": h.hand_id,
                "players": len(h.players),
                "actions": len(h.actions),
                "board": h.board,
            }
            for h in sample
        ],
        "total_available": len(hands),
    }
