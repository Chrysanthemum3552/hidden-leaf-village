# ComfyUI + GGUF 실행 및 실험 보고서

이 저장소는 ComfyUI를 활용해 GGUF 양자화 모델(Flux.1 시리즈)을 실행하고<br>
실제 성능 비교 실험을 수행한 결과를 정리한 문서입니다.<br>
`flux_gguf_real.py` 스크립트를 통해 ComfyUI API 기반 자동화 추론을 지원합니다.

## 📌 설치
### 1. ComfyUI 설치
```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python -m pip install -r requirements.txt
```

권장: Python 3.10~3.11, conda 가상환경 사용

2. GGUF 커스텀 노드 설치
```bash
cd custom_nodes
git clone https://github.com/city96/ComfyUI-GGUF.git
cd ComfyUI-GGUF
python -m pip install -r requirements.txt
cd ../..
```
3. 모델 디렉토리 생성
```bash
mkdir -p ComfyUI/models/unet \
         ComfyUI/models/vae \
         ComfyUI/models/clip
```

4. 모델 다운로드
UNet (GGUF Quantized)
```bash
wget -O ComfyUI/models/unet/flux1-schnell-Q4_K_S.gguf \
  https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_S.gguf

wget -O ComfyUI/models/unet/flux1-schnell-Q6_K.gguf \
  https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q6_K.gguf

wget -O ComfyUI/models/unet/flux1-schnell-Q8_0.gguf \
  https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q8_0.gguf
```

VAE
```bash
wget -O ComfyUI/models/vae/ae.safetensors \
  https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors
```

Text Encoder (CLIP)
```bash
wget -O ComfyUI/models/clip/clip_l.safetensors \
  https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/pytorch_model.bin
```
▶️ 실행
```bash
cd ComfyUI
python main.py
```

UI 접속: http://localhost:8188

디렉토리 구조
```text
ComfyUI/
├─ main.py
├─ flux_gguf_real.py
├─ custom_nodes/
│  └─ ComfyUI-GGUF/
└─ models/
   ├─ unet/
   │   ├─ flux1-schnell-Q4_K_S.gguf
   │   ├─ flux1-schnell-Q6_K.gguf
   │   └─ flux1-schnell-Q8_0.gguf
   ├─ vae/
   │   └─ ae.safetensors
   └─ clip/
       └─ clip_l.safetensors
```
🧪 실험 보고서
1. 실험 방법

실행기: `flux_gguf_real.py` (ComfyUI API 기반)

환경: `NVIDIA L4 24GB VRAM`, `Python 3.11`, `CUDA 12.4`

모델:

`flux1-schnell-Q4_K_S.gguf` (6.32 GB)

`flux1-schnell-Q6_K.gguf` (9.16 GB)

`flux1-schnell-Q8_0.gguf` (11.82 GB)

해상도: `1024×1024`

스텝 수: `4`

공통 프롬프트:
```text
"a renaissance master painter creating a detailed portrait, 
intricate brush strokes visible, oil paints on wooden palette, 
canvas with half-finished masterpiece, artist's weathered hands with paint stains, 
vintage easel, studio filled with classical sculptures, antique furniture, 
scattered art supplies, dramatic chiaroscuro lighting, dust particles in sunbeams, 
highly detailed, sharp focus, clean composition, 8k quality, photorealistic"
```
2. 측정 지표

첫 실행 시간: 모델 최초 로딩 포함 (cold start)

캐싱 후 실행 시간: 동일 모델 재실행 시 latency

3. 결과
| 모델                        | 크기 (GB) | 첫 실행 시간 | 캐싱 후 실행 시간 |
|-----------------------------|-----------|--------------|------------------|
| flux1-schnell-Q4_K_S.gguf   | 6.32 GB   | 48.12초      | 12.04초          |
| flux1-schnell-Q6_K.gguf     | 9.16 GB   | 64.16초      | 14.04초          |
| flux1-schnell-Q8_0.gguf     | 11.82 GB  | 76.17초      | 10.03초          |
4. 인사이트

모델 크기가 커질수록 첫 실행 시간 증가 → 디스크→VRAM 로딩 시간 때문

캐싱 후 속도는 단순히 크기에 비례하지 않음

Q8_0: 가장 큰 모델이지만 캐싱 후 가장 빠름

Q4_K_S: 경량 모델로 빠르지만, 캐싱 효율은 낮음

Q6_K: 모든 면에서 중간값, 특출난 장점은 없음

✅ 결론

빠른 실험 반복이 필요 → Q4_K_S

품질+속도 균형 필요 → Q8_0

⚡ 자동화 실행기 (flux_gguf_real.py)
개요

ComfyUI API를 활용한 자동 추론/로그 기록기

이미지 저장 + CSV 로그 기록 + 성능 통계 출력 지원

사용법

ComfyUI 서버 실행

cd ComfyUI
python main.py


별도 터미널에서 실행

python flux_gguf_real.py --model flux1-schnell-Q4_K_S.gguf --prompt "a beautiful sunset"

### 주요 옵션

| 옵션          | 설명                     | 기본값                        |
|---------------|--------------------------|-------------------------------|
| `--model`     | 실행할 GGUF 모델 파일명  | `flux1-schnell-Q4_K_S.gguf`   |
| `--prompt`    | 이미지 생성 프롬프트     | `"a beautiful landscape"`      |
| `--resolution`| 이미지 해상도 (정사각형) | `512`                         |
| `--steps`     | Diffusion 생성 스텝 수   | `4`                           |
| `--compare`   | 모든 모델 비교 실행      | `False`                       |
| `--comfyui_url` | ComfyUI 서버 URL        | `http://127.0.0.1:8188`       |
실행 예시
# 단일 모델 실행
```bash
python flux_gguf_real.py --model flux1-schnell-Q8_0.gguf \
  --prompt "a futuristic city with flying cars" \
  --resolution 1024 --steps 6
```
# 다중 모델 비교 실행
```bash
python flux_gguf_real.py --compare --resolution 512 --steps 4
```
출력

gguf_results/ 폴더에 생성 이미지 + CSV 로그 저장

CSV에는 모델명, 프롬프트, 실행 시간, 성공 여부, 이미지 경로 기록

실행 종료 후 모델별 평균/범위/최고속도 모델 자동 출력

📖 참고

[ComfyUI 공식 저장소](https://github.com/comfyanonymous/ComfyUI)
[ComfyUI-GGUF 플러그인](https://github.com/city96/ComfyUI-GGUF)
[FLUX GPU Requirements, 설치방법](https://www.internetmap.kr/entry/FLUX-GPU-requirements)