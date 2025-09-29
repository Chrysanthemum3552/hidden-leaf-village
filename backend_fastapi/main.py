import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# 프로젝트 루트 경로
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

# FastAPI 앱 생성
app = FastAPI(
    title="ad-gen-service",
    description="(1) 메뉴판 생성 (2) 글→이미지 (3) 이미지→글",
    version="1.0.0",
)

# CORS 허용 (프론트엔드에서 접근 가능하게)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 저장소 경로 (uploads / outputs 디렉토리 생성)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
)
for sub in ("uploads", "outputs"):
    os.makedirs(os.path.join(STORAGE_ROOT, sub), exist_ok=True)

# 정적 파일 서빙 (/static 경로로 접근 가능)
app.mount("/static", StaticFiles(directory=STORAGE_ROOT), name="static")

# --- 라우터 임포트 ---
from routes.image_from_copy import router as image_from_copy_router
from routes.copy_from_image import router as copy_from_image_router
from routes.menu_service import router as menu_service_router

# --- 라우터 포함 ---
app.include_router(image_from_copy_router, prefix="/generate", tags=["image-from-copy"])
app.include_router(copy_from_image_router, prefix="/generate", tags=["copy-from-image"])
app.include_router(menu_service_router, prefix="/generate", tags=["menu-service"])
