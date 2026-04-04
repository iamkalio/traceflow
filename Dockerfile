FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY app /app/app

ENV PYTHONPATH=/app/backend
WORKDIR /app/backend
EXPOSE 8000

# CWD must be /app/backend so alembic.ini script_location=migrations resolves to /app/backend/migrations
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
