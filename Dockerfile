FROM python:3.12-slim

WORKDIR /app

# Backend
COPY src/requirements.txt src/
RUN pip install --no-cache-dir -r src/requirements.txt

COPY src/ src/
COPY app/ app/

RUN mkdir -p src/data

WORKDIR /app/src
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
