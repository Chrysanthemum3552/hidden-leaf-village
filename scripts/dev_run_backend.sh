#!/bin/bash
# FastAPI 백엔드 실행 스크립트
cd "$(dirname "$0")/../backend_fastapi" || exit
uvicorn main:app --reload --host 0.0.0.0 --port 8000
