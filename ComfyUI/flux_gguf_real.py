"""
실제 FLUX GGUF 추론 시스템
ComfyUI API를 통한 진짜 이미지 생성

사용법:
    # ComfyUI 서버 먼저 실행
    cd ComfyUI && python main.py
    
    # 별도 터미널에서 실행
    python flux_gguf_real.py --model Q4_K_S --prompt "a beautiful sunset"
"""

import requests
import json
import time
import uuid
import logging
from pathlib import Path
from PIL import Image
import io
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime
import pandas as pd

class ComfyUIGGUFRunner:
    """ComfyUI GGUF 실제 추론 실행기"""
    
    def __init__(self, 
                 comfyui_url: str = "http://127.0.0.1:8188",
                 logger: Optional[logging.Logger] = None):
        self.url = comfyui_url
        self.logger = logger or self._setup_logger()
        self.client_id = str(uuid.uuid4())
        
        # 연결 테스트
        self._test_connection()
    
    def _setup_logger(self) -> logging.Logger:
        """로거 설정"""
        logger = logging.getLogger('flux_gguf_real')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _test_connection(self):
        """ComfyUI 연결 테스트"""
        try:
            response = requests.get(f"{self.url}/system_stats", timeout=5)
            if response.status_code == 200:
                self.logger.info("ComfyUI 연결 성공")
            else:
                self.logger.warning(f"ComfyUI 응답 이상: {response.status_code}")
        except Exception as e:
            self.logger.error(f"ComfyUI 연결 실패: {e}")
            self.logger.error("ComfyUI 서버가 실행 중인지 확인하세요")
            raise
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """사용 가능한 모델 목록 조회"""
        try:
            response = requests.get(f"{self.url}/object_info")
            data = response.json()
            
            models = {}
            
            # GGUF 모델 확인
            if "UnetLoaderGGUF" in data:
                unet_info = data["UnetLoaderGGUF"]["input"]["required"]
                if "unet_name" in unet_info:
                    models["gguf_models"] = unet_info["unet_name"][0]
            
            # VAE 모델 확인  
            if "VAELoader" in data:
                vae_info = data["VAELoader"]["input"]["required"]
                if "vae_name" in vae_info:
                    models["vae_models"] = vae_info["vae_name"][0]
            
            # CLIP 모델 확인
            if "DualCLIPLoader" in data:
                clip_info = data["DualCLIPLoader"]["input"]["required"]
                if "clip_name1" in clip_info:
                    models["clip_models"] = clip_info["clip_name1"][0]
            
            return models
            
        except Exception as e:
            self.logger.error(f"모델 목록 조회 실패: {e}")
            return {}
    
    def create_workflow(self, 
                       gguf_model: str,
                       prompt: str,
                       width: int = 512,
                       height: int = 512,
                       steps: int = 4,
                       seed: int = None) -> Dict:
        """GGUF 워크플로우 생성"""
        
        if seed is None:
            seed = int(time.time())
        
        # FLUX.1-schnell 최적화 워크플로우
        workflow = {
            "1": {
                "inputs": {
                    "unet_name": gguf_model
                },
                "class_type": "UnetLoaderGGUF",
                "_meta": {"title": "Load GGUF Model"}
            },
            "2": {
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "t5xxl_fp16.safetensors", 
                    "type": "flux"
                },
                "class_type": "DualCLIPLoader",
                "_meta": {"title": "Load CLIP"}
            },
            "3": {
                "inputs": {
                    "text": prompt,
                    "clip": ["2", 0]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Encode Prompt"}
            },
            "4": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent"}
            },
            "5": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,  # schnell은 CFG 1.0 고정
                    "sampler_name": "euler",
                    "scheduler": "simple", 
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["3", 0],  # schnell은 negative 불필요
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "Sample"}
            },
            "6": {
                "inputs": {
                    "vae_name": "ae.safetensors"
                },
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
                    "filename_prefix": f"gguf_{gguf_model.split('.')[0]}",
                    "images": ["7", 0]
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save"}
            }
        }
        
        return workflow
    
    def generate_image(self,
                      gguf_model: str,
                      prompt: str, 
                      **kwargs) -> Tuple[bool, Dict]:
        """실제 이미지 생성"""
        
        self.logger.info(f"생성 시작: {gguf_model}")
        self.logger.info(f"프롬프트: {prompt[:50]}...")
        
        start_time = time.time()
        
        try:
            # 워크플로우 생성
            workflow = self.create_workflow(gguf_model, prompt, **kwargs)
            
            # 작업 제출
            response = requests.post(
                f"{self.url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id}
            )
            response.raise_for_status()
            
            prompt_id = response.json()["prompt_id"]
            self.logger.info(f"작업 ID: {prompt_id}")
            
            # 완료 대기
            success, result = self._wait_completion(prompt_id, timeout=300)
            
            total_time = time.time() - start_time
            
            if success:
                self.logger.info(f"생성 완료: {total_time:.2f}초")
                
                # 메타데이터 구성
                metadata = {
                    "success": True,
                    "gguf_model": gguf_model,
                    "prompt": prompt,
                    "generation_time": total_time,
                    "prompt_id": prompt_id,
                    "timestamp": datetime.now().isoformat(),
                    **kwargs,
                    **result
                }
                
                return True, metadata
            else:
                self.logger.error(f"생성 실패: {result.get('error', 'Unknown')}")
                return False, {
                    "success": False, 
                    "error": result.get('error'),
                    "generation_time": total_time
                }
                
        except Exception as e:
            self.logger.error(f"생성 중 오류: {e}")
            return False, {
                "success": False,
                "error": str(e), 
                "generation_time": time.time() - start_time
            }
    
    def _wait_completion(self, prompt_id: str, timeout: int = 300) -> Tuple[bool, Dict]:
        """작업 완료 대기"""
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 히스토리 확인
                response = requests.get(f"{self.url}/history/{prompt_id}")
                
                if response.status_code == 200:
                    history = response.json()
                    
                    if prompt_id in history:
                        task_info = history[prompt_id]
                        status = task_info.get("status", {})
                        
                        # 완료됨
                        if status.get("completed", False):
                            # 결과 이미지 수집
                            images = self._collect_images(task_info)
                            return True, {
                                "images": images,
                                "task_info": task_info
                            }
                        
                        # 에러 발생
                        if "error" in status:
                            return False, {"error": status["error"]}
                
                time.sleep(2)  # 2초 대기
                
            except Exception as e:
                self.logger.warning(f"상태 확인 실패: {e}")
                time.sleep(3)
        
        return False, {"error": "Timeout"}
    
    def _collect_images(self, task_info: Dict) -> List[Image.Image]:
        """결과 이미지 수집"""
        
        images = []
        
        try:
            outputs = task_info.get("outputs", {})
            
            for node_id, output in outputs.items():
                if "images" in output:
                    for img_data in output["images"]:
                        # 이미지 다운로드
                        img_url = f"{self.url}/view"
                        params = {
                            "filename": img_data["filename"],
                            "subfolder": img_data.get("subfolder", ""),
                            "type": img_data.get("type", "output")
                        }
                        
                        img_response = requests.get(img_url, params=params)
                        
                        if img_response.status_code == 200:
                            image = Image.open(io.BytesIO(img_response.content))
                            images.append(image)
                            self.logger.info(f"이미지 수집: {img_data['filename']}")
        
        except Exception as e:
            self.logger.error(f"이미지 수집 실패: {e}")
        
        return images

class GGUFPerformanceTester:
    """GGUF 성능 테스터"""
    
    def __init__(self, runner: ComfyUIGGUFRunner, output_dir: str = "gguf_results"):
        self.runner = runner
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results = []
    
    def test_single_model(self, model_name: str, prompt: str, **kwargs) -> Dict:
        """단일 모델 테스트"""
        
        success, result = self.runner.generate_image(model_name, prompt, **kwargs)
        
        if success and result.get("images"):
            # 이미지 저장
            for i, image in enumerate(result["images"]):
                filename = f"{model_name.split('.')[0]}_{int(time.time())}_{i}.png"
                save_path = self.output_dir / filename
                image.save(save_path)
                result[f"saved_image_{i}"] = str(save_path)
        
        return result
    
    def compare_models(self, 
                      model_list: List[str],
                      test_prompts: List[str],
                      **kwargs) -> pd.DataFrame:
        """다중 모델 비교"""
        
        self.runner.logger.info(f"모델 비교 시작: {len(model_list)}개 모델 × {len(test_prompts)}개 프롬프트")
        
        total_tests = len(model_list) * len(test_prompts)
        test_count = 0
        
        for prompt_idx, prompt in enumerate(test_prompts):
            self.runner.logger.info(f"\n프롬프트 {prompt_idx+1}: {prompt[:50]}...")
            
            for model in model_list:
                test_count += 1
                progress = test_count / total_tests * 100
                
                self.runner.logger.info(f"진행률: {test_count}/{total_tests} ({progress:.1f}%) - {model}")
                
                result = self.test_single_model(model, prompt, **kwargs)
                result["prompt_idx"] = prompt_idx
                result["model_name"] = model
                
                self.results.append(result)
        
        # 결과 DataFrame
        df = pd.DataFrame(self.results)
        
        # 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = self.output_dir / f"gguf_comparison_{timestamp}.csv"
        df.to_csv(csv_path, index=False)
        
        self.runner.logger.info(f"결과 저장: {csv_path}")
        
        return df
    
    def analyze_results(self, df: pd.DataFrame):
        """결과 분석"""
        
        print("\n" + "="*60)
        print("FLUX GGUF 성능 분석 결과")
        print("="*60)
        
        # 성공한 테스트만
        df_success = df[df['success'] == True]
        
        if len(df_success) == 0:
            print("성공한 테스트가 없습니다.")
            return
        
        # 모델별 통계
        stats = df_success.groupby('model_name').agg({
            'generation_time': ['mean', 'std', 'min', 'max'],
            'success': 'count'
        }).round(2)
        
        print(f"\n모델별 성능 (성공 {len(df_success)}/{len(df)}개)")
        print("-" * 60)
        
        for model in stats.index:
            time_stats = stats.loc[model, 'generation_time']
            count = int(stats.loc[model, ('success', 'count')])
            
            print(f"{model}:")
            print(f"  생성 시간: {time_stats['mean']:.2f}±{time_stats['std']:.2f}초")
            print(f"  범위: {time_stats['min']:.2f}-{time_stats['max']:.2f}초")
            print(f"  테스트 수: {count}개")
            print()
        
        # 추천
        if len(df_success) > 0:
            fastest = df_success.loc[df_success['generation_time'].idxmin()]
            print(f"최고 속도: {fastest['model_name']} ({fastest['generation_time']:.2f}초)")

# 테스트 프롬프트
TEST_PROMPTS = [
    "a beautiful sunset over mountains",
    "a futuristic city with flying cars", 
    "a peaceful garden with cherry blossoms",
    "a vintage car on a country road",
    "a wise old wizard with magical staff"
]

def main():
    parser = argparse.ArgumentParser(description='FLUX GGUF 실제 성능 테스트')
    parser.add_argument('--model', default='flux1-schnell-Q4_K_S.gguf', help='GGUF 모델 파일명')
    parser.add_argument('--prompt', default='a beautiful landscape', help='테스트 프롬프트')
    parser.add_argument('--compare', action='store_true', help='모든 모델 비교')
    parser.add_argument('--resolution', type=int, default=512, help='해상도')
    parser.add_argument('--steps', type=int, default=4, help='생성 스텝')
    parser.add_argument('--comfyui_url', default='http://127.0.0.1:8188', help='ComfyUI URL')
    
    args = parser.parse_args()
    
    try:
        # 실행기 초기화
        runner = ComfyUIGGUFRunner(args.comfyui_url)
        
        # 사용 가능한 모델 확인
        available = runner.get_available_models()
        gguf_models = available.get("gguf_models", [])
        
        runner.logger.info(f"사용 가능한 GGUF 모델: {gguf_models}")
        
        if not gguf_models:
            runner.logger.error("GGUF 모델이 없습니다. models/unet/ 폴더를 확인하세요.")
            return
        
        # 성능 테스터 초기화
        tester = GGUFPerformanceTester(runner)
        
        if args.compare:
            # 모든 모델 비교
            df_results = tester.compare_models(
                gguf_models,
                TEST_PROMPTS[:3],
                width=args.resolution,
                height=args.resolution,
                steps=args.steps
            )
            tester.analyze_results(df_results)
        else:
            # 단일 모델 테스트
            if args.model not in gguf_models:
                runner.logger.warning(f"모델 {args.model}을 찾을 수 없습니다. 첫 번째 모델 사용: {gguf_models[0]}")
                args.model = gguf_models[0]
            
            result = tester.test_single_model(
                args.model,
                args.prompt,
                width=args.resolution,
                height=args.resolution,
                steps=args.steps
            )
            
            if result["success"]:
                runner.logger.info("테스트 성공!")
                runner.logger.info(f"생성 시간: {result['generation_time']:.2f}초")
                if "saved_image_0" in result:
                    runner.logger.info(f"이미지 저장: {result['saved_image_0']}")
            else:
                runner.logger.error(f"테스트 실패: {result.get('error')}")
    
    except Exception as e:
        print(f"실행 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()