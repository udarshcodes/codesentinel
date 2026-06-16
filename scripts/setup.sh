#!/bin/bash
set -e

echo "==========================================="
echo " CodeSentinel WSL Bootstrap Setup"
echo "==========================================="

# 1. Create and activate fresh Linux virtual environment
echo "--> Creating Python virtual environment (.venv)..."
rm -rf .venv venv venv_win wsl_venv* temp_venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Python Dependencies
echo "--> Installing Python dependencies..."
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install semgrep

# 3. Install Node Dependencies (if package.json exists)
if [ -f "backend/package.json" ]; then
    echo "--> Installing Backend Node dependencies..."
    cd backend && npm install && cd ..
fi

if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    echo "--> Installing Frontend Node dependencies..."
    cd frontend && npm install && cd ..
fi

if [ -d "backend/admin_dashboard" ] && [ -f "backend/admin_dashboard/package.json" ]; then
    echo "--> Installing Admin Dashboard Node dependencies..."
    cd backend/admin_dashboard && npm install && cd ..
fi

# 4. Environment Verification
echo "--> Checking environment variables..."
if [ ! -f "backend/.env" ]; then
    echo "⚠️ Warning: backend/.env not found! Please create it based on your Windows environment."
fi

echo "==========================================="
echo " Setup Complete! "
echo " Next steps:"
echo " 1. source .venv/bin/activate"
echo " 2. python backend/main.py"
echo "==========================================="
