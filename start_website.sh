#!/bin/bash

echo "Starting Balance Dashboard..."
echo ""
echo "Starting Bot API Server on port 8000..."
python bot_api.py &
API_PID=$!
sleep 3

echo ""
echo "Starting Flask Website on port 5000..."
python website/app.py &
WEB_PID=$!

echo ""
echo "Dashboard started!"
echo "Bot API PID: $API_PID"
echo "Website PID: $WEB_PID"
echo "Press Ctrl+C to stop both services"

# Function to handle cleanup
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $API_PID 2>/dev/null
    kill $WEB_PID 2>/dev/null
    echo "Services stopped"
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Wait for processes
wait