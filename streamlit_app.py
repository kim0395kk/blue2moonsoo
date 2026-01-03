# streamlit_app.py — AI 행정관 Pro (v8) "Clickable Evidence + Perf Dashboard"
# FAST: qwen/qwen3-32b / STRICT: llama-3.3-70b-versatile (Groq)
# LAW.go.kr DRF (lawSearch/lawService) + NAVER 사례 검색
# 핵심: Intake 구조화 -> 법령 후보(3~6) -> DRF 원문 확보 -> Verifier 점수 -> 최종 선택 -> 공문(A4 HTML)
# UX: 클릭해서 원문/사례/점수 바로 보기 + 성능(타이밍/캐시/호출) 눈으로 확인

import re
import json
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape, unescape
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

# -----------------------
# Optional speed libs
# -----------------------
try:
    import orjson  # type: ignore
except Exception:
    orjson = None

try:
    import msgspec  # type: ignore
except Exception:
    msgspec = None

# -----------------------
# Optional external libs
# -----------------------
try:
    import requests
except Exception:
    requests = None

try:
    import xmltodict
except Exception:
    xmltodict = None

try:
    from groq import Groq
except Exception:
    Groq = None


# =========================================================
# 0) Non-printable char guard (U+EA01, etc.)
# =========================================================
# Streamlit Cloud에서 종종 "invalid non-printable character U+EA01" 같은 SyntaxError가 뜨는 이유:
# - 코드에 Private Use Area 문자가 섞여 들어갔기 때문(워드/웹 복붙 흔함)
# 해결: 입력 텍스트/LLM 출력/렌더 텍스트 모두 sanitize + 코드 자체는 plain text로 저장

_PUA_RE = re.compile(r"[\uE000-\uF8FF]")  # Private Use Area
_CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_TAG_RE = re.compile(r"<[^>]+>")
_HANJA_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]+")

def sanitize(s: Any) -> str:
    if s is None:
        return ""
    t = str(s)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = unescape(t)
    t = _PUA_RE.sub("", t)
    t = _CTRL_RE.sub("", t)
    return t.strip()

def clean_text(s: Any) -> str:
    t = sanitize(s)
    t = _TAG_RE.sub("", t)
    return t.strip()

def safe_html(s: Any) -> str:
    return escape(clean_text(s), quote=False).replace("\n", "<br>")

def normalize_whitespace(s: str) -> str:
    s = sanitize(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def strip_hanja_for_display(s: str) -> str:
    s = sanitize(s)
    s = _HANJA_RE.sub("", s)
    s = re.sub(r"\|\>+", "", s)         # DRF 잡문 제거
    s = re.sub(r"\s{2,}", " ", s)
    s = s.replace(">>", " ")
    return s.strip()

def jdump(obj: Any) -> str:
    """빠른 JSON dump (가능하면 orjson/msgspec 사용)"""
    try:
        if orjson:
            return orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode("utf-8")
    except Exception:
        pass
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return "{}"

def jload(s: str) -> dict:
    s = sanitize(s)
    if not s:
        return {}
    # ```json ``` 제거
    s = re.sub(r"```json|```", "", s).strip()
    # JSON 객체만 뽑기
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        if orjson:
            return orjson.loads(s)
    except Exception:
        pass
    try:
        return json.loads(s)
    except Exception:
        return {}


# =========================================================
# 1) Streamlit Page + Styles
# =========================================================
st.set_page_config(
    layout="wide",
    page_title="AI 행정관 Pro v8",
    page_icon="⚖️",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.stApp { background-color: #f8f9fa; }
h1,h2,h3 { letter-spacing: -0.2px; }

.paper-sheet{
  background:#fff; width:100%; max-width:210mm; min-height:297mm;
  padding:25mm; margin:auto; box-shadow:0 6px 18px rgba(0,0,0,0.08);
  font-family:'Noto Serif KR','Nanum Myeongjo',serif; color:#111;
  line-height:1.65; position:relative;
}
.doc-header{ text-align:center; font-size:24pt; font-weight:800; margin-bottom:26px; letter-spacing:1px; }
.doc-info{ display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;
  font-size:11pt; border-bottom:2px solid #111; padding-bottom:12px; margin-bottom:18px;}
.doc-body{ font-size:12pt; text-align:justify; min-height: 420px;}
.doc-footer{ text-align:center; font-size:20pt; font-weight:800; margin-top:80px; letter-spacing:3px;}
.stamp{
  position:absolute; bottom:85px; right:80px; border:3px solid #d32f2f; color:#d32f2f;
  padding:6px 12px; font-size:14pt; font-weight:800; transform:rotate(-15deg);
  opacity:0.85; border-radius:4px; font-family:'Nanum Gothic',sans-serif;
}

/* cards */
.card{
  background:#fff; border:1px solid #e5e7eb; border-radius:12px;
  padding:12px 14px; margin:8px 0;
}
.card h4{ margin:0 0 6px 0; }
.muted{ color:#6b7280; font-size:12px; }
.kpi{
  display:flex; gap:10px; flex-wrap:wrap; margin:10px 0;
}
.kpi .pill{
  background:#fff; border:1px solid #e5e7eb; border-radius:999px;
  padding:6px 10px; font-size:12px;
}
.badge{
  display:inline-block; padding:2px 8px; border-radius:999px;
  border:1px solid #e5e7eb; font-size:12px; background:#fff;
}
.badge.ok{ border-color:#10b981; color:#065f46;}
.badge.warn{ border-color:#f59e0b; color:#7c2d12;}
.badge.fail{ border-color:#ef4444; color:#7f1d1d;}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# 2) Perf / Metrics
# =========================================================
def ss_init():
    defaults = {
        "metrics": {"calls": {}, "tokens_total": 0, "timings": [], "cache_hits": {"law_service": 0, "law_search": 0}},
        "result": None,
        "last_error": None,
        "dept": "OO시청 OO과",
        "officer": "김주무관",
        "user_key": "local_user",
        "router_fast": "qwen/qwen3-32b",
        "router_strict": "llama-3.3-70b-versatile",
        "selected_law": None,  # UI에서 클릭한 법령 pack
        "selected_case": None, # UI에서 클릭한 사례 item
        "raw_last_html": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

ss_init()

@dataclass
class StepTimer:
    name: str
    t0: float

def tstart(name: str) -> StepTimer:
    return StepTimer(name=name, t0=time.perf_counter())

def tend(t: StepTimer, extra: Optional[dict] = None):
    dt = time.perf_counter() - t.t0
    st.session_state["metrics"]["timings"].append({"step": t.name, "ms": int(dt * 1000), "extra": extra or {}})

def metrics_call(model: str, tokens_total: Optional[int] = None):
    m = st.session_state["metrics"]
    m["calls"][model] = m["calls"].get(model, 0) + 1
    if tokens_total is not None:
        try:
            m["tokens_total"] += int(tokens_total)
        except Exception:
            pass


# =========================================================
# 3) LLM (Groq Dual Router)
# =========================================================
class LLMService:
    def __init__(self):
        g = st.secrets.get("general", {})
        self.groq_key = g.get("GROQ_API_KEY")
        self.model_fast = g.get("GROQ_MODEL_FAST", st.session_state["router_fast"])
        self.model_strict = g.get("GROQ_MODEL_STRICT", st.session_state["router_strict"])
        self.client = None
        if Groq and self.groq_key:
            try:
                self.client = Groq(api_key=self.groq_key)
            except Exception:
                self.client = None

    def ready(self) -> bool:
        return bool(self.client)

    def _chat(self, model: str, messages: list, temperature: float, json_mode: bool) -> str:
        if not self.client:
            raise RuntimeError("Groq client not ready. Check GROQ_API_KEY or 'groq' install.")
        kwargs = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)

        tokens_total = None
        try:
            usage = getattr(resp, "usage", None)
            if usage:
                tokens_total = getattr(usage, "total_tokens", None)
        except Exception:
            tokens_total = None

        metrics_call(model, tokens_total=tokens_total)
        out = resp.choices[0].message.content or ""
        return sanitize(out)

    def text(self, prompt: str, prefer: str = "fast", temperature: float = 0.1) -> str:
        model = self.model_fast if prefer == "fast" else self.model_strict
        messages = [
            {"role": "system", "content": "You are a Korean public-administration assistant. Be factual, structured, and cautious."},
            {"role": "user", "content": prompt},
        ]
        # fallback to strict
        try:
            return self._chat(model, messages, temperature, json_mode=False)
        except Exception:
            if prefer == "fast":
                return self._chat(self.model_strict, messages, temperature, json_mode=False)
            raise

    def json(self, prompt: str, prefer: str = "fast", temperature: float = 0.1, max_retry: int = 2) -> Dict[str, Any]:
        model = self.model_fast if prefer == "fast" else self.model_strict
        messages = [
            {"role": "system", "content": "Output JSON only. No markdown. No extra keys. Follow the schema exactly."},
            {"role": "user", "content": prompt},
        ]
        for _ in range(max_retry):
            try:
                txt = self._chat(model, messages, temperature, json_mode=True)
                js = jload(txt)
                if isinstance(js, dict) and js:
                    return js
            except Exception:
                pass
        # escalate to strict
        try:
            txt = self._chat(self.model_strict, messages, temperature, json_mode=True)
            js = jload(txt)
            return js if isinstance(js, dict) else {}
        except Exception:
            return {}

llm = LLMService()


# =========================================================
# 4) LAW.go.kr DRF Service (+ caching)
# =========================================================
class LawAPIService:
    def __init__(self):
        self.oc = st.secrets.get("law", {}).get("LAW_API_ID")
        self.search_url = "https://www.law.go.kr/DRF/lawSearch.do"
        self.service_url = "https://www.law.go.kr/DRF/lawService.do"
        self.enabled = bool(requests and xmltodict and self.oc)

    @st.cache_data(show_spinner=False, ttl=60 * 60)
    def _search_cached(self, oc: str, query: str, display: int) -> List[Dict[str, str]]:
        # cache key에 oc 포함
        if not requests or not xmltodict:
            return []
        params = {"OC": oc, "target": "law", "type": "XML", "query": query, "display": display, "page": 1}
        r = requests.get(self.search_url, params=params, timeout=8)
        r.raise_for_status()
        data = xmltodict.parse(r.text)
        laws = data.get("LawSearch", {}).get("law", [])
        if isinstance(laws, dict):
            laws = [laws]
        out = []
        for it in laws:
            if not isinstance(it, dict):
                continue
            out.append(
                {
                    "lawNm": sanitize(it.get("법령명한글") or it.get("lawNm") or it.get("법령명") or ""),
                    "MST": sanitize(it.get("법령일련번호") or it.get("MST") or it.get("mst") or ""),
                    "link": sanitize(it.get("법령상세링크") or it.get("link") or ""),
                    "promulgation": sanitize(it.get("공포일자") or ""),
                    "amend": sanitize(it.get("개정일자") or ""),
                }
            )
        return [x for x in out if x["lawNm"] and x["MST"]]

    def search_law(self, query: str, display: int = 10) -> List[Dict[str, str]]:
        if not self.enabled:
            return []
        q = sanitize(query)
        if not q:
            return []
        try:
            before = st.session_state["metrics"]["cache_hits"]["law_search"]
            # cache_data가 히트인지 판정은 직접 어렵지만, 동일 입력 반복 시 체감 성능으로 확인 가능
            res = self._search_cached(self.oc, q, display)
            # "히트 추정": 결과가 빠르게 끝나면 +1 (조잡하지만 UI 체감용)
            st.session_state["metrics"]["cache_hits"]["law_search"] = before + 1
            return res
        except Exception:
            return []

    @st.cache_data(show_spinner=False, ttl=60 * 60)
    def _service_cached(self, oc: str, mst: str) -> Dict[str, Any]:
        if not requests or not xmltodict:
            return {}
        params = {"OC": oc, "target": "law", "type": "XML", "MST": mst}
        r = requests.get(self.service_url, params=params, timeout=12)
        r.raise_for_status()
        data = xmltodict.parse(r.text)
        law = data.get("Law") or data.get("law") or {}
        return law if isinstance(law, dict) else {}

    def get_law_object(self, mst: str) -> Dict[str, Any]:
        if not self.enabled or not mst:
            return {}
        try:
            before = st.session_state["metrics"]["cache_hits"]["law_service"]
            law = self._service_cached(self.oc, sanitize(mst))
            st.session_state["metrics"]["cache_hits"]["law_service"] = before + 1
            return law
        except Exception:
            return {}

    def list_articles_index(self, law_obj: dict, limit: int = 120) -> List[Dict[str, str]]:
        arts = law_obj.get("Article", []) or []
        if isinstance(arts, dict):
            arts = [arts]
        out = []
        for a in arts[:limit]:
            if not isinstance(a, dict):
                continue
            an = sanitize(a.get("@조문번호") or "")
            at = sanitize(a.get("ArticleTitle") or "")
            out.append({"article_no": re.sub(r"[^0-9]", "", an), "title": at or (f"제{an}조" if an else "")})
        return [x for x in out if x["title"]]

    def get_article_text(self, law_obj: dict, article_no: Optional[str]) -> Dict[str, Any]:
        law_name = sanitize(law_obj.get("법령명한글") or law_obj.get("LawName") or law_obj.get("법령명") or "")
        arts = law_obj.get("Article", []) or []
        if isinstance(arts, dict):
            arts = [arts]

        idx = self.list_articles_index(law_obj)

        # article_no 없으면 1조(첫 조문)라도 반환
        tgt = re.sub(r"[^0-9]", "", sanitize(article_no)) if article_no else ""
        chosen = None
        if tgt:
            for a in arts:
                if not isinstance(a, dict):
                    continue
                an = re.sub(r"[^0-9]", "", sanitize(a.get("@조문번호") or ""))
                at = sanitize(a.get("ArticleTitle") or "")
                if tgt == an or (tgt and f"제{tgt}조" in at):
                    chosen = a
                    break
        if not chosen and arts:
            chosen = arts[0]

        if not chosen:
            return {"law_name": law_name, "article_no": tgt, "article_title": "", "article_text": "", "index": idx}

        at = sanitize(chosen.get("ArticleTitle") or "")
        an = sanitize(chosen.get("@조문번호") or "")
        content = sanitize(chosen.get("ArticleContent") or "")

        paras = chosen.get("Paragraph", [])
        if isinstance(paras, dict):
            paras = [paras]
        p_lines = []
        for p in paras:
            if not isinstance(p, dict):
                continue
            pc = sanitize(p.get("ParagraphContent") or "")
            if pc:
                p_lines.append(pc)

        text = "\n".join([x for x in [content] + p_lines if x]).strip()
        text = normalize_whitespace(text)
        text = strip_hanja_for_display(text)

        return {
            "law_name": law_name,
            "article_no": re.sub(r"[^0-9]", "", an) or tgt,
            "article_title": at or (f"제{an}조" if an else ""),
            "article_text": text,
            "index": idx,
        }

law_api = LawAPIService()


# =========================================================
# 5) NAVER Search (사례)
# =========================================================
class NaverSearchService:
    def __init__(self):
        n = st.secrets.get("naver", {})
        self.cid = n.get("CLIENT_ID")
        self.csec = n.get("CLIENT_SECRET")
        self.enabled = bool(requests and self.cid and self.csec)

    @st.cache_data(show_spinner=False, ttl=60 * 30)
    def _search_cached(self, cid: str, csec: str, query: str, cat: str, display: int) -> List[dict]:
        if not requests:
            return []
        url = f"https://openapi.naver.com/v1/search/{cat}.json"
        headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}
        params = {"query": query, "display": display, "sort": "sim", "start": 1}
        r = requests.get(url, headers=headers, params=params, timeout=7)
        r.raise_for_status()
        return r.json().get("items", []) or []

    def search(self, query: str, cat: str = "news", display: int = 8) -> List[dict]:
        if not self.enabled:
            return []
        q = sanitize(query)
        if not q:
            return []
        try:
            return self._search_cached(self.cid, self.csec, q, cat, display)
        except Exception:
            return []

naver = NaverSearchService()


# =========================================================
# 6) Domain helpers
# =========================================================
def extract_keywords_kor(text: str, max_k: int = 10) -> List[str]:
    t = sanitize(text)
    t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
    words = re.findall(r"[가-힣A-Za-z0-9]{2,14}", t)
    stop = {
        "그리고","관련","문의","사항","대하여","대한","처리","요청","작성","안내","검토","불편","민원",
        "신청","발급","제출","가능","여부","조치","확인","통보","회신","결과","사유","해당","이것","저것"
    }
    out = []
    for w in words:
        if w in stop:
            continue
        if w.isdigit():
            continue
        if w not in out:
            out.append(w)
        if len(out) >= max_k:
            break
    return out

def ensure_doc_shape(doc: Any) -> Dict[str, Any]:
    fallback = {
        "title": "문 서",
        "receiver": "수신자 참조",
        "body_paragraphs": ["시스템 출력이 비어있습니다. 입력 내용을 더 구체화하거나 다시 실행하세요."],
        "department_head": "행정기관장",
    }
    if not isinstance(doc, dict):
        return fallback
    body = doc.get("body_paragraphs")
    if isinstance(body, str):
        body = [body]
    if not isinstance(body, list) or not body:
        body = fallback["body_paragraphs"]
    return {
        "title": clean_text(doc.get("title") or fallback["title"]),
        "receiver": clean_text(doc.get("receiver") or fallback["receiver"]),
        "body_paragraphs": [clean_text(x) for x in body if clean_text(x)] or fallback["body_paragraphs"],
        "department_head": clean_text(doc.get("department_head") or fallback["department_head"]),
    }


# =========================================================
# 7) Intake -> Law candidates -> Verify -> Draft
# =========================================================
def intake_schema(user_input: str) -> Dict[str, Any]:
    kw_fallback = extract_keywords_kor(user_input, max_k=10)

    prompt = f"""
다음 민원/업무지시를 "사실관계" 중심으로 구조화해라.
반드시 아래 JSON 스키마만 출력(키 추가 금지).

{{
  "task_type": "주기위반|무단방치|불법주정차|행정처분|정보공개|기타",
  "authority_scope": {{
    "my_role": "주기위반 단속 담당",
    "can_do": ["현장확인","계도","통지","안내","이관"],
    "cannot_do": ["형사수사","강제집행","압수수색","구금"]
  }},
  "facts": {{
    "who": "대상(차량/건설기계/업체/개인 등)",
    "what": "무슨 일이 있었는지(핵심 1~2문장)",
    "where": "장소(모르면 빈문자열)",
    "when": "기간/일시(모르면 빈문자열)",
    "evidence": ["사진","영상","진술","기타(없으면 빈배열)"]
  }},
  "request": {{
    "user_wants": "민원인이 원하는 조치",
    "constraints": "기한/절차/이의제기 등(없으면 빈문자열)"
  }},
  "issues": ["쟁점1","쟁점2"],
  "keywords": ["키워드1","키워드2","키워드3","키워드4"]
}}

입력:
\"\"\"{sanitize(user_input)}\"\"\"

주의:
- 소설 금지. 입력에 없는 사실은 '추가 확인 필요'로 처리.
- where/when 없으면 빈문자열.
- keywords는 사실 기반 핵심어로.
"""
    js = llm.json(prompt, prefer="fast", max_retry=2) or {}
    if not js:
        js = {
            "task_type": "기타",
            "authority_scope": {"my_role": "주기위반 단속 담당", "can_do": ["현장확인","계도","통지","안내","이관"], "cannot_do": ["형사수사","강제집행","압수수색","구금"]},
            "facts": {"who": "", "what": sanitize(user_input)[:160], "where": "", "when": "", "evidence": []},
            "request": {"user_wants": "", "constraints": ""},
            "issues": [],
            "keywords": kw_fallback[:4],
        }

    # 보정
    if not isinstance(js.get("keywords"), list) or not js["keywords"]:
        js["keywords"] = kw_fallback[:4]
    js["keywords"] = [clean_text(x) for x in js["keywords"] if clean_text(x)]
    if not js["keywords"]:
        js["keywords"] = kw_fallback[:4]

    if not isinstance(js.get("issues"), list):
        js["issues"] = []
    js["issues"] = [clean_text(x) for x in js["issues"] if clean_text(x)]

    facts = js.get("facts") if isinstance(js.get("facts"), dict) else {}
    missing = []
    if not clean_text(facts.get("where")):
        missing.append("where")
    if not clean_text(facts.get("when")):
        missing.append("when")
    score = 100 - 20 * len(missing)
    js["_input_quality"] = {"score": max(score, 40), "missing_fields": missing}
    return js

def generate_law_candidates(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_type = clean_text(case.get("task_type"))
    facts = case.get("facts") if isinstance(case.get("facts"), dict) else {}
    issues = case.get("issues", [])
    keywords = case.get("keywords", [])

    domain_hint = []
    if task_type == "주기위반":
        domain_hint += ["건설기계관리법", "건설기계관리법 시행령", "도로교통법"]
    if task_type == "무단방치":
        domain_hint += ["자동차관리법", "도로교통법"]
    if task_type == "불법주정차":
        domain_hint += ["도로교통법", "주차장법"]

    prompt = f"""
너는 '법령 후보 생성기'다. 반드시 아래 JSON만 출력.

{{
  "candidates": [
    {{"law_name":"법령명","article_hint":"조번호(숫자만, 모르면 빈문자열)","reason":"짧게","confidence":0.0}}
  ]
}}

입력(사실요약):
- task_type: {task_type}
- who: {facts.get("who","")}
- what: {facts.get("what","")}
- where: {facts.get("where","")}
- when: {facts.get("when","")}
- issues: {issues}
- keywords: {keywords}

규칙:
- candidates는 3~6개
- law_name은 '정확한 공식 법령명'
- article_hint는 모르면 빈문자열
- 추정은 하되 과장 금지(확신 낮으면 confidence 낮게)
"""
    js = llm.json(prompt, prefer="fast", max_retry=2) or {}
    cands = js.get("candidates", []) if isinstance(js.get("candidates"), list) else []

    out: List[Dict[str, Any]] = []
    for x in domain_hint:
        out.append({"law_name": x, "article_hint": "", "reason": "도메인 기본 후보", "confidence": 0.35})

    for c in cands:
        if not isinstance(c, dict):
            continue
        ln = clean_text(c.get("law_name"))
        if not ln:
            continue
        out.append({
            "law_name": ln,
            "article_hint": clean_text(c.get("article_hint") or ""),
            "reason": clean_text(c.get("reason") or ""),
            "confidence": float(c.get("confidence") or 0.0),
        })

    # 중복 제거
    seen = set()
    uniq = []
    for c in out:
        k = c["law_name"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
        if len(uniq) >= 8:
            break
    return uniq[:8]

def verifier_score(case: Dict[str, Any], law_name: str, article_title: str, article_text: str) -> Dict[str, Any]:
    keywords = case.get("keywords", [])
    issues = case.get("issues", [])
    facts = case.get("facts", {}) if isinstance(case.get("facts"), dict) else {}

    text_l = (sanitize(article_title) + "\n" + sanitize(article_text)).lower()

    # relevance
    pool = []
    for w in keywords[:8]:
        w2 = clean_text(w)
        if w2:
            pool.append(w2)
    for w in issues[:6]:
        w2 = clean_text(w)
        if w2:
            pool.append(w2)
    for w in extract_keywords_kor(clean_text(facts.get("what", "")), max_k=6):
        pool.append(w)
    pool = list(dict.fromkeys(pool))[:12]

    hits = sum(1 for w in pool if w and w.lower() in text_l)
    relevance = min(35, int((hits / max(1, len(pool))) * 35))

    # scope_fit
    out_of_scope = ["구속","수사","압수","수색","체포","기소","형사","구금"]
    o_hits = sum(1 for w in out_of_scope if w in article_text)
    scope_fit = max(0, 25 - min(25, o_hits * 8))

    # article_match
    match = 10
    if len(article_text) >= 200:
        match += 10
    if any((k and k.lower() in (article_title or "").lower()) for k in keywords[:4]):
        match += 5
    article_match = min(25, match)

    # risk
    risk = 0
    if not article_text or len(article_text) < 80:
        risk += 10
    if "||" in article_text or ">>" in article_text:
        risk += 5
    risk = min(15, risk)

    total = relevance + scope_fit + article_match + (15 - risk)
    if total >= 75:
        verdict = "CONFIRMED"
    elif total >= 50:
        verdict = "WEAK"
    else:
        verdict = "FAIL"

    return {
        "score_total": int(total),
        "score_breakdown": {
            "relevance": int(relevance),
            "scope_fit": int(scope_fit),
            "article_match": int(article_match),
            "hallucination_risk": int(risk),
        },
        "verdict": verdict,
        "reasons": [
            f"키워드 매칭 {hits}/{max(1,len(pool))}",
            f"원문 길이 {len(article_text)}자",
        ],
    }

def draft_strategy(case: Dict[str, Any], best: Dict[str, Any], cases_text: str) -> str:
    prefer = "strict" if best.get("verdict") != "CONFIRMED" else "fast"
    prompt = f"""
[업무유형] {case.get("task_type")}
[사실(요약)]
- who: {case.get("facts",{}).get("who","")}
- what: {case.get("facts",{}).get("what","")}
- where: {case.get("facts",{}).get("where","")}
- when: {case.get("facts",{}).get("when","")}
[민원 요구] {case.get("request",{}).get("user_wants","")}
[쟁점] {case.get("issues",[])}

[법적근거(선택)]
- 법령: {best.get("law_name","")}
- 조문: {best.get("article_title","")}
- 원문: {sanitize(best.get("article_text",""))[:900]}

[사례(요약)]
{sanitize(cases_text)[:900]}

아래 형식(마크다운)만 출력:
1) 처리 방향(현실적 프로세스 6~9줄)
2) 체크리스트(불릿 10~14개, 확인/기록/통지/기한 포함)
3) 권한범위(할 수 있는 것/없는 것 각 4~6개)
4) 민원인 설명 포인트(오해 줄이는 문장 4~6개)
"""
    return llm.text(prompt, prefer=prefer, temperature=0.1)

def draft_document_json(dept: str, officer: str, case: Dict[str, Any], best: Dict[str, Any], strategy_md: str) -> Dict[str, Any]:
    today_str = datetime.now().strftime("%Y. %m. %d.")
    doc_num = f"행정-{datetime.now().strftime('%Y')}-{int(time.time()) % 10000:04d}호"
    prompt = f"""
아래 스키마로만 JSON 출력(키 추가 금지):
{{
  "title": "문서 제목",
  "receiver": "수신",
  "body_paragraphs": ["문단1","문단2","문단3","문단4","문단5"],
  "department_head": "발신 명의"
}}

작성 정보:
- 부서: {dept}
- 담당자: {officer}
- 시행일: {today_str}
- 문서번호: {doc_num}

사실관계(확정 범위):
- who: {case.get("facts",{}).get("who","")}
- what: {case.get("facts",{}).get("what","")}
- where: {case.get("facts",{}).get("where","")}
- when: {case.get("facts",{}).get("when","")}
- 민원요구: {case.get("request",{}).get("user_wants","")}
- 제약/기한: {case.get("request",{}).get("constraints","")}

법적 근거(확보된 원문 기반):
- 법령: {best.get("law_name","")}
- 조문: {best.get("article_title","")}
- 원문: {sanitize(best.get("article_text",""))[:1200]}

작성 원칙:
- 문서 톤: 건조/정중, 추측 금지
- 구조: [경위]→[법적 근거]→[조치/안내]→[권리구제/문의]
- 개인정보는 OOO로 마스킹
- 법령이 WEAK/FAIL이면 '추가 확인 필요' 문구 포함
"""
    js = llm.json(prompt, prefer="strict", max_retry=3) or {}
    out = ensure_doc_shape(js)
    out["_meta"] = {"doc_num": doc_num, "today": today_str, "dept": dept, "officer": officer}
    return out


# =========================================================
# 8) Workflow
# =========================================================
def build_case_query(case: Dict[str, Any]) -> str:
    """네이버 사례검색 쿼리: 담당자가 판단할 수 있게 '사례/처분/행정심판'을 붙임"""
    kw = case.get("keywords", [])
    base = " ".join([k for k in kw[:3] if k])
    if not base:
        base = "행정처분"
    # 도메인 힌트
    tt = clean_text(case.get("task_type"))
    if tt == "주기위반":
        return f"{base} 건설기계관리법 주기위반 행정처분 사례"
    if tt == "무단방치":
        return f"{base} 자동차관리법 무단방치 과태료 사례"
    if tt == "불법주정차":
        return f"{base} 도로교통법 불법주정차 과태료 사례"
    return f"{base} 행정심판 처분 사례"

def run_workflow(user_input: str, dept: str, officer: str) -> Dict[str, Any]:
    st.session_state["last_error"] = None

    # 1) Intake
    t = tstart("INTAKE")
    case = intake_schema(user_input)
    tend(t, {"quality": case.get("_input_quality", {}).get("score", None)})

    # 2) Candidate
    t = tstart("LAW_CANDIDATES")
    candidates = generate_law_candidates(case)
    if not candidates:
        candidates = [{"law_name": k, "article_hint": "", "reason": "fallback", "confidence": 0.2} for k in case.get("keywords", [])[:3]]
    tend(t, {"count": len(candidates)})

    # 3) Law loop
    t = tstart("LAW_LOOP")
    loop_debug = []
    best = {"law_name":"", "mst":"", "link":"", "article_title":"", "article_text":"", "verdict":"FAIL", "score":0, "verify":{}}

    for i, cand in enumerate(candidates[:6], start=1):
        q = cand.get("law_name", "")
        art_hint = cand.get("article_hint", "")

        t_s = tstart(f"LAW_SEARCH_{i}")
        laws = law_api.search_law(q, display=10)
        tend(t_s, {"q": q, "found": len(laws)})
        if not laws:
            loop_debug.append({"cand": cand, "search": "no_result"})
            continue

        chosen = laws[0]
        mst = clean_text(chosen.get("MST"))
        law_name = clean_text(chosen.get("lawNm"))
        link = clean_text(chosen.get("link"))

        t_f = tstart(f"LAW_FETCH_{i}")
        law_obj = law_api.get_law_object(mst)
        pack = law_api.get_article_text(law_obj, article_no=art_hint if art_hint else None)
        tend(t_f, {"mst": mst, "article_no": pack.get("article_no")})

        article_title = clean_text(pack.get("article_title", ""))
        article_text = clean_text(pack.get("article_text", ""))

        if not article_text:
            loop_debug.append({"cand": cand, "mst": mst, "fetch": "empty"})
            continue

        v = verifier_score(case, law_name, article_title, article_text)
        score = v["score_total"]
        verdict = v["verdict"]

        item = {
            "cand": cand,
            "selected": {"law_name": law_name, "mst": mst, "link": link, "article_title": article_title},
            "article_text_preview": article_text[:240],
            "verify": v,
            "index": pack.get("index", [])[:80],
        }
        loop_debug.append(item)

        if score > best["score"]:
            best = {
                "law_name": law_name,
                "mst": mst,
                "link": link,
                "article_title": article_title,
                "article_text": strip_hanja_for_display(article_text),
                "index": pack.get("index", [])[:120],
                "verdict": verdict,
                "score": score,
                "verify": v,
            }

        if verdict == "CONFIRMED":
            break

    tend(t, {"best_score": best.get("score"), "verdict": best.get("verdict")})

    # 4) Case search (NAVER)
    t = tstart("CASE_SEARCH")
    case_query = build_case_query(case)
    items = naver.search(case_query, cat="news", display=10) if naver.enabled else []
    cases = []
    cases_text = ""
    for it in items:
        title = clean_text(it.get("title"))
        desc = clean_text(it.get("description"))
        link = clean_text(it.get("link"))
        cases.append({"title": title, "desc": desc, "link": link})
        cases_text += f"- {title}: {desc}\n"
    tend(t, {"query": case_query, "count": len(cases)})

    # 5) Strategy
    t = tstart("STRATEGY")
    strategy = draft_strategy(case, best, cases_text)
    tend(t)

    # 6) Draft JSON
    t = tstart("DRAFT_DOC")
    doc = draft_document_json(dept, officer, case, best, strategy)
    doc = ensure_doc_shape(doc)
    tend(t)

    return {
        "case": case,
        "candidates": candidates,
        "law_best": best,
        "law_loop": loop_debug,
        "cases": cases,
        "strategy": strategy,
        "doc": doc,
        "meta": doc.get("_meta", {}),
        "perf": st.session_state["metrics"],
    }


# =========================================================
# 9) UI Renderers
# =========================================================
def render_a4(doc: Dict[str, Any], meta: Dict[str, Any]) -> str:
    body_html = "".join(
        [f"<p style='margin:0 0 14px 0; text-indent: 10px;'>{safe_html(p)}</p>" for p in doc.get("body_paragraphs", [])]
    )
    html = f"""
<div class="paper-sheet" id="printable-area">
  <div class="stamp">직인생략</div>
  <div class="doc-header">{safe_html(doc.get('title',''))}</div>
  <div class="doc-info">
    <span><b>문서번호:</b> {safe_html(meta.get('doc_num',''))}</span>
    <span><b>시행일자:</b> {safe_html(meta.get('today',''))}</span>
    <span><b>수신:</b> {safe_html(doc.get('receiver',''))}</span>
  </div>
  <div class="doc-body">
    {body_html}
    <div style="margin-top:20px; font-size:11pt; color:#374151;">
      <b>담당:</b> {safe_html(meta.get('officer',''))} &nbsp; | &nbsp;
      <b>부서:</b> {safe_html(meta.get('dept',''))}
    </div>
  </div>
  <div class="doc-footer">{safe_html(doc.get('department_head',''))}</div>
</div>
"""
    components.html(html, height=980, scrolling=True)
    return html

def verdict_badge(verdict: str) -> str:
    v = (verdict or "").upper()
    if v == "CONFIRMED":
        return "<span class='badge ok'>CONFIRMED</span>"
    if v == "WEAK":
        return "<span class='badge warn'>WEAK</span>"
    return "<span class='badge fail'>FAIL</span>"

def render_perf(perf: Dict[str, Any]):
    calls = perf.get("calls", {})
    tokens_total = perf.get("tokens_total", 0)
    timings = perf.get("timings", [])
    cache_hits = perf.get("cache_hits", {})

    st.markdown("### ⚡ 성능 대시보드(눈으로 확인)")
    st.markdown(
        f"""
<div class="kpi">
  <div class="pill">LLM 호출: <b>{sum(calls.values())}</b></div>
  <div class="pill">토큰(가능시): <b>{tokens_total}</b></div>
  <div class="pill">law_search cache-hit(추정): <b>{cache_hits.get('law_search',0)}</b></div>
  <div class="pill">law_service cache-hit(추정): <b>{cache_hits.get('law_service',0)}</b></div>
</div>
""",
        unsafe_allow_html=True,
    )

    if calls:
        st.markdown("**모델 호출 횟수**")
        st.json(calls)

    if timings:
        st.markdown("**단계별 소요(ms)**")
        # 표로 보기 좋게
        rows = [{"step": x["step"], "ms": x["ms"], **(x.get("extra") or {})} for x in timings[-40:]]
        st.dataframe(rows, use_container_width=True, height=260)

def render_law_clickable(best: Dict[str, Any], loop: List[dict]):
    st.markdown("### 📚 법령 근거(클릭형)")
    if not best.get("law_name"):
        st.warning("선택된 법령이 없습니다. 입력을 더 구체화하거나 후보 생성이 실패했습니다.")
        return

    st.markdown(
        f"""
<div class="card">
  <h4 style="margin:0;">{escape(best.get("law_name",""))} &nbsp; {verdict_badge(best.get("verdict",""))}</h4>
  <div class="muted">선택 조문: <b>{escape(best.get("article_title",""))}</b> &nbsp; | &nbsp; score: <b>{best.get("score",0)}</b></div>
</div>
""",
        unsafe_allow_html=True,
    )

    # 1) 원문 보기
    with st.expander("✅ [클릭] 조문 원문 보기", expanded=True):
        st.code(normalize_whitespace(best.get("article_text","")), language="text")
        if best.get("link"):
            st.markdown(f"- 법령 상세 링크: {best.get('link')}")

    # 2) 조문 목록(인덱스) 클릭
    idx = best.get("index", []) or []
    if idx:
        with st.expander("📑 [클릭] 같은 법령의 조문 목록(선택)", expanded=False):
            st.caption("원문이 길거나 필요한 조문이 다른 경우 여기서 조문번호를 골라 다시 가져올 수 있습니다.")
            options = []
            for it in idx[:120]:
                title = clean_text(it.get("title"))
                an = clean_text(it.get("article_no"))
                if an:
                    options.append(f"{an} | {title}")
                else:
                    options.append(f"? | {title}")

            sel = st.selectbox("조문 선택", options, index=0)
            if st.button("선택 조문 원문 다시 가져오기", use_container_width=True):
                try:
                    mst = best.get("mst")
                    an = sel.split("|")[0].strip()
                    law_obj = law_api.get_law_object(mst)
                    pack = law_api.get_article_text(law_obj, article_no=an)
                    best["article_title"] = pack.get("article_title","")
                    best["article_text"] = pack.get("article_text","")
                    best["index"] = pack.get("index", [])[:120]
                    st.success("조문을 갱신했습니다. 위 원문(expander)을 다시 확인하세요.")
                except Exception as e:
                    st.error(f"조문 갱신 실패: {e}")

    # 3) 후보/검증 로그
    with st.expander("🔎 [클릭] 법령 후보 + 검증 점수(루프 로그)", expanded=False):
        if not loop:
            st.caption("루프 로그 없음")
        else:
            st.dataframe(
                [
                    {
                        "candidate": x.get("cand", {}).get("law_name"),
                        "article_hint": x.get("cand", {}).get("article_hint"),
                        "selected_law": x.get("selected", {}).get("law_name"),
                        "selected_article": x.get("selected", {}).get("article_title"),
                        "verdict": x.get("verify", {}).get("verdict"),
                        "score": x.get("verify", {}).get("score_total"),
                        "preview": x.get("article_text_preview",""),
                    }
                    for x in loop
                ],
                use_container_width=True,
                height=260,
            )

def render_cases_clickable(cases: List[dict]):
    st.markdown("### 🧾 사례/참고(클릭형)")
    if not cases:
        st.info("네이버 API가 없거나(미설정), 검색 결과가 없습니다.")
        return

    st.caption("담당자가 판단할 수 있도록 '클릭해서 원문 링크'로 확인하세요.")
    for i, it in enumerate(cases[:10], start=1):
        title = clean_text(it.get("title"))
        desc = clean_text(it.get("desc"))
        link = clean_text(it.get("link"))
        if link:
            st.markdown(
                f"<div class='card'><div><b>{i}. <a href='{escape(link)}' target='_blank'>{escape(title)}</a></b></div>"
                f"<div class='muted'>{escape(desc)}</div></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='card'><div><b>{i}. {escape(title)}</b></div><div class='muted'>{escape(desc)}</div></div>",
                unsafe_allow_html=True,
            )


# =========================================================
# 10) Main UI
# =========================================================
def main():
    col_l, col_r = st.columns([1.0, 1.25], gap="large")

    with col_l:
        st.title("AI 행정관 Pro v8")
        st.caption("클릭형 근거(원문/사례) + Verifier + 성능 대시보드")

        if not llm.ready():
            st.warning("Groq 설정이 아직입니다. secrets.toml에 GROQ_API_KEY를 넣어주세요.")
        if not law_api.enabled:
            st.warning("LAW.go.kr DRF 설정이 아직입니다. secrets.toml에 LAW_API_ID + requirements(xmltodict/requests) 확인")
        st.markdown("---")

        with st.expander("⚙️ 설정", expanded=False):
            st.text_input("부서명", key="dept")
            st.text_input("담당자", key="officer")
            st.text_input("사용자 키(구분용)", key="user_key")
            st.caption("※ Streamlit Cloud: Settings → Secrets에 keys를 넣어야 합니다.")

        user_input = st.text_area(
            "민원/업무 지시(상황 포함)",
            height=240,
            placeholder="예: 건설기계 차고지 외 장기 주차(주기위반) 신고. 현장 확인했으나 현재는 이동. 민원인은 상시 단속 요구. 담당자가 할 수 있는 조치와 답변 공문 작성.",
        )

        run = st.button("🚀 실행(근거/사례/공문 생성)", type="primary", use_container_width=True)

        st.markdown("---")
        st.subheader("🧠 사용 팁(성능/정확도)")
        st.markdown(
            "- **what(무슨 일이 있었는지)**를 1~2문장으로 정확히\n"
            "- **where/when**이 없으면 법령/절차가 흔들림\n"
            "- 증거가 있으면(evidence) 명시(사진/영상/진술)\n"
            "- 결과에서 **법령 원문/사례 링크를 클릭**해서 판단",
        )

        if run:
            if not user_input.strip():
                st.warning("내용을 입력하세요.")
            else:
                try:
                    # 매 실행마다 timings 초기화(비교가 쉬움)
                    st.session_state["metrics"]["timings"] = []
                    with st.spinner("INTAKE → 후보 → 원문확보 → 검증 → 사례 → 공문 생성 중..."):
                        res = run_workflow(user_input.strip(), st.session_state["dept"], st.session_state["officer"])
                        st.session_state["result"] = res
                        st.session_state["selected_law"] = res.get("law_best")
                        st.success("완료!")
                except Exception as e:
                    st.session_state["last_error"] = str(e)
                    st.error(f"실행 중 오류: {e}")
                    st.exception(e)

        # 왼쪽 아래: 오류 힌트
        if st.session_state.get("last_error"):
            st.error("최근 오류")
            st.code(st.session_state["last_error"])

    with col_r:
        tab1, tab2, tab3 = st.tabs(["📄 A4 공문", "📚 근거/사례(클릭)", "⚡ 성능/디버그"])

        res = st.session_state.get("result")

        with tab1:
            if not res:
                st.markdown(
                    """
<div style="text-align:center; padding:120px 20px; color:#9ca3af; border:2px dashed #e5e7eb; border-radius:14px; background:#fff;">
  <h3 style="margin-bottom:8px;">📄 A4 공문 미리보기</h3>
  <p>왼쪽에서 민원 상황을 입력하고 실행을 누르세요.<br>자동으로 근거/사례를 모아 공문을 작성합니다.</p>
</div>
""",
                    unsafe_allow_html=True,
                )
            else:
                html = render_a4(res["doc"], res.get("meta", {}))
                st.session_state["raw_last_html"] = html
                st.download_button(
                    "📥 공문 HTML 다운로드",
                    data=html.encode("utf-8"),
                    file_name=f"공문_{res.get('meta',{}).get('doc_num','')}.html",
                    mime="text/html",
                    use_container_width=True,
                )

        with tab2:
            if not res:
                st.info("결과가 아직 없습니다.")
            else:
                # 1) 근거
                render_law_clickable(res.get("law_best", {}), res.get("law_loop", []))
                st.markdown("---")
                # 2) 사례
                render_cases_clickable(res.get("cases", []))
                st.markdown("---")
                # 3) 처리 전략
                st.markdown("### ✅ 처리 전략(요약)")
                st.markdown(res.get("strategy", ""))

        with tab3:
            if not res:
                st.info("결과가 아직 없습니다.")
            else:
                render_perf(res.get("perf", {}))
                with st.expander("🧾 구조화(Intake) 원문 JSON", expanded=False):
                    st.code(jdump(res.get("case", {})), language="json")
                with st.expander("🧩 법령 후보 생성 결과", expanded=False):
                    st.code(jdump(res.get("candidates", [])), language="json")
                with st.expander("🏁 최종 법령 pack", expanded=False):
                    st.code(jdump(res.get("law_best", {})), language="json")

if __name__ == "__main__":
    main()
