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
fi

# uvicorn --reload spawns a child worker whose PID differs from $!; killing
# only the parent can leave that child orphaned and stuck holding the port.
# Always sweep port 8001 as well so no zombie backend survives a restart.
PIDS=$(lsof -t -i:8001 2>/dev/null)
if [ ! -z "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    sleep 1
    PIDS=$(lsof -t -i:8001 2>/dev/null)
    if [ ! -z "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
    fi
    echo "Backend on port 8001 stopped."
fi

# 2. Stop frontend launcher using PID (npm run dev / tauri dev)
if [ -f ".frontend.pid" ]; then
    FRONTEND_LAUNCHER_PID=$(cat .frontend.pid)
    if kill -0 $FRONTEND_LAUNCHER_PID 2>/dev/null; then
        # Kill the launcher and its child processes (vite/tauri)
        pkill -P $FRONTEND_LAUNCHER_PID 2>/dev/null || true
        kill $FRONTEND_LAUNCHER_PID 2>/dev/null || true
        echo "Frontend launcher stopped (PID: $FRONTEND_LAUNCHER_PID)."
    fi
    rm .frontend.pid
fi

# 3. Kill any remaining frontend/tauri processes on port 1420
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
