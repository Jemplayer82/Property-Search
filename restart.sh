#!/bin/bash
fuser -k 5050/tcp 2>/dev/null
sleep 1
cd ~/property-search
nohup ./venv/bin/gunicorn -w 1 -b 0.0.0.0:5050 --timeout 120 --preload app:app > app.log 2>&1 &
echo  > app.pid
echo Property Search restarted
