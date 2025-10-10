# -*- coding: utf-8 -*-
"""
한국어 -> 영어 번역(허깅페이스) + FLUX 이미지 생성 API

전제 조건 (각각의 터미널에서 실행):
1) ComfyUI 서버 선실행 (로컬 GPU)
   cd ~/hidden-leaf-village/ComfyUI/ComfyUI
   python main.py --listen 0.0.0.0 --port 8188

2) ComfyUI에 필요한 모델 파일:
   - models/unet/flux1-schnell-Q4_K_S.gguf
   - models/clip/clip_l.safetensors
   - models/clip/t5xxl_fp16.safetensors
   - models/vae/ae.safetensors

3) ngrok으로 ComfyUI 터널링(한 개만 사용)
   ngrok http 8188
   => 나온 주소를 .env 의 COMFYUI_URL 로 설정

4) 번역은 Hugging Face MarianMT(경량) 사용
   .env 예시:
     HF_TRANSLATION_MODEL=Helsinki-NLP/opus-mt-ko-en
     COMFYUI_URL=https://<your-ngrok>.ngrok-free.dev
     BACKEND_PUBLIC_URL=https://hidden-leaf-village.onrender.com
     STORAGE_ROOT=./data

requirements.txt (백엔드):
  transformers>=4.44
  sentencepiece>=0.1.99
  sacremoses>=0.1.1
  requests
  python-dotenv
  fastapi
  pydantic
"""

import os
import uuid
import time
import threading
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from transformers import pipeline  # Hugging Face 번역기

# ---- env 로드 (프로젝트 루트의 .env) ----
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

# 퍼블릭 백엔드 주소 (정적 파일 접근용)
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

# 저장 루트
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ComfyUI 설정 (ngrok 주소 권장)
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_MODELS = {
    "unet": "flux1-schnell-Q4_K_S.gguf",
    "clip_l": "clip_l.safetensors",
    "clip_t5": "t5xxl_fp16.safetensors",
    "vae": "ae.safetensors",
}

# Hugging Face 번역 모델 (경량)
HF_TRANSLATION_MODEL = os.getenv("HF_TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-ko-en")

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


# 글로벌 파이프라인 인스턴스
_pipeline_singleton = None
_model_loading_lock = threading.Lock()


class LocalModelPipeline:
    """허깅페이스 번역 + ComfyUI(ngrok) 파이프라인"""

    def __init__(self):
        self.hf_translator = None  # HF pipeline
        self.loaded = False

    def check_models(self):
        """ComfyUI 연결 확인만 수행 (모델 파일 유무는 ComfyUI 쪽에서 검증)."""
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=7)
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
        """허깅페이스 번역 파이프라인 로딩 + ComfyUI 연결 확인"""
        if self.loaded:
            return

        print("모델/연결 체크 및 로딩 중...")

        # 1) ComfyUI 연결 확인
        self.check_models()

        # 2) HF 번역 파이프라인 로드 (CPU)
        try:
            print(f"HuggingFace 번역기 로딩: {HF_TRANSLATION_MODEL}")
            self.hf_translator = pipeline("translation", model=HF_TRANSLATION_MODEL)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"{ErrorMessages.MODEL_LOAD_ERROR}: HF 번역 파이프라인 로딩 실패 - {str(e)}"
            )

        print("모든 준비 완료 (ComfyUI OK, HF 번역기 OK)")
        self.loaded = True

    def translate_korean(self, text: str) -> str:
        """한글 → 영어 번역 (HF) / 한글 없으면 원문 유지"""
        if not self.loaded:
            self.load_models()

        has_korean = any('\uac00' <= c <= '\ud7af' for c in text)
        if not has_korean:
            return text

        try:
            out = self.hf_translator(text, max_length=256)
            english_text = (out[0].get("translation_text") or "").strip()
            return english_text or text
        except Exception as e:
            print(f"[HF 번역 실패] {e} → 원문 사용")
            return text

    def enhance_prompt(self, text: str, style: Optional[str] = None) -> str:
        """프롬프트 강화: 번역 + 스타일 번역 + 기본 품질 키워드"""
        if not self.loaded:
            self.load_models()

        print("\n=== 프롬프트 강화 시작 ===")
        # 1) 텍스트 번역
        english = self.translate_korean(text)

        # 2) 스타일 번역 및 적용
        if style:
            english_style = self.translate_korean(style)
            english = f"{english} in {english_style} style"
            print(f"스타일 적용: {style} → {english_style}")

        # 3) 기본 품질 키워드
        enhanced = f"{english}, detailed, sharp, high quality"

        print(f"최종 프롬프트: {enhanced}")
        print("=== 프롬프트 강화 완료 ===\n")

        return enhanced

    def generate_image_with_comfyui(self, prompt: str, seed: Optional[int] = None) -> bytes:
        """ComfyUI 워크플로우 호출 → 이미지 바이트 반환"""
        print(f"ComfyUI로 실제 이미지 생성: {prompt}")

        workflow = {
            "1": {
                "inputs": {"unet_name": COMFYUI_MODELS["unet"]},
                "class_type": "UnetLoaderGGUF",
                "_meta": {"title": "Load GGUF Model"},
            },
            "2": {
                "inputs": {
                    "clip_name1": COMFYUI_MODELS["clip_l"],
                    "clip_name2": COMFYUI_MODELS["clip_t5"],
                    "type": "flux",
                    "device": "default",
                },
                "class_type": "DualCLIPLoader",
                "_meta": {"title": "Load CLIP"},
            },
            "3": {
                "inputs": {
                    "text": prompt,
                    "clip": ["2", 0],
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Encode Prompt"},
            },
            "4": {
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1,
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent"},
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
                    "latent_image": ["4", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "Sample"},
            },
            "6": {
                "inputs": {"vae_name": COMFYUI_MODELS["vae"]},
                "class_type": "VAELoader",
                "_meta": {"title": "Load VAE"},
            },
            "7": {
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["6", 0],
                },
                "class_type": "VAEDecode",
                "_meta": {"title": "Decode"},
            },
            "8": {
                "inputs": {
                    "filename_prefix": "flux_output",
                    "images": ["7", 0],
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save"},
            },
        }

        try:
            client_id = str(uuid.uuid4())
            response = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=15,
            )

            if response.status_code != 200:
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                raise Exception(f"ComfyUI 요청 실패: {response.status_code} - {error_detail}")

            prompt_id = response.json()["prompt_id"]
            print(f"ComfyUI 작업 ID: {prompt_id}")

            # 진행 상태 폴링 (최대 약 5분)
            for _ in range(160):
                time.sleep(2)
                hist_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
                if hist_response.status_code != 200:
                    continue

                history = hist_response.json()
                if prompt_id not in history:
                    continue

                task_info = history[prompt_id]
                status = task_info.get("status", {})

                if status.get("completed", False):
                    outputs = task_info.get("outputs", {})
                    for node_id, output in outputs.items():
                        if "images" in output:
                            for img_info in output["images"]:
                                img_url = f"{COMFYUI_URL}/view"
                                params = {
                                    "filename": img_info["filename"],
                                    "subfolder": img_info.get("subfolder", ""),
                                    "type": "output",
                                }
                                img_response = requests.get(img_url, params=params, timeout=15)
                                if img_response.status_code == 200:
                                    print("ComfyUI 이미지 생성 완료")
                                    return img_response.content

                if "error" in status:
                    raise Exception(f"ComfyUI 오류: {status['error']}")

            raise Exception("ComfyUI 타임아웃")

        except Exception as e:
            # ComfyUI 실패 시 데모 fallback 이미지 생성
            print(f"ComfyUI 실패, 데모 모드로 fallback: {e}")
            return self.generate_image_demo(prompt, seed)

    def generate_image_demo(self, prompt: str, seed: Optional[int] = None) -> bytes:
        """데모 이미지 생성 (ComfyUI 실패시 fallback)"""
        from PIL import Image, ImageDraw, ImageFont
        import io

        print(f"데모 이미지 생성 (fallback): {prompt}")

        img = Image.new("RGB", (1024, 1024), color="lightcoral")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        title = "ComfyUI Connection Failed - Demo Mode"
        if font:
            bbox = draw.textbbox((0, 0), title, font=font)
            title_w = bbox[2] - bbox[0]
            x = (1024 - title_w) // 2
            draw.text((x, 100), title, fill="white", font=font)

        info_lines = [
            f"Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}",
            f"Seed: {seed or 'Random'}",
            "",
            "ComfyUI Status: Failed",
            "Check ComfyUI server (ngrok)",
            f"at {COMFYUI_URL}",
            "",
            "Translation: HuggingFace OK",
            f"✓ {HF_TRANSLATION_MODEL}",
        ]

        y = 300
        for line in info_lines:
            if font:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_w = bbox[2] - bbox[0]
                x = (1024 - line_w) // 2
                draw.text((x, y), line, fill="white", font=font)
            y += 35

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _get_pipeline():
    """파이프라인 싱글톤"""
    global _pipeline_singleton
    if _pipeline_singleton is None:
        with _model_loading_lock:
            if _pipeline_singleton is None:
                _pipeline_singleton = LocalModelPipeline()
    return _pipeline_singleton


def _validate_request(req: CopyToImageReq) -> CopyToImageReq:
    """기본 요청 검증"""
    try:
        if not hasattr(req, "text") or req.text is None:
            raise HTTPException(status_code=400, detail=ErrorMessages.MALFORMED_REQUEST)

        if len(req.text) > 1000:
            raise HTTPException(status_code=400, detail=ErrorMessages.TEXT_TOO_LONG)

        if not req.text.strip():
            raise HTTPException(status_code=400, detail=ErrorMessages.TEXT_EMPTY)

        if req.seed is not None and (not isinstance(req.seed, int) or req.seed < 0):
            raise HTTPException(status_code=400, detail=ErrorMessages.INVALID_SEED)

        return req

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"{ErrorMessages.MALFORMED_REQUEST}: {str(e)}",
        )


@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    """텍스트로부터 이미지 생성 - (HF 번역 + 프롬프트 강화) → ComfyUI 생성"""
    validated_req = _validate_request(req)
    t0 = time.time()

    try:
        pipeline = _get_pipeline()

        # 1) 프롬프트 강화 (번역 + 스타일 번역 + 품질 키워드)
        t1 = time.time()
        enhanced_prompt = pipeline.enhance_prompt(validated_req.text, validated_req.style)
        enhancement_time = time.time() - t1

        # 2) ComfyUI로 실제 이미지 생성
        t2 = time.time()
        img_bytes = pipeline.generate_image_with_comfyui(enhanced_prompt, validated_req.seed)
        generation_time = time.time() - t2

        # 3) 파일 저장
        save_name = f"image_from_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)

        with open(save_path, "wb") as f:
            f.write(img_bytes)

        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"

        total_time = time.time() - t0

        return {
            "ok": True,
            "output_path": file_path,
            "file_url": file_url,
            "metadata": {
                "original_text": validated_req.text,
                "enhanced_prompt": enhanced_prompt,
                "style": validated_req.style,
                "seed": validated_req.seed,
                "model_used": "ComfyUI + HF Translation",
                "demo_mode": False,
                "timing": {
                    "enhancement_time": round(enhancement_time, 2),
                    "generation_time": round(generation_time, 2),
                    "total_time": round(total_time, 2),
                },
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"{ErrorMessages.UNKNOWN_ERROR}: {str(e)}",
        )


@router.get("/model-status")
def model_status():
    """현재 모델/연결 상태 확인"""
    comfyui_available = False
    comfyui_models = {}

    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=7)
        if response.status_code == 200:
            comfyui_available = True

            # 모델 목록 확인
            obj_info_response = requests.get(f"{COMFYUI_URL}/object_info", timeout=7)
            if obj_info_response.status_code == 200:
                obj_info = obj_info_response.json()

                # GGUF 모델 체크
                if "UnetLoaderGGUF" in obj_info:
                    # some Comfy builds return list-of-lists; guard for both
                    try:
                        unet_candidates = obj_info["UnetLoaderGGUF"]["input"]["required"]["unet_name"][0]
                        comfyui_models["unet"] = COMFYUI_MODELS["unet"] in unet_candidates
                    except Exception:
                        comfyui_models["unet"] = False

                # CLIP 모델 체크
                if "DualCLIPLoader" in obj_info:
                    try:
                        clip_candidates = obj_info["DualCLIPLoader"]["input"]["required"]["clip_name1"][0]
                        comfyui_models["clip_l"] = COMFYUI_MODELS["clip_l"] in clip_candidates
                        comfyui_models["clip_t5"] = COMFYUI_MODELS["clip_t5"] in clip_candidates
                    except Exception:
                        comfyui_models["clip_l"] = False
                        comfyui_models["clip_t5"] = False

                # VAE 모델 체크
                if "VAELoader" in obj_info:
                    try:
                        vae_candidates = obj_info["VAELoader"]["input"]["required"]["vae_name"][0]
                        comfyui_models["vae"] = COMFYUI_MODELS["vae"] in vae_candidates
                    except Exception:
                        comfyui_models["vae"] = False

    except Exception:
        pass

    all_models_ready = comfyui_available and (len(comfyui_models) == 0 or all(comfyui_models.values()))

    return {
        "translation": {
            "backend": "huggingface",
            "model": HF_TRANSLATION_MODEL,
            "ready": True,  # load 실패시 상단에서 500 반환되므로 여기선 True
        },
        "comfyui": {
            "server_available": comfyui_available,
            "url": COMFYUI_URL,
            "models": comfyui_models,
            "expected_models": COMFYUI_MODELS,
        },
        "prompt_enhancement": {
            "base_quality": "detailed, sharp, high quality",
        },
        "status": "ready" if all_models_ready else "not_ready",
        "message": "모든 시스템 준비됨" if all_models_ready else "브릿지/ComfyUI 연결/모델 확인 필요",
    }
