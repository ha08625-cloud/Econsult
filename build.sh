#!/bin/bash
# build.sh - Railway build and start script
# Runs from the project root directory.
# 1. Install Python dependencies
# 2. Install frontend dependencies and build
# 3. Start the server (database seeding happens at server startup via FastAPI lifespan)

set -e  # Exit immediately if any command fails

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing frontend dependencies ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Starting server ==="
PYTHONPATH=backend uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
