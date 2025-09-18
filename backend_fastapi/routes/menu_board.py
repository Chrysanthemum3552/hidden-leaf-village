import os, uuid, base64
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import io, requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image, ImageDraw  # 폴백용

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
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _headers():
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key missing")
    h = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    org = os.getenv("OPENAI_ORG_ID")
    proj = os.getenv("OPENAI_PROJECT_ID")
    if org:  h["OpenAI-Organization"] = org
    if proj: h["OpenAI-Project"] = proj
    return h

class MenuItem(BaseModel):
    name: str
    price: int
    desc: Optional[str] = None

class MenuReq(BaseModel):
    shop_name: Optional[str] = None
    items: List[MenuItem]
    background_url: Optional[str] = None
    theme: Optional[str] = "simple"

def _items_to_bullets(items: List[MenuItem]) -> str:
    lines = []
    for it in items:
        if it.desc:
            lines.append(f"- {it.name} (₩{it.price}): {it.desc}")
        else:
            lines.append(f"- {it.name} (₩{it.price})")
    return "\n".join(lines)

@router.post("/menu-board")
def menu_board(req: MenuReq):
    title = req.shop_name or "MENU"
    bullets = _items_to_bullets(req.items)
    theme = req.theme or "simple"

    prompt = (
        f"{theme} 스타일의 고해상도 음식점 메뉴 포스터를 디자인해줘. "
        f"제목: {title}. 깔끔한 헤더, 읽기 쉬운 항목 리스트, 적절한 간격, "
        f"테마에 맞는 은은한 장식, 한국어에 적합한 타이포그래피를 포함할 것. "
        f"메뉴 항목:\n{bullets}\n"
        "출력은 완성된 인쇄용 메뉴 포스터처럼 보여야 한다."
    )

    # 1) OpenAI Images API 시도 (정사각형만 허용됨)
    try:
        url = f"{OPENAI_BASE}/images/generations"
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "size": "1024x1024",  # 정사각형 (400 회피)
            "response_format": "b64_json",
        }
        r = requests.post(url, headers=_headers(), json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        b64 = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64)

        save_name = f"menu_board_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)
        with open(save_path, "wb") as f:
            f.write(img_bytes)

        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"
        return {"ok": True, "output_path": file_path, "file_url": file_url}

    except requests.RequestException:
        # 2) 실패 시 폴백: Pillow로 간단히 렌더
        img = Image.new("RGB", (1024, 1440), color=(250, 250, 245))
        d = ImageDraw.Draw(img)
        y = 40
        d.text((40, y), title, fill=(20, 20, 20)); y += 60
        d.text((40, y), f"Theme: {theme}", fill=(80, 80, 80)); y += 40
        d.text((40, y), "-" * 50, fill=(120, 120, 120)); y += 20

        for it in req.items:
            line = f"{it.name}  ......  ₩{it.price}"
            d.text((40, y), line, fill=(30, 30, 30)); y += 32
            if it.desc:
                d.text((60, y), it.desc, fill=(90, 90, 90)); y += 26
        y += 20
        d.text((40, y), "-" * 50, fill=(120, 120, 120))

        save_name = f"menu_board_fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)
        img.save(save_path)

        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"
        return {"ok": True, "output_path": file_path, "file_url": file_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
