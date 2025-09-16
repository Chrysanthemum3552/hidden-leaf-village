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

# 에러 메시지 상수 정의
class ErrorMessages:
    # 400 Bad Request
    TEXT_TOO_LONG = "텍스트 길이가 1000자를 초과합니다."
    TEXT_EMPTY = "유효한 텍스트를 입력해주세요."
    INVALID_SEED = "seed 값은 0 이상의 정수여야 합니다."
    MALFORMED_REQUEST = "요청 형식이 올바르지 않습니다."
    
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

def _validate_request(req: CopyToImageReq) -> CopyToImageReq:
    """기본 요청 검증"""
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
        
        # 빈 텍스트 체크
        if not req.text.strip():
            raise HTTPException(
                status_code=400, 
                detail=ErrorMessages.TEXT_EMPTY
            )
        
        # seed 검증
        if req.seed is not None and (not isinstance(req.seed, int) or req.seed < 0):
            raise HTTPException(
                status_code=400, 
                detail=ErrorMessages.INVALID_SEED
            )
        
        return req
        
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
        
        # Content policy 위반 (DALL-E-3 내장 필터링)
        if response.status_code == 400 and ("content_policy" in error_type.lower() or "policy" in error_message.lower()):
            return HTTPException(
                status_code=400,
                detail="요청한 내용이 이미지 생성 정책에 위배됩니다."
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

@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    """텍스트로부터 이미지 생성"""
    
    # 기본 요청 검증
    validated_req = _validate_request(req)
    
    try:
        style_snippet = f" in {validated_req.style} style" if validated_req.style else ""
        prompt = (
            f'다음 문구에 어울리는 광고 이미지를 생성해줘{style_snippet}. '
            f'Ad copy: "{validated_req.text}". 높은 퀄리티, sharp, clean composition.'
        )
        
        url = f"{OPENAI_BASE}/images/generations"
        payload = {
            # gpt-image-1 권한 이슈 있으면 dall-e-3 사용
            "model": "dall-e-3",
            "prompt": prompt,
            "size": "1024x1024",
        }
        
        # seed가 있으면 추가 (DALL-E-3는 seed를 직접 지원하지 않으므로 무시됨)
        # 필요시 프롬프트에 포함하거나 다른 방식으로 처리

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