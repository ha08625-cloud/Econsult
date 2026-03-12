# Build stage: install Node and build the frontend
FROM node:22-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Final stage: Python runtime with built frontend
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy data files (condition JSON rulesets)
COPY data/ ./data/

# Copy admin portal (standalone CDN page, not part of Vite build)
COPY admin/ .admin/

# Copy built frontend from build stage
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "PYTHONPATH=backend uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
