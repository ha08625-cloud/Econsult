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

# Copy application source
COPY app/ ./app/
COPY main.py ./

# Copy data files (condition JSON rulesets)
COPY data/ ./data/

# Copy built frontend from build stage
# The Vite build produces frontend/dist/ which includes both the patient
# form (dist/index.html) and the admin portal (dist/admin-ui/index.html).
# Both are served by the StaticFiles mount at / in main.py.
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
