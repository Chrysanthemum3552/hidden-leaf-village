# hidden-leaf-village
이타치가 왜 강한지 아십니까?

![탈주닌자 이타치](https://i3.ruliweb.com/img/24/12/26/1940304a2c2349a83.webp)

---
# 필독
```text

api키는 깃헙에 직접 업로드가 불가능하여 .env파일은 따로 가져와야함 Discord에 업로드를 해놓겠습니다.
불러오는 방법은 .env파일을 루트폴더(가장 상위폴더)에 넣고 아래를 입력하면 되긴하는데 직접 쓰셔도 괜찮습니다.

load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True) # .env를 로드하는 코드

#해당 파일의 정보들을 가져오는 코드
OPENAI_BASE = os.getenv("TEAM_GPT_BASE_URL", "https://api.openai.com/v1").rstrip("/") 
OPENAI_KEY = os.getenv("TEAM_GPT_API_KEY")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

※걍 GPT께 맡기십쇼.... ㅠ

```
---

# ad-gen-service 디렉토리 구조

```text
소상 공인을 위한 생성형 AI 프로젝트/
├─ .env.example
├─ README.md
│
├─ scripts/
│  ├─ dev_run_backend.sh        # FastAPI 실행 스크립트
│  └─ dev_run_frontend.sh       # Streamlit 실행 스크립트
│
├─ backend_fastapi/             #백앤드 폴더
│  ├─ requirements.txt
│  ├─ main.py                   # FastAPI 부트스트랩 + 라우터 등록
│  └─ routes/
│     ├─ copy_from_image.py     # (3) 이미지→글 생성 ⭐신한호님
│     ├─ image_from_copy.py     # (2) 글→이미지 생성 ⭐정민영님
│     └─ menu_board.py          # (1) 메뉴판 생성    ⭐주대성님
│
├─ frontend_streamlit/          # 프론트 앤드 폴더
│  ├─ requirements.txt
│  ├─ app.py                    # 홈(버튼 3개)
│  └─ pages/
│     ├─ 1_광고_이미지_생성.py     # (2) 글→이미지
│     ├─ 2_광고_글_생성.py         # (3) 이미지→글
│     └─ 3_메뉴판_생성.py          # (1) 메뉴/가격 입력
│
└─ data/
   ├─ uploads/                  # 업로드/원본 저장
   └─ outputs/                  # 생성 결과 저장(이미지/로그)


```

---

```text
# 실행방법

1. 첫 번째 터미널을 열고 backend_fastapi 디렉터리로 이동한 뒤 다음을 입력
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

2. 새로운 터미널을 하나 더 열고 이번엔 frontend_streamlit 디렉터리로 이동 뒤 다음을 입력
python -m streamlit run app.py --server.port 8501
```
