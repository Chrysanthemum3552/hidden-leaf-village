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

# ──────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트 .env 로드 (단, 본 파일은 서비스 URL 하드코딩을 사용)
# ──────────────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../hidden-leaf-village
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

router = APIRouter()

# Render 퍼블릭 백엔드 URL (정적파일 URL 만들 때만 사용)
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "https://hidden-leaf-village.onrender.com").rstrip("/")

# 출력 경로 (백엔드 컨테이너 내부 고정)
STORAGE_ROOT = os.getenv(
    "STORAGE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
)
OUTPUT_DIR = os.path.join(STORAGE_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# ✅ 하드코딩된 외부 서비스 URL (Cloudflared 터널)
# ──────────────────────────────────────────────────────────────────────────────
# ComfyUI (로컬 127.0.0.1:8188 → https://*.trycloudflare.com)
COMFYUI_URL="https://baking-tomorrow-cow-broadband.trycloudflare.com"

# Rosetta GGUF 추론 서버 (로컬 127.0.0.1:8101 → https://*.trycloudflare.com)
ROSETTA_URL="https://commodity-yards-committee-events.trycloudflare.com"




# ComfyUI에서 사용할 모델 파일명 (해당 노드/플러그인에 설치되어 있어야 함)
COMFYUI_MODELS = {
    "unet": "flux1-schnell-Q4_K_S.gguf",
    "clip_l": "clip_l.safetensors",
    "clip_t5": "t5xxl_fp16.safetensors",
    "vae": "ae.safetensors",
}

# ──────────────────────────────────────────────────────────────────────────────
# 에러 메시지 상수
# ──────────────────────────────────────────────────────────────────────────────
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

    # 502 Bad Gateway
    TRANSLATION_ERROR = "번역 서비스에 일시적인 문제가 발생했습니다."
    IMAGE_GENERATION_ERROR = "이미지 생성 서비스에 일시적인 문제가 발생했습니다."

# ──────────────────────────────────────────────────────────────────────────────
# 요청 스키마
# ──────────────────────────────────────────────────────────────────────────────
class CopyToImageReq(BaseModel):
    text: str
    style: Optional[str] = None
    seed: Optional[int] = None

# ──────────────────────────────────────────────────────────────────────────────
# 파이프라인 (원격 서비스 호출 기반)
# ──────────────────────────────────────────────────────────────────────────────
_pipeline_singleton = None
_model_loading_lock = threading.Lock()


class RemoteServicesPipeline:
    """
    번역/분석: 원격 Rosetta 서비스 호출 (/infer)
    이미지 생성: 원격 ComfyUI 호출 (/prompt → /history/{id} → /view)
    """

    def __init__(self):
        self.loaded = False

    # ─────────────── 유틸: 원격 Rosetta 호출 ───────────────
    @staticmethod
    def _rosetta_infer(prompt: str, max_tokens: int = 256, temperature: float = 0.2, timeout: int = 60) -> str:
        try:
            r = requests.post(
                f"{ROSETTA_URL}/infer",
                json={"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            text = (data.get("text") or "").strip()
            return text
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"{ErrorMessages.TRANSLATION_ERROR}: {e}")

    # ─────────────── 서비스 헬스/준비 상태 확인 ───────────────
    def check_services(self):
        # ComfyUI 상태
        try:
            r = requests.get(f"{COMFYUI_URL}/api/system_stats", timeout=10)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI system_stats HTTP {r.status_code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"{ErrorMessages.IMAGE_GENERATION_ERROR}: ComfyUI 연결 실패 - {e}")

        # Rosetta 상태
        try:
            r = requests.get(f"{ROSETTA_URL}/health", timeout=10)
            if r.status_code != 200:
                raise RuntimeError(f"Rosetta health HTTP {r.status_code}")
            if not r.json().get("ok"):
                raise RuntimeError("Rosetta health returned ok=false")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"{ErrorMessages.TRANSLATION_ERROR}: Rosetta 연결 실패 - {e}")

    def load(self):
        """원격 서비스 사용 준비 확인 (로컬 모델 로딩 없음)"""
        if self.loaded:
            return
        self.check_services()
        self.loaded = True

    # ─────────────── 프롬프트 관련 기능 (번역/분류/강화) ───────────────
    @staticmethod
    def _contains_korean(text: str) -> bool:
        return any('\uac00' <= ch <= '\ud7af' for ch in text)

    def translate_to_english_if_korean(self, text: str) -> str:
        """입력이 한글이면 영어로 번역, 아니면 원문 유지 (Rosetta 호출)"""
        if not self._contains_korean(text):
            return text

        prompt = (
            "Translate the following Korean text to natural English for image generation. "
            "Only output the translation, no explanations.\n\n"
            f"Korean: {text}\nEnglish:"
        )
        translated = self._rosetta_infer(prompt, max_tokens=256, temperature=0.2)
        # 후처리: 앞뒤 접두어 제거
        if "English:" in translated:
            translated = translated.split("English:", 1)[-1]
        return translated.strip() or text

    def classify_has_person(self, english: str) -> bool:
        """문구에 명시적으로 사람/초상 관련 단어가 포함되는지 (YES/NO)"""
        prompt = (
            "Answer ONLY YES or NO.\n\n"
            f"Text: {english}\n\n"
            "Question: Does this text explicitly contain any human-related words "
            "(man, woman, person, people, child, boy, girl, baby, face, portrait, model, actor, actress, selfie)?\n"
            "Do NOT infer implied presence.\n\n"
            "Answer:"
        )
        ans = self._rosetta_infer(prompt, max_tokens=5, temperature=0.0).lower()
        return "yes" in ans

    def classify_has_object(self, english: str) -> bool:
        """문구가 사물/제품 묘사를 포함하는지 러프 체크 (YES/NO)"""
        prompt = (
            "Answer ONLY YES or NO.\n\n"
            f"Text: {english}\n\n"
            "Question: Does this text explicitly describe a product or object (e.g., cup, bag, phone, dessert, burger, coffee, poster)?\n"
            "Do NOT guess. Only explicit words.\n\n"
            "Answer:"
        )
        ans = self._rosetta_infer(prompt, max_tokens=5, temperature=0.0).lower()
        return "yes" in ans

    def enhance_prompt(self, text: str, style: Optional[str]) -> str:
        """번역 → 분류 → 품질 키워드 추가 → 스타일 합성"""
        self.load()

        # 1) 번역
        english = self.translate_to_english_if_korean(text)

        # 2) 분류
        has_person = self.classify_has_person(english)
        has_object = self.classify_has_object(english)

        # 3) 기본 품질 키워드
        enhanced = f"{english}, sharp, clean composition, high quality"

        if has_person:
            enhanced += ", portrait, detailed face, natural skin texture, studio lighting"
        if has_object:
            enhanced += ", product photo, centered object, crisp edges"

        if style:
            enhanced = f"{enhanced}, in {style} style"

        return enhanced

    # ─────────────── ComfyUI 이미지 생성 ───────────────
    def generate_image_with_comfyui(self, prompt: str, seed: Optional[int] = None) -> bytes:
        """
        ComfyUI REST:
          POST /prompt -> prompt_id
          GET  /history/{prompt_id} -> completed 시 outputs
          GET  /view?filename=...&subfolder=...&type=output -> 이미지 bytes
        """
        self.load()

        # 워크플로우 정의 (ComfyUI-GGUF + FLUX 셋업 기준)
        workflow = {
            "1": {
                "inputs": {"unet_name": COMFYUI_MODELS["unet"]},
                "class_type": "UnetLoaderGGUF",
                "_meta": {"title": "Load GGUF UNet"}
            },
            "2": {
                "inputs": {
                    "clip_name1": COMFYUI_MODELS["clip_l"],
                    "clip_name2": COMFYUI_MODELS["clip_t5"],
                    "type": "flux"
                },
                "class_type": "DualCLIPLoader",
                "_meta": {"title": "Load CLIP (flux)"}
            },
            "3": {
                "inputs": {"text": prompt, "clip": ["2", 0]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Encode Positive"}
            },
            "4": {
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Latent Canvas"}
            },
            "5": {
                "inputs": {
                    "seed": seed if isinstance(seed, int) and seed >= 0 else int(time.time()) % 1_000_000,
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["3", 0],  # 간단히 동일 negative
                    "latent_image": ["4", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"}
            },
            "6": {
                "inputs": {"vae_name": COMFYUI_MODELS["vae"]},
                "class_type": "VAELoader",
                "_meta": {"title": "Load VAE"}
            },
            "7": {
                "inputs": {"samples": ["5", 0], "vae": ["6", 0]},
                "class_type": "VAEDecode",
                "_meta": {"title": "Decode"}
            },
            "8": {
                "inputs": {"filename_prefix": "flux_output", "images": ["7", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "Save"}
            }
        }

        try:
            # 1) 프롬프트 제출
            client_id = str(uuid.uuid4())
            r = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=30,
            )
            r.raise_for_status()
            prompt_id = r.json().get("prompt_id")
            if not prompt_id:
                raise RuntimeError("ComfyUI /prompt 응답에 prompt_id 가 없습니다.")

            # 2) 완료 대기 (최대 ~5분)
            for _ in range(150):
                time.sleep(2)
                h = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=15)
                if h.status_code != 200:
                    continue
                hist = h.json() or {}
                if prompt_id not in hist:
                    continue
                task = hist[prompt_id]
                status = task.get("status", {})
                if status.get("completed"):
                    outputs = task.get("outputs", {})
                    for _, out in outputs.items():
                        if "images" in out:
                            for img in out["images"]:
                                params = {
                                    "filename": img["filename"],
                                    "subfolder": img.get("subfolder", ""),
                                    "type": "output",
                                }
                                vr = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=30)
                                if vr.status_code == 200:
                                    return vr.content
                    break
                if status.get("error"):
                    raise RuntimeError(f"ComfyUI 오류: {status.get('error')}")

            raise RuntimeError("ComfyUI 이미지 생성 타임아웃")

        except Exception as e:
            # 실패 시 데모 이미지로 폴백
            return self._generate_image_demo(prompt, seed, str(e))

    @staticmethod
    def _generate_image_demo(prompt: str, seed: Optional[int], reason: str) -> bytes:
        """ComfyUI 실패 시 간단한 PNG로 폴백"""
        from PIL import Image, ImageDraw, ImageFont
        import io

        img = Image.new('RGB', (1024, 1024), color='#8A3FFC')  # 보라 계열
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        lines = [
            "DEMO IMAGE (fallback)",
            "",
            f"Prompt: {prompt[:70]}{'...' if len(prompt) > 70 else ''}",
            f"Seed: {seed if seed is not None else 'Random'}",
            "",
            f"ComfyUI_URL: {COMFYUI_URL}",
            f"Rosetta_URL: {ROSETTA_URL}",
            "",
            "Reason:",
            reason[:70] + ('...' if len(reason) > 70 else '')
        ]
        y = 100
        for line in lines:
            if font:
                bbox = draw.textbbox((0, 0), line, font=font)
                x = (1024 - (bbox[2] - bbox[0])) // 2
                draw.text((x, y), line, fill='white', font=font)
            y += 36

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _get_pipeline() -> RemoteServicesPipeline:
    global _pipeline_singleton
    if _pipeline_singleton is None:
        with _model_loading_lock:
            if _pipeline_singleton is None:
                _pipeline_singleton = RemoteServicesPipeline()
    return _pipeline_singleton


def _validate_request(req: CopyToImageReq) -> CopyToImageReq:
    try:
        if not hasattr(req, 'text') or req.text is None:
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
        raise HTTPException(status_code=400, detail=f"{ErrorMessages.MALFORMED_REQUEST}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# 라우트: 텍스트 → 이미지
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/image-from-copy")
def image_from_copy(req: CopyToImageReq):
    validated = _validate_request(req)
    t0 = time.time()

    try:
        pipeline = _get_pipeline()

        # 1) 프롬프트 강화
        t_enh0 = time.time()
        enhanced_prompt = pipeline.enhance_prompt(validated.text, validated.style)
        t_enh = time.time() - t_enh0

        # 2) 이미지 생성 (ComfyUI)
        t_gen0 = time.time()
        img_bytes = pipeline.generate_image_with_comfyui(enhanced_prompt, validated.seed)
        t_gen = time.time() - t_gen0

        # 3) 파일 저장
        save_name = f"image_from_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(OUTPUT_DIR, save_name)
        try:
            with open(save_path, "wb") as f:
                f.write(img_bytes)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{ErrorMessages.FILE_SAVE_ERROR}: {e}")

        file_path = os.path.abspath(save_path).replace("\\", "/")
        file_url = f"{BACKEND_PUBLIC_URL}/static/outputs/{save_name}"

        return {
            "ok": True,
            "output_path": file_path,
            "file_url": file_url,
            "metadata": {
                "original_text": validated.text,
                "enhanced_prompt": enhanced_prompt,
                "style": validated.style,
                "seed": validated.seed,
                "model_used": "ComfyUI via Cloudflared + Rosetta via Cloudflared",
                "timing": {
                    "enhancement_time": round(t_enh, 2),
                    "generation_time": round(t_gen, 2),
                    "total_time": round(time.time() - t0, 2),
                },
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{ErrorMessages.UNKNOWN_ERROR}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# 라우트: 모델/서비스 상태 확인
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/model-status")
def model_status():
    comfy_ok = False
    comfy_models = {}

    # ComfyUI 상태
    try:
        rs = requests.get(f"{COMFYUI_URL}/api/system_stats", timeout=10)
        comfy_ok = (rs.status_code == 200)
    except Exception:
        comfy_ok = False

    # ComfyUI 모델 목록(선택적) — object_info 구조는 버전/커스텀노드마다 다름
    try:
        oi = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        if oi.status_code == 200:
            obj = oi.json()
            # 간단히 기대 모델명이 문자열로 포함되는지만 러프 체크
            comfy_models = {
                "unet": COMFYUI_MODELS["unet"] in str(obj.get("UnetLoaderGGUF", "")),
                "clip_l": COMFYUI_MODELS["clip_l"] in str(obj.get("DualCLIPLoader", "")),
                "clip_t5": COMFYUI_MODELS["clip_t5"] in str(obj.get("DualCLIPLoader", "")),
                "vae": COMFYUI_MODELS["vae"] in str(obj.get("VAELoader", "")),
            }
    except Exception:
        pass

    # Rosetta 상태
    rosetta_ok = False
    rosetta_model = None
    try:
        rh = requests.get(f"{ROSETTA_URL}/health", timeout=10)
        if rh.status_code == 200:
            j = rh.json()
            rosetta_ok = bool(j.get("ok"))
            rosetta_model = j.get("model")
    except Exception:
        rosetta_ok = False

    all_ready = comfy_ok and rosetta_ok

    return {
        "comfyui": {
            "server_available": comfy_ok,
            "url": COMFYUI_URL,
            "models_presence_guess": comfy_models,
        },
        "rosetta": {
            "server_available": rosetta_ok,
            "url": ROSETTA_URL,
            "model_path": rosetta_model,
        },
        "dependencies": {
            "backend_outputs_dir": OUTPUT_DIR,
            "static_serving_hint": f"{BACKEND_PUBLIC_URL}/static/outputs/<filename>.png"
        },
        "status": "ready" if all_ready else "not_ready",
        "message": "모든 시스템 준비됨" if all_ready else "외부 서비스 연결을 확인하세요",
    }
