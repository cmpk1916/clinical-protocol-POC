FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.7.3
COPY pyproject.toml uv.lock ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["sh", "-c", "/app/.venv/bin/alembic upgrade head && exec /app/.venv/bin/uvicorn protocol_poc.app:app --host 0.0.0.0 --port 8000"]
