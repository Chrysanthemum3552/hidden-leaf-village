from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import os, io, requests, random, json, base64, numpy as np

from openai import OpenAI

# --- 기본 설정 ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
router = APIRouter()  # 3개 파일이 공통으로 사용할 하나의 라우터

# --- 폰트 및 API 키 설정 ---
FONT_CACHE = {}
GOOGLE_FONTS_API_KEY = os.getenv("GOOGLE_FONTS_API_KEY")
GOOGLE_FONTS_LIST_CACHE = None
FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fonts"))
DEFAULT_FONT_REGULAR = os.path.join(FONT_DIR, "NotoSansKR-Regular.ttf")


# =====================================================================================
#  Pydantic 모델 정의 (3개 파일의 모델들을 모두 합침)
# =====================================================================================

class RedesignReq(BaseModel):
    target_image_url: str = Field(..., description="기존 메뉴판 이미지의 URL")
    redesign_request: str = Field(..., description="재디자인을 위한 컨셉 요청")


class BgReq(BaseModel):
    size: Tuple[int, int] = (1080, 1528)
    design_keywords: Optional[List[str]] = Field(None)
    color_palette: Optional[List[str]] = Field(None)


class MenuReq(BaseModel):
    shop_name: Optional[str] = None
    theme: Optional[str] = None
    title: Optional[str] = None
    background_url: Optional[str] = None
    font_styles: Optional[List[str]] = None
    items: List[dict]
    auto_desc: Optional[bool] = False
    model: Optional[str] = "gpt-4o-mini"
    temperature: Optional[float] = 0.7


# =====================================================================================
#  헬퍼 함수 정의 (3개 파일의 함수들을 모두 합침)
# =====================================================================================

def get_base64_image(image_url: str) -> Optional[str]:
    # ... (menu_redesigner.py의 함수)
    try:
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        buffered = io.BytesIO()
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Image loading failed: {e}")
        return None


def gpt_analyze_and_design(base64_img: str, request: str) -> dict:
    # ... (menu_redesigner.py의 함수)
    system_prompt = f"""
    당신은 메뉴판을 재디자인하는 전문 '아트 디렉터'입니다. 사용자의 이미지와 요청을 분석하여, 새로운 메뉴판 디자인에 필요한 모든 요소를 구체적인 JSON 형식으로 제공해야 합니다.
    1. MenuItems: 이미지에서 모든 메뉴 항목(name, price)을 정확히 추출하세요.
    2. NewTitle: 새로운 컨셉에 어울리는 창의적인 메뉴판 제목을 제안하세요.
    3. DesignKeywords: 사용자 요청을 바탕으로 디자인 컨셉을 표현하는 핵심 키워드를 3~5개 영어로 제공하세요.
    4. ColorPalette: 디자인 컨셉에 어울리는 주요 색상 2~3개를 HEX 코드로 제안하세요.
    5. FontStyles: 메뉴 제목과 내용에 어울릴 폰트 스타일을 2가지 제안하세요. (예: ["붓글씨 제목체", "고딕 본문체"])
    사용자 요청: "{request}"
    응답은 반드시 명시된 JSON 구조를 따라야 합니다.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.7, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "메뉴판 이미지를 분석하고 재디자인 파라미터를 생성해줘."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"GPT Vision Error: {e}")
        return {}


def generate_dalle_background(keywords: List[str], colors: List[str], size: Tuple[int, int]) -> Optional[Image.Image]:
    # ... (menu_background.py의 함수)
    prompt = (
        f"A high-quality menu background image for a restaurant. Style inspired by: {', '.join(keywords)}. "
        f"Primary color palette: {', '.join(colors)}. The design must be artistic, abstract, minimalist, with plenty of empty space for text. "
        f"Avoid any text or letters. Pure background texture or pattern."
    )
    try:
        response = client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1792", quality="standard", n=1)
        res = requests.get(response.data[0].url)
        res.raise_for_status()
        return Image.open(io.BytesIO(res.content)).resize(size, Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"DALL-E failed: {e}")
        return None


def get_google_font(style: str, size: int) -> ImageFont.ImageFont:
    # ... (menu_board.py의 함수)
    def get_fallback_font():
        try:
            return ImageFont.truetype(DEFAULT_FONT_REGULAR, size)
        except IOError:
            return ImageFont.load_default()

    if not GOOGLE_FONTS_API_KEY: return get_fallback_font()
    try:
        # (API 호출 로직은 이전과 동일하게 유지)
        global GOOGLE_FONTS_LIST_CACHE
        if not GOOGLE_FONTS_LIST_CACHE:
            resp = requests.get(
                f"https://www.googleapis.com/webfonts/v1/webfonts?key={GOOGLE_FONTS_API_KEY}&sort=popularity")
            resp.raise_for_status()
            GOOGLE_FONTS_LIST_CACHE = resp.json().get("items", [])
        style_kw = "serif" if "명조" in style else "handwriting" if "손글씨" in style else "sans-serif"
        candidates = [f for f in GOOGLE_FONTS_LIST_CACHE if
                      "korean" in f.get("subsets", []) and f.get("category") == style_kw]
        if not candidates: raise ValueError("Font not found")
        font_url = random.choice(candidates)["files"].get("regular")
        if not font_url: raise ValueError("URL not found")
        res = requests.get(font_url)
        res.raise_for_status()
        return ImageFont.truetype(io.BytesIO(res.content), size)
    except Exception as e:
        return get_fallback_font()


def get_text_color(background: Image.Image) -> str:
    # ... (menu_board.py의 함수)
    thumb = background.resize((50, 50)).convert("L")
    return "#333333" if np.mean(np.array(thumb)) > 128 else "#FFFFFF"


def render_menu(req: MenuReq):
    # ... (menu_board.py의 함수)
    w, h = 1080, 1528
    if req.background_url:
        try:
            r = requests.get(req.background_url, timeout=10)
            r.raise_for_status()
            canvas = Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception:
            canvas = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    else:
        canvas = Image.new("RGBA", (w, h), (255, 255, 255, 255))

    draw = ImageDraw.Draw(canvas)
    text_color = get_text_color(canvas.convert("RGB"))
    final_title = req.title or req.shop_name or "Menu"
    title_font_style = req.font_styles[0] if req.font_styles else (req.theme or "고딕")
    item_font_style = req.font_styles[1] if req.font_styles and len(req.font_styles) > 1 else (req.theme or "고딕")
    title_font = get_google_font(title_font_style, 72)
    item_font = get_google_font(item_font_style, 42)
    desc_font = get_google_font(item_font_style, 30)

    draw.text((w // 2, 150), final_title, font=title_font, fill=text_color, anchor="ms")
    y = 300
    for it in req.items:
        price_str = f"{it.get('price', 0):,}원"
        draw.text((120, y), it.get('name', ''), font=item_font, fill=text_color, anchor="ls")
        draw.text((w - 120, y), price_str, font=item_font, fill=text_color, anchor="rs")
        y += 60
        if it.get("desc"):
            draw.text((120, y), it["desc"], font=desc_font, fill=text_color, anchor="ls")
            y += 40
        y += 40
    return canvas.convert("RGB")


# =====================================================================================
#  API 엔드포인트 정의 (3개 파일의 엔드포인트를 모두 합침)
# =====================================================================================

@router.post("/redesign/menu-board", tags=["Menu Redesign"])
def redesign_menu_board_endpoint(req: RedesignReq):
    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

    base64_img = get_base64_image(req.target_image_url)
    if not base64_img: raise HTTPException(status_code=400, detail="이미지 URL 로드 실패")

    design_data = gpt_analyze_and_design(base64_img, req.redesign_request)
    if not design_data or "MenuItems" not in design_data:
        raise HTTPException(status_code=500, detail="AI 이미지 분석 실패")

    try:
        bg_req_data = {
            "design_keywords": design_data.get("DesignKeywords", []),
            "color_palette": design_data.get("ColorPalette", []),
        }
        bg_resp = requests.post(f"{base_url}/generate/menu-background", json=bg_req_data, timeout=60)
        bg_resp.raise_for_status()
        new_bg_url = bg_resp.json().get("background_url")

        menu_req_data = {
            "title": design_data["NewTitle"], "items": design_data["MenuItems"],
            "auto_desc": True, "background_url": new_bg_url,
            "font_styles": design_data.get("FontStyles", []),
        }
        board_resp = requests.post(f"{base_url}/generate/menu-board", json=menu_req_data, timeout=20)
        board_resp.raise_for_status()
        return board_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재디자인 중 오류 발생: {e}")


@router.post("/generate/menu-background", tags=["Image Generation"])
def make_menu_background_endpoint(req: BgReq):
    if req.design_keywords and req.color_palette:
        img = generate_dalle_background(req.design_keywords, req.color_palette, req.size)
    else:
        img = Image.new("RGB", req.size, "#F0F0F0")

    if not img: raise HTTPException(status_code=500, detail="AI 배경 생성 실패")

    storage = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "outputs"))
    os.makedirs(storage, exist_ok=True)
    fname = f"bg_dalle_{random.randint(0, 999999):06}.png"
    img.save(os.path.join(storage, fname), "PNG")

    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    return {"ok": True, "background_url": f"{base_url}/static/outputs/{fname}"}


@router.post("/generate/menu-board", tags=["Image Generation"])
def generate_menu_endpoint(req: MenuReq):
    img = render_menu(req)
    storage = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "outputs"))
    os.makedirs(storage, exist_ok=True)
    fname = f"menu_{random.randint(0, 999999):06}.png"
    output_path = os.path.join(storage, fname)
    img.save(output_path, "PNG")
    return {"ok": True, "output_path": output_path}