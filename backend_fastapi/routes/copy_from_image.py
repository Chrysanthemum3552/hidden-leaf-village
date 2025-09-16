"""
모듈: copy_from_image.py
역할: 업로드된 '이미지'를 OpenAI 비전 모델에 넣어 '한국어 광고 카피'를 생성하는 FastAPI 라우터.

핵심 포인트
- 안정성: requests.Session + Retry로 429/5xx 재시도, (connect, read) 타임아웃 분리
- 입력 검증: 확장자/용량 조기 검사 → 잘못된 입력 빠르게 차단
- 폴백: 지정/기본 모델 오류(400/404) 시 FALLBACK 모델로 자동 재시도
- 로깅: 이미지 경로/컨텍스트/결과/토큰 사용량을 텍스트로 기록
- 응답: 로컬 경로(uploaded_path) + 정적 URL(uploaded_url) 둘 다 제공 → 프론트가 URL로 안전 렌더

환경변수(.env)
- TEAM_GPT_BASE_URL, TEAM_GPT_API_KEY
- BACKEND_PUBLIC_URL (예: http://localhost:8000)
- STORAGE_ROOT (기본: routes/../../data)
- OPENAI_VISION_MODEL, OPENAI_VISION_FALLBACK_MODEL
- MAX_FILE_MB
엔드포인트: POST /copy-from-image
"""

import os, uuid, base64, mimetypes, json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from dotenv import load_dotenv

# ── .env 로드: repo-root/.env 를 항상 읽도록 경로를 상위 2단계로 계산
#    (routes/ → backend_fastapi/ → repo-root/)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)  # 셸/컨테이너 변수보다 .env를 우선 적용

router = APIRouter()

# ── 환경변수/기본값: 코드 수정 없이 환경만 바꿔서 동작 전환 가능
OPENAI_BASE = os.getenv("TEAM_GPT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_KEY = os.getenv("TEAM_GPT_API_KEY")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

# ── 파일 저장 경로: 기본은 backend_fastapi/data (현재 구조와 일치)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
UPLOAD_DIR = os.path.join(STORAGE_ROOT, "uploads")
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 모델 기본/폴백: 주 모델 이슈시 서비스 연속성 확보
MODEL_VISION = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
MODEL_FALLBACK = os.getenv("OPENAI_VISION_FALLBACK_MODEL", "gpt-4o")

# ── 입력 검증 정책: 과대용량/유효하지 않은 확장자 조기 차단
MAX_FILE_MB = float(os.getenv("MAX_FILE_MB", "15"))
ALLOWED_EXTS = {"jpg", "jpeg", "png", "webp"}

def _headers():
    """OpenAI 호출 헤더 구성. 키가 없으면 즉시 500으로 실패시켜 문제를 빠르게 드러냄."""
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key missing")
    h = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    org = os.getenv("OPENAI_ORG_ID")
    proj = os.getenv("OPENAI_PROJECT_ID")
    if org:  h["OpenAI-Organization"] = org
    if proj: h["OpenAI-Project"] = proj
    return h

def _to_data_url(content: bytes, content_type: Optional[str]) -> str:
    """이미지를 base64 data URL로 변환하여 Chat API에 바로 첨부(외부 스토리지 불필요)."""
    b64 = base64.b64encode(content).decode("utf-8")
    ct = content_type or "image/png"
    return f"data:{ct};base64,{b64}"

def _requests_session() -> requests.Session:
    """네트워크 일시 오류(429/5xx)를 흡수하기 위한 Session + Retry 구성.
    - backoff_factor=0.5: 0.5s, 1.0s 순으로 지수 백오프
    - timeout은 POST 호출 시 (connect=10s, read=120s)로 별도 지정
    """
    s = requests.Session()
    retry = Retry(
        total=2, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def _now() -> str:
    """로그/파일명에 쓰는 타임스탬프 포맷(충돌 방지 + 추적 용이)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

@router.post("/copy-from-image")
async def copy_from_image(
    file: UploadFile = File(...),
    # ▼ 옵션 파라미터: 안 줘도 기존 호출과 100% 하위호환. 주면 카피 품질을 세밀 제어.
    tone: str = Form("짧고 강렬, 자연스러운 한국어"),
    platform: Optional[str] = Form(None),             # instagram/naver/coupang/smartstore/x
    target_audience: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    product: Optional[str] = Form(None),
    char_limit_headline: int = Form(24),
    char_limit_subline: int = Form(48),
    hashtags_n: int = Form(3),
    model_override: Optional[str] = Form(None),
):
    try:
        # 0) 입력 검증: 보안/안정성을 위해 초기에 거른다.
        ext = (file.filename.split(".")[-1] or "").lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}. Allowed: {sorted(ALLOWED_EXTS)}")

        content = await file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            raise HTTPException(status_code=400, detail=f"File too large: {size_mb:.2f} MB (limit {MAX_FILE_MB} MB)")

        # 업로드 헤더가 비어 있는 경우도 있어 MIME 추정으로 보정
        content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"

        # 1) 파일 저장: 타임스탬프 + UUID로 이름 충돌/덮어쓰기 방지
        save_name = f"upload_{_now()}_{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(UPLOAD_DIR, save_name)
        with open(save_path, "wb") as f:
            f.write(content)

        # 2) 이미지 → data URL 변환: 외부 업로드 없이 곧장 Chat API에 첨부
        image_data_url = _to_data_url(content, content_type)

        # 2-1) 플랫폼 힌트 (※ 추가 사항)
        #  - 이전 코드에는 없던 선택 요소. 채널 특성을 '가볍게' 반영하기 위해 넣어본 가이드입니다.
        #  - 비워도 동작에 영향 없음(문맥 강화 용도). 필요 없으면 프론트에서 전달 생략 가능.
        platform_hint = {
            "instagram": "인스타그램은 짧고 강렬, 해시태그 친화적.",
            "naver": "네이버는 정보성/신뢰감 강조.",
            "coupang": "커머스 톤, 혜택/가격/배송 강조.",
            "smartstore": "스마트스토어 톤, 혜택·구성·신뢰 포인트.",
            "x": "X(트위터)는 초단문 이목집중."
        }.get((platform or "").lower(), "플랫폼 일반 톤.")

        # 2-2) 프롬프트 문맥: 길이 제한/타깃 등을 명문화하여 톤 일관성 확보
        base_text = (
            f"이 이미지에 어울리는 광고 문구를 만들어줘.\n"
            f"톤앤매너: {tone}\n"
            f"플랫폼 가이드: {platform_hint}\n"
            f"타깃: {target_audience or '일반 소비자'}\n"
            f"브랜드: {brand or 'N/A'} / 제품: {product or '이미지 기반 추론'}\n"
            f"헤드라인 {char_limit_headline}자 이내, 서브라인 {char_limit_subline}자 이내, 해시태그 {hashtags_n}개 이내.\n"
            f"헤드라인 1줄 + 서브라인 1줄 + 해시태그 제안."
        )

        # 3) OpenAI Chat Completions 호출
        url = f"{OPENAI_BASE}/chat/completions"
        payload = {
            "model": (model_override or MODEL_VISION),  # 모델 강제 교체가 필요하면 model_override 사용
            "messages": [
                {
                    "role": "system",
                    "content": "You are an advertising copywriter. Output concise Korean ad copy that reads naturally."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": base_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}}
                    ]
                },
            ],
            "temperature": 0.8,
        }

        session = _requests_session()

        # 3-1) 1차 호출
        r = session.post(url, headers=_headers(), json=payload, timeout=(10, 120))
        if r.status_code >= 400:
            # 3-2) 모델 자체 이슈(400/404)면 폴백 모델로 재시도 → 가용성 유지
            if r.status_code in (400, 404) and (model_override or MODEL_VISION) != MODEL_FALLBACK:
                payload["model"] = MODEL_FALLBACK
                r = session.post(url, headers=_headers(), json=payload, timeout=(10, 120))
        r.raise_for_status()

        # 4) 결과 파싱: 단순/안전하게 첫 메시지의 content만 사용
        data = r.json()
        copy = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        copy = (copy or "").strip()

        # 5) 로깅: 재현성/디버깅/분석을 위해 컨텍스트와 함께 저장
        log_name = f"copy_from_image_{_now()}_{uuid.uuid4().hex[:8]}.txt"
        log_path = os.path.join(OUTPUT_DIR, log_name)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"[IMAGE]\n{os.path.abspath(save_path)}\n\n")
            f.write(f"[CONTEXT]\n")
            ctx = {
                "tone": tone, "platform": platform, "target_audience": target_audience,
                "brand": brand, "product": product,
                "char_limit_headline": char_limit_headline,
                "char_limit_subline": char_limit_subline,
                "hashtags_n": hashtags_n,
                "model": payload["model"],
            }
            f.write(json.dumps(ctx, ensure_ascii=False, indent=2))
            f.write("\n\n[COPY]\n")
            f.write(copy)
            usage = data.get("usage")
            if usage:
                f.write("\n\n[USAGE]\n")
                f.write(json.dumps(usage, ensure_ascii=False, indent=2))

        # 6) 응답: 프론트는 uploaded_url(정적 URL) 사용 권장. uploaded_path는 보조 용도.
        uploaded_path = os.path.abspath(save_path).replace("\\", "/")
        uploaded_url = f"{BACKEND_PUBLIC_URL}/static/uploads/{save_name}"
        log_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{log_name}"

        return {
            "ok": True,
            "copy": copy,
            "uploaded_path": uploaded_path,   # 로컬 경로(디버그/내부용)
            "uploaded_url": uploaded_url,     # 정적 URL(프론트 렌더용 권장)
            "log_path": os.path.abspath(log_path).replace("\\", "/"),
            "log_url": log_url,
        }

    except requests.RequestException as e:
        # OpenAI 응답 전문(resp.text)을 detail에 동봉 → 문제 원인 파악이 쉬움
        resp = getattr(e, "response", None)
        detail = f"OpenAI error: {e}"
        if resp is not None:
            try:
                detail += f"\n{resp.text}"
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=detail)
    except HTTPException:
        # 위에서 명시적으로 던진 HTTPException은 그대로 전달
        raise
    except Exception as e:
        # 예측하지 못한 예외는 500으로 래핑
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
