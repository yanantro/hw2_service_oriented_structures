FROM python:3.12-slim AS codegen
RUN mkdir -p /usr/share/man/man1 \
 && apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements-codegen.txt .
RUN pip install --no-cache-dir -r requirements-codegen.txt
COPY openapi ./openapi
COPY scripts ./scripts
RUN sed -i 's/\r$//' scripts/generate.sh && bash scripts/generate.sh

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY openapi ./openapi
COPY --from=codegen /build/generated ./generated
ENV PYTHONPATH=/app/generated:/app \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
