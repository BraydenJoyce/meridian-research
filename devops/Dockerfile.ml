FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgl1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
    ultralytics>=8.0.0 \
    onnxruntime>=1.17.0 \
    anthropic==0.40.0 \
    pydantic>=2.0.0 \
    pillow \
    numpy \
    structlog \
    pyyaml \
    scikit-learn

FROM base AS runtime
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY ml/ /app/ml/
COPY backend/app/schemas/ /app/backend/app/schemas/
ENV PYTHONPATH=/app
WORKDIR /app
CMD ["python", "ml/train/train.py", "--help"]
