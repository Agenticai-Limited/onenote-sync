#!/bin/bash
nohup $PWD/.venv/bin/uvicorn app.main:app --port 8005 > $PWD/run.log 2>&1 &
echo $! > ./pid.file &