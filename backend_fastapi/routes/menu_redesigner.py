from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional
from PIL import Image
import os, io, requests, random, json, re, base64

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
router = APIRouter()

# ... (RedesignReq, get_base64_image, gpt_analyze_and_design 함수는 이전과 동일) ...

class RedesignReq(BaseModel):
    target_image_url: str = Field(..., description="기존 메뉴판 이미지의 URL")
    redesign_request: str = Field(..., description="재디자인을 위한 컨셉 요청")


def get_base64_image(image_url: str) -> Optional[str]:
    """URL에서 이미지를 로드하고 Base64로 인코딩합니다."""
    try:
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))

        buffered = io.BytesIO()
        if img.mode == 'RGBA' or img.mode == 'P':
            img = img.convert('RGB')
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Image loading or encoding failed: {e}")
        return None


def gpt_analyze_and_design(base64_img: str, request: str) -> dict:
    """GPT Vision을 사용하여 이미지 분석 및 풍부한 디자인 파라미터를 생성합니다."""
    system_prompt = f"""
    당신은 메뉴판을 디자인하는 전문 '아트 디렉터'입니다.
    사용자의 이미지와 요청을 분석하여, 새로운 메뉴판 디자인에 필요한 모든 요소를 구체적인 JSON 형식으로 제공해야 합니다.

    1.  **MenuItems**: 이미지에서 모든 메뉴 항목(name, price)을 정확히 추출하세요. 가격은 정수형(쉼표 없이)으로 추출해야 합니다. 추출할 수 없으면 빈 배열 `[]`을 반환하세요.
    2.  **NewTitle**: 새로운 컨셉에 어울리는 창의적인 메뉴판 제목을 제안하세요.
    3.  **DesignKeywords**: 사용자 요청을 바탕으로 디자인 컨셉을 표현하는 핵심 키워드를 3~5개 영어로 제공하세요. (예: ["dark wood", "japanese calligraphy", "red lantern", "minimalist"])
    4.  **ColorPalette**: 디자인 컨셉에 어울리는 주요 색상 2~3개를 HEX 코드로 제안하세요. (예: ["#3D2B1F", "#D92525", "#FFFFFF"])
    5.  **FontStyles**: 메뉴 제목과 내용에 어울릴 폰트 스타일을 2가지 제안하세요. (예: ["붓글씨 제목체", "고딕 본문체"])

    사용자 요청: "{request}"

    응답은 반드시 아래 JSON 구조를 따라야 하며, 다른 설명은 절대 포함하지 마세요.
    {{
        "NewTitle": "예시: 교토의 밤",
        "MenuItems": [
            {{"name": "메뉴 이름", "price": 10000}}
        ],
        "DesignKeywords": ["keyword1", "keyword2", "keyword3"],
        "ColorPalette": ["#RRGGBB", "#RRGGBB"],
        "FontStyles": ["제목 폰트 스타일", "본문 폰트 스타일"]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "이 메뉴판 이미지를 분석하고, 주어진 요청에 맞춰 재디자인 파라미터를 JSON으로 생성해줘."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"GPT Vision Error: {e}")
        return {}


@router.post("/menu-board")
def redesign_menu_board(req: RedesignReq):
    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    bg_url_endpoint = f"{base_url}/generate/menu-background"
    board_url_endpoint = f"{base_url}/generate/menu-board"

    base64_img = get_base64_image(req.target_image_url)
    if not base64_img:
        return {"ok": False, "error": "제공된 이미지 URL에서 파일을 로드할 수 없거나 형식이 잘못되었습니다. (URL: " + req.target_image_url + ")"}

    design_data = gpt_analyze_and_design(base64_img, req.redesign_request)

    if not design_data or "MenuItems" not in design_data:
        return {"ok": False, "error": "AI가 이미지 분석에 실패했거나 유효한 디자인 파라미터를 생성하지 못했습니다. 서버 로그를 확인하거나 이미지를 변경해 보세요."}

    try:
        # ✅ [수정] API 요청 시 JSON 키를 소문자 snake_case로 변경
        bg_req_data = {
            "concept": req.redesign_request,
            "design_keywords": design_data.get("DesignKeywords", []),
            "color_palette": design_data.get("ColorPalette", []),
            "size": [1080, 1528]
        }

        bg_resp = requests.post(bg_url_endpoint, json=bg_req_data, timeout=60) # DALL-E 시간 고려하여 timeout 증가
        bg_resp.raise_for_status()
        new_bg_url = bg_resp.json().get("background_url")

        menu_req_data = {
            "title": design_data["NewTitle"],
            "items": design_data["MenuItems"],
            "auto_desc": True,
            "background_url": new_bg_url,
            "font_styles": design_data.get("FontStyles", []),
            "theme": design_data.get("DesignKeywords", ["modern"])[0]
        }

        board_resp = requests.post(board_url_endpoint, json=menu_req_data, timeout=20)
        board_resp.raise_for_status()
        return board_resp.json()

    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"내부 API 호출 오류가 발생했습니다. (Error: {e})"}
    except Exception as e:
        return {"ok": False, "error": f"재디자인 중 알 수 없는 오류가 발생했습니다: {e}"}