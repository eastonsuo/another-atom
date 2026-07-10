FROM node:22-alpine AS studio-builder

WORKDIR /studio
COPY studio/package.json studio/package-lock.json ./
RUN npm ci
COPY studio/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.11
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY another_atom/ ./another_atom/
COPY --from=studio-builder /studio/dist ./studio/dist
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn another_atom.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
