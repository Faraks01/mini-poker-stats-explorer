# Mini Poker Stats Explorer

Прототип покерного статистического explorer'а для анализа и сравнения частот действий population vs GTO.

## Что это

Dashboard для покерной аналитики, который:
- Парсит hand history файлы двух форматов (PokerStars, WPN)
- Вычисляет статистики (bet/check/fold frequency, line frequency)
- Сравнивает поведение population с GTO-референсом
- Показывает дельту и достаточность выборки

```
┌─────────────────────────────────────────────────────────────┐
│ GTO Data: ✓ 500,000 hands    Population: ✓ 45,000 hands     │
├─────────────────────────────────────────────────────────────┤
│ Spot [SRP ▼]  Formation [BB_BTN ▼]  Position [IP ▼]  ...    │
├─────────────────────────────────────────────────────────────┤
│ Stat                │  GTO   │  Pop   │ Delta  │  State     │
│ Flop cbet           │ 57.6%  │ 62.1%  │ +4.5%  │ AVAILABLE  │
│                     │n=23424 │n=1542  │        │            │
└─────────────────────────────────────────────────────────────┘
```

## Быстрый старт

### Конфигурация окружения

- Шаблон: **`.env.example`**. При первом запуске **`run.sh`** копирует его в **`.env`**, если файла ещё нет.
- Переменные подхватываются через **`python-dotenv`** при старте приложения (`src/api/main.py`).
- Относительные пути в `.env` считаются **от корня репозитория** (удобно при любом рабочем каталоге).

| Переменная | Назначение |
|------------|------------|
| `TEST_BASE_PATH` | Каталог с подпапками `GTO bots data/` и `Тестовая база данные популяции/`. Пусто — авто: `./Test base`, если есть, иначе корень репо. |
| `STATS_SQLITE_CACHE` | Путь к SQLite-кэшу распарсенных рук. По умолчанию (если переменная не задана в окружении): **`.cache/hands.db`**. Пустая строка — **без кэша**. |
| `STATS_LOAD_WORKERS` | Число потоков при параллельном чтении нескольких `.txt`. Пусто — `min(8, CPU+2)`. |
| `STATS_SQLITE_CACHE_REBUILD` | `1` / `true` / `yes` — не читать кэш, перепарсить и перезаписать. |

В **Docker** при сборке в образ копируется `.env.example` как `/app/.env`; `docker-compose.yml` задаёт `TEST_BASE_PATH=/app/Test base` и монтирует `./Test base` в контейнер.

### Вариант A: Bash-скрипт (рекомендуется)

```bash
chmod +x run.sh   # один раз, если нет права на выполнение
./run.sh
```

Скрипт: venv → зависимости → при отсутствии `.env` копирует из `.env.example` → uvicorn на порту **8000**. Скрипт должен быть с **Unix-окончаниями строк (LF)**.

### Вариант B: Docker Compose

```bash
docker compose up --build
# либо: docker-compose up --build
```

Данные: том `./Test base:/app/Test base:ro`, переменная `TEST_BASE_PATH` в `docker-compose.yml`.

### Вариант C: Вручную

```bash
cp -n .env.example .env   # опционально
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

---

**После запуска:**
- Dashboard: http://localhost:8000/ui/ (редирект с `/`)
- API Docs: http://localhost:8000/docs

## Структура проекта

```
mini-poker-stats-explorer/
├── src/
│   ├── domain/           # Модели + hand_analysis (контекст руки)
│   ├── application/      # Порты, use cases, движки (FilterEngine, HandStatContextPort)
│   ├── infrastructure/   # Парсеры, движки, репозитории, DataLoader, hand_sync, hand_sqlite_cache
│   └── api/              # FastAPI + Jinja2/HTMX UI, context_params
├── docs/                 # Документация
├── Test base/            # Данные (не в git)
├── .env.example          # Шаблон переменных окружения
├── .env                  # Локальная конфигурация (не в git)
├── .cache/               # SQLite-кэш рук по умолчанию (не в git)
├── stat_catalog.json     # Каталог статистик
├── diagnosis.md          # Отчёт о разработке
├── run.sh                # Скрипт запуска
├── Dockerfile            # Docker образ (+ копия .env из .env.example)
└── docker-compose.yml    # Docker Compose
```

## Документация

| Документ | Описание |
|----------|----------|
| [diagnosis.md](./diagnosis.md) | **Отчёт** — что построил, как, почему |
| [POKER_EXPLAINED.md](./docs/POKER_EXPLAINED.md) | Покер и прототип для новичков |
| [MANUAL_TEST.md](./docs/MANUAL_TEST.md) | Пошаговая инструкция проверки |
| [DECISIONS.md](./docs/DECISIONS.md) | Принятые решения и roadmap |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Гексагональная архитектура |
| [DATA_FLOW.md](./docs/DATA_FLOW.md) | Путь данных от файла до UI |
| [API.md](./docs/API.md) | REST API endpoints |
| [DEVELOPMENT.md](./docs/DEVELOPMENT.md) | Разработка и отладка |
| [ASSUMPTIONS.md](./docs/ASSUMPTIONS.md) | Допущения и ограничения |
| [COMPLIANCE.md](./docs/COMPLIANCE.md) | Проверка соответствия требованиям |

## Стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11+ |
| Web framework | FastAPI |
| Валидация | Pydantic |
| UI | Jinja2 + HTMX |
| Стили | Pico CSS |
| Контейнеризация | Docker |
| Конфиг | python-dotenv (`.env`) |

## Загрузка и кэш рук

- **Параллельно:** все `*.txt` в каталоге источника обрабатываются пулом потоков (отдельный парсер на файл).
- **SQLite:** после успешного парсинга руки можно сохранить в БД; при совпадении отпечатка каталога/файла следующий старт читает кэш вместо повторного парсинга.
- Отпечаток учитывает путь, размер и mtime для файла либо список `.txt` в каталоге.

## Данные

**Источники:**
- `GTO bots data/` — PokerStars-формат, selfplay (~500k рук)
- `Тестовая база данные популяции/` — WPN-формат, реальные игроки

**Каталог статистик** (`stat_catalog.json`):
- 20 статистик (14 available, 6 no data/no stat)
- Фильтры: spot, formation, position, role, street
- Метрики: BET/CHECK/FOLD/RAISE_FREQUENCY, LINE_FREQUENCY

## Основные возможности

| Функция | Статус |
|---------|--------|
| Парсинг PokerStars формата | ✅ |
| Парсинг WPN формата | ✅ |
| Фильтрация по контексту стата (`contextFilters`) | ✅ |
| Доп. фильтр набора рук (`FilterContext`, UI + REST) | ✅ |
| Расчёт статистик | ✅ |
| Сравнение pop vs GTO | ✅ |
| Отображение sample/denominator | ✅ |
| Lazy loading данных + синхронизация в `InMemoryHandRepository` | ✅ |
| Параллельный парсинг каталогов `.txt` + опциональный SQLite-кэш рук | ✅ |
| UI: все статы из каталога по умолчанию, фильтр по `state`, пагинация | ✅ |
| Bet sizing статистики | ⚠️ Частично |
| Breakdown по категориям | ❌ |
| Список раздач | ❌ |
| Графики | ❌ |

## Ship Decision

**GO with conditions**

✅ Готово:
- Основной флоу работает
- Проценты считаются из данных
- Sample/denominator видны
- Документация полная

⚠️ Для production:
- Тесты
- Кэширование **готовых** агрегатов стата (по запросу; кэш **распарсенных** рук уже есть)
- Нормализация formation (BB_SB = SB_BB)
- Обработка edge cases в парсерах

## API Endpoints

```
GET  /                      → редирект на /ui/
GET  /ui/                   → Dashboard (HTML)
GET  /api/stats             → Список статистик (фильтры spot/formation/…, state, offset, limit, total)
GET  /api/stats/{id}        → Расчёт статистики (source=gto|population, опц. hf_* — фильтр рук)
GET  /api/compare/{id}      → Сравнение pop vs GTO (опц. hf_* — тот же фильтр рук)
GET  /api/data/status       → Статус загрузки
POST /api/data/load/{src}   → Запуск загрузки
GET  /docs                  → Swagger UI
```

**Фильтр рук в REST** (query, все необязательны): `hf_spot`, `hf_formation`, `hf_position`, `hf_role`, `hf_street`, `hf_line_prefix` — сужают набор раздач до расчёта (через `FilterEngine.apply` в use case).

## Пример использования API

```bash
# Статус загрузки
curl http://localhost:8000/api/data/status

# Список статов с пагинацией (все из каталога; фильтр state опционален)
curl "http://localhost:8000/api/stats?offset=0&limit=40"
curl "http://localhost:8000/api/stats?state=AVAILABLE&offset=0&limit=20"

# Расчёт статистики
curl "http://localhost:8000/api/stats/stat-005?source=gto"

# Тот же стат только по SRP и флопу (фильтр рук)
curl "http://localhost:8000/api/stats/stat-005?source=gto&hf_spot=SRP&hf_street=flop"

# Сравнение
curl "http://localhost:8000/api/compare/stat-005"

# Сравнение с фильтром рук
curl "http://localhost:8000/api/compare/stat-005?hf_spot=SRP&hf_formation=BB_BTN"
```
