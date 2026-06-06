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
COPY scripts/railway_start.sh ./scripts/railway_start.sh
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p eval1/outputs eval1/data/uploads && chmod +x scripts/railway_start.sh

EXPOSE 8000

CMD ["sh", "scripts/railway_start.sh"]
