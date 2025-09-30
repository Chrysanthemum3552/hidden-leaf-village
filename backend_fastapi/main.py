import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# ─────────────────────────────────────────
# .env 로드 (프로젝트 루트의 .env 우선)
# ─────────────────────────────────────────
# backend_fastapi/main.py 기준으로 두 단계 상위가 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    # 로컬 개발 등의 경우 현재 작업 디렉터리에서 로드
    load_dotenv()

# ─────────────────────────────────────────
# FastAPI 앱
# ─────────────────────────────────────────
app = FastAPI(
    title="ad-gen-service",
    description="(1) 메뉴판 생성 (2) 글→이미지 (3) 이미지→글",
    version="1.0.0",
)

# CORS (프론트엔드 접근 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# 저장소 경로 및 정적 파일 마운트
# ─────────────────────────────────────────
# 기본값: backend_fastapi/../data  (프로젝트 루트의 data)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
)

# uploads / outputs 디렉터리 보장
for sub in ("uploads", "outputs"):
    os.makedirs(os.path.join(STORAGE_ROOT, sub), exist_ok=True)

# /static/* 로 정적 파일 서빙 (예: /static/outputs/xxx.png)
app.mount("/static", StaticFiles(directory=STORAGE_ROOT), name="static")

# 공개용 베이스 URL (Render에 환경변수로 설정 권장)
BASE_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

# ─────────────────────────────────────────
# 라우터 등록
# ─────────────────────────────────────────
from routes.image_from_copy import router as image_from_copy_router
from routes.copy_from_image import router as copy_from_image_router
from routes.menu_service import router as menu_service_router

# prefix와 tags를 일관되게 설정
app.include_router(image_from_copy_router, prefix="/generate", tags=["image-from-copy"])
app.include_router(copy_from_image_router, prefix="/generate", tags=["copy-from-image"])
app.include_router(menu_service_router,  prefix="/generate", tags=["menu-service"])

# ─────────────────────────────────────────
# 헬스체크 & 인덱스
# ─────────────────────────────────────────
@app.get("/")
def root():
    return {
        "ok": True,
        "service": "ad-gen-service",
        "static_example": f"{BASE_URL}/static/outputs/",
        "endpoints": {
            "image_from_copy": "/generate/…",
            "copy_from_image": "/generate/…",
            "menu_service": "/generate/…"
        }
    }

@app.get("/healthz")
def healthz():
    # 간단한 쓰기 가능 여부 체크 (outputs 디렉터리 존재/쓰기 가능)
    try:
        test_path = Path(STORAGE_ROOT) / "outputs" / ".healthcheck"
        test_path.write_text("ok", encoding="utf-8")
        if test_path.exists():
            test_path.unlink(missing_ok=True)
        writable = True
    except Exception:
        writable = False

    return {
        "status": "ok",
        "storage_root": STORAGE_ROOT,
        "writable": writable
    }
