#!/bin/bash
# SpaceNote Start Script for Linux

# Get directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

echo "================================================="
echo "  SpaceNote Starting on Linux..."
echo "================================================="

# 1. Setup/Activate Python Virtual Environment
if [ ! -d "backend/venv" ]; then
    echo "Creating virtual environment for backend..."
    python3 -m venv backend/venv
fi

echo "Activating virtual environment..."
source backend/venv/bin/activate

# Install requirements if needed
if [ -f "backend/requirements.txt" ]; then
    echo "Checking/Installing backend dependencies..."
    pip install -q -r backend/requirements.txt
fi

# 2. Run Python Backend in background
echo "Starting backend on port 8001..."
# Run uvicorn using the virtual environment's python/uvicorn
nohup uvicorn main:app --port 8001 --app-dir backend > backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid
echo "Backend started with PID: $BACKEND_PID (logs: backend.log)"

# 3. Wait for backend to start
echo "Waiting for backend to be ready..."
sleep 3

# 4. Start frontend
MODE=$1

if [ -z "$MODE" ]; then
    if [ -t 0 ]; then
        echo ""
        echo "-------------------------------------------------"
        echo "Select execution mode:"
        echo "1) Web Mode (Start Vite dev server and use browser)"
        echo "2) Desktop Mode (Start Tauri GUI app)"
        echo "-------------------------------------------------"
        read -p "Enter choice [1 or 2, default: 1]: " choice
        if [ "$choice" = "2" ]; then
            MODE="desktop"
        else
            MODE="web"
        fi
    else
        MODE="web"
    fi
fi

if [ "$MODE" = "desktop" ] || [ "$MODE" = "2" ]; then
    echo "Starting SpaceNote in Desktop Mode (Tauri)..."
    nohup npm run tauri dev > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > .frontend.pid
    echo "Frontend (Tauri) started with PID: $FRONTEND_PID (logs: frontend.log)"
else
    echo "Starting SpaceNote in Web Mode (Vite)..."
    nohup npm run dev < /dev/null > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > .frontend.pid
    echo "Frontend (Vite) started with PID: $FRONTEND_PID (logs: frontend.log)"
    echo "Access the app at: http://localhost:1420"
fi

echo "-------------------------------------------------"
echo "SpaceNote is running in the background."
echo "  Backend : http://localhost:8001  (PID $BACKEND_PID, backend.log)"
echo "  Frontend: PID $FRONTEND_PID  (frontend.log)"
echo "  Tail logs : tail -f backend.log frontend.log"
echo "  Stop      : ./stop.sh"
echo "================================================="
