import os, uuid, base64
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, File, UploadFile, HTTPException
from dotenv import load_dotenv

# ---- env 로드 ----
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

OPENAI_BASE = os.getenv("TEAM_GPT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_KEY = os.getenv("TEAM_GPT_API_KEY")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
UPLOAD_DIR = os.path.join(STORAGE_ROOT, "uploads")
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL_VISION = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

def _headers():
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key missing")
    h = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    org = os.getenv("OPENAI_ORG_ID")
    proj = os.getenv("OPENAI_PROJECT_ID")
    if org:  h["OpenAI-Organization"] = org
    if proj: h["OpenAI-Project"] = proj
    return h

def _to_data_url(content: bytes, content_type: str) -> str:
    b64 = base64.b64encode(content).decode("utf-8")
    ct = content_type or "image/png"
    return f"data:{ct};base64,{b64}"

@router.post("/copy-from-image")
async def copy_from_image(file: UploadFile = File(...)):
    try:
        # 1) 업로드 저장
        ext = (file.filename.split(".")[-1] or "png").lower()
        save_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(UPLOAD_DIR, save_name)
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        # 2) Vision 모델 호출(이미지를 base64 data URL로 전달)
        image_data_url = _to_data_url(content, file.content_type)

        url = f"{OPENAI_BASE}/chat/completions"
        payload = {
            "model": MODEL_VISION,
            "messages": [
                {"role": "system",
                 "content": "You are an advertising copywriter. Look at the image and write a concise, catchy Korean ad copy with 1-2 punchy lines, plus 3 short hashtag suggestions."},
                {"role": "user",
                 "content": [
                     {"type": "text", "text": "이 이미지에 어울리는 광고 문구를 만들어줘. 톤앤매너: 짧고 강렬, 자연스러운 한국어."},
                     {"type": "image_url", "image_url": {"url": image_data_url}}
                 ]},
            ],
            "temperature": 0.8,
        }

        r = requests.post(url, headers=_headers(), json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        copy = data["choices"][0]["message"]["content"].strip()

        # 3) 로그 저장
        log_name = f"copy_from_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.txt"
        log_path = os.path.join(OUTPUT_DIR, log_name)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"image_path: {os.path.abspath(save_path)}\ncopy:\n{copy}\n")

        # 4) 경로 + URL 반환
        uploaded_path = os.path.abspath(save_path).replace("\\", "/")
        uploaded_url = f"{BACKEND_PUBLIC_URL}/static/uploads/{save_name}"
        log_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{log_name}"

        return {
            "ok": True,
            "copy": copy,
            "uploaded_path": uploaded_path,
            "uploaded_url": uploaded_url,
            "log_path": os.path.abspath(log_path).replace("\\", "/"),
            "log_url": log_url,
        }
    except requests.RequestException as e:
        resp = getattr(e, "response", None)
        detail = f"OpenAI error: {e}"
        if resp is not None:
            try:
                detail += f"\n{resp.text}"
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
