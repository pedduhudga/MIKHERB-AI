#!/bin/bash
set -e

echo "=== Starting MIKHERB AI ==="

# Start backend FastAPI server in background
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Backend started (PID $BACKEND_PID) on http://localhost:8000"

# Serve frontend
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
