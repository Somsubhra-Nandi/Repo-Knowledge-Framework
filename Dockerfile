FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip \
    && pip install -e ".[core]" --no-cache-dir

COPY . .

EXPOSE 8000
CMD ["uvicorn", "graphrag.api:app", "--host", "0.0.0.0", "--port", "8000"]
