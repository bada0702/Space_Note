#!/bin/bash
# SpaceNote Stop Script for Linux

# Get directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

echo "================================================="
echo "  Stopping SpaceNote..."
echo "================================================="

# 1. Stop backend using PID
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID
        echo "Backend stopped (PID: $BACKEND_PID)."
    else
        echo "Backend process (PID: $BACKEND_PID) was not running."
    fi
    rm .backend.pid
else
    # Fallback: kill any uvicorn process on port 8001
    PID=$(lsof -t -i:8001 2>/dev/null)
    if [ ! -z "$PID" ]; then
        kill $PID
        echo "Backend on port 8001 stopped."
    fi
fi

# 2. Kill frontend/tauri processes
FRONTEND_PID=$(lsof -t -i:1420 2>/dev/null)
if [ ! -z "$FRONTEND_PID" ]; then
    kill $FRONTEND_PID
    echo "SpaceNote Frontend (port 1420) stopped (PID: $FRONTEND_PID)."
else
    FRONTEND_PID=$(pgrep -f "vite.*Space_Note_v100" 2>/dev/null)
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID
        echo "SpaceNote Frontend stopped (PID: $FRONTEND_PID)."
    else
        echo "SpaceNote Frontend was not running."
    fi
fi
pkill -f "tauri.*Space_Note_v100" 2>/dev/null || true
echo "Vite / Tauri processes terminated."

echo "-------------------------------------------------"
echo "SpaceNote shutdown complete."
echo "================================================="
