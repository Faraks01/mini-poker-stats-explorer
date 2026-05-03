#!/bin/bash
set -e

echo "=== Mini Poker Stats Explorer ==="
echo ""

# Цвета вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # сброс цвета

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: python3 не найден. Установите Python 3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "Версия Python: ${GREEN}${PYTHON_VERSION}${NC}"

# Создание venv при отсутствии
if [ ! -d ".venv" ]; then
    echo ""
    echo -e "${YELLOW}Создание виртуального окружения...${NC}"
    python3 -m venv .venv
fi

# Активация venv
source .venv/bin/activate

# Конфигурация окружения
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Создан .env из .env.example${NC}"
fi

# Установка зависимостей
echo ""
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install -q -r requirements.txt

# Проверка наличия данных
if [ ! -d "Test base" ]; then
    echo ""
    echo -e "${YELLOW}Предупреждение: каталог «Test base» не найден.${NC}"
    echo "Положите истории раздач в папку «Test base/»:"
    echo "  Test base/"
    echo "    ├── GTO bots data/"
    echo "    └── Тестовая база данные популяции/"
fi

# Запуск сервера
echo ""
echo -e "${GREEN}Запуск сервера...${NC}"
echo ""
echo "  Дашборд: http://localhost:8000"
echo "  API:     http://localhost:8000/docs"
echo ""
echo "Ctrl+C — остановка"
echo ""

uvicorn src.api.main:app --host 0.0.0.0 --port 8000
