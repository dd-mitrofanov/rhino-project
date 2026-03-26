FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN groupadd -r api && useradd -r -g api -d /app -s /sbin/nologin api
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
USER api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
