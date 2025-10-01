"""
한국어 -> 영어 번역 + FLUX 이미지 생성 API (Render FastAPI ↔ ngrok 로컬 모델/ComfyUI)

전제 조건:
- FastAPI는 Render에서 구동(메모리 512MB 제한)
- 번역 모델과 ComfyUI는 "로컬"에서 실행하고 ngrok으로 공개
  - Render FastAPI는 아래 두 주소로만 붙음:
    1) TRANSLATION_BRIDGE_URL  (로컬 번역 브릿지 ngrok)
    2) COMFYUI_URL             (로컬 ComfyUI ngrok)

로컬 측 준비:
1) ComfyUI (예: 8188) 실행 후 ngrok http 8188
   → 예: https://comfy-xxxx.ngrok-free.app

2) 번역 브릿지(간단 FastAPI) 실행 후 ngrok http 7000 (예시)
   - /translate:  POST { "text": "..." } → { "text": "..." (영어) }
   - /classify :  POST { "text": "...", "type": "person"|"object" } → { "yes": true/false }
   → 예: https://trans-xxxx.ngrok-free.app
   (번역 모델 llama.cpp를 이 브릿지에서 로드하세요. Render에서는 절대 모델 로드 X)

Render 측(이 파일):
- 아래 TRANSLATION_BRIDGE_URL, COMFYUI_URL 을 ngrok 주소로 설정
- BACKEND_PUBLIC_URL은 Render 도메인 그대로 유지하면 /static/* 경로로 업로드 파일 접근 가능

사용법:
1) (로컬) ComfyUI + 번역브릿지 실행 후 ngrok으로 공개
2) (Render) FastAPI 서버 정상 구동
3) POST /image-from-copy
   { "text":"하늘을 나는 고양이", "style":"realistic", "seed":0 }
"""

import os, uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading
import time
import requests

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# llama_cpp 는 "로컬 모델 fallback" 용으로만 남겨둠 (remote 모드면 절대 사용하지 않음)
try:
    from llama_cpp import Llama
    GGUF_AVAILABLE = True
except ImportError:
    GGUF_AVAILABLE = False

# ---- env 로드 (프로젝트 루트의 .env) ----
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

# Render에서 정적 파일이 서비스되는 공개 URL (Render 환경변수 또는 디폴트)
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "https://hidden-leaf-village.onrender.com").rstrip("/")

# 저장 루트 (Render 파일시스템)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================
# 🔗 원격(ngrok) 엔드포인트
# ==========================
# 1) 로컬 ComfyUI ngrok 주소
COMFYUI_URL = "https://nonblamable-timothy-superattainable.ngrok-free.dev"

# 2) 로컬 번역 브릿지 ngrok 주소 (중요: 이게 있으면 'remote' 모드로 동작)
TRANSLATION_BRIDGE_URL = os.getenv("TRANSLATION_BRIDGE_URL", "https://YOUR-TRANSLATION-NGROK-URL").rstrip("/")

# ComfyUI에서 기대하는 모델 파일명 (ComfyUI 측 models 폴더에 준비)
COMFYUI_MODELS = {
    "unet": "flux1-schnell-Q4_K_S.gguf",
    "clip_l": "clip_l.safetensors", 
    "clip_t5": "t5xxl_fp16.safetensors",
    "vae": "ae.safetensors"
}

# === 로컬 모델 fallback (Render에선 사실상 사용 불가이므로 off가 기본) ===
# Hugging Face Hub 경로를 남겨두지만, Render 메모리 한계 때문에 remote 모드가 기본입니다.
HF_REPO_ID = "Chloros/rosetta-12b-gguf"
HF_FILENAME = "yanolja_rosetta_12b_q4_k_m.gguf"

# 에러 메시지 상수 정의
class ErrorMessages:
    # 400 Bad Request
    TEXT_TOO_LONG = "텍스트 길이가 1000자를 초과합니다."
    TEXT_EMPTY = "유효한 텍스트를 입력해주세요."
    INVALID_SEED = "seed 값은 0 이상의 정수여야 합니다."
    MALFORMED_REQUEST = "요청 형식이 올바르지 않습니다."
    
    # 500 Internal Server Error
    CONFIG_ERROR = "서버 설정 오류가 발생했습니다."
    FILE_SAVE_ERROR = "이미지 파일 저장 중 오류가 발생했습니다."
    UNKNOWN_ERROR = "알 수 없는 서버 오류가 발생했습니다."
    MODEL_LOAD_ERROR = "모델 로딩 중 오류가 발생했습니다."
    MODEL_MISSING_ERROR = "필요한 모델 파일이 없습니다."
    
    # 502 Bad Gateway
    TRANSLATION_ERROR = "번역 서비스에 일시적인 문제가 발생했습니다."
    IMAGE_GENERATION_ERROR = "이미지 생성 서비스에 일시적인 문제가 발생했습니다."


class CopyToImageReq(BaseModel):
    text: str
    style: Optional[str] = None
    seed: Optional[int] = None


# 글로벌 모델 인스턴스
_translator = None
_model_loading_lock = threading.Lock()


class LocalModelPipeline:
    """
    텍스트→이미지 파이프라인
    - remote 모드: Render에선 이 모드가 기본. 로컬 번역 브릿지(ngrok) + 로컬 ComfyUI(ngrok)에 HTTP로 붙음.
    - local  모드: (개발자 로컬에서만) llama-cpp로 gguf 직접 로드 (Render 메모리 제한 때문에 실서비스에선 비권장)
    """
    def __init__(self):
        self.translator = None
        self.loaded = False

        # remote 모드 여부
        self.remote_translation = bool(TRANSLATION_BRIDGE_URL and TRANSLATION_BRIDGE_URL.startswith("http"))
    
    # ---------- 공용 헬퍼 ----------
    def _http_post_json(self, url: str, payload: dict, timeout=15):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code >= 400:
                raise HTTPException(502, f"Upstream error {r.status_code}: {r.text[:300]}")
            return r.json()
        except requests.RequestException as e:
            raise HTTPException(502, f"Upstream request failed: {e}")

    # ---------- 셋업/체크 ----------
    def check_models(self):
        """
        원격 모드: 번역 브릿지 health, ComfyUI 연결만 확인
        로컬 모드: gguf 파일 존재, llama-cpp 설치 여부 확인
        """
        # 1) 번역 브릿지(원격) 또는 로컬 모델 체크
        if self.remote_translation:
            # /health 또는 /translate 간단 호출로 확인
            try:
                ping = self._http_post_json(f"{TRANSLATION_BRIDGE_URL}/translate", {"text":"안녕"}, timeout=8)
                if not isinstance(ping, dict) or "text" not in ping:
                    raise HTTPException(502, f"{ErrorMessages.TRANSLATION_ERROR}: 브릿지 응답 형식 오류")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(502, f"{ErrorMessages.TRANSLATION_ERROR}: 번역 브릿지 연결 실패 - {e}")
        else:
            # === 로컬 모드 (Render에선 사실상 비활성) ===
            try:
                from huggingface_hub import hf_hub_download
                model_path = Path(hf_hub_download(repo_id=HF_REPO_ID, filename=HF_FILENAME))
            except Exception as e:
                raise HTTPException(500, f"{ErrorMessages.MODEL_MISSING_ERROR}: HF 다운로드 실패 - {e}")
            if not GGUF_AVAILABLE:
                raise HTTPException(500, f"{ErrorMessages.CONFIG_ERROR}: llama-cpp-python이 설치되지 않았습니다")

        # 2) ComfyUI 연결 확인
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"{ErrorMessages.MODEL_MISSING_ERROR}: ComfyUI 서버에 연결할 수 없습니다"
                )
        except requests.RequestException:
            raise HTTPException(
                status_code=500,
                detail=f"{ErrorMessages.MODEL_MISSING_ERROR}: ComfyUI 서버가 실행되지 않았습니다"
            )
    
    def load_models(self):
        """
        remote 모드: 별도 로딩 없음(브릿지 ping만 성공하면 준비 완료)
        local  모드: llama-cpp로 gguf 로딩 (Render에서는 메모리 제한으로 비권장)
        """
        if self.loaded:
            return
        
        print("파이프라인 체크 및 로딩 시작...")
        self.check_models()

        if self.remote_translation:
            print("원격 번역 브릿지 모드: 모델 로딩 불필요")
            self.translator = None
        else:
            # === 로컬 모드 (개발자 로컬에서만) ===
            from huggingface_hub import hf_hub_download
            model_path = Path(hf_hub_download(repo_id=HF_REPO_ID, filename=HF_FILENAME))
            print(f"번역 모델 로딩(로컬): {model_path.name}")
            try:
                self.translator = Llama(
                    model_path=str(model_path),
                    n_ctx=512,
                    n_threads=4,
                    n_gpu_layers=-1,
                    verbose=False
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"{ErrorMessages.MODEL_LOAD_ERROR}: 번역 모델 로딩 실패 - {str(e)}"
                )
        
        print("모든 준비 완료")
        self.loaded = True
    
    # ---------- 번역/분류 ----------
    def translate_korean(self, text: str) -> str:
        """
        한글을 영어로 번역
        - remote 모드: /translate 호출
        - local  모드: llama-cpp 호출
        """
        if not self.loaded:
            self.load_models()
        
        # 한글 포함 확인
        has_korean = any('\uac00' <= char <= '\ud7af' for char in text)
        if not has_korean:
            print(f"한글 없음, 원문 사용: {text}")
            return text
        
        if self.remote_translation:
            try:
                resp = self._http_post_json(f"{TRANSLATION_BRIDGE_URL}/translate", {"text": text}, timeout=12)
                english_text = (resp.get("text") or "").strip()
                return english_text or text
            except HTTPException:
                raise
            except Exception as e:
                print(f"번역 오류(브릿지): {e}, 원문 사용")
                return text

        # === 로컬 모드 ===
        print(f"한글 번역 중(로컬 llama): {text}")
        prompt = f"""Translate the following Korean text to English:

Korean: {text}
English:"""
        try:
            response = self.translator(
                prompt,
                max_tokens=100,
                temperature=0.0,
                stop=["Korean:", "\n\n", "Translation:"]
            )
            english_text = response['choices'][0]['text'].strip()
            if "English:" in english_text:
                english_text = english_text.split("English:")[-1]
            english_text = english_text.split("\n")[0].strip()
            return english_text or text
        except Exception as e:
            print(f"번역 오류(로컬): {e}, 원문 사용")
            return text
    
    def classify_person(self, english: str) -> bool:
        """
        사람 여부 판단 (명시적 단어 포함 여부)
        - remote 모드: /classify 호출(type=person)
        - local  모드: llama-cpp
        """
        if not self.loaded:
            self.load_models()
        
        if self.remote_translation:
            try:
                resp = self._http_post_json(f"{TRANSLATION_BRIDGE_URL}/classify",
                                            {"text": english, "type": "person"},
                                            timeout=6)
                return bool(resp.get("yes", False))
            except HTTPException:
                raise
            except Exception as e:
                print(f"인물 판단 오류(브릿지): {e}")
                return False

        # === 로컬 모드 ===
        prompt = f"""Answer only YES or NO.

Text: {english}

Question: Does this text explicitly contain any human-related words 
(such as man, woman, person, people, child, boy, girl, baby, face, portrait, model, actor, actress, selfie)?

Rules:
- Answer YES only if at least one of these words appears in the text.
- If none of these words appear, you MUST answer NO.
- Do not assume or guess implied humans (e.g., someone riding a bicycle).
- Do not use context or imagination. Base your answer only on explicit words in the text.

Answer:"""
        try:
            response = self.translator(prompt, max_tokens=5, temperature=0.0, stop=["\n"])
            answer = response['choices'][0]['text'].strip().lower()
            return "yes" in answer
        except Exception as e:
            print(f"인물 판단 오류(로컬): {e}")
            return False
    
    def classify_object(self, english: str) -> bool:
        """
        사물 여부 판단 (명시적 단어 포함 여부) — 의도상 '사람 단어'가 있으면 YES로 하던 원래 버그성 규칙을 그대로 유지
        - remote 모드: /classify(type=object) 호출 (동일 규칙을 브릿지에서 구현)
        - local  모드: llama-cpp
        """
        if not self.loaded:
            self.load_models()
        
        if self.remote_translation:
            try:
                resp = self._http_post_json(f"{TRANSLATION_BRIDGE_URL}/classify",
                                            {"text": english, "type": "object"},
                                            timeout=6)
                return bool(resp.get("yes", False))
            except HTTPException:
                raise
            except Exception as e:
                print(f"사물 판단 오류(브릿지): {e}")
                return False

        # === 로컬 모드 === (원본 규칙 유지)
        prompt = f"""Answer with only YES or NO.

Text: {english}

Rule:
- Answer YES only if the text explicitly mentions humans or human-related words.
- Do NOT infer implied presence.
- If unclear, answer NO.

Answer:"""
        try:
            response = self.translator(prompt, max_tokens=5, temperature=0.0, stop=["\n"])
            answer = response['choices'][0]['text'].strip().lower()
            return "yes" in answer
        except Exception as e:
            print(f"사물 판단 오류(로컬): {e}")
            return False
    
    def enhance_prompt(self, text: str) -> str:
        """프롬프트 강화: 번역 + 분류 + 키워드 추가 (원본 로직 유지)"""
        if not self.loaded:
            self.load_models()
        
        print("\n=== 프롬프트 강화 시작 ===")
        
        # 1. 번역
        english = self.translate_korean(text)
        
        # 2. 분류
        print("콘텐츠 분류 중...")
        has_person = self.classify_person(english)
        has_object = self.classify_object(english)
        
        # 3. 키워드 강화
        enhanced = f"{english}, sharp, clean composition, high quality"
        
        if has_person:
            enhanced += ", portrait, detailed face, natural skin texture"
            print("  인물 키워드 추가")
        
        if has_object:
            enhanced += ", sharp edges"
            print("  사물 키워드 추가")
        
        print(f"최종 강화 프롬프트: {enhanced}")
        print("=== 프롬프트 강화 완료 ===\n")
        
        return enhanced
    
    def generate_image_with_comfyui(self, prompt: str, style: Optional[str] = None, seed: Optional[int] = None) -> bytes:
        """ComfyUI(ngrok)로 실제 이미지 생성 (원본 워크플로우 유지)"""
        print(f"ComfyUI로 실제 이미지 생성: {prompt}")
        
        # ComfyUI 워크플로우 정의 (검증된 구조 사용)
        workflow = {
            "1": {
                "inputs": {"unet_name": COMFYUI_MODELS["unet"]},
                "class_type": "UnetLoaderGGUF",
                "_meta": {"title": "Load GGUF Model"}
            },
            "2": {
                "inputs": {
                    "clip_name1": COMFYUI_MODELS["clip_l"],
                    "clip_name2": COMFYUI_MODELS["clip_t5"],
                    "type": "flux"
                },
                "class_type": "DualCLIPLoader",
                "_meta": {"title": "Load CLIP"}
            },
            "3": {
                "inputs": {
                    "text": f"{prompt} in {style} style" if style else prompt,
                    "clip": ["2", 0]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Encode Prompt"}
            },
            "4": {
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent"}
            },
            "5": {
                "inputs": {
                    "seed": seed or int(time.time()) % 1000000,
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "Sample"}
            },
            "6": {
                "inputs": {"vae_name": COMFYUI_MODELS["vae"]},
                "class_type": "VAELoader",
                "_meta": {"title": "Load VAE"}
            },
            "7": {
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["6", 0]
                },
                "class_type": "VAEDecode",
                "_meta": {"title": "Decode"}
            },
            "8": {
                "inputs": {
                    "filename_prefix": "flux_output",
                    "images": ["7", 0]
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save"}
            }
        }
        
        try:
            # 워크플로우 실행
            client_id = str(uuid.uuid4())
            
            response = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=12
            )
            
            if response.status_code != 200:
                error_detail = ""
                try:
                    error_detail = response.json()
                except:
                    error_detail = response.text
                raise Exception(f"ComfyUI 요청 실패: {response.status_code} - {error_detail}")
            
            prompt_id = response.json()["prompt_id"]
            print(f"ComfyUI 작업 ID: {prompt_id}")
            
            # 완료 대기
            for _ in range(150):  # 5분 타임아웃
                time.sleep(2)
                
                hist_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=8)
                if hist_response.status_code == 200:
                    history = hist_response.json()
                    
                    if prompt_id in history:
                        task_info = history[prompt_id]
                        status = task_info.get("status", {})
                        
                        if status.get("completed", False):
                            # 이미지 다운로드
                            outputs = task_info.get("outputs", {})
                            for node_id, output in outputs.items():
                                if "images" in output:
                                    for img_info in output["images"]:
                                        img_url = f"{COMFYUI_URL}/view"
                                        params = {
                                            "filename": img_info["filename"],
                                            "subfolder": img_info.get("subfolder", ""),
                                            "type": "output"
                                        }
                                        
                                        img_response = requests.get(img_url, params=params, timeout=12)
                                        if img_response.status_code == 200:
                                            print("ComfyUI 이미지 생성 완료")
                                            return img_response.content
                        
                        elif "error" in status:
                            raise Exception(f"ComfyUI 오류: {status['error']}")
            
            raise Exception("ComfyUI 타임아웃")
            
        except Exception as e:
            # ComfyUI 실패시 데모 모드로 fallback
            print(f"ComfyUI 실패, 데모 모드로 fallback: {e}")
            return self.generate_image_demo(prompt, style, seed)
    
    def generate_image_demo(self, prompt: str, style: Optional[str] = None, seed: Optional[int] = None) -> bytes:
        """데모 이미지 생성 (ComfyUI 실패시 fallback)"""
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        print(f"데모 이미지 생성 (fallback): {prompt}")
        
        # 1024x1024 이미지 생성
        img = Image.new('RGB', (1024, 1024), color='lightcoral')
        draw = ImageDraw.Draw(img)
        
        # 제목
        title_font = None
        try:
            title_font = ImageFont.load_default()
        except:
            pass
        
        # 제목 텍스트
        title = "ComfyUI Connection Failed - Demo Mode"
        if title_font:
            bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = bbox[2] - bbox[0]
            x_pos = (1024 - title_width) // 2
            draw.text((x_pos, 100), title, fill='white', font=title_font)
        
        # 프롬프트 정보
        info_lines = [
            f"Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}",
            f"Style: {style or 'None'}",
            f"Seed: {seed or 'Random'}",
            "",
            "ComfyUI Status: Failed (ngrok?)",
            f"Check: {COMFYUI_URL}",
            "",
            "Translation: remote bridge",
            f"Bridge: {TRANSLATION_BRIDGE_URL}"
        ]
        
        y_offset = 300
        for line in info_lines:
            if title_font:
                bbox = draw.textbbox((0, 0), line, font=title_font)
                line_width = bbox[2] - bbox[0]
                x_pos = (1024 - line_width) // 2
                draw.text((x_pos, y_offset), line, fill='white', font=title_font)
            y_offset += 35
        
        # PIL 이미지를 bytes로 변환
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        return img_bytes.getvalue()


def _get_local_pipeline():
    """파이프라인 싱글톤"""
    global _translator
    
    if _translator is None:
        with _model_loading_lock:
            if _translator is None:
                _translator = LocalModelPipeline()
    
    return _translator


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


@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    """텍스트로부터 이미지 생성 - 프롬프트 강화 적용"""
    
    # 기본 요청 검증
    validated_req = _validate_request(req)
    
    start_time = time.time()
    
    try:
        pipeline = _get_local_pipeline()
        
        # 1. 프롬프트 강화 (번역 + 분류 + 키워드 추가)
        enhancement_start = time.time()
        enhanced_prompt = pipeline.enhance_prompt(validated_req.text)
        enhancement_time = time.time() - enhancement_start
        
        # 2. 스타일 적용 (선택사항)
        if validated_req.style:
            final_prompt = f"{enhanced_prompt} in {validated_req.style} style"
        else:
            final_prompt = enhanced_prompt
        
        # 3. ComfyUI로 실제 이미지 생성
        generation_start = time.time()
        img_bytes = pipeline.generate_image_with_comfyui(
            final_prompt, 
            validated_req.style, 
            validated_req.seed
        )
        generation_time = time.time() - generation_start
        
        # 4. 파일 저장 (Render 파일시스템 → Render 정적 URL로 접근)
        save_name = f"image_from_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)
        
        with open(save_path, "wb") as f:
            f.write(img_bytes)
            
        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"
        
        total_time = time.time() - start_time
        
        return {
            "ok": True, 
            "output_path": file_path, 
            "file_url": file_url,
            "metadata": {
                "original_text": validated_req.text,
                "enhanced_prompt": enhanced_prompt,
                "final_prompt": final_prompt,
                "style": validated_req.style,
                "seed": validated_req.seed,
                "model_used": "ComfyUI(remote) + TranslationBridge(remote)",
                "demo_mode": False,
                "timing": {
                    "enhancement_time": round(enhancement_time, 2),
                    "generation_time": round(generation_time, 2),
                    "total_time": round(total_time, 2)
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"{ErrorMessages.UNKNOWN_ERROR}: {str(e)}"
        )


# 모델 상태 확인 엔드포인트
@router.get("/model-status")
def model_status():
    """현재 모델/브릿지/ComfyUI 상태 확인 (remote 우선)"""
    
    # 번역(브릿지) 체크
    bridge_ok = False
    try:
        # 간단 ping
        ping = requests.post(f"{TRANSLATION_BRIDGE_URL}/translate", json={"text": "테스트"}, timeout=5)
        bridge_ok = (ping.status_code == 200 and "text" in (ping.json() or {}))
    except Exception:
        bridge_ok = False
    
    # ComfyUI 연결 체크
    comfyui_available = False
    comfyui_models = {}
    
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if response.status_code == 200:
            comfyui_available = True
            
            # 모델 목록 확인
            obj_info_response = requests.get(f"{COMFYUI_URL}/object_info", timeout=5)
            if obj_info_response.status_code == 200:
                obj_info = obj_info_response.json()
                
                # GGUF 모델 체크
                if "UnetLoaderGGUF" in obj_info:
                    unet_models = obj_info["UnetLoaderGGUF"]["input"]["required"]["unet_name"][0]
                    comfyui_models["unet"] = COMFYUI_MODELS["unet"] in unet_models
                
                # CLIP 모델 체크  
                if "DualCLIPLoader" in obj_info:
                    clip_models = obj_info["DualCLIPLoader"]["input"]["required"]["clip_name1"][0]
                    comfyui_models["clip_l"] = COMFYUI_MODELS["clip_l"] in clip_models
                    comfyui_models["clip_t5"] = COMFYUI_MODELS["clip_t5"] in clip_models
                
                # VAE 모델 체크
                if "VAELoader" in obj_info:
                    vae_models = obj_info["VAELoader"]["input"]["required"]["vae_name"][0]
                    comfyui_models["vae"] = COMFYUI_MODELS["vae"] in vae_models
    
    except:
        pass
    
    all_models_ready = bridge_ok and comfyui_available and all(comfyui_models.values()) if comfyui_models else (bridge_ok and comfyui_available)
    
    return {
        "translation_bridge": {
            "url": TRANSLATION_BRIDGE_URL,
            "reachable": bridge_ok
        },
        "comfyui": {
            "server_available": comfyui_available,
            "url": COMFYUI_URL,
            "models": comfyui_models,
            "expected_models": COMFYUI_MODELS
        },
        "dependencies": {
            "mode": "remote" if TRANSLATION_BRIDGE_URL else "local-fallback",
            "gguf_available": GGUF_AVAILABLE
        },
        "prompt_enhancement": {
            "base_quality": "sharp, clean composition, high quality",
            "person_keywords": "portrait, detailed face, natural skin texture",
            "object_keywords": "product photo, centered object, sharp edges"
        },
        "status": "ready" if all_models_ready else "not_ready",
        "message": "모든 시스템 준비됨" if all_models_ready else "브릿지/ComfyUI 연결 확인 필요"
    }
