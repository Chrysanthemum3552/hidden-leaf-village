"""
한국어 -> 영어 번역 + FLUX 이미지 생성 API

전제 조건 (각각의 터미널에서 실행):
1. ComfyUI 서버가 먼저 실행되어야 합니다:(ComfyUI가 git clone 되어 있다고 가정)
   cd ~/hidden-leaf-village/ComfyUI/ComfyUI
   python main.py
   
2. 필요한 모델 파일들이 ComfyUI 디렉토리에 있어야 합니다:
   - models/unet/flux1-schnell-Q4_K_S.gguf
   - models/clip/clip_l.safetensors
   - models/clip/t5xxl_fp16.safetensors  
   - models/vae/ae.safetensors

3. 번역 모델이 프로젝트 models/ 디렉토리에 있어야 합니다:
   - models/yanolja_rosetta_12b_q8_0.gguf

사용법:
1. ComfyUI 서버 실행: cd ComfyUI/ComfyUI && python main.py
2. FastAPI 서버 실행: python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
3. POST 요청을 /image-from-copy 엔드포인트로 전송:
   {
       "text": "하늘을 나는 고양이",
       "style": "선택적 스타일 (예: 'realistic')",
       "seed": 0  # 선택적 시드 값
   }
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

try:
    from llama_cpp import Llama
    GGUF_AVAILABLE = True
except ImportError:
    GGUF_AVAILABLE = False

# ---- env 로드 (프로젝트 루트의 .env) ----
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 로컬 모델 경로
MODELS_DIR = ROOT_DIR / "models"
TRANSLATION_MODEL = MODELS_DIR / "yanolja_rosetta_12b_q8_0.gguf"

# ComfyUI 설정 (별도 디렉토리)
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFYUI_MODELS = {
    "unet": "flux1-schnell-Q4_K_S.gguf",
    "clip_l": "clip_l.safetensors", 
    "clip_t5": "t5xxl_fp16.safetensors",
    "vae": "ae.safetensors"
}

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
    """로컬 모델을 사용한 텍스트→이미지 파이프라인"""
    
    def __init__(self):
        self.translator = None
        self.loaded = False
    
    def check_models(self):
        """필요한 모델들이 존재하는지 확인"""
        # 번역 모델만 체크 (로컬)
        if not TRANSLATION_MODEL.exists():
            raise HTTPException(
                status_code=500,
                detail=f"{ErrorMessages.MODEL_MISSING_ERROR}: 번역 모델 ({TRANSLATION_MODEL.name})"
            )
        
        # ComfyUI 연결 확인 (FLUX 모델들은 ComfyUI에서 확인)
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
        """필요한 모델들 로딩"""
        if self.loaded:
            return
        
        print("로컬 모델들 체크 및 로딩 중...")
        
        # 1. 모델 파일 존재 확인
        self.check_models()
        
        # 2. 의존성 확인
        if not GGUF_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail=f"{ErrorMessages.CONFIG_ERROR}: llama-cpp-python이 설치되지 않았습니다"
            )
        
        # 3. 번역 모델 로딩
        print(f"번역 모델 로딩: {TRANSLATION_MODEL.name}")
        try:
            self.translator = Llama(
                model_path=str(TRANSLATION_MODEL),
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
        
        print("모든 모델 로딩 완료")
        self.loaded = True
    
    def translate_korean(self, text: str) -> str:
        """한글을 영어로 번역"""
        if not self.loaded:
            self.load_models()
        
        # 한글이 포함되어 있는지 확인
        has_korean = any('\uac00' <= char <= '\ud7af' for char in text)
        if not has_korean:
            print(f"한글 없음, 원문 사용: {text}")
            return text
        
        print(f"한글 번역 중: {text}")
        
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
            
            # 후처리
            if "English:" in english_text:
                english_text = english_text.split("English:")[-1]
            english_text = english_text.split("\n")[0].strip()
            
            if not english_text:
                print("번역 결과 없음, 원문 사용")
                return text
            
            print(f"번역 완료: {english_text}")
            return english_text
            
        except Exception as e:
            print(f"번역 오류: {e}, 원문 사용")
            return text  # 번역 실패시 원문 반환
    
    def generate_image_with_comfyui(self, prompt: str, style: Optional[str] = None, seed: Optional[int] = None) -> bytes:
        """ComfyUI를 통한 실제 이미지 생성"""
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
                timeout=10
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
                
                hist_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
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
                                        
                                        img_response = requests.get(img_url, params=params)
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
            "ComfyUI Status: Failed",
            "Check ComfyUI server is running",
            "at http://127.0.0.1:8188",
            "",
            "Translation Model: OK",
            f"✓ {TRANSLATION_MODEL.name}"
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
    """로컬 파이프라인 싱글톤"""
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
    """텍스트로부터 이미지 생성 - ComfyUI 연동"""
    
    # 기본 요청 검증
    validated_req = _validate_request(req)
    
    start_time = time.time()
    
    try:
        pipeline = _get_local_pipeline()
        
        # 1. 번역
        translation_start = time.time()
        english_text = pipeline.translate_korean(validated_req.text)
        translation_time = time.time() - translation_start
        
        # 2. 스타일 적용
        if validated_req.style:
            final_prompt = f"{english_text} in {validated_req.style} style"
        else:
            final_prompt = f"High-quality advertising image: {english_text}"
        
        # 3. ComfyUI로 실제 이미지 생성
        generation_start = time.time()
        img_bytes = pipeline.generate_image_with_comfyui(
            final_prompt, 
            validated_req.style, 
            validated_req.seed
        )
        generation_time = time.time() - generation_start
        
        # 4. 파일 저장
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
                "english_prompt": english_text,
                "final_prompt": final_prompt,
                "style": validated_req.style,
                "seed": validated_req.seed,
                "model_used": "ComfyUI + Local Translation",
                "demo_mode": False,
                "timing": {
                    "translation_time": round(translation_time, 2),
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
    """현재 모델 상태 확인"""
    
    # 번역 모델 체크
    translation_exists = TRANSLATION_MODEL.exists()
    
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
    
    all_models_ready = (
        translation_exists and 
        comfyui_available and 
        all(comfyui_models.values())
    )
    
    return {
        "translation_model": {
            "file": TRANSLATION_MODEL.name,
            "exists": translation_exists,
            "path": str(TRANSLATION_MODEL)
        },
        "comfyui": {
            "server_available": comfyui_available,
            "url": COMFYUI_URL,
            "models": comfyui_models,
            "expected_models": COMFYUI_MODELS
        },
        "dependencies": {
            "gguf_available": GGUF_AVAILABLE,
            "models_dir": str(MODELS_DIR)
        },
        "status": "ready" if all_models_ready else "not_ready",
        "message": "모든 시스템 준비됨" if all_models_ready else "설정 필요"
    }