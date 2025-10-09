import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# ─────────────────────────────────────────
# .env 로드 (프로젝트 루트의 .env 우선)
# ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
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
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
)
for sub in ("uploads", "outputs"):
    os.makedirs(os.path.join(STORAGE_ROOT, sub), exist_ok=True)

app.mount("/static", StaticFiles(directory=STORAGE_ROOT), name="static")

# 공개용 베이스 URL (Render에 환경변수로 설정 권장)
BASE_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

# ─────────────────────────────────────────
# 라우터 등록
# ─────────────────────────────────────────
# image_from_copy 라우트는 원격 Rosetta/ComfyUI 호출 기반 (_get_pipeline)
from routes.image_from_copy import router as image_from_copy_router, _get_pipeline
from routes.copy_from_image import router as copy_from_image_router
from routes.menu_service import router as menu_service_router

app.include_router(image_from_copy_router, prefix="/generate", tags=["image-from-copy"])
app.include_router(copy_from_image_router, prefix="/generate", tags=["copy-from-image"])
app.include_router(menu_service_router,  prefix="/generate", tags=["menu-service"])

# ─────────────────────────────────────────
# 서버 시작 시 초기화
# ─────────────────────────────────────────
@app.on_event("startup")
def preload_services():
    """
    서버 시작 시 원격 서비스 연결 여부만 가볍게 체크.
    (ComfyUI / Rosetta 둘 다 Cloudflared 터널 통해 연결됨)
    """
    try:
        pipeline = _get_pipeline()
        pipeline.check_services()
        print("✅ 원격 서비스 연결 확인 완료 (ComfyUI + Rosetta)")
    except Exception as e:
        print(f"⚠️ 원격 서비스 확인 실패 (무시 가능): {e}")

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
            "image_from_copy": "/generate/image-from-copy",
            "copy_from_image": "/generate/copy-from-image",
            "menu_service": "/generate/menu-service"
        }
    }

@app.get("/healthz")
def healthz():
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
