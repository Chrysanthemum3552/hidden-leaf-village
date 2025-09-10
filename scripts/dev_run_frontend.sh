#!/bin/bash
# Streamlit 프론트엔드 실행 스크립트
cd "$(dirname "$0")/../frontend_streamlit" || exit
streamlit run app.py --server.port 8501
