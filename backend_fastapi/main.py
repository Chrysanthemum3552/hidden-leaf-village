import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

app = FastAPI(
    title="ad-gen-service",
    description="(1) 메뉴판 생성 (2) 글→이미지 (3) 이미지→글",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
)
for sub in ("uploads", "outputs"):
    os.makedirs(os.path.join(STORAGE_ROOT, sub), exist_ok=True)

app.mount("/static", StaticFiles(directory=STORAGE_ROOT), name="static")

# 라우터
from routes.image_from_copy import router as image_from_copy_router
from routes.copy_from_image import router as copy_from_image_router
from routes.menu_board import router as menu_board_router

app.include_router(image_from_copy_router, prefix="/generate", tags=["image-from-copy"])
app.include_router(copy_from_image_router, prefix="/generate", tags=["copy-from-image"])
app.include_router(menu_board_router, prefix="/generate", tags=["menu-board"])
