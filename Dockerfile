FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install poetry && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY tatamishot/ ./tatamishot/

ENV OUTPUT_DIR=/output

EXPOSE 8484

CMD ["python", "-m", "uvicorn", "tatamishot.main:app", "--host", "0.0.0.0", "--port", "8484"]
