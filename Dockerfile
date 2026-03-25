FROM python:3.12-slim

WORKDIR /app

COPY src/requirements.txt /app/src/
RUN pip install --no-cache-dir -r /app/src/requirements.txt

COPY src /app/src
COPY app /app/app

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["sh", "-c", "alembic -c /app/src/alembic.ini upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir /app/src"]
