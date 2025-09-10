import os, uuid, base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# ---- env 로드 (프로젝트 루트의 .env) ----
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

OPENAI_BASE = os.getenv("TEAM_GPT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_KEY = os.getenv("TEAM_GPT_API_KEY")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

class CopyToImageReq(BaseModel):
    text: str
    style: Optional[str] = None
    seed: Optional[int] = None  # OpenAI Images는 seed 직접 지원X

def _headers():
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key missing")
    h = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    org = os.getenv("OPENAI_ORG_ID")
    proj = os.getenv("OPENAI_PROJECT_ID")
    if org:  h["OpenAI-Organization"] = org
    if proj: h["OpenAI-Project"] = proj
    return h

@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    style_snippet = f" in {req.style} style" if req.style else ""
    prompt = (
        f'다음 문구에 어울리는 광고 이미지를 생성해줘{style_snippet}. '
        f'Ad copy: "{req.text}". 높은 퀄리티, sharp, clean composition.'
    )

    try:
        url = f"{OPENAI_BASE}/images/generations"
        payload = {
            # gpt-image-1 권한 이슈 있으면 dall-e-3 사용
            "model": "dall-e-3",
            "prompt": prompt,
            "size": "1024x1024",
        }

        r = requests.post(url, headers=_headers(), json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()

        # --- 호환 처리: b64_json 또는 url 모두 지원 ---
        try:
            datum = data["data"][0]
        except (KeyError, IndexError):
            raise HTTPException(status_code=502, detail=f"Unexpected image response: {data}")

        if "b64_json" in datum and datum["b64_json"]:
            img_bytes = base64.b64decode(datum["b64_json"])
        elif "url" in datum and datum["url"]:
            # URL 다운받아서 저장
            img_resp = requests.get(datum["url"], timeout=180)
            img_resp.raise_for_status()
            img_bytes = img_resp.content
        else:
            raise HTTPException(status_code=502, detail=f"Image data missing (keys={list(datum.keys())})")

        save_name = f"image_from_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)
        with open(save_path, "wb") as f:
            f.write(img_bytes)

        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"
        return {"ok": True, "output_path": file_path, "file_url": file_url}

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

