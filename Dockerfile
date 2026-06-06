# Stage 1: build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python API + static frontend
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY eval1/ ./eval1/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p eval1/outputs eval1/data/uploads

EXPOSE 8000

CMD ["sh", "-c", "uvicorn eval1.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
