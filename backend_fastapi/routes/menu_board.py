from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
import os, io, requests, random, numpy as np

from openai import OpenAI

client = OpenAI(api_key=os.getenv("TEAM_GPT_API_KEY"))
router = APIRouter()

FONT_CACHE = {}
GOOGLE_FONTS_API_KEY = os.getenv("GOOGLE_FONTS_API_KEY")
GOOGLE_FONTS_LIST_CACHE = None


class MenuItem(BaseModel):
    name: str
    price: int
    desc: Optional[str] = None
    badge: Optional[str] = None


class MenuReq(BaseModel):
    title: Optional[str] = None
    items: List[MenuItem]
    theme: Optional[str] = None
    background_url: Optional[str] = None
    auto_desc: Optional[bool] = True
    model: Optional[str] = "gpt-4o-mini"
    temperature: Optional[float] = 0.7
    font_styles: Optional[List[str]] = None


def get_google_font(style: str, size: int) -> ImageFont.ImageFont:
    """구글 폰트에서 스타일과 한글을 지원하는 폰트를 찾아 다운로드하고 로드합니다."""
    cache_key = f"{style.lower()}_{size}"
    if cache_key in FONT_CACHE:
        font_path = FONT_CACHE[cache_key]
        font_path.seek(0)
        return ImageFont.truetype(font_path, size)

    default_font = ImageFont.load_default()
    if not GOOGLE_FONTS_API_KEY:
        print("⚠️ GOOGLE_FONTS_API_KEY is not set. Using default font.")
        return default_font

    global GOOGLE_FONTS_LIST_CACHE
    try:
        if not GOOGLE_FONTS_LIST_CACHE:
            print("Fetching Google Fonts list...")
            response = requests.get(
                f"https://www.googleapis.com/webfonts/v1/webfonts?key={GOOGLE_FONTS_API_KEY}&sort=popularity")
            response.raise_for_status()
            GOOGLE_FONTS_LIST_CACHE = response.json().get("items", [])

        style_keywords = []
        if any(s in style for s in ["붓글씨", "calligraphy", "serif", "명조"]):
            style_keywords.append("serif")
        if any(s in style for s in ["손글씨", "handwriting", "pen"]):
            style_keywords.append("handwriting")
        if any(s in style for s in ["고딕", "gothic", "sans-serif"]):
            style_keywords.append("sans-serif")

        candidate_fonts = []
        for f in GOOGLE_FONTS_LIST_CACHE:
            if "korean" in f.get("subsets", []):
                if f.get("category") in style_keywords or any(
                        kw.replace("-", "") in f["family"].lower().replace(" ", "") for kw in style_keywords):
                    candidate_fonts.append(f)

        if not candidate_fonts:
            print(f"No specific font found for style '{style}'. Falling back to Noto Sans KR.")
            candidate_fonts = [f for f in GOOGLE_FONTS_LIST_CACHE if f["family"] == "Noto Sans KR"]

        chosen_font = random.choice(candidate_fonts)
        print(f"Selected font for style '{style}': {chosen_font['family']}")

        files = chosen_font.get("files", {})
        font_url = files.get("regular") or files.get("400") or next(iter(files.values()), None)

        if not font_url:
            raise ValueError(f"No font file URL found for {chosen_font['family']}")

        font_res = requests.get(font_url)
        font_res.raise_for_status()
        font_path = io.BytesIO(font_res.content)
        FONT_CACHE[cache_key] = font_path
        font_path.seek(0)

        return ImageFont.truetype(font_path, size)

    except Exception as e:
        print(f"❌ Failed to load Google Font for style '{style}': {e}. Using default font.")
        return default_font


def get_text_color(background: Image.Image) -> str:
    """배경 이미지의 평균 밝기를 계산하여 적절한 텍스트 색상을 반환합니다."""
    thumb = background.resize((50, 50)).convert("L")
    avg_brightness = np.mean(np.array(thumb))
    return "#333333" if avg_brightness > 128 else "#FFFFFF"


def gpt_desc(name: str, model: str, temperature: float) -> Optional[str]:
    """GPT로 간단 메뉴 설명 한 줄 생성 (실패 시 None)."""
    if not client.api_key: return None
    try:
        prompt = f"메뉴판에 들어갈 '{name}' 의 짧고 먹음직스러운 한국어 설명을 15자 이내로 한 줄로 써줘."
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}]
        )
        text = (resp.choices[0].message.content or "").strip().replace('"', '').replace("'", "")
        return text
    except Exception as e:
        print(f"gpt_desc failed: {e}")
        return None


def render_menu(req: MenuReq):
    w, h = 1080, 1528

    try:
        r = requests.get(req.background_url, timeout=10)
        r.raise_for_status()
        canvas = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        canvas = Image.new("RGBA", (w, h), (245, 245, 245, 255))

    draw = ImageDraw.Draw(canvas)
    text_color = get_text_color(canvas.convert("RGB"))

    title_font_style = req.font_styles[0] if req.font_styles and len(req.font_styles) > 0 else "고딕"
    item_font_style = req.font_styles[1] if req.font_styles and len(req.font_styles) > 1 else "고딕"

    title_font = get_google_font(title_font_style, 72)
    item_font = get_google_font(item_font_style, 42)
    desc_font = get_google_font(item_font_style, 30)

    if req.title:
        draw.text((w // 2, 150), req.title, font=title_font, fill=text_color, anchor="ms")

    y = 300
    for it in req.items:
        price = f"{it.price:,}원"
        draw.text((120, y), it.name, font=item_font, fill=text_color, anchor="ls")
        draw.text((w - 120, y), price, font=item_font, fill=text_color, anchor="rs")

        y += 60
        desc = it.desc

        # ✅ [수정] gpt_desc 호출 로직을 복원했습니다.
        if (desc is None or not str(desc).strip()) and req.auto_desc:
            desc = gpt_desc(it.name, req.model or "gpt-4o-mini", float(req.temperature or 0.7)) or ""

        if desc:
            draw.text((120, y), desc, font=desc_font, fill=text_color, anchor="ls")
            y += 40

        y += 40

    return canvas.convert("RGB")


@router.post("/menu-board")
def generate_menu(req: MenuReq):
    img = render_menu(req)
    storage = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    out_dir = os.path.join(storage, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"menu_{random.randint(0, 999999):06}.png"
    img.save(os.path.join(out_dir, fname), "PNG")
    base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    return {"ok": True, "file_url": f"{base}/static/outputs/{fname}"}
