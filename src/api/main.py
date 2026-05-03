"""
Точка входа приложения FastAPI.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from src.api.routes import router
from src.api.ui_routes import router as ui_router
from src.api.dependencies import init_data_sources, get_loader


def get_test_base_path() -> str:
    env_path = os.environ.get("TEST_BASE_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return str(p)

    current = _PROJECT_ROOT
    test_base = current / "Test base"
    if test_base.exists():
        return str(test_base)

    return str(current)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = get_loader()
    base_path = get_test_base_path()
    init_data_sources(loader, base_path)

    loader.start_loading("gto")

    yield


app = FastAPI(
    title="Mini Poker Stats Explorer",
    description="Анализ покерной статистики: сравнение популяции с GTO",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ui_router, prefix="/ui")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/")
