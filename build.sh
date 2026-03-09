#!/bin/bash
# build.sh - Railway build and start script
# Runs from the project root directory.
# 1. Install Python dependencies
# 2. Install frontend dependencies and build
# 3. Seed the database
# 4. Start the server

set -e  # Exit immediately if any command fails

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing frontend dependencies ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Seeding database ==="
PYTHONPATH=backend python backend/seed_db.py

echo "=== Starting server ==="
PYTHONPATH=backend uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
