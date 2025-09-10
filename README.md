# hidden-leaf-village
이타치가 왜 강한지 아십니까?

![탈주닌자 이타치](https://i3.ruliweb.com/img/24/12/26/1940304a2c2349a83.webp)


---

# ad-gen-service 디렉토리 구조

```text
ad-gen-service/
├─ README.md
├─ .env.example
├─ scripts/
│  ├─ dev_run_backend.sh
│  └─ dev_run_frontend.sh
│
├─ backend_fastapi/
│  ├─ requirements.txt
│  ├─ main.py               # (FastAPI 기본 설정 및 통합)
│  ├─ models.py             # (공용 데이터 모델)
│  ├─ storage.py            # (저장소 유틸)
│  ├─ services/
│  │  ├─ image_utils.py     # (문구→이미지 관련 유틸, 리사이즈 등)
│  │  └─ menu_render.py     # (메뉴판 렌더링 유틸, Pillow/ReportLab)
│  └─ routers/
│     ├─ copy_from_image.py # (이미지→문구 API, GPT 호출 포함)
│     ├─ image_from_copy.py # (문구→이미지 API, GPT 호출 포함)
│     └─ menu_board.py      # (메뉴→메뉴판 API, GPT 호출 포함)
│
├─ frontend_streamlit/
│  ├─ requirements.txt
│  ├─ app.py                # (홈 화면 및 전체 네비게이션)
│  ├─ components/
│  │  ├─ api_client.py      # (FastAPI 연동 클라이언트)
│  │  ├─ ui.py              # (공통 UI 컴포넌트)
│  │  └─ validators.py      # (입력 검증)
│  ├─ pages/
│  │  ├─ 1_사진→문구.py     # (이미지→문구 프론트엔드)
│  │  ├─ 2_문구→이미지.py   # (문구→이미지 프론트엔드)
│  │  └─ 3_메뉴→메뉴판.py   # (메뉴→메뉴판 프론트엔드)
│  ├─ assets/
│  │  └─ styles.css         # (스타일/폰트/버튼 크기)
│  └─ .streamlit/
│     └─ secrets.toml       # (환경설정/API 주소)
│
└─ data/
   ├─ uploads/              # (업로드 이미지 저장)
   └─ outputs/              # (생성 결과 저장)
```

---


# ad-gen-service 디렉토리 구조 (파일별 역할 설명)

```text
ad-gen-service/
├─ README.md                # 프로젝트 소개 및 실행 방법
├─ .env.example             # 환경변수 예시 (API 키 등)
├─ scripts/                 # 개발 편의 스크립트 모음
│  ├─ dev_run_backend.sh    # FastAPI 백엔드 실행 스크립트
│  └─ dev_run_frontend.sh   # Streamlit 프론트 실행 스크립트
│
├─ backend_fastapi/         # 백엔드 (FastAPI 기반)
│  ├─ requirements.txt      # 백엔드 패키지 의존성
│  ├─ main.py               # FastAPI 앱 초기화, 라우터 등록, CORS/Static 설정
│  ├─ models.py             # 요청/응답 데이터 모델 정의 (Pydantic)
│  ├─ storage.py            # 업로드/출력 파일 저장 및 경로 유틸
│  ├─ services/             # 기능별 내부 로직
│  │  ├─ image_utils.py     # 이미지 리사이즈/배너 생성 등 유틸 함수
│  │  └─ menu_render.py     # 메뉴판 이미지를 Pillow/ReportLab으로 렌더링
│  └─ routers/              # API 엔드포인트 정의
│     ├─ copy_from_image.py # 이미지 → 광고 문구 생성 API
│     ├─ image_from_copy.py # 광고 문구 → 이미지 생성 API
│     └─ menu_board.py      # 메뉴/가격 입력 → 메뉴판 생성 API
│
├─ frontend_streamlit/      # 프론트엔드 (Streamlit 기반)
│  ├─ requirements.txt      # 프론트엔드 패키지 의존성
│  ├─ app.py                # 메인 홈 화면 (큰 버튼으로 3가지 기능 연결)
│  ├─ components/           # 공통 컴포넌트
│  │  ├─ api_client.py      # FastAPI와 통신하는 HTTP 클라이언트
│  │  ├─ ui.py              # UI 요소(큰 버튼, 네비게이션 등) 모음
│  │  └─ validators.py      # 입력값 검증 유틸
│  ├─ pages/                # 기능별 페이지
│  │  ├─ 1_사진→문구.py     # 이미지 업로드 → 광고 문구 출력 페이지
│  │  ├─ 2_문구→이미지.py   # 광고 문구 입력 → 이미지 생성 페이지
│  │  └─ 3_메뉴→메뉴판.py   # 메뉴/가격 입력 → 메뉴판 생성 페이지
│  ├─ assets/
│  │  └─ styles.css         # 전체 스타일 정의 (폰트 크기, 버튼 크기 등)
│  └─ .streamlit/
│     └─ secrets.toml       # Streamlit 비밀값 (API_BASE URL 등)
│
└─ data/                    # 파일 저장 디렉토리
   ├─ uploads/              # 업로드된 원본 파일 저장
   └─ outputs/              # 생성된 결과물 저장 (이미지, 메뉴판 등)
```




