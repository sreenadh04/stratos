FROM python:3.13-slim

WORKDIR /app

RUN apt-get update     && apt-get install -y --no-install-recommends gcc libpq-dev     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN python -m pip install --no-cache-dir uv
RUN uv sync

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "stratos.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
