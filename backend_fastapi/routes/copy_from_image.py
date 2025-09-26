# -*- coding: utf-8 -*-
import os, re, json, uuid, base64, mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from dotenv import load_dotenv, find_dotenv

router = APIRouter()
ALLOWED_EXTS = {"jpg","jpeg","png","webp"}

# .env
_HERE = Path(__file__).resolve()
for _p in (_HERE.parents[2]/".env", _HERE.parents[1]/".env", _HERE.parent/".env", Path(find_dotenv())):
    try:
        if _p and _p.exists(): load_dotenv(dotenv_path=_p, override=True); break
    except: pass

OPENAI_BASE = os.getenv("TEAM_GPT_BASE_URL","https://api.openai.com/v1").rstrip("/")
OPENAI_KEY  = os.getenv("TEAM_GPT_API_KEY")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL","http://localhost:8000").rstrip("/")
STORAGE_ROOT = os.getenv("STORAGE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..","data")))
UPLOAD_DIR, OUTPUT_DIR = os.path.join(STORAGE_ROOT,"uploads"), os.path.join(STORAGE_ROOT,"outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True); os.makedirs(OUTPUT_DIR, exist_ok=True)
MODEL_VISION  = os.getenv("OPENAI_VISION_MODEL","gpt-4o-mini")
MODEL_FALLBACK= os.getenv("OPENAI_VISION_FALLBACK_MODEL","gpt-4o")
MAX_FILE_MB   = float(os.getenv("MAX_FILE_MB","15"))

def _now_str(): return datetime.now().strftime("%Y%m%d_%H%M%S")
def _headers():
    if not OPENAI_KEY: raise HTTPException(500,"OpenAI API key missing")
    h={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"}
    if os.getenv("OPENAI_ORG_ID"): h["OpenAI-Organization"]=os.getenv("OPENAI_ORG_ID")
    if os.getenv("OPENAI_PROJECT_ID"): h["OpenAI-Project"]=os.getenv("OPENAI_PROJECT_ID")
    return h
def _session():
    s=requests.Session(); ad=HTTPAdapter(max_retries=Retry(total=2,backoff_factor=.5,status_forcelist=[429,500,502,503,504],allowed_methods=frozenset(["POST"])))
    s.mount("https://",ad); s.mount("http://",ad); return s
def _data_url(b,ct): return f"data:{(ct or 'image/png')};base64,{base64.b64encode(b).decode()}"
def _smart_trim(t,l):
    t=(t or "").strip()
    if len(t)<=l: return t
    cut=re.sub(r"[\s,.:;/\-–—_]+?$","",t[:l])
    return cut if re.search(r"[.!?…]$",cut) else cut+"..."
def _norm_tags(tags,n,allow_emoji):
    out=[]; 
    for t in (tags or [])[:max(0,n)]:
        t=re.sub(r"^#+","",(t or "").strip()); 
        if not allow_emoji: t=re.sub(r"[^\w가-힣0-9_]+","",t)
        if t: out.append("#"+t)
    uniq=[]; seen=set()
    for t in out:
        if t not in seen: uniq.append(t); seen.add(t)
    return uniq
def _contains_banned(t,b): 
    t=t or ""; return any(x.lower() in t.lower() for x in (b or []))
def _platform_hint(p):
    return {"instagram":"인스타그램은 짧고 강렬, 해시태그 친화적.",
            "naver":"네이버는 정보성/신뢰감 강조.",
            "coupang":"커머스 톤, 혜택/가격/배송 강조.",
            "smartstore":"스마트스토어 톤, 혜택·구성·신뢰 포인트.",
            "x":"X(트위터)는 초단문 이목집중."}.get((p or "").lower(),"플랫폼 일반 톤.")
def _csv(s): return [w.strip() for w in (s or "").split(",") if w.strip()]
def _any_in(t,ws):
    t=(t or "").lower(); return any((w or "").lower() in t for w in (ws or []))
def _tobool(x): return str(x).strip().lower() in ("1","true","yes","on")
def _json_obj(raw, fb):
    if raw is None: return fb
    try: v=json.loads(raw)
    except:
        m=re.search(r"\{.*\}", str(raw), re.S)
        if not m: return fb
        try: v=json.loads(m.group(0))
        except: return fb
    return v if isinstance(v,dict) else fb
def _norm_candidates(p):
    c=p.get("candidates",[]); out=[]
    if isinstance(c,dict): out=[c]
    elif isinstance(c,list):
        for x in c:
            if isinstance(x,dict): out.append(x)
            elif isinstance(x,str) and x.strip(): out.append({"headline":x.strip(),"subline":"","hashtags":[],"reasons":""})
    return out
def _norm_keywords(p,n):
    k=p.get("keywords")
    if isinstance(k,list): return [str(x).strip() for x in k if str(x).strip()][:n]
    if isinstance(k,str): return [q.strip() for q in re.split(r"[,\n/|]",k) if q.strip()][:n]
    return []

# Persona DB(축약)
AGE_DB: Dict[str,Dict[str,Any]]={
 "10대":{"style":"짧고 즉발 구어체","lexicon":["찐","가보자","핵꿀템","힙","겟"],"avoid":["과도한 공손체(습니다)","장문"],"cta":["지금 겟"],"emoji":"allow1","formality":"casual","punctuation":"light","headline_len":(6,14),"subline_len":(10,32),"required":[]},
 "20대":{"style":"트렌디·담백","lexicon":["미니멀","워라밸","가심비","무드","데일리"],"avoid":["과대광고","과한 신조어"],"cta":["지금 바로 확인!"],"emoji":"allow1","formality":"neutral","punctuation":"light","headline_len":(8,18),"subline_len":(12,44),"required":[]},
 "30대":{"style":"실용/퀄리티/시간 절약, 담백 존댓말","lexicon":["퀄리티","효율","루틴","집중"],"avoid":["속어","밈"],"cta":["지금 확인하세요"],"emoji":"none","formality":"polite","punctuation":"normal","headline_len":(10,22),"subline_len":(16,50),"required":[]},
 "40대":{"style":"신뢰/유지관리/건강, 정중체","lexicon":["신뢰","안심","내구","A/S"],"avoid":["속어","밈"],"cta":["지금 확인하십시오"],"emoji":"none","formality":"polite","punctuation":"normal","headline_len":(10,22),"subline_len":(18,60),"required":[]},
 "시니어":{"style":"명료한 정보 1~2개","lexicon":["편안하게","가독성","서비스","안전"],"avoid":["은어","속어","밈"],"cta":["지금 확인십시오"],"emoji":"none","formality":"polite","punctuation":"normal","headline_len":(10,22),"subline_len":(18,60),"required":[]},
}
ROLE_DB: Dict[str,Dict[str,Any]]={
 "학생":{"style_add":"가격/휴대성/학습편의","lexicon_add":["가성비","휴대성","필수템"],"avoid_add":[],"required_add":[]},
 "직장인":{"style_add":"업무 효율·시간·집중·루틴","lexicon_add":["업무시간","집중","루틴","생산성"],"avoid_add":["속어","밈"],"cta_add":["지금 확인하세요"],"required_add":[]},
 "자영업":{"style_add":"매출/운영/비용·관리","lexicon_add":["매출","운영","관리","비용절감"],"avoid_add":["속어"],"cta_add":["지금 확인하세요"],"required_add":[]},
 "육아":{"style_add":"안심/저자극/성분","lexicon_add":["저자극","안심","아이 피부","육아템","빠른흡수","성분","검증"],"avoid_add":["속어","밈","자극"],"cta_add":["지금 만나보세요"],"required_add":["아기","아이","우리 아이","유아","아이용"]},
 "프리미엄":{"style_add":"원료/보증/차별","lexicon_add":["프리미엄","장인","원료","보증"],"avoid_add":["싼티"],"cta_add":["지금 확인하기"],"required_add":[]},
}
def _parse_persona(p:Optional[str])->Tuple[Optional[str],Optional[str]]:
    if not p: return None,None
    tokens=re.split(r"[\/\s,]+",p.strip()); age=role=None
    for t in tokens:
        if t in AGE_DB: age=t
        if t in ROLE_DB: role=t
    if not age and p in AGE_DB: age=p
    if not role and p in ROLE_DB: role=p
    return age,role
def _merge_spec(a:Dict[str,Any], r:Optional[Dict[str,Any]])->Dict[str,Any]:
    s=dict(a)
    if r:
        s["style"]=f"{s['style']} {r.get('style_add','')}".strip()
        for ka,kb in [("lexicon","lexicon_add"),("avoid","avoid_add"),("cta","cta_add"),("required","required_add")]:
            s[ka]=list(dict.fromkeys((s.get(ka,[]) or [])+(r.get(kb,[]) or [])))
    return s
def _persona(persona:Optional[str])->Optional[Dict[str,Any]]:
    age,role=_parse_persona(persona)
    if not age and not role: return None
    if not age and role: age="20대"
    return _merge_spec(AGE_DB.get(age) or AGE_DB["20대"], ROLE_DB.get(role) if role else None)

def _formality_score_kor(t:str)->float:
    if not t: return 0.0
    s=0.0
    s+=1.0*len(re.findall(r"(습니다|습니까|하세요|하실|해요|되어요|되세요)",t))
    s-=0.7*len(re.findall(r"(해봐|가보자|하자|해버려|ㄱㄱ|ㄴㄴ|ㅇㅇ)",t))
    return s
def _count_emoji(t:str)->int: return 0 if not t else len(re.findall(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]",t))
def _len_score(t:str,r:Tuple[int,int])->float:
    n=len((t or "").strip()); lo,hi=r
    if n==0: return 0.0
    if lo<=n<=hi: return 3.0
    d=min(abs(n-lo),abs(n-hi)); return max(-2.0,3.0-0.3*d)
def _punct_score(t:str,mode:str)->float:
    if not t: return 0.0
    ex=t.count("!")+t.count("!!"); q=t.count("?")
    return (-0.8*max(0,ex-1)-0.5*max(0,q-1)) if mode=="light" else (-0.4*max(0,ex-2))
def _hit(t:str,ws:List[str])->int:
    t=(t or "").lower(); return sum(1 for w in (ws or []) if w and w.lower() in t)
def _persona_directives(sp:Dict[str,Any])->str:
    allow="이모지 금지." if sp.get("emoji")=="none" else "이모지는 최대 1개만."
    formal={"casual":"종결형 ~해요/반말 혼용(속어 과용 금지).","neutral":"종결형 ~해요 중심. 과격/자극 금지.","polite":"종결형 ~습니다/십시오체. 속어 금지."}[sp.get("formality","neutral")]
    meme="밈/유행어 1개만 은은하게." if sp.get("emoji")!="none" else "밈/유행어 금지."
    return f"문체:{sp['style']} 권장CTA:{', '.join(sp.get('cta',[])) or 'N/A'}. {allow} {formal} {meme} 피해야 할 표현:{', '.join(sp.get('avoid',[])) or '없음'}."
def _persona_stylepack(sp:Dict[str,Any])->str:
    req=sp.get("required",[]); req_line=f"- 반드시 다루기:{', '.join(req)}\n" if req else ""
    return ("스타일팩:\n"
            f"- 문체:{sp['style']}\n- 필수 어휘 최소 1개:{', '.join(sp.get('lexicon',[])) or '없음'}\n"
            f"{req_line}- 금지:{', '.join(sp.get('avoid',[])) or '없음'}\n- 권장 CTA:{', '.join(sp.get('cta',[])) or '없음'}\n"
            f"- 헤드라인:{sp['headline_len'][0]}~{sp['headline_len'][1]}자\n- 서브라인:{sp['subline_len'][0]}~{sp['subline_len'][1]}자\n"
            f"- 구두점/이모지:{'이모지 금지' if sp.get('emoji')=='none' else '이모지 최대 1개'}, {'구두점 절제' if sp.get('punctuation')=='light' else '보통'}\n")
def _boost_persona(c:Dict[str,str], sp:Optional[Dict[str,Any]])->float:
    if not sp: return 0.0
    head, sub = c.get("headline","") or "", c.get("subline","") or ""
    text=f"{head} {sub}"; s=0.0
    s+=_len_score(head,tuple(sp["headline_len"]))+_len_score(sub,tuple(sp["subline_len"]))
    f=_formality_score_kor(text); fm=sp.get("formality","neutral")
    s+= (min(2.5,max(0.0,f)) if fm=="polite" else (min(2.0,max(0.0,-f)) if fm=="casual" else 1.0-abs(f)*0.2))
    em=_count_emoji(text); s+= (-2.0 if sp.get("emoji")=="none" and em>0 else (-1.0 if sp.get("emoji")=="allow1" and em>1 else 0))
    s+=_punct_score(text,sp.get("punctuation","normal"))+1.5*_hit(text,sp.get("lexicon",[]))+1.0*_hit(text,sp.get("cta",[]))
    req=sp.get("required",[])
    if req: s+=3.0 if any(r.lower() in text.lower() for r in req) else -4.0
    for bad in sp.get("avoid",[]):
        if bad and bad in text: s-=2.0
    return s
def _boost_brand(c:Dict[str,str], brand:Optional[str])->int:
    if not brand: return 0
    t=f"{c.get('headline','')} {c.get('subline','')}".lower()
    return 4 if brand.lower() in t else 0
def _schema_hint(n,hn): return '{"candidates":[{"headline":string,"subline":string,"hashtags":array[string,최대 '+str(hn)+'개],"reasons":string}] x'+str(n)+'}'
def _score(c,h_lim,s_lim,banned,platform):
    head,sub,tags=c.get("headline","") or "", c.get("subline","") or "", (c.get("hashtags",[]) or [])
    len_pen=abs(len(head)-h_lim)*.8+abs(len(sub)-s_lim)*.2
    ban_pen=200 if (_contains_banned(head,banned) or _contains_banned(sub,banned)) else 0
    plat_bonus=-5 if platform in ("instagram","x") and len(tags)>=1 else 0
    return max(0.0,100-len_pen-ban_pen+plat_bonus)
def _style_score(c, goal, inv, h_lim):
    s=0.0; head=c.get("headline","") or ""; sub=c.get("subline","") or ""
    if goal=="low_involvement_push" or inv=="low":
        if len(head)<=int(0.8*h_lim): s+=6
        if re.search(r"(지금|바로|오늘|담기|보기|클릭)",sub): s+=4
    if goal=="high_involvement_compare" or inv=="high":
        hits=sum(int(k in sub) for k in ["비교","대비","기준","성능","내구","AS","성분","검증"]); s+=min(8.0,2.0*hits)
    if goal=="curiosity" and re.search(r"[?？]$",head): s+=4.0
    return s
def _trend(trend_style, meme, allow_emoji):
    if (trend_style or "light").lower()=="none": return "트렌드/밈은 사용하지 마라."
    base=f"아래 키워드 중 딱 1개만 자연스럽게 녹여라: {', '.join([s.strip() for s in str(meme).split(',') if s and s.strip()])}." if meme else "최근 대중 유행어 1개만 은은하게 사용(과장/자극/민감 금지)."
    emoji="이모지 사용 금지." if not allow_emoji else "이모지는 최대 1개만."
    inten="티 나지 않게 은은하게." if trend_style=="light" else "눈에 띄되 과하지 않게 한 번만."
    return f"{base} {emoji} 밈/유행어 반복 금지. 표현 강도: {inten}"
def _involvement(ocr,cat,price,override):
    if override in ("low","high"): return override
    sc=0; low=["스낵","간식","키링","립밤","티셔츠","무료배송","오늘출발"]; high=["보험","렌탈","프리미엄","보증","AS","성능","스펙","계약","정기구독"]
    bundle=f"{cat or ''} {ocr or ''}"
    if any(k in bundle for k in low): sc-=1
    if any(k in bundle for k in high): sc+=1
    if price and re.search(r"\d{2,3}[,]?\d{3}",price):
        v=int(re.sub(r"[^\d]","",price)); sc+=2 if v>=300000 else (-1 if v<=30000 else 0)
    return "high" if sc>=1 else "low"
def _jaccard(a,b,n=2):
    def grams(s): s=re.sub(r"\s+"," ",(s or "").strip()); return {s[i:i+n] for i in range(max(0,len(s)-n+1))}
    A,B=grams(a),grams(b); 
    return 0.0 if not A or not B else len(A & B)/len(A | B)
def _diverse(scored,k=3,sim=0.6):
    picked=[]
    for _,c in scored:
        txt=f"{c.get('headline','')} {c.get('subline','')}"
        if any(_jaccard(txt,f"{p.get('headline','')} {p.get('subline','')}",2)>sim for p in picked): continue
        picked.append(c)
        if len(picked)>=k: break
    return picked or ([scored[0][1]] if scored else [])
def _naturalness():
    return ("자연스러움 가이드:\n- 한국어 일상 구어(번역투/과장/막연어 금지).\n- 헤드: 이점 1개. 서브: 상황+근거+담백 CTA.\n"
            "- 뜬표현 대신 구체 단서. 브랜드 1회, 해시태그 0~3.\n- 길이(페르소나 우선): 헤드 8~18자, 서브 18~44자, 감탄/이모지 남발 금지.\n")
def _persona_examples(persona:Optional[str])->str:
    p=(persona or "").strip()
    generic="예시(톤 참고용):\n- 헤드: {핵심 이점 한마디}\n- 서브: {상황/맥락}에 맞는 {카테고리}. {근거}. {담백 CTA}\n"
    ex={
      "10대":"예시(톤 참고용):\n- 헤드: 한 번에 딱 {핵심 이점}\n- 서브: 가볍게 쓰는 {카테고리}. {근거}. {CTA}\n",
      "20대":"예시(톤 참고용):\n- 헤드: {핵심 이점}, 데일리로 충분\n- 서브: {카테고리}. {근거}. {CTA}\n",
      "30대":"예시(톤 참고용):\n- 헤드: 오늘도 합리적인 선택\n- 서브: {카테고리}. {효율/퀄리티 근거}. {CTA}\n",
      "40대":"예시(톤 참고용):\n- 헤드: 부담은 줄이고, 만족은 길게\n- 서브: {카테고리}. {신뢰/내구 근거}. {정중 CTA}\n",
      "시니어":"예시(톤 참고용):\n- 헤드: 편안하게 오래 쓰는 한 가지\n- 서브: {카테고리}. {안전/서비스 근거}. {정중 CTA}\n",
      "학생":"예시(톤 참고용):\n- 헤드: {상황}, 이것 하나면 끝\n- 서브: {카테고리}. {가격/휴대성 근거}. {CTA}\n",
      "직장인":"예시(톤 참고용):\n- 헤드: 바쁜 하루, {핵심 이점}\n- 서브: {카테고리}. {시간/집중 근거}. {정중 CTA}\n",
      "자영업":"예시(톤 참고용):\n- 헤드: 운영은 가볍게, 만족은 단단하게\n- 서브: {카테고리}. {비용/관리 근거}. {정중 CTA}\n",
      "육아":"예시(톤 참고용):\n- 헤드: 우리 아이, {핵심 이점}\n- 서브: {카테고리}. {성분/저자극 근거}. {CTA}\n",
      "프리미엄":"예시(톤 참고용):\n- 헤드: 디테일로 완성되는 프리미엄\n- 서브: {카테고리}. {원료/보증 근거}. {정중 CTA}\n",
    }
    for k,v in ex.items():
        if k in p: return v
    return generic

@router.post("/copy-from-image")
async def copy_from_image(
    file: UploadFile = File(...),
    tone: str = Form("짧고 강렬, 자연스러운 한국어"),
    platform: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    product: Optional[str] = Form(None),
    char_limit_headline: int = Form(24),
    char_limit_subline: int = Form(48),
    hashtags_n: int = Form(3),
    model_override: Optional[str] = Form(None),
    persona: Optional[str] = Form(None),
    user_keywords_csv: Optional[str] = Form(None),
    must_include_keywords: str = Form("false"),
    business_name: Optional[str] = Form(None),
    must_include_brand: str = Form("false"),
    n_candidates: int = Form(3),
    creativity: float = Form(0.8),
    trend_style: str = Form("light"),
    meme_keywords: Optional[str] = Form(None),
    allow_emoji: bool = Form(False),
    style_goal: str = Form("auto"),
    involvement_override: Optional[str] = Form(None),
    price_hint: Optional[str] = Form(None),
    category_hint: Optional[str] = Form(None),
    banned_keywords_csv: Optional[str] = Form("최저가,전품목,전상품,무제한,완전무료"),
):
    try:
        ext=(file.filename.split(".")[-1] or "").lower()
        if ext not in ALLOWED_EXTS: raise HTTPException(400,f"Unsupported file type: .{ext}. Allowed: {sorted(ALLOWED_EXTS)}")
        content=await file.read(); size_mb=len(content)/(1024*1024)
        if size_mb>MAX_FILE_MB: raise HTTPException(400,f"File too large: {size_mb:.2f} MB (limit {MAX_FILE_MB} MB)")
        ct=file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"

        save_name=f"upload_{_now_str()}_{uuid.uuid4().hex[:8]}.{ext}"
        save_path=os.path.join(UPLOAD_DIR,save_name)
        with open(save_path,"wb") as f: f.write(content)

        image_data_url=_data_url(content,ct)
        platform_hint=_platform_hint(platform)
        involvement=_involvement("",category_hint,price_hint,involvement_override)
        goal=style_goal if style_goal!="auto" else ("low_involvement_push" if involvement=="low" else "high_involvement_compare")
        banned=[s.strip() for s in (banned_keywords_csv or "").split(",") if s.strip()]

        auto_meme=None
        if (persona and any(a in persona for a in ["10대","20대"])) and not meme_keywords:
            try:
                from .trends import get_memes
                cand=get_memes(max_items=5,persona=persona)
                if cand and isinstance(cand[0],str) and cand[0].strip(): auto_meme=cand[0].strip()
            except: auto_meme=None
        trend_directive=_trend(trend_style, meme_keywords or auto_meme, allow_emoji)

        user_keywords=_csv(user_keywords_csv)
        must_kw=_tobool(must_include_keywords)
        must_brand=_tobool(must_include_brand)
        brand_name=(business_name or brand or "").strip()
        persona_spec=_persona(persona)

        temp=max(0.0,min(float(creativity),1.0))
        if persona_spec:
            if persona_spec.get("formality") in ("casual","neutral"): temp=min(1.0,max(0.75,temp)); n_candidates=max(n_candidates,4)
            elif persona_spec.get("formality")=="polite": temp=min(0.8,max(0.45,temp))

        rules=[
            "이 이미지에 어울리는 광고 문구를 만들어줘.",
            f"톤앤매너: {tone}",
            f"플랫폼 가이드: {platform_hint}",
            f"타깃: {target_audience or '일반 소비자'}",
            f"브랜드: {brand or 'N/A'} / 제품: {product or '이미지 기반 추론'}",
            f"헤드라인 {char_limit_headline}자 이내, 서브라인 {char_limit_subline}자 이내, 해시태그 {hashtags_n}개 이내.",
            trend_directive,
            ("이모지 금지." if not allow_emoji else "이모지는 최대 1개만, 남발 금지."),
            "금칙어·공격적 표현·규제 위반 표현 금지.",
        ]
        if persona_spec:
            rules += ["타깃 페르소나 어휘/말투 반영.","페르소나 톤: "+persona_spec["style"], _persona_directives(persona_spec), _persona_stylepack(persona_spec), _naturalness(), _persona_examples(persona)]
        else:
            rules.append(_naturalness())
        if user_keywords: rules.append(f"다음 핵심 키워드 중 1개 이상 자연스럽게 반영: {', '.join(user_keywords)}")
        if must_kw and user_keywords: rules.append("핵심 키워드 중 최소 1개는 헤드라인 또는 서브라인에 반드시 포함.")
        if brand_name:
            rules.append(f"상호/브랜드명은 자연스럽게 1회 표기: {brand_name}")
            if must_brand: rules.append("상호/브랜드명은 헤드라인 또는 서브라인에 반드시 포함.")
        if goal=="low_involvement_push":
            rules += ["설명 짧게, 이점 1개 집중.","CTA 1회(예:'지금 담기').","가격/혜택/배송 중 1개만 강조.","숫자 1개만."]
        elif goal=="high_involvement_compare":
            rules += ["비교 기준 2~3개","근거 기반 표현 1회","수치 1~2개","헤드=가치, 서브=핵심 비교."]
        elif goal=="curiosity":
            rules += ["질문형 헤드 1회 허용","서브에 힌트","클릭 유도 1회(예:'지금 확인')."]
        if banned: rules.append(f"다음 단어/구 금지: {', '.join(banned)}")

        n_candidates=max(1,min(int(n_candidates),5))
        schema=_schema_hint(n_candidates,hashtags_n)
        base_text="\n".join(rules)+("\n\n반드시 JSON 형식으로만 출력. 기타 텍스트 금지.\n예시 스키마: "+schema)

        url=f"{OPENAI_BASE}/chat/completions"
        payload={"model":(model_override or MODEL_VISION),
                 "messages":[
                   {"role":"system","content":"You are a Korean advertising copywriter. Always return strictly valid JSON that matches the requested schema."},
                   {"role":"user","content":[{"type":"text","text":base_text},{"type":"image_url","image_url":{"url":image_data_url}}]},
                 ],
                 "temperature":temp,"response_format":{"type":"json_object"}}
        s=_session()
        r=s.post(url,headers=_headers(),json=payload,timeout=(10,120))
        if r.status_code>=400 and payload["model"]!=MODEL_FALLBACK:
            payload["model"]=MODEL_FALLBACK; r=s.post(url,headers=_headers(),json=payload,timeout=(10,120))
        r.raise_for_status()

        data=r.json()
        raw=(data.get("choices",[{}])[0].get("message",{}) or {}).get("content","") or "{}"
        parsed=_json_obj(raw,{"candidates":[]})
        candidates=_norm_candidates(parsed)

        norm=[]
        for c in candidates:
            head=_smart_trim(c.get("headline",""),char_limit_headline)
            sub =_smart_trim(c.get("subline",""),char_limit_subline)
            tags=_norm_tags(c.get("hashtags",[]),hashtags_n,allow_emoji)
            norm.append({"headline":head,"subline":sub,"hashtags":tags,"reasons":c.get("reasons","")})
        if not norm: norm=[{"headline":"딱 맞는 한 줄","subline":"이미지의 장점을 간결하게 담았습니다.","hashtags":["#추천"],"reasons":"fallback"}]

        scored=[]
        for c in norm:
            s1=_score(c,char_limit_headline,char_limit_subline,banned,(platform or "").lower())
            s2=_style_score(c,goal,involvement,char_limit_headline)
            s3=_boost_persona(c,persona_spec); s4=_boost_brand(c,brand_name)
            scored.append((s1+s2+s3+s4,c))
        scored.sort(key=lambda x:x[0], reverse=True)
        best=scored[0][1]
        _ = _diverse(scored,k=min(3,len(scored)),sim=0.6)  # diversified (대안은 아래서 다시 계산해 반환)

        refine_needed=False; refine_reqs=[]
        if must_kw and user_keywords and not (_any_in(best["headline"],user_keywords) or _any_in(best["subline"],user_keywords)):
            refine_needed=True; refine_reqs.append(f"핵심 키워드: {', '.join(user_keywords)}")
        if must_brand and brand_name and not (_any_in(best["headline"],[brand_name]) or _any_in(best["subline"],[brand_name])):
            refine_needed=True; refine_reqs.append(f"브랜드명: {brand_name}")
        if persona_spec:
            text_best=f"{best['headline']} {best['subline']}"
            if persona_spec.get("lexicon") and _hit(text_best,persona_spec["lexicon"])==0:
                refine_needed=True; refine_reqs.append(f"필수 어휘 중 최소 1개 포함: {', '.join(persona_spec['lexicon'])}")
            if persona_spec.get("cta") and _hit(text_best,persona_spec["cta"])==0:
                refine_needed=True; refine_reqs.append(f"권장 CTA 1개 포함: {', '.join(persona_spec['cta'])}")
            req_terms=persona_spec.get("required",[])
            if req_terms and not any(r.lower() in text_best.lower() for r in req_terms):
                refine_needed=True; refine_reqs.append(f"다음 중 1개 이상 포함: {', '.join(req_terms)}")

        if refine_needed:
            refine_payload={"model":payload["model"],
                "messages":[
                    {"role":"system","content":"You are a precise Korean copy editor. Return strictly valid JSON."},
                    {"role":"user","content":("아래 JSON 후보에서 다음 항목이 최소 한 번 포함되도록 최소 수정.\n"+ "\n".join(refine_reqs)
                        + f"\n헤드 {char_limit_headline}자, 서브 {char_limit_subline}자, 해시태그 {hashtags_n}개 이내. 중복/남발 금지. JSON만.")},
                    {"role":"user","content":json.dumps(best,ensure_ascii=False)},
                ],
                "temperature":0.3,"response_format":{"type":"json_object"}}
            rr=s.post(url,headers=_headers(),json=refine_payload,timeout=(10,120))
            if rr.status_code>=400 and refine_payload["model"]!=MODEL_FALLBACK:
                refine_payload["model"]=MODEL_FALLBACK; rr=s.post(url,headers=_headers(),json=refine_payload,timeout=(10,120))
            rr.raise_for_status()
            rb=(rr.json().get("choices",[{}])[0].get("message",{}) or {}).get("content","{}")
            ro=_json_obj(rb,{})
            best={"headline":_smart_trim(ro.get("headline",best["headline"]),char_limit_headline),
                  "subline": _smart_trim(ro.get("subline", best["subline"]), char_limit_subline),
                  "hashtags":_norm_tags(ro.get("hashtags",best["hashtags"]),hashtags_n,allow_emoji),
                  "reasons": (ro.get("reasons") or best.get("reasons",""))+" (refined)"}

        if must_brand and brand_name:
            combo=f"{best.get('headline','')} {best.get('subline','')}".lower()
            if brand_name.lower() not in combo:
                best["subline"]=_smart_trim((best.get("subline") or "").rstrip()+f" · {brand_name}",char_limit_subline)

        log_name=f"copy_from_image_{_now_str()}_{uuid.uuid4().hex[:8]}.txt"
        log_path=os.path.join(OUTPUT_DIR,log_name)
        try:
            with open(log_path,"w",encoding="utf-8") as f:
                f.write(f"[IMAGE]\n{os.path.abspath(save_path)}\n\n")
                ctx={"tone":tone,"platform":platform,"target_audience":target_audience,"brand":brand,"product":product,
                     "char_limit_headline":char_limit_headline,"char_limit_subline":char_limit_subline,"hashtags_n":hashtags_n,
                     "model":payload["model"],"n_candidates":n_candidates,"creativity":temp,"persona":persona,
                     "persona_resolved":_parse_persona(persona),"user_keywords":user_keywords,"must_include_keywords":must_kw,
                     "trend_style":trend_style,"meme_keywords":meme_keywords or auto_meme,"allow_emoji":allow_emoji,
                     "involvement":involvement,"style_goal":goal,"price_hint":price_hint,"category_hint":category_hint,
                     "business_name":business_name,"brand_used":brand_name,"must_include_brand":must_brand}
                f.write("[CONTEXT]\n"); f.write(json.dumps(ctx,ensure_ascii=False,indent=2))
                f.write("\n\n[CANDIDATES]\n"); f.write(json.dumps([c for _,c in scored],ensure_ascii=False,indent=2))
                f.write("\n\n[BEST]\n"); f.write(json.dumps(best,ensure_ascii=False,indent=2))
                usage=data.get("usage")
                if usage: f.write("\n\n[USAGE]\n"); f.write(json.dumps(usage,ensure_ascii=False,indent=2))
        except: pass

        uploaded_path=os.path.abspath(save_path).replace("\\","/")
        uploaded_url=f"{BACKEND_PUBLIC_URL}/static/uploads/{save_name}"
        log_url=f"{BACKEND_PUBLIC_URL}/static/outputs/{log_name}"

        copy_text=f"{best['headline']}\n{best['subline']}\n"+(" ".join(best["hashtags"]) if best["hashtags"] else "")
        return {"ok":True,"copy":copy_text,"structured":best,"alternatives":[c for c in _diverse(scored,k=min(3,len(scored)))],
                "involvement":involvement,"style_goal":goal,"uploaded_path":uploaded_path,"uploaded_url":uploaded_url,
                "log_path":os.path.abspath(log_path).replace('\\','/'),"log_url":log_url}
    except requests.RequestException as e:
        resp=getattr(e,"response",None); detail=f"OpenAI error: {e}"
        if resp is not None:
            try: detail+=f"\n{resp.text}"
            except: pass
        raise HTTPException(502,detail=detail)
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,detail=f"Server error: {e}")

@router.post("/copy-from-image/suggest")
async def suggest_keywords(file: UploadFile = File(...), n: int = Form(6)):
    ext=(file.filename.split(".")[-1] or "").lower()
    if ext not in ALLOWED_EXTS: raise HTTPException(400,"Unsupported file type")
    content=await file.read()
    image_data_url=_data_url(content, file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg")
    prompt=("이미지를 보고 한국어 핵심 키워드를 1~8개 제안해줘. 카테고리/재질·색·형태/사용상황/계절·감정/기능·혜택을 섞어라. "
            "각 키워드는 1~3어절, 해시태그/이모지 없이 평문. JSON만 반환: {\"keywords\": [\"...\"]}")
    payload={"model":MODEL_VISION,"messages":[
        {"role":"system","content":"You extract concise Korean keywords from images. Always return JSON."},
        {"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":image_data_url}}]}
    ],"temperature":0.2,"response_format":{"type":"json_object"}}
    s=_session(); r=s.post(f"{OPENAI_BASE}/chat/completions",headers=_headers(),json=payload,timeout=(10,120))
    if r.status_code>=400 and MODEL_VISION!=MODEL_FALLBACK:
        payload["model"]=MODEL_FALLBACK; r=s.post(f"{OPENAI_BASE}/chat/completions",headers=_headers(),json=payload,timeout=(10,120))
    r.raise_for_status()
    parsed=_json_obj((r.json().get("choices",[{}])[0].get("message",{}) or {}).get("content","{}"),{"keywords":[]})
    return {"ok":True,"keywords":_norm_keywords(parsed,n=max(1,min(int(n),8)))}
