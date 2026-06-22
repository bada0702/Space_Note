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
uvicorn main:app --port 8001 --reload --app-dir backend &
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid
echo "Backend started with PID: $BACKEND_PID"

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
    npm run tauri dev
else
    echo "Starting SpaceNote in Web Mode (Vite)..."
    echo "Access the app at: http://localhost:1420"
    npm run dev
fi
