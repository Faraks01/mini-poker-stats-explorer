FROM python:3.11-slim

WORKDIR /app

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY src/ src/
COPY stat_catalog.json .
COPY .env.example .env

# Порт
EXPOSE 8000

# Запуск сервера
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
