FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для DuckDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и ставим зависимости
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Копируем код приложения
COPY . .

# Создаём папку для БД (будет смонтирована как volume)
RUN mkdir -p /app/data

EXPOSE 8501

CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]