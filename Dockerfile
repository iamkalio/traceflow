FROM python:3.12-slim

WORKDIR /app

COPY src/requirements.txt /app/src/
RUN pip install --no-cache-dir -r /app/src/requirements.txt

COPY src /app/src
COPY app /app/app

ENV PYTHONPATH=/app/src
WORKDIR /app/src
EXPOSE 8000

# CWD must be /app/src so alembic.ini script_location=migrations resolves to /app/src/migrations
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
