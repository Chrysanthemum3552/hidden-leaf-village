import os
from typing import Optional, Dict, Any

import requests
import streamlit as st
from dotenv import load_dotenv


# 1) 환경/상수
load_dotenv()

BACKEND: str = os.getenv("BACKEND_URL", "http://localhost:8000")
API_ENDPOINT: str = f"{BACKEND}/generate/copy-from-image"
REQ_TIMEOUT: int = 120

AGE_OPTIONS = ["", "10대", "20대", "30대", "40대", "시니어"]
ROLE_OPTIONS = ["", "학생", "직장인", "자영업", "육아", "프리미엄"]


# 2) 헬퍼 함수
def compose_persona(age: str, role: str) -> str:
    """연령/역할 선택값을 백엔드의 'persona' 문자열로 합성."""
    if age and role:
        return f"{age} {role}"
    return age or role or ""


def fetch_bytes(url: Optional[str], timeout: int = 10) -> Optional[bytes]:
    """
    URL에서 이미지를 바이트로 받아오기.
    - 1차 시도: 그대로 호출
    - 2차 시도: 'localhost' → '127.0.0.1' 대체 후 재시도
    """
    if not url:
        return None
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        try:
            alt = url.replace("localhost", "127.0.0.1")
            if alt != url:
                r2 = requests.get(alt, timeout=timeout)
                r2.raise_for_status()
                return r2.content
        except Exception:
            return None
    return None


def post_generate(files: Dict[str, Any], data: Dict[str, Any]) -> requests.Response:
    """백엔드 /generate/copy-from-image POST 요청."""
    return requests.post(API_ENDPOINT, files=files, data=data, timeout=REQ_TIMEOUT)


# 3) 페이지 기본 설정
st.set_page_config(page_title="광고 글 생성", page_icon="✍️", layout="centered")
st.title("✍️ 광고 글 생성 (이미지 → 문구)")


# 4) 입력 섹션
img = st.file_uploader("이미지를 업로드하세요", type=["png", "jpg", "jpeg", "webp"])

col1, col2 = st.columns(2)
with col1:
    age = st.selectbox("연령(선택)", AGE_OPTIONS, index=0)
with col2:
    role = st.selectbox("역할/상황(선택)", ROLE_OPTIONS, index=0)

# 키워드 입력(세션키 선초기화)
if "kw_input" not in st.session_state:
    st.session_state.kw_input = ""

st.text_input(
    "핵심 키워드 (선택, 쉼표)",
    key="kw_input",
    placeholder=(
        "예: 가성비, 빠른배송, 신상, 데일리, 미니멀, 감성 "
        "휴대성, 내구성, 성능, 프리미엄, 검증, A/S "
        "간편, 안심, 친환경, 선물추천, 한정, 오늘만"
    ),
    help="쉼표(,)로 구분해 1~3개 정도 입력하면 톤을 맞춰드려요. 비워도 됩니다.",
)

must_include_kw = st.checkbox("핵심 키워드 최소 1개는 반드시 포함", value=False)

business_name = st.text_input("상호/브랜드명 (선택)", placeholder="예: 나뭇잎마을")
must_include_brand = st.checkbox("상호/브랜드명을 문구에 반드시 포함", value=False)

st.markdown("---")

# 5) 액션: 생성 버튼 → 요청/응답 처리
if st.button("광고 글 생성", use_container_width=False):
    if not img:
        st.warning("이미지를 선택하세요.")
    else:
        with st.spinner("생성 중..."):
            # 5-1) 요청 준비
            files = {"file": (img.name, img.getvalue(), img.type)}
            persona_val = compose_persona(age, role)
            payload = {
                "persona": persona_val or None,
                "user_keywords_csv": (st.session_state.get("kw_input") or None),
                "must_include_keywords": str(bool(must_include_kw)).lower(),  # "true"/"false"
                "business_name": business_name or None,
                "must_include_brand": str(bool(must_include_brand)).lower(),
            }
            # 비어있는 값 제거
            data = {k: v for k, v in payload.items() if v not in ("", None)}

            # 5-2) 요청/에러 처리
            try:
                resp = post_generate(files, data)
            except Exception as e:
                st.error(f"요청 오류: {e}")
            else:
                if not resp.ok:
                    st.error(f"실패: {resp.text}")
                else:
                    res = resp.json()
                    st.success("완료!")

                    # 5-3) 결과 렌더링: 이미지
                    img_url = res.get("uploaded_url")
                    img_path = res.get("uploaded_path")

                    content = fetch_bytes(img_url) if img_url else None
                    if content:
                        st.image(content, caption="업로드 이미지", use_column_width=True)
                    elif img_path and os.path.exists(img_path):
                        st.image(img_path, caption="업로드 이미지(로컬)", use_column_width=True)
                    else:
                        st.info("이미지를 자동 표시하지 못했어요. 아래 링크로 직접 열어보세요.")
                        if img_url:
                            st.markdown(f"[이미지 열기]({img_url})")

                    # 5-4) 결과 렌더링: 카피/구조
                    st.subheader("생성된 광고 문구")
                    st.write(res.get("copy", ""))

                    structured = res.get("structured") or {}
                    if structured:
                        st.caption("헤드라인 / 서브라인 / 해시태그")
                        st.write(f"**{structured.get('headline','')}**")
                        st.write(structured.get('subline',''))
                        tags = " ".join(structured.get('hashtags', []))
                        if tags:
                            st.write(tags)

                    # 5-5) 로그/디버그
                    st.caption(f"log: {res.get('log_url') or res.get('log_path')}")
                    with st.expander("응답 원본(JSON) 보기"):
                        st.json(res)
