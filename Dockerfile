# Build stage: install Node and build the frontend
FROM node:22-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Copy shared JSON constants that are imported by the frontend build.
# consultation_outcomes.json lives at app/core/ alongside the Python module
# that reads it. It is not inside frontend/, so it must be copied explicitly.
# The import in OutcomeScreen.tsx resolves two levels up from src/screens/
# to the /frontend workdir root, which is where this file lands.
COPY app/core/consultation_outcomes.json ./
RUN npm run build

# Final stage: Python runtime with built frontend
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY main.py ./

# Copy Alembic configuration and migrations
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy data files (condition JSON rulesets)
COPY data/ ./data/

# Copy built frontend from build stage
COPY --from=frontend-build /frontend/dist ./frontend/dist

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]