# Diagnosis

## Что построил

Mini Poker Stats Explorer — прототип для анализа покерной статистики, сравнивающий поведение population (реальных игроков) с GTO (оптимальной стратегией).

**Компоненты:**
- Парсеры hand history (PokerStars, WPN форматы)
- Анализатор контекста раздач (`HandAnalyzer` в `src/domain/hand_analysis.py`)
- Два связанных порта движков: узкий `HandStatContextPort` (для расчёта стата) и `FilterEngine` (для `FilterContext` по рукам)
- Движок расчёта статистик (`DefaultStatsEngine`: один проход opportunity/success по рукам)
- Репозитории рук в памяти + `DataLoader` (лоадер не знает о репозиториях; синхронизация `hand_sync.sync_repository_from_loader` из API)
- Use cases: перед расчётом `filter_engine.apply(hands, FilterContext)`
- REST API (FastAPI)
- Web UI (Jinja2 + HTMX: фильтры каталога и рук, пагинация таблицы)
- Lazy loading данных с фоновой загрузкой

**Стек:** Python 3.11+, FastAPI, Pydantic, Jinja2, HTMX, Pico CSS, python-dotenv

---

## Как понял данные

### Hand History файлы

**GTO bots data (PokerStars формат):**
- Selfplay симуляции — компьютер играет сам с собой
- Все карты видны (Dealt to каждому игроку)
- Имена игроков = позиции (UTG, HJ, CO, BU, SB, BB)
- 6-max столы, $0.50/$1 блайнды
- ~50MB на файл, ~50k рук на файл

**Population data (WPN формат):**
- Реальные игроки с никнеймами
- Карты обычно скрыты
- Разные размеры столов (2-9 игроков)
- Высокие ставки ($50/$100)
- ~1200 файлов разного размера

### stat_catalog.json

Каталог из 20 статистик. Каждая определяет:

```json
{
  "id": "stat-005",
  "label": "Flop continuation bet frequency",
  "contextFilters": {
    "spot": "SRP",        // тип банка: SRP (один рейз) или 3BP (ререйз)
    "formation": "BB_BTN", // кто в банке
    "position": "IP",      // относительная позиция
    "role": "PFR",         // роль на префлопе
    "street": "flop"       // улица
  },
  "opportunity": {         // когда считать denominator
    "street": "flop",
    "canAct": true
  },
  "success": {             // когда считать numerator
    "street": "flop",
    "action": "bet"
  },
  "minSample": 30          // минимальная выборка
}
```

**Понимание:**
- `contextFilters` — какие раздачи учитывать
- `opportunity` — denominator: сколько раз игрок был в ситуации
- `success` — numerator: сколько раз выполнил действие
- `state` — AVAILABLE/NO_DATA/NO_STAT/INVALID_CONTEXT

---

## Как считаю numerator / denominator

### Алгоритм

На вход в расчёт попадает уже **отфильтрованный** список рук: сначала use case применяет `FilterEngine.apply(repo_hands, FilterContext)` (опционально из query/UI), затем `StatsEngine.calculate`.

```python
for hand in hands_filtered:
    # 1. Проверить contextFilters стата
    context = analyze_hand(hand)  # spot, formation, role, position, line
    if not matches_stat_context(hand, stat):
        continue
    
    # 2. Найти целевого игрока (по contextFilters position/role)
    player = find_target_player(context, stat)
    if not player:
        continue
    
    # 3. Проверить opportunity (denominator)
    if matches_opportunity(context, player, stat.opportunity):
        denominator += 1
        
        # 4. Проверить success (numerator)
        if matches_success(context, player, stat.success):
            numerator += 1

value = numerator / denominator if denominator > 0 else None
```

Внутри `DefaultStatsEngine` шаги 3–4 объединены в **один проход** по списку рук. Поле **`facingAction`** в `opportunity` каталога **пока не поддерживается** (игнорируется).

### Пример: Flop Cbet (stat-005)

**Контекст:** SRP, BB_BTN, IP, PFR

1. Раздача: BTN рейзит, BB коллирует → SRP, formation=BB_BTN
2. BTN = PFR (рейзил), IP (действует после BB)
3. Opportunity: флоп дошли, BTN может действовать → +1 denominator
4. Success: BTN сделал bet → +1 numerator

**Результат:** 13493 / 23424 = 57.6%

---

## Решения по ходу работы

### Архитектура: Гексагональная

**Почему:** Требование заменяемости источника данных. Порты позволяют подменить FileLoader на ClickHouseAdapter без изменения бизнес-логики.

### Порты в application/, не domain/

**Почему:** Clean Architecture подход. Use cases определяют нужные интерфейсы. Domain по-прежнему не зависит от application; **`HandAnalyzer`** лежит в **domain** (`hand_analysis.py`), чтобы инфраструктурные адаптеры не тянули прикладной слой ради анализа рук.

### Два парсера + CompositeParser

**Почему:** Форматы существенно разные. Отдельные парсеры проще отлаживать. CompositeParser делает auto-detect прозрачным.

### Auto-detect позиций по именам в GTO

**Почему:** В GTO данных имена = позиции (UTG, HJ...). Если все имена — позиции, не переназначаем.

### HandAnalyzer в domain + HandStatContextPort

**Почему:** Анализ раздачи — чистая логика над доменными типами. Кэш `HandContext` живёт в `DefaultFilterEngine`, который реализует и `FilterEngine`, и узкий порт **`HandStatContextPort`** для `DefaultStatsEngine` (без жёсткой связки на конкретный класс фильтра).

### Lazy loading с фоновой загрузкой

**Почему:** 500k рук = долгая загрузка. Blocking при старте — плохой UX. Фоновая загрузка + polling статуса.

**Дополнительно (ускорение):**
- **Параллельный парсинг:** все `*.txt` в каталоге источника обрабатываются пулом потоков; на каждый файл создаётся свой `CompositeParser` / `FileHandHistoryLoader`, чтобы не делить мутабельное состояние между потоками. Порядок склейки рук — по имени файла (как раньше при последовательном цикле).
- **SQLite-кэш распарсенных рук (`hand_sqlite_cache`):** отпечаток источника (файл: путь+size+mtime; каталог: список `.txt` с size+mtime). При совпадении отпечатка и имени источника (`gto` / `population`) данные читаются из БД без парсинга. Параметры: `.env` / переменные окружения (`STATS_SQLITE_CACHE`, `STATS_LOAD_WORKERS`, `STATS_SQLITE_CACHE_REBUILD`). По умолчанию путь кэша — `.cache/hands.db` от корня репозитория; отключение — пустая `STATS_SQLITE_CACHE`.
- **`load_dotenv`** в `main.py` до регистрации роутов; шаблон конфигурации — `.env.example`, при первом `./run.sh` копируется `.env`.

### Jinja2 + HTMX вместо React

**Почему:** Прототип за 4 часа. HTMX даёт реактивность без JS-фреймворка. Один сервер, проще деплой.

### In-memory хранение и синхронизация с лоадером

**Почему:** Простота. Достаточно для 500k рук. Руки для расчётов хранятся в **`InMemoryHandRepository`** (по источникам gto / population); **`DataLoader`** только грузит файлы в память процесса. Перед use case API вызывает **`sync_repository_from_loader`**, чтобы репозиторий отражал актуальный снимок лоадера (лоадер о репозиториях не знает).

---

## Обработанные edge cases

### Парсинг

| Case | Решение |
|------|---------|
| Имена = позиции (GTO) | Auto-detect, не переназначать |
| Heads-up (2 игрока) | Отдельная логика позиций SB/BB |
| UTF-8 с ошибками | `errors="ignore"` при чтении |
| Пустые файлы | Skip с continue |
| Нет флопа (все фолдят) | `streets_seen` не включает flop |

### Расчёт

| Case | Решение |
|------|---------|
| denominator = 0 | `value = None`, `state = "NO_DATA"` |
| denominator < minSample | `state = "LOW_SAMPLE"` |
| NO_STAT / INVALID_CONTEXT | Возвращаем сразу без расчёта |
| Multiway pot (3+ игрока) | `formation = "MULTIWAY"`, не анализируем детально |

### UI

| Case | Решение |
|------|---------|
| Данные ещё грузятся | Показываем spinner, polling каждые 3 сек |
| Нет данных для источника | Показываем "-" вместо 0% |
| Очень длинные названия | CSS truncation |
| Список стата в таблице | По умолчанию **все** статы из `stat_catalog.json`; фильтр «Статус» сужает (например, только `AVAILABLE`) |

---

## Что не успел

| Функционал | Причина |
|------------|---------|
| **Bet sizing** | Требует парсинга сумм ставок и категоризации (1/3, 1/2, pot, overbet) |
| **Breakdown по категориям** | Нужна группировка по hand range, board texture |
| **Список подходящих раздач** | Нужен endpoint + UI для отображения |
| **Графики** | Plotly/Chart.js интеграция |
| **Formation нормализация** | BB_SB ≠ SB_BB — теряем данные |
| **Тесты** | Unit/integration тесты |
| **Кэширование агрегатов стата** | Каждый запрос пересчитывает проценты; есть кэш **распарсенных** рук (SQLite) и кэш контекста руки в `DefaultFilterEngine`, но не кэш готовых значений стата по фильтру |
| **`facingAction` в opportunity** | Не реализовано; поле в каталоге игнорируется |

---

## Оставшиеся риски

### Высокие

| Риск | Влияние | Митигация |
|------|---------|-----------|
| Ошибки парсинга | Некорректные статистики | Добавить валидацию, тесты |
| Formation mismatch | Потеря данных (BB_SB vs SB_BB) | Нормализовать порядок |

### Средние

| Риск | Влияние | Митигация |
|------|---------|-----------|
| Производительность | Тяжёлый пересчёт при большом n рук | Параллельный ingest, SQLite-кэш парса, кэш агрегатов (не сделан) |
| Memory usage | Большой объём рук в RAM | Кэш на диске после парса; при необходимости — streaming / БД |
| Line encoding упрощён | Потеря информации о sizing | Расширить кодировку |

### Низкие

| Риск | Влияние | Митигация |
|------|---------|-----------|
| Новые форматы HH | Не парсятся | Добавить парсер |
| Multiway pots | Не анализируются | Расширить HandAnalyzer |

---

## Как использовался AI

### Роль AI (Claude)

AI выступал как pair programmer с пошаговым протоколом:
1. Предложение вариантов (A/B/C) для каждого шага
2. Ожидание выбора пользователя
3. Реализация выбранного варианта
4. Проверка и переход к следующему шагу

### Что делал AI

- Анализ входных данных (форматы HH, stat_catalog.json)
- Проектирование архитектуры
- Написание кода (парсеры, движки, API, UI)
- Создание документации
- Отладка ошибок
- Проверка соответствия требованиям

### Что делал человек

- Выбор направления (опции A/B/C)
- Уточнение требований
- Финальные решения по архитектуре
- Запросы на документацию

### Режим работы

Использовался "cavemanov" режим — сжатые ответы на русском языке + "interaction-protocol" — пошаговая работа с вариантами.

### Примеры решений

| Шаг | Варианты | Выбор | Обоснование |
|-----|----------|-------|-------------|
| Структура проекта | Минимальная / Полная | Полная (B) | Меньше рефакторинга потом |
| Парсеры | Универсальный / Раздельные | Раздельные (B) | Проще отлаживать |
| UI | Jinja2+HTMX / Gradio | Jinja2+HTMX | Контроль над вёрсткой, один сервер |
| Загрузка | Eager / Lazy | Lazy (B) | Не блокируем старт |

---

## Итог

**Прототип работает.** Основной флоу реализован:
- Загрузка данных из файлов (в т.ч. параллельно по файлам; опционально повторное чтение из SQLite-кэша)
- Парсинг двух форматов
- Расчёт статистик из каталога (в UI по умолчанию весь каталог, без отсечения только по `AVAILABLE`)
- Сравнение population vs GTO через use case
- Отображение в UI с фильтрами каталога и рук, пагинацией таблицы
- REST: пагинация списка статов, параметры `hf_*` для фильтра рук на `/api/stats/{id}` и `/api/compare/{id}`
- Конфигурация через `.env` / `.env.example`; Docker-образ собирается с копией `.env.example` → `/app/.env`, `docker-compose` задаёт `TEST_BASE_PATH` и монтирует `Test base`

**Ship Decision: GO with conditions**
- Для демо — готов
- Для production — нужны тесты, кэш **готовых** метрик (при необходимости), нормализация formation
