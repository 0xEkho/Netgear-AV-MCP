FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev
COPY src/ src/
COPY .env.example .env.example
EXPOSE 8080
CMD ["uv", "run", "mcp-server"]
