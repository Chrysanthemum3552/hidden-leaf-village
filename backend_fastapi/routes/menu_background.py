from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Tuple, List
from PIL import Image
import os, requests, io, random

from openai import OpenAI

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class BgReq(BaseModel):
    concept: Optional[str] = None
    size: Tuple[int, int] = (1080, 1528)
    # ✅ [수정] menu_redesigner.py로부터 받을 새로운 디자인 파라미터 추가
    design_keywords: Optional[List[str]] = Field(None, description="AI가 생성한 디자인 핵심 키워드")
    color_palette: Optional[List[str]] = Field(None, description="AI가 추천한 HEX 색상 코드 리스트")


def generate_dalle_background(keywords: List[str], colors: List[str], size: Tuple[int, int]) -> Optional[Image.Image]:
    """DALL-E 3를 사용하여 메뉴판 배경 이미지를 생성합니다."""

    # AI 프롬프트 엔지니어링: 키워드와 색상을 바탕으로 DALL-E에게 보낼 명령어를 구체적으로 작성
    prompt = (
        f"A high-quality menu background image for a restaurant. "
        f"The overall style is inspired by: {', '.join(keywords)}. "
        f"The primary color palette should be: {', '.join(colors)}. "
        f"The design must be artistic, abstract, and minimalist, with plenty of empty space in the center for text. "
        f"Avoid any text or letters in the image. It should be a pure background texture or pattern."
    )

    try:
        print(f"🎨 DALL-E Prompt: {prompt}")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",  # DALL-E 3가 지원하는 세로 비율 사이즈
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url

        # 생성된 이미지를 다운로드하여 PIL Image 객체로 변환
        res = requests.get(image_url)
        res.raise_for_status()
        dalle_image = Image.open(io.BytesIO(res.content))

        # 요청된 사이즈로 리사이즈
        return dalle_image.resize(size, Image.Resampling.LANCZOS)

    except Exception as e:
        print(f"❌ DALL-E image generation failed: {e}")
        return None


@router.post("/menu-background")
def make_menu_background(req: BgReq):
    # ✅ [수정] DALL-E 이미지 생성 로직을 기본으로 사용
    if req.design_keywords and req.color_palette:
        img = generate_dalle_background(req.design_keywords, req.color_palette, req.size)
    else:
        # 키워드가 없는 경우, 기존 컨셉으로 간단한 그라데이션 배경 생성 (Fallback)
        print("⚠️ Design keywords not provided. Falling back to simple gradient.")
        img = Image.new("RGB", req.size, "#F0F0F0")

    if not img:
        return {"ok": False, "error": "AI background generation failed."}

    storage = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    out_dir = os.path.join(storage, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"bg_dalle_{random.randint(0, 999999):06}.png"
    img.save(os.path.join(out_dir, fname), "PNG")

    base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    return {"ok": True, "background_url": f"{base}/static/outputs/{fname}", "theme": "dalle_generated"}