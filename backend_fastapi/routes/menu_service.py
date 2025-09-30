# backend_fastapi/routes/menu_service.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import os, io, requests, random, json, base64, numpy as np
import textwrap

from openai import OpenAI

# ──────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
router = APIRouter()

# 폰트/경로
FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
GOOGLE_FONTS_API_KEY = os.getenv("GOOGLE_FONTS_API_KEY")
GOOGLE_FONTS_LIST_CACHE: Optional[List[Dict[str, Any]]] = None

FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fonts"))
DEFAULT_FONT_REGULAR = os.path.join(FONT_DIR, "NotoSansKR-Regular.ttf")

# 저장 루트: routes 기준 2단계 ↑ 의 data (main.py와 동일한 project_root/data)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)

# ──────────────────────────────────────────────────────────────────
# Pydantic 모델
# ──────────────────────────────────────────────────────────────────
class RedesignReq(BaseModel):
    target_image_url: str = Field(..., description="기존 메뉴판 이미지의 URL")
    redesign_request: str = Field(..., description="재디자인을 위한 컨셉 요청")

class BgReq(BaseModel):
    size: Tuple[int, int] = (1080, 1528)
    design_keywords: Optional[List[str]] = Field(None)
    color_palette: Optional[List[str]] = Field(None)

class MenuItem(BaseModel):
    name: str
    price: int
    desc: Optional[str] = None

class MenuReq(BaseModel):
    shop_name: Optional[str] = None
    theme: Optional[str] = None
    title: Optional[str] = None
    background_url: Optional[str] = None
    font_styles: Optional[List[str]] = None
    items: List[MenuItem]
    auto_desc: Optional[bool] = False
    model: Optional[str] = "gpt-4o-mini"
    temperature: Optional[float] = 0.7

# ──────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────
def _safe_open_image_from_bytes(b: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(b))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img

def get_base64_image(image_url: str) -> Optional[str]:
    try:
        r = requests.get(image_url, timeout=15)
        r.raise_for_status()
        img = _safe_open_image_from_bytes(r.content)
        buff = io.BytesIO()
        img.save(buff, format="JPEG", quality=92)
        return base64.b64encode(buff.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[get_base64_image] failed: {e}")
        return None

def gpt_analyze_and_design(base64_img: str, request_txt: str) -> dict:
    system_prompt = f"""
당신은 메뉴판을 재디자인하는 전문 '아트 디렉터'입니다.
아래 JSON 스키마를 반드시 따르세요.

필수 키:
- MenuItems: 배열. 각 항목은 {{ "name": str, "price": int, "desc": str(옵션) }}
- NewTitle: 문자열
- DesignKeywords: 3~5개 영어 키워드 (배경 스타일)
- ColorPalette: 2~3개 HEX 색상 (예: ["#112233","#abcdef"])
- FontStyles: 2개 스타일 설명 (예: ["붓글씨 제목체","고딕 본문체"])

사용자 요청: "{request_txt}"
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "메뉴판 이미지를 분석하고 재디자인 파라미터를 JSON으로 생성해줘."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]}
            ]
        )
        content = resp.choices[0].message.content
        return json.loads(content) if content else {}
    except Exception as e:
        print(f"[gpt_analyze_and_design] error: {e}")
        return {}

def _openai_image_to_pil(img_obj: Any, size: Tuple[int, int]) -> Optional[Image.Image]:
    """
    OpenAI images.generate 응답의 data[0]가 url 또는 b64_json일 수 있음.
    둘 다 안전하게 처리.
    """
    try:
        if getattr(img_obj, "url", None):
            res = requests.get(img_obj.url, timeout=20)
            res.raise_for_status()
            pil = _safe_open_image_from_bytes(res.content)
        elif getattr(img_obj, "b64_json", None):
            raw = base64.b64decode(img_obj.b64_json)
            pil = _safe_open_image_from_bytes(raw)
        else:
            return None
        return pil.resize(size, Image.Resampling.LANCZOS).convert("RGB")
    except Exception as e:
        print(f"[_openai_image_to_pil] failed: {e}")
        return None

def generate_dalle_background(keywords: List[str], colors: List[str], size: Tuple[int, int]) -> Optional[Image.Image]:
    if not keywords or not colors:
        return Image.new("RGB", size, "#F0F0F0")

    prompt = (
        "A high-quality restaurant menu background. "
        f"Style keywords: {', '.join(keywords)}. "
        f"Color palette: {', '.join(colors)}. "
        "Artistic, abstract, minimalist; lots of negative space; "
        "NO letters, NO text; pure background texture."
    )
    # 1차: dall-e-3, 2차: gpt-image-1 폴백
    for model_name in ("dall-e-3", "gpt-image-1"):
        try:
            resp = client.images.generate(
                model=model_name,
                prompt=prompt,
                size="1024x1792",
                quality="standard",
                n=1
            )
            img = _openai_image_to_pil(resp.data[0], size)
            if img is not None:
                return img
        except Exception as e:
            print(f"[generate_dalle_background] {model_name} failed: {e}")

    # 최종 폴백: 단색
    return Image.new("RGB", size, "#F0F0F0")

def _fallback_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(DEFAULT_FONT_REGULAR, size)
    except Exception:
        return ImageFont.load_default()

def get_google_font(style_desc: str, size: int) -> ImageFont.ImageFont:
    """
    style_desc에 '명조','손글씨' 등의 한글 키워드가 들어오면
    Google Fonts category를 유추. 실패 시 폴백 폰트.
    + 동일 (style_desc, size) 조합은 캐시.
    """
    cache_key = (style_desc or "sans", size)
    if cache_key in FONT_CACHE:
        return FONT_CACHE[cache_key]

    if not GOOGLE_FONTS_API_KEY:
        f = _fallback_font(size)
        FONT_CACHE[cache_key] = f
        return f
    try:
        global GOOGLE_FONTS_LIST_CACHE
        if not GOOGLE_FONTS_LIST_CACHE:
            resp = requests.get(
                f"https://www.googleapis.com/webfonts/v1/webfonts?key={GOOGLE_FONTS_API_KEY}&sort=popularity",
                timeout=20
            )
            resp.raise_for_status()
            GOOGLE_FONTS_LIST_CACHE = resp.json().get("items", [])

        if "명조" in (style_desc or "") or "serif" in (style_desc or "").lower():
            category = "serif"
        elif "손글씨" in (style_desc or "") or "hand" in (style_desc or "").lower():
            category = "handwriting"
        else:
            category = "sans-serif"

        candidates = [f for f in GOOGLE_FONTS_LIST_CACHE
                      if "korean" in f.get("subsets", []) and f.get("category") == category]

        font_url = None
        if candidates:
            selected = random.choice(candidates)
            if "files" in selected:
                font_url = selected["files"].get("regular") or next(iter(selected["files"].values()), None)

        if font_url:
            f_res = requests.get(font_url, timeout=20)
            f_res.raise_for_status()
            font = ImageFont.truetype(io.BytesIO(f_res.content), size)
        else:
            font = _fallback_font(size)

        FONT_CACHE[cache_key] = font
        return font
    except Exception as e:
        print(f"[get_google_font] fallback due to: {e}")
        f = _fallback_font(size)
        FONT_CACHE[cache_key] = f
        return f

def get_text_color(background: Image.Image) -> str:
    thumb = background.resize((48, 48)).convert("L")
    mean_val = float(np.array(thumb).mean())
    return "#333333" if mean_val > 128 else "#FFFFFF"

def _textsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if not text:
        return []
    # 대충 2~3회전으로 맞추기: 폭이 넘치면 단어 단위 wrap
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _textsize(draw, test, font)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def render_menu(req: MenuReq) -> Image.Image:
    # 입력 방어
    if not req.items or len(req.items) == 0:
        raise ValueError("items가 비어 있습니다.")
    for it in req.items:
        if not isinstance(it.price, int):
            try:
                it.price = int(it.price)  # 문자열 숫자 방어
            except Exception:
                it.price = 0

    w, h = 1080, 1528

    # 배경 준비
    if req.background_url:
        try:
            r = requests.get(req.background_url, timeout=15)
            r.raise_for_status()
            bg = _safe_open_image_from_bytes(r.content)
            canvas = bg.resize((w, h), Image.Resampling.LANCZOS).convert("RGB")
        except Exception as e:
            print(f"[render_menu] background load failed: {e}")
            canvas = Image.new("RGB", (w, h), (255, 255, 255))
    else:
        canvas = Image.new("RGB", (w, h), (255, 255, 255))

    draw = ImageDraw.Draw(canvas)
    text_color = get_text_color(canvas)

    # 폰트
    final_title = req.title or req.shop_name or "Menu"
    title_font_style = req.font_styles[0] if req.font_styles else (req.theme or "고딕")
    item_font_style  = req.font_styles[1] if (req.font_styles and len(req.font_styles) > 1) else (req.theme or "고딕")

    title_font = get_google_font(title_font_style, 78)
    item_font  = get_google_font(item_font_style, 44)
    desc_font  = get_google_font(item_font_style, 30)

    # 타이틀 (중앙 정렬)
    title_w, title_h = _textsize(draw, final_title, title_font)
    draw.text(((w - title_w) // 2, 110), final_title, font=title_font, fill=text_color)

    # 아이템 리스트
    y = 240
    left_x = 120
    right_margin = 120
    line_gap = 24
    desc_max_width = w - left_x - right_margin

    for it in req.items:
        name = it.name.strip()
        price_str = f"{it.price:,}원"

        # 좌측 이름
        draw.text((left_x, y), name, font=item_font, fill=text_color)

        # 우측 가격 (오른쪽 정렬)
        price_w, price_h = _textsize(draw, price_str, item_font)
        draw.text((w - right_margin - price_w, y), price_str, font=item_font, fill=text_color)
        y += max(price_h, 44) + 6

        # 설명 (존재 시 줄바꿈)
        if it.desc:
            for line in _wrap_text(draw, it.desc.strip(), desc_font, desc_max_width):
                draw.text((left_x, y), line, font=desc_font, fill=text_color)
                y += _textsize(draw, line, desc_font)[1] + 4

        y += line_gap

    return canvas

# ──────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────
@router.post("/redesign/menu-board", tags=["Menu Redesign"])
def redesign_menu_board_endpoint(req: RedesignReq):
    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

    base64_img = get_base64_image(req.target_image_url)
    if not base64_img:
        raise HTTPException(status_code=400, detail="이미지 URL 로드 실패")

    design_data = gpt_analyze_and_design(base64_img, req.redesign_request)
    if not design_data or "MenuItems" not in design_data:
        raise HTTPException(status_code=500, detail="AI 이미지 분석 실패")

    try:
        # 1) 배경 생성
        bg_req_data = {
            "design_keywords": design_data.get("DesignKeywords", []),
            "color_palette": design_data.get("ColorPalette", []),
        }
        bg_resp = requests.post(f"{base_url}/generate/menu-background", json=bg_req_data, timeout=60)
        bg_resp.raise_for_status()
        new_bg_url = bg_resp.json().get("background_url")

        # 2) 메뉴 보드 생성
        menu_req_data = {
            "title": design_data.get("NewTitle") or "Menu",
            "items": design_data["MenuItems"],
            "auto_desc": True,
            "background_url": new_bg_url,
            "font_styles": design_data.get("FontStyles", []),
        }
        board_resp = requests.post(f"{base_url}/generate/menu-board", json=menu_req_data, timeout=60)
        board_resp.raise_for_status()
        return board_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재디자인 중 오류 발생: {e}")

@router.post("/menu-background", tags=["Image Generation"])
def make_menu_background_endpoint(req: BgReq):
    img = generate_dalle_background(req.design_keywords or [], req.color_palette or [], req.size)
    if not img:
        raise HTTPException(status_code=500, detail="AI 배경 생성 실패")

    storage = os.path.join(STORAGE_ROOT, "outputs")
    os.makedirs(storage, exist_ok=True)

    fname = f"bg_{random.randint(0, 999999):06}.png"
    img.save(os.path.join(storage, fname), "PNG", optimize=True)

    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    return {"ok": True, "background_url": f"{base_url}/static/outputs/{fname}"}

@router.post("/menu-board", tags=["Image Generation"])
def generate_menu_endpoint(req: MenuReq):
    try:
        img = render_menu(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"렌더링 실패: {e}")

    storage = os.path.join(STORAGE_ROOT, "outputs")
    os.makedirs(storage, exist_ok=True)

    fname = f"menu_{random.randint(0, 999999):06}.png"
    output_path = os.path.join(storage, fname)
    try:
        img.save(output_path, "PNG", optimize=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 저장 실패: {e}")

    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    public_url = f"{base_url}/static/outputs/{fname}"
    return {"ok": True, "url": public_url}

@router.post("/menu-board", tags=["Image Generation"])
def generate_menu_endpoint(req: MenuReq):
    try:
        img = render_menu(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"렌더링 실패: {e}")

    storage = os.path.join(STORAGE_ROOT, "outputs")
    os.makedirs(storage, exist_ok=True)

    fname = f"menu_{random.randint(0, 999999):06}.png"
    output_path = os.path.join(storage, fname)
    try:
        img.save(output_path, "PNG", optimize=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 저장 실패: {e}")

    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    public_url = f"{base_url}/static/outputs/{fname}"

    return {
        "ok": True,
        "url": public_url,                 # 기존 키 유지
        "image_url": public_url,           # 프론트가 이 키를 볼 가능성이 큼
        "path": f"/static/outputs/{fname}",# 디버깅/로깅용(선택)
        "filename": fname                  
    }


