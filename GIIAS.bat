@echo off
cd /d C:\Users\difotoin\comfyui-api-client

set PYTHONPATH=.
uvicorn src.app.api.api:app --reload

pause