"""
Маршруты UI: шаблоны Jinja2 и HTMX.
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from src.infrastructure.data_loader import DataLoader, LoadingState
from src.infrastructure.hand_sync import sync_repository_from_loader
from src.application.use_cases import ListStatsUseCase, CompareWithGTOUseCase
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

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница дашборда."""
    return templates.TemplateResponse(request, "index.html")


@router.get("/status", response_class=HTMLResponse)
async def get_status(request: Request, loader: DataLoader = Depends(get_loader)):
    """Фрагмент строки состояния для HTMX."""
    status = loader.get_all_sources_status()
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {
            "gto": status.get(
                "gto",
                {
                    "state": "not_started",
                    "hands_count": 0,
                    "files_loaded": 0,
                    "files_total": 0,
                },
            ),
            "pop": status.get(
                "population",
                {
                    "state": "not_started",
                    "hands_count": 0,
                    "files_loaded": 0,
                    "files_total": 0,
                },
            ),
        },
    )


@router.post("/load-population", response_class=HTMLResponse)
async def load_population(loader: DataLoader = Depends(get_loader)):
    """Запуск фоновой загрузки данных популяции."""
    loader.start_loading(POPULATION_SOURCE)
    return ""


@router.get("/stats-table", response_class=HTMLResponse)
async def stats_table(
    request: Request,
    spot: Optional[str] = Query(None),
    formation: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    hand_street: Optional[str] = Query(None),
    hand_line_prefix: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=200),
    loader: DataLoader = Depends(get_loader),
    catalog=Depends(get_catalog),
    stats_engine=Depends(get_stats_engine),
    filter_engine=Depends(get_filter_engine),
):
    """Фрагмент таблицы статистик для HTMX."""
    list_uc = ListStatsUseCase(catalog)
    filtered, total = list_uc.execute(
        available_only=False,
        spot=spot,
        formation=formation,
        position=position,
        role=role,
        stat_state=state,
        offset=offset,
        limit=limit,
    )

    hand_filter = parse_filter_context(
        spot=spot,
        formation=formation,
        position=position,
        role=role,
        street=hand_street,
        line_prefix=hand_line_prefix,
    )

    gto_hands = loader.get_hands_if_loaded(GTO_SOURCE)
    pop_hands = loader.get_hands_if_loaded(POPULATION_SOURCE)

    gto_repo = get_hand_repository(GTO_SOURCE)
    pop_repo = get_hand_repository(POPULATION_SOURCE)
    if gto_hands:
        sync_repository_from_loader(loader, GTO_SOURCE, gto_repo)
    if pop_hands:
        sync_repository_from_loader(loader, POPULATION_SOURCE, pop_repo)

    gto_f = filter_engine.apply(gto_repo.get_all(), hand_filter) if gto_hands else []
    pop_f = (
        filter_engine.apply(pop_repo.get_all(), hand_filter) if pop_hands else []
    )

    stats_data = []
    for stat in filtered:
        gto_result = stats_engine.calculate(gto_f, stat) if gto_f else None
        pop_result = stats_engine.calculate(pop_f, stat) if pop_f else None

        gto_value = gto_result.value if gto_result else None
        pop_value = pop_result.value if pop_result else None

        delta = None
        if pop_value is not None and gto_value is not None:
            delta = pop_value - gto_value

        stats_data.append(
            {
                "id": stat.id,
                "label": stat.label,
                "spot": stat.spot,
                "formation": stat.formation,
                "position": stat.position,
                "role": stat.role,
                "street": stat.street,
                "state": stat.state,
                "gto_value": gto_value,
                "gto_sample": gto_result.denominator if gto_result else 0,
                "pop_value": pop_value,
                "pop_sample": pop_result.denominator if pop_result else 0,
                "delta": delta,
            }
        )

    base_params = {
        "spot": spot,
        "formation": formation,
        "position": position,
        "role": role,
        "state": state,
        "hand_street": hand_street,
        "hand_line_prefix": hand_line_prefix,
        "limit": limit,
    }
    q_clean = {k: v for k, v in base_params.items() if v is not None and v != ""}
    next_offset = offset + len(filtered)
    has_next = next_offset < total
    next_query = None
    if has_next:
        next_query = urlencode({**q_clean, "offset": next_offset})

    return templates.TemplateResponse(
        request,
        "partials/stats_table.html",
        {
            "stats": stats_data,
            "total_count": total,
            "offset": offset,
            "limit": limit,
            "has_next": has_next,
            "next_query": next_query,
        },
    )


@router.get("/comparison/{stat_id}", response_class=HTMLResponse)
async def comparison(
    stat_id: str,
    request: Request,
    spot: Optional[str] = Query(None),
    formation: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    hand_street: Optional[str] = Query(None),
    hand_line_prefix: Optional[str] = Query(None),
    loader: DataLoader = Depends(get_loader),
    catalog=Depends(get_catalog),
    stats_engine=Depends(get_stats_engine),
    filter_engine=Depends(get_filter_engine),
):
    """Фрагмент модального окна сравнения для HTMX."""
    stat = catalog.get_by_id(stat_id)
    if not stat:
        return templates.TemplateResponse(
            request,
            "partials/comparison_simple.html",
            {"message": "Статистика не найдена"},
        )

    gto_hands = loader.get_hands_if_loaded(GTO_SOURCE)
    pop_hands = loader.get_hands_if_loaded(POPULATION_SOURCE)
    if not gto_hands and not pop_hands:
        st_gto = loader.get_state(GTO_SOURCE)
        st_pop = loader.get_state(POPULATION_SOURCE)
        if st_gto == LoadingState.LOADING or st_pop == LoadingState.LOADING:
            return templates.TemplateResponse(
                request,
                "partials/comparison_simple.html",
                {"message": "Данные ещё загружаются…"},
            )
        return templates.TemplateResponse(
            request,
            "partials/comparison_simple.html",
            {"message": "Нет загруженных данных для сравнения."},
        )

    pop_repo = get_hand_repository(POPULATION_SOURCE)
    gto_repo = get_hand_repository(GTO_SOURCE)
    sync_repository_from_loader(loader, POPULATION_SOURCE, pop_repo)
    sync_repository_from_loader(loader, GTO_SOURCE, gto_repo)

    hand_filter = parse_filter_context(
        spot=spot,
        formation=formation,
        position=position,
        role=role,
        street=hand_street,
        line_prefix=hand_line_prefix,
    )

    use_case = CompareWithGTOUseCase(
        pop_repo, gto_repo, catalog, stats_engine, filter_engine
    )
    cmp_res = use_case.execute(stat_id, hand_filter)
    if not cmp_res:
        return templates.TemplateResponse(
            request,
            "partials/comparison_simple.html",
            {"message": "Статистика не найдена"},
        )

    return templates.TemplateResponse(
        request,
        "partials/comparison.html",
        {
            "stat": stat,
            "cmp": cmp_res,
            "delta": cmp_res.delta,
        },
    )
