import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# hidden-leaf-village (프로젝트 루트)
ROOT_DIR = Path(__file__).resolve().parents[1]  # backend_fastapi 상위 -> hidden-leaf-village
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

# 이미지/업로드 저장 경로: hidden-leaf-village/data
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.join(ROOT_DIR, "data")   # → hidden-leaf-village/data
)

# 하위 폴더 생성 (uploads, outputs)
for sub in ("uploads", "outputs"):
    os.makedirs(os.path.join(STORAGE_ROOT, sub), exist_ok=True)

# 정적 파일 라우트 설정
# http://localhost:8000/static/outputs/파일.png → hidden-leaf-village/data/outputs/파일.png
app.mount("/static", StaticFiles(directory=STORAGE_ROOT), name="static")

# 라우터
from routes.image_from_copy import router as image_from_copy_router
from routes.copy_from_image import router as copy_from_image_router
from routes.menu_board import router as menu_board_router

# 엔드포인트 등록
from routes.menu_redesigner import router as menu_redesigner_router
from routes.menu_background import router as menu_background_router


# --- 라우터 포함 ---
app.include_router(image_from_copy_router, prefix="/generate", tags=["image-from-copy"])
app.include_router(copy_from_image_router, prefix="/generate", tags=["copy-from-image"])
app.include_router(menu_board_router, prefix="/generate", tags=["menu-board"])
app.include_router(menu_redesigner_router, prefix="/redesign", tags=["menu-redesign"])
app.include_router(menu_background_router, prefix="/generate", tags=["menu-background"])
