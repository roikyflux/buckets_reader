#!/bin/bash
APP_ENV=development uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PID=$!
sleep 3
echo "Health check:"
curl -s http://localhost:8000/health
echo -e "\nDocs development:"
curl -o /dev/null -s -w "%{http_code}" http://localhost:8000/docs
echo ""
kill $PID
wait $PID 2>/dev/null

APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PID2=$!
sleep 3
echo "Docs production:"
curl -o /dev/null -s -w "%{http_code}" http://localhost:8000/docs
echo ""
kill $PID2
wait $PID2 2>/dev/null
