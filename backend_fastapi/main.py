"""
FastAPI Main Entry (Render 배포용)
- ComfyUI와 Rosetta 서버는 ngrok으로 터널링
- .env 파일을 통해 동적으로 ngrok URL을 읽어옴
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# ----------------------------
# 1. 환경 변수 로드 (.env)
# ----------------------------
load_dotenv()

# Render에서 호스팅되는 백엔드 주소
BACKEND_URL = os.getenv("BACKEND_URL", "https://hidden-leaf-village.onrender.com").rstrip("/")

# ngrok 터널링된 외부 서버 주소
COMFYUI_URL = os.getenv("COMFYUI_URL", "").rstrip("/")
TRANSLATION_BRIDGE_URL = os.getenv("TRANSLATION_BRIDGE_URL", "").rstrip("/")

# 데이터 저장 루트 (uploads / outputs)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
)

# ----------------------------
# 2. FastAPI 앱 설정
# ----------------------------
app = FastAPI(
    title="ad-gen-service",
    description="소상공인을 위한 광고 콘텐츠 생성 서비스 (메뉴판 / 이미지 / 광고문구)",
    version="1.0.0",
)

# ----------------------------
# 3. CORS 허용
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 시에는 Render 도메인만 허용 가능
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# ✅ 4-1. 정적 파일 경로 설정 (추가 부분)
# ----------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]  # hidden-leaf-village/
STATIC_DIR = ROOT_DIR / "static"
OUTPUT_DIR = ROOT_DIR / "data" / "outputs"

# /static → static/images, static/fonts 등
app.mount("/static", StaticFiles(directory=ROOT_DIR / "data"), name="static")
app.mount("/outputs", StaticFiles(directory=ROOT_DIR / "data" / "outputs"), name="outputs")

# ----------------------------
# 4. 라우터 등록
# ----------------------------
from routes import copy_from_image, image_from_copy, menu_service

app.include_router(copy_from_image.router, prefix="/generate", tags=["copy_from_image"])
app.include_router(image_from_copy.router, prefix="/generate", tags=["image_from_copy"])
app.include_router(menu_service.router, prefix="/generate", tags=["menu_service"])

# ----------------------------
# 5. 헬스체크 & 연결 상태 확인
# ----------------------------
@app.get("/")
def health_check():
    """
    Render에 배포된 FastAPI 서버의 기본 루트.
    ngrok으로 연결된 서버 주소를 함께 반환해줌.
    """
    return {
        "ok": True,
        "backend": BACKEND_URL,
        "comfyui_tunnel": COMFYUI_URL,
        "translation_tunnel": TRANSLATION_BRIDGE_URL,
        "storage_root": STORAGE_ROOT,
    }

# ----------------------------
# 6. 서버 시작 메시지 (선택)
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    print(f"✅ FastAPI started on {BACKEND_URL}")
    print(f"🌉 ComfyUI via: {COMFYUI_URL}")
    print(f"🈶 Translation via: {TRANSLATION_BRIDGE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
