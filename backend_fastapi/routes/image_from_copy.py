import os, uuid, base64
import re  # 추가: 보안 필터링용
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

# 보안 필터링 설정
BLOCKED_KEYWORDS = {
    '무시하고', 'ignore', 'instead', '대신에', 'violence', '폭력', 'sexual', '성적', 
    'explicit', '노출', 'harmful', '유해', 'delete', '삭제', 'hack', '해킹',
    'nude', '나체', 'drug', '마약', 'weapon', '무기', 'blood', '피'
}

ALLOWED_STYLES = {
    "minimal", "modern", "vintage", "elegant", "bold", "artistic", 
    "professional", "casual", "luxury", "vibrant", "monochrome"
}

# 에러 메시지 상수 정의
class ErrorMessages:
    # 400 Bad Request
    TEXT_TOO_LONG = "텍스트 길이가 1000자를 초과합니다."
    TEXT_EMPTY = "유효한 텍스트를 입력해주세요."
    INVALID_STYLE = "지원하지 않는 스타일입니다."
    INVALID_SEED = "seed 값은 0 이상의 정수여야 합니다."
    MALFORMED_REQUEST = "요청 형식이 올바르지 않습니다."
    
    # 403 Forbidden
    CONTENT_BLOCKED = "부적절한 내용이 포함되어 있습니다."
    CONTENT_POLICY_VIOLATION = "콘텐츠 정책을 위반하는 내용입니다."
    
    # 429 Too Many Requests
    RATE_LIMIT_EXCEEDED = "요청 횟수 제한을 초과했습니다. 잠시 후 다시 시도해주세요."
    
    # 500 Internal Server Error
    CONFIG_ERROR = "서버 설정 오류가 발생했습니다."
    FILE_SAVE_ERROR = "이미지 파일 저장 중 오류가 발생했습니다."
    UNKNOWN_ERROR = "알 수 없는 서버 오류가 발생했습니다."
    
    # 502 Bad Gateway
    OPENAI_API_ERROR = "이미지 생성 서비스에 일시적인 문제가 발생했습니다."
    OPENAI_RESPONSE_ERROR = "이미지 생성 서비스로부터 올바르지 않은 응답을 받았습니다."
    IMAGE_DOWNLOAD_ERROR = "생성된 이미지 다운로드 중 오류가 발생했습니다."

class CopyToImageReq(BaseModel):
    text: str
    style: Optional[str] = None
    seed: Optional[int] = None

# 보안 필터링 함수들
def _sanitize_input(text: str) -> str:
    """기본 입력 정제"""
    if not text:
        return ""
    # 특수문자 제거, 길이 제한
    sanitized = re.sub(r'[^\w\s가-힣.,!?-]', '', text.strip())
    return sanitized[:500]

def _check_malicious_content(text: str) -> bool:
    """악성 키워드 검사"""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in BLOCKED_KEYWORDS)

def _validate_style(style: Optional[str]) -> Optional[str]:
    """스타일 검증"""
    if not style:
        return None
    clean_style = style.lower().strip()
    return clean_style if clean_style in ALLOWED_STYLES else None

def _validate_seed(seed: Optional[int]) -> Optional[int]:
    """seed 값 검증"""
    if seed is None:
        return None
    if not isinstance(seed, int) or seed < 0:
        raise HTTPException(
            status_code=400, 
            detail=ErrorMessages.INVALID_SEED
        )
    return seed

def _validate_and_clean_request(req: CopyToImageReq) -> CopyToImageReq:
    """요청 검증 및 정제"""
    try:
        # 기본 유효성 검사
        if not hasattr(req, 'text') or req.text is None:
            raise HTTPException(
                status_code=400, 
                detail=ErrorMessages.MALFORMED_REQUEST
            )
        
        # 텍스트 길이 체크 (400 Bad Request)
        if len(req.text) > 1000:
            raise HTTPException(
                status_code=400, 
                detail=ErrorMessages.TEXT_TOO_LONG
            )
        
        # 악성 콘텐츠 체크 (403 Forbidden)
        if _check_malicious_content(req.text):
            raise HTTPException(
                status_code=403, 
                detail=ErrorMessages.CONTENT_BLOCKED
            )
        
        # 입력 정제
        clean_text = _sanitize_input(req.text)
        if not clean_text.strip():
            raise HTTPException(
                status_code=400, 
                detail=ErrorMessages.TEXT_EMPTY
            )
        
        # 스타일 검증
        validated_style = _validate_style(req.style)
        if req.style and not validated_style:
            raise HTTPException(
                status_code=400,
                detail=f"{ErrorMessages.INVALID_STYLE} 지원 스타일: {', '.join(ALLOWED_STYLES)}"
            )
        
        # seed 검증
        validated_seed = _validate_seed(req.seed)
        
        # 정제된 요청 반환
        return CopyToImageReq(
            text=clean_text,
            style=validated_style,
            seed=validated_seed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"{ErrorMessages.MALFORMED_REQUEST}: {str(e)}"
        )

def _headers():
    """OpenAI API 헤더 생성"""
    if not OPENAI_KEY:
        raise HTTPException(
            status_code=500, 
            detail=ErrorMessages.CONFIG_ERROR
        )
    
    h = {
        "Authorization": f"Bearer {OPENAI_KEY}", 
        "Content-Type": "application/json"
    }
    
    org = os.getenv("OPENAI_ORG_ID")
    proj = os.getenv("OPENAI_PROJECT_ID")
    if org: 
        h["OpenAI-Organization"] = org
    if proj: 
        h["OpenAI-Project"] = proj
    
    return h

def _handle_openai_error(response) -> HTTPException:
    """OpenAI API 에러 처리"""
    try:
        error_data = response.json()
        error_type = error_data.get("error", {}).get("type", "")
        error_message = error_data.get("error", {}).get("message", "")
        
        # Rate limit 에러
        if response.status_code == 429 or "rate_limit" in error_type.lower():
            return HTTPException(
                status_code=429,
                detail=ErrorMessages.RATE_LIMIT_EXCEEDED
            )
        
        # Content policy 위반
        if "content_policy" in error_type.lower() or "policy" in error_message.lower():
            return HTTPException(
                status_code=403,
                detail=ErrorMessages.CONTENT_POLICY_VIOLATION
            )
        
        # 일반적인 API 에러
        return HTTPException(
            status_code=502,
            detail=f"{ErrorMessages.OPENAI_API_ERROR}: {error_message}"
        )
        
    except Exception:
        # JSON 파싱 실패 시
        return HTTPException(
            status_code=502,
            detail=f"{ErrorMessages.OPENAI_API_ERROR} (상태 코드: {response.status_code})"
        )

@router.post("/safe-image-from-copy")
def safe_image_from_copy(req: CopyToImageReq):
    """보안 필터링을 거친 안전한 이미지 생성 (권장)"""
    
    # 보안 검증 및 정제
    validated_req = _validate_and_clean_request(req)
    
    # 기존 검증된 API 호출
    return image_from_copy(validated_req)

@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    """원본 이미지 생성 API (내부용)"""
    
    try:
        style_snippet = f" in {req.style} style" if req.style else ""
        prompt = (
            f'다음 문구에 어울리는 광고 이미지를 생성해줘{style_snippet}. '
            f'Ad copy: "{req.text}". 높은 퀄리티, sharp, clean composition.'
        )
        url = f"{OPENAI_BASE}/images/generations"
        payload = {
            # gpt-image-1 권한 이슈 있으면 dall-e-3 사용
            "model": "dall-e-3",
            "prompt": prompt,
            "size": "1024x1024",
        }

        # OpenAI API 호출
        r = requests.post(url, headers=_headers(), json=payload, timeout=180)
        
        # API 에러 처리
        if not r.ok:
            raise _handle_openai_error(r)

        data = r.json()

        # 응답 데이터 검증
        try:
            datum = data["data"][0]
        except (KeyError, IndexError):
            raise HTTPException(
                status_code=502, 
                detail=f"{ErrorMessages.OPENAI_RESPONSE_ERROR}: {list(data.keys())}"
            )

        # 이미지 데이터 처리
        img_bytes = None
        
        if "b64_json" in datum and datum["b64_json"]:
            try:
                img_bytes = base64.b64decode(datum["b64_json"])
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"{ErrorMessages.OPENAI_RESPONSE_ERROR}: base64 디코딩 실패"
                )
                
        elif "url" in datum and datum["url"]:
            try:
                img_resp = requests.get(datum["url"], timeout=180)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
            except requests.RequestException as e:
                raise HTTPException(
                    status_code=502,
                    detail=ErrorMessages.IMAGE_DOWNLOAD_ERROR
                )
        else:
            raise HTTPException(
                status_code=502, 
                detail=f"{ErrorMessages.OPENAI_RESPONSE_ERROR}: 이미지 데이터 없음 (키: {list(datum.keys())})"
            )

        # 파일 저장
        try:
            save_name = f"image_from_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
            save_path = os.path.join(OUTPUT_DIR, save_name)
            
            with open(save_path, "wb") as f:
                f.write(img_bytes)
                
            file_path = os.path.abspath(save_path).replace("\\", "/")
            file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"
            
            return {
                "ok": True, 
                "output_path": file_path, 
                "file_url": file_url
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"{ErrorMessages.FILE_SAVE_ERROR}: {str(e)}"
            )

    except HTTPException:
        raise
    except requests.RequestException as e:
        # 네트워크 관련 에러
        raise HTTPException(
            status_code=502,
            detail=f"{ErrorMessages.OPENAI_API_ERROR}: 네트워크 오류"
        )
    except Exception as e:
        # 예상치 못한 에러
        raise HTTPException(
            status_code=500,
            detail=f"{ErrorMessages.UNKNOWN_ERROR}: {str(e)}"
        )