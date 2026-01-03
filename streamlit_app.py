# streamlit_app.py — AI 행정관 Pro (v8.1) "Click-to-Verify" + Performance Lab
# ✅ 목표
# - 법적근거: 후보 리스트 → 클릭 → (1) 원문 조문 (2) 관련 사례(뉴스/웹) 를 한 화면에서 확인
# - 공문: A4 용지 느낌 HTML 렌더 + HTML 다운로드
# - 성능: requests.Session 재사용 + cache_data + 성능 실험실(p50/p95/메모리) 탭
# - 안정성: U+EA01 같은 비표시 문자 제거, Optional imports, 실패 시 graceful fallback
#
# -------------------------------
# secrets.toml (Streamlit Cloud)
# -------------------------------
# [general]
# GROQ_API_KEY = "..."
# GROQ_MODEL_FAST = "qwen/qwen3-32b"
# GROQ_MODEL_STRICT = "llama-3.3-70b-versatile"
#
# [law]
# LAW_API_ID = "..."  # law.go.kr DRF OC 값
#
# [naver]
# CLIENT_ID = "..."
# CLIENT_SECRET = "..."
#
# [supabase]  # 옵션(로그/히스토리)
# SUPABASE_URL = "https://xxxx.supabase.co"
# SUPABASE_KEY = "service_role_or_anon_key"
#
# -------------------------------
# requirements.txt (권장)
# -------------------------------
# streamlit
# groq
# requests
# xmltodict
# python-dateutil
# pandas
# (optional) orjson msgspec supabase

import json
import re
import time
import statistics
import tracemalloc
from dataclasses import dataclass
from datetime import datetime
from html import escape, unescape
from time import perf_counter_ns
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

try:
    import pandas as pd
except Exception:
    pd = None

# Optional libs
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    import requests
except Exception:
    requests = None

try:
    import xmltodict
except Exception:
    xmltodict = None

try:
    import orjson
except Exception:
    orjson = None

try:
    import msgspec
except Exception:
    msgspec = None

try:
    from supabase import create_client
except Exception:
    create_client = None


# =========================
# 1) Page & Style
# =========================
st.set_page_config(
    layout="wide",
    page_title="AI 행정관 Pro (v8.1)",
    page_icon="⚖️",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.stApp { background-color: #f8f9fa; }

/* A4 paper */
.paper-sheet {
  background: #fff; width: 100%; max-width: 210mm; min-height: 297mm;
  padding: 25mm; margin: auto; box-shadow: 0 6px 18px rgba(0,0,0,0.08);
  font-family: 'Noto Serif KR','Nanum Myeongjo',serif;
  color:#111; line-height:1.65; position:relative;
}
.doc-header { text-align:center; font-size:24pt; font-weight:800; margin-bottom:22px; letter-spacing:1px; }
.doc-info {
  display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;
  font-size:11pt; border-bottom:2px solid #111; padding-bottom:12px; margin-bottom:20px;
}
.doc-body { font-size:12pt; text-align: justify; }
.doc-footer { text-align:center; font-size:20pt; font-weight:800; margin-top:80px; letter-spacing:3px; }
.stamp {
  position:absolute; bottom:85px; right:80px; border:3px solid #d32f2f; color: #d32f2f;
  padding:6px 12px; font-size:14pt; font-weight:800; transform:rotate(-15deg);
  opacity:0.85; border-radius:4px; font-family: 'Nanum Gothic', sans-serif;
}
.small-muted { color:#6b7280; font-size:12px; }

/* Clickable list cards */
.card {
  background:#fff; border:1px solid #e5e7eb; border-radius:12px;
  padding:12px 14px; margin:10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.card-title { font-weight:800; font-size:15px; margin-bottom:6px; }
.card-sub { color:#374151; font-size:13px; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; background:#f3f4f6; color:#111; margin-left:6px; }

/* Agent logs */
.agent-log {
  font-family: 'Pretendard', sans-serif; font-size: 0.92rem; padding: 8px 12px;
  border-radius: 8px; margin-bottom: 6px; background: white; border: 1px solid #e5e7eb;
}
.log-legal { border-left: 5px solid #3b82f6; }
.log-search { border-left: 5px solid #f97316; }
.log-strat { border-left: 5px solid #8b5cf6; }
.log-draft { border-left: 5px solid #ef4444; }
.log-sys   { border-left: 5px solid #9ca3af; }

.ev-card{
  background:#fff; border:1px solid #e5e7eb; border-radius:10px;
  padding:10px 12px; margin:8px 0;
}
.ev-title{ font-weight:700; }
.ev-desc{ color:#374151; margin-top:4px; }

</style>
""",
    unsafe_allow_html=True,
)

# =========================
# 2) Sanitizers & Helpers
# =========================
_TAG_RE = re.compile(r"<[^>]+>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
# 한자(CJK Unified Ideographs) 제거 (표시용)
_HANJA_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]+")
# Private Use Area 포함 비표시 문자(문제의 U+EA01도 포함) 제거
_PUA_RE = re.compile(r"[\uE000-\uF8FF]")


def scrub_invisible(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = _PUA_RE.sub("", s)
    # 혹시 남아있는 이상한 제어문자 제거
    s = _CTRL_RE.sub("", s)
    return s


def clean_text(value) -> str:
    """HTML 태그/제어문자/PUA 제거"""
    if value is None:
        return ""
    s = scrub_invisible(unescape(str(value)))
    s = _TAG_RE.sub("", s)
    s = _CTRL_RE.sub("", s)
    return s.strip()


def safe_html(value) -> str:
    return escape(clean_text(value), quote=False).replace("\n", "<br>")


def normalize_whitespace(s: str) -> str:
    s = clean_text(s)
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_hanja_for_display(s: str) -> str:
    """표시용: 한자 제거 + 잡문 패턴 정리"""
    s = clean_text(s)
    if not s:
        return ""
    s = _HANJA_RE.sub("", s)
    s = re.sub(r"\|\>+", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def truncate_text(s: str, max_chars: int = 2800) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n...(내용 축소됨)"


def safe_json_dump(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def ensure_doc_shape(doc):
    fallback = {
        "title": "문 서 (생성 실패)",
        "receiver": "수신자 참조",
        "body_paragraphs": ["시스템 오류로 인해 문서 생성에 실패했습니다."],
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
        "_meta": doc.get("_meta", {}),
        "_qa": doc.get("_qa", {}),
    }


def extract_keywords_kor(text: str, max_k: int = 8) -> List[str]:
    """간이 키워드: LLM 실패시 fallback"""
    t = clean_text(text)
    if not t:
        return []
    t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
    words = re.findall(r"[가-힣A-Za-z0-9]{2,14}", t)
    stop = {
        "그리고", "관련", "문의", "사항", "대하여", "대한", "처리", "요청",
        "작성", "안내", "검토", "불편", "민원", "신청", "발급", "제출",
        "가능", "여부", "조치", "확인", "통보", "회신", "결과", "사유",
        "합니다", "있습니다", "없습니다", "등"
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


# =========================
# 3) Metrics
# =========================
def metrics_init():
    if "metrics" not in st.session_state:
        st.session_state["metrics"] = {"calls": {}, "tokens_total": 0}


def metrics_add(model_name: str, tokens_total: Optional[int] = None):
    metrics_init()
    m = st.session_state["metrics"]
    m["calls"][model_name] = m["calls"].get(model_name, 0) + 1
    if tokens_total is not None:
        try:
            m["tokens_total"] += int(tokens_total)
        except Exception:
            pass


metrics_init()


# =========================
# 4) LLM Service (Dual Router)
# =========================
class LLMService:
    """FAST + STRICT"""
    def __init__(self):
        g = st.secrets.get("general", {})
        self.groq_key = g.get("GROQ_API_KEY")
        self.model_fast = g.get("GROQ_MODEL_FAST", "qwen/qwen3-32b")
        self.model_strict = g.get("GROQ_MODEL_STRICT", "llama-3.3-70b-versatile")
        self.client = None

        if Groq and self.groq_key:
            try:
                self.client = Groq(api_key=self.groq_key)
            except Exception:
                self.client = None

    def _chat(self, model: str, messages, temp: float, json_mode: bool):
        if not self.client:
            raise RuntimeError("Groq client not ready (missing key/lib).")

        kwargs = {"model": model, "messages": messages, "temperature": temp}
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

        metrics_add(model, tokens_total=tokens_total)
        return resp.choices[0].message.content or ""

    def _parse_json(self, text: str) -> Dict[str, Any]:
        text = clean_text(text)
        try:
            return json.loads(text)
        except Exception:
            cleaned = re.sub(r"```json|```", "", text).strip()
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return {}
            return {}

    def generate_text(self, prompt: str, prefer: str = "fast", temp: float = 0.1) -> str:
        if not self.client:
            return "Groq API Key가 없거나 라이브러리 미설치"

        model_first = self.model_fast if prefer == "fast" else self.model_strict
        messages = [
            {"role": "system", "content": "You are a Korean public-administration assistant. Be factual, structured, and practical."},
            {"role": "user", "content": prompt},
        ]

        try:
            return self._chat(model_first, messages, temp, json_mode=False)
        except Exception:
            if prefer == "fast":
                try:
                    return self._chat(self.model_strict, messages, temp, json_mode=False)
                except Exception as e2:
                    return f"LLM Error: {e2}"
            return "LLM Error"

    def generate_json(self, prompt: str, prefer: str = "fast", temp: float = 0.1, max_retry: int = 2) -> Dict[str, Any]:
        if not self.client:
            return {}

        sys_json = "Output JSON only. No markdown. No explanation. Follow the schema exactly."
        messages = [
            {"role": "system", "content": sys_json},
            {"role": "user", "content": prompt},
        ]
        model_first = self.model_fast if prefer == "fast" else self.model_strict

        for _ in range(max_retry):
            try:
                txt = self._chat(model_first, messages, temp, json_mode=True)
                js = self._parse_json(txt)
                if js:
                    return js
            except Exception:
                pass

        # escalate
        try:
            txt = self._chat(self.model_strict, messages, temp, json_mode=True)
            js = self._parse_json(txt)
            return js if js else {}
        except Exception:
            return {}


llm = LLMService()


# =========================
# 5) LAW API (DRF) — Search + Service (XML)
# =========================
class LawAPIService:
    def __init__(self):
        self.oc = st.secrets.get("law", {}).get("LAW_API_ID")
        self.search_url = "https://www.law.go.kr/DRF/lawSearch.do"
        self.service_url = "https://www.law.go.kr/DRF/lawService.do"
        self.enabled = bool(requests and xmltodict and self.oc)
        self.session = requests.Session() if (requests and self.enabled) else None

    def search_law(self, query: str, display: int = 10) -> List[Dict[str, str]]:
        if not self.enabled or not query:
            return []
        try:
            params = {"OC": self.oc, "target": "law", "type": "XML", "query": query, "display": display, "page": 1}
            r = self.session.get(self.search_url, params=params, timeout=7)
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
                        "lawNm": clean_text(it.get("법령명한글") or it.get("lawNm") or it.get("법령명") or ""),
                        "MST": clean_text(it.get("법령일련번호") or it.get("MST") or it.get("mst") or ""),
                        "link": clean_text(it.get("법령상세링크") or it.get("link") or ""),
                        "promulgation": clean_text(it.get("공포일자") or ""),
                        "amend": clean_text(it.get("개정일자") or ""),
                    }
                )
            return [x for x in out if x.get("lawNm") and x.get("MST")]
        except Exception:
            return []

    def _extract_articles(self, law_obj: dict) -> List[dict]:
        articles = law_obj.get("Article", []) or []
        if isinstance(articles, dict):
            articles = [articles]
        return [a for a in articles if isinstance(a, dict)]

    def get_article_by_mst(self, mst: str, article_no: Optional[str] = None) -> Dict[str, Any]:
        if not self.enabled or not mst:
            return {}
        try:
            params = {"OC": self.oc, "target": "law", "type": "XML", "MST": mst}
            r = self.session.get(self.service_url, params=params, timeout=12)
            r.raise_for_status()
            data = xmltodict.parse(r.text)

            law = data.get("Law") or data.get("law") or {}
            law_name = clean_text(law.get("법령명한글") or law.get("LawName") or law.get("법령명") or "")
            articles = self._extract_articles(law)

            idx = []
            for a in articles[:120]:
                at = clean_text(a.get("ArticleTitle") or "")
                an = clean_text(a.get("@조문번호") or "")
                if at:
                    idx.append(at)
                elif an:
                    idx.append(f"제{an}조")

            if not article_no:
                if articles:
                    return self._format_article(law_name, mst, articles[0], idx)
                return {"law_name": law_name, "mst": mst, "all_articles_index": idx}

            tgt = re.sub(r"[^0-9]", "", str(article_no))
            if not tgt:
                if articles:
                    return self._format_article(law_name, mst, articles[0], idx)
                return {"law_name": law_name, "mst": mst, "all_articles_index": idx}

            for a in articles:
                an = clean_text(a.get("@조문번호") or "")
                at = clean_text(a.get("ArticleTitle") or "")
                if tgt == re.sub(r"[^0-9]", "", an) or (tgt and f"제{tgt}조" in at):
                    return self._format_article(law_name, mst, a, idx)

            if articles:
                pack = self._format_article(law_name, mst, articles[0], idx)
                pack["_note"] = f"요청한 제{tgt}조를 찾지 못해 첫 조문으로 표시"
                return pack
            return {"law_name": law_name, "mst": mst, "all_articles_index": idx}

        except Exception:
            return {}

    def _format_article(self, law_name: str, mst: str, art: dict, idx: List[str]) -> Dict[str, Any]:
        at = clean_text(art.get("ArticleTitle") or "")
        an = clean_text(art.get("@조문번호") or "")
        content = clean_text(art.get("ArticleContent") or "")

        paras = art.get("Paragraph", [])
        if isinstance(paras, dict):
            paras = [paras]
        p_lines = []
        for p in paras:
            if not isinstance(p, dict):
                continue
            pc = clean_text(p.get("ParagraphContent") or "")
            if pc:
                p_lines.append(pc)

        text = "\n".join([x for x in [content] + p_lines if x]).strip()
        text = normalize_whitespace(text)
        text_disp = strip_hanja_for_display(text)

        return {
            "law_name": law_name,
            "mst": mst,
            "article_no": re.sub(r"[^0-9]", "", an) or "",
            "article_title": at or (f"제{an}조" if an else ""),
            "article_text": text_disp,
            "all_articles_index": idx,
        }


law_api = LawAPIService()


# =========================
# 6) NAVER Search (News/Web)
# =========================
class NaverSearchService:
    def __init__(self):
        n = st.secrets.get("naver", {})
        self.cid = n.get("CLIENT_ID")
        self.csec = n.get("CLIENT_SECRET")
        self.enabled = bool(requests and self.cid and self.csec)
        self.session = requests.Session() if (requests and self.enabled) else None

    def search(self, query: str, cat: str = "news", display: int = 5):
        if not self.enabled or not query:
            return []
        try:
            url = f"https://openapi.naver.com/v1/search/{cat}.json"
            headers = {"X-Naver-Client-Id": self.cid, "X-Naver-Client-Secret": self.csec}
            params = {"query": query, "display": display, "sort": "sim", "start": 1}
            r = self.session.get(url, headers=headers, params=params, timeout=7)
            r.raise_for_status()
            return r.json().get("items", []) or []
        except Exception:
            return []


naver = NaverSearchService()


# =========================
# 7) Supabase (optional)
# =========================
class DatabaseService:
    def __init__(self):
        self.client = None
        s = st.secrets.get("supabase", {})
        self.url = s.get("SUPABASE_URL")
        self.key = s.get("SUPABASE_KEY")
        if create_client and self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
            except Exception:
                self.client = None

    def enabled(self) -> bool:
        return bool(self.client)

    def insert_run(self, row: dict) -> Tuple[bool, str, Optional[str]]:
        if not self.client:
            return False, "DB 미연결", None
        try:
            safe_row = json.loads(safe_json_dump(row))
            resp = self.client.table("runs").insert(safe_row).execute()
            run_id = None
            data = getattr(resp, "data", None)
            if data and isinstance(data, list) and data:
                run_id = data[0].get("run_id") or data[0].get("id")
            return True, "저장 성공", run_id
        except Exception as e:
            return False, f"저장 실패: {e}", None


db = DatabaseService()


# =========================
# 8) Core: Intake → Candidates → Click-to-Verify → Draft
# =========================
@st.cache_data(ttl=3600, show_spinner=False)
def cached_law_search(q: str) -> List[Dict[str, str]]:
    return law_api.search_law(q, display=10)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_article(mst: str, article_no: str) -> Dict[str, Any]:
    return law_api.get_article_by_mst(mst, article_no=article_no or None)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_naver(q: str, cat: str) -> List[Dict[str, Any]]:
    return naver.search(q, cat=cat, display=7)


def intake_schema(user_input: str) -> Dict[str, Any]:
    kw_fallback = extract_keywords_kor(user_input, max_k=10)
    prompt = f"""
다음 민원/업무 지시를 "행정사실관계" 중심으로 구조화해라.
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
"""{user_input}"""

주의:
- 입력에 없는 사실은 '추가 확인 필요'로 처리.
- 장소/시간이 없으면 빈문자열.
- keywords는 '사실 기반' 핵심어로.
"""
    js = llm.generate_json(prompt, prefer="fast", max_retry=2) or {}
    if not js:
        return {
            "task_type": "기타",
            "authority_scope": {"my_role": "주기위반 단속 담당", "can_do": ["현장확인", "계도", "통지", "안내", "이관"], "cannot_do": ["형사수사", "강제집행", "압수수색", "구금"]},
            "facts": {"who": "", "what": clean_text(user_input)[:160], "where": "", "when": "", "evidence": []},
            "request": {"user_wants": "", "constraints": ""},
            "issues": [],
            "keywords": kw_fallback[:4],
            "_input_quality": {"score": 60, "missing_fields": ["where", "when"]},
        }

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
    score = max(40, 100 - 20 * len(missing))
    js["_input_quality"] = {"score": score, "missing_fields": missing}
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
- what: {facts.get("what","")}
- where: {facts.get("where","")}
- when: {facts.get("when","")}
- issues: {issues}
- keywords: {keywords}

규칙:
- candidates는 4~7개
- law_name은 "공식 법령명" 우선
- article_hint는 모르면 빈문자열
- 내 권한(주기위반 단속 담당) 범위에서 다룰 가능성이 큰 법령 우선
"""
    js = llm.generate_json(prompt, prefer="fast", max_retry=2) or {}
    cands = js.get("candidates", []) if isinstance(js.get("candidates"), list) else []

    out = [{"law_name": x, "article_hint": "", "reason": "도메인 규칙 후보", "confidence": 0.35} for x in domain_hint]
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

    seen = set()
    uniq = []
    for c in out:
        k = c["law_name"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
        if len(uniq) >= 10:
            break
    return uniq


def verifier_score(case: Dict[str, Any], article_title: str, article_text: str) -> Dict[str, Any]:
    keywords = case.get("keywords", [])
    issues = case.get("issues", [])
    facts = case.get("facts", {}) if isinstance(case.get("facts"), dict) else {}

    text = (article_title + "\n" + article_text).lower()

    pool = []
    for w in (keywords or [])[:8]:
        w2 = clean_text(w)
        if w2:
            pool.append(w2)
    for w in (issues or [])[:6]:
        w2 = clean_text(w)
        if w2:
            pool.append(w2)
    for w in extract_keywords_kor(clean_text(facts.get("what", "")), max_k=6):
        pool.append(w)
    pool = list(dict.fromkeys(pool))[:12]

    hits = 0
    for w in pool:
        if w and w.lower() in text:
            hits += 1
    relevance = min(40, int((hits / max(1, len(pool))) * 40))

    out_of_scope = ["구속", "수사", "압수", "수색", "체포", "기소", "형사", "구금"]
    o_hits = sum(1 for w in out_of_scope if w in article_text)
    scope_fit = max(0, 25 - min(25, o_hits * 8))

    match = 10
    if len(article_text) >= 220:
        match += 10
    if any(k.lower() in (article_title.lower() if article_title else "") for k in (keywords or [])[:4] if k):
        match += 5
    article_match = min(25, match)

    risk = 0
    if not article_text or len(article_text) < 80:
        risk += 10
    if "||" in article_text or ">>" in article_text:
        risk += 5
    risk = min(15, risk)

    total = relevance + scope_fit + article_match + (15 - risk)
    verdict = "CONFIRMED" if total >= 78 else ("WEAK" if total >= 55 else "FAIL")

    return {
        "score_total": int(total),
        "verdict": verdict,
        "breakdown": {
            "relevance": int(relevance),
            "scope_fit": int(scope_fit),
            "article_match": int(article_match),
            "risk": int(risk),
        },
        "notes": [f"키워드 매칭 {hits}/{max(1,len(pool))}", f"원문 길이 {len(article_text)}자"],
    }


def build_case_query_for_examples(case: Dict[str, Any], law_name: str, article_title: str) -> str:
    kws = case.get("keywords", []) or []
    base = " ".join([k for k in kws[:3] if k])
    title = clean_text(article_title).replace(" ", "")
    return f"{law_name} {title} {base} 과태료 처분 사례"


def load_law_pack_from_candidate(case: Dict[str, Any], cand: Dict[str, Any]) -> Dict[str, Any]:
    q = clean_text(cand.get("law_name", ""))
    if not q:
        return {"error": "empty_candidate"}

    results = cached_law_search(q)
    if not results:
        return {"error": "no_search_result", "law_name_query": q}

    chosen = results[0]
    mst = clean_text(chosen.get("MST"))
    law_name = clean_text(chosen.get("lawNm"))
    link = clean_text(chosen.get("link"))
    art_hint = clean_text(cand.get("article_hint") or "")

    pack = cached_article(mst, art_hint)
    pack["law_name"] = law_name or pack.get("law_name", q)
    pack["mst"] = mst
    pack["link"] = link
    pack["article_hint"] = art_hint

    art_title = clean_text(pack.get("article_title", ""))
    art_text = clean_text(pack.get("article_text", ""))

    v = verifier_score(case, art_title, art_text)
    pack["verify"] = v
    pack["score"] = v.get("score_total", 0)
    pack["verdict"] = v.get("verdict", "FAIL")
    return pack


def draft_strategy(case: Dict[str, Any], law_pack: Dict[str, Any], examples_text: str) -> str:
    prefer = "strict" if law_pack.get("verdict") != "CONFIRMED" else "fast"
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
- 법령: {law_pack.get("law_name","")}
- 조문: {law_pack.get("article_title","")}
- 원문(정리): {truncate_text(law_pack.get("article_text","") , 900)}

[사례(요약)]
{truncate_text(examples_text, 900)}

아래 형식(마크다운)만 출력:
1) 처리 방향(현실적인 행정 프로세스 중심, 6~10줄)
2) 체크리스트(불릿 10~14개, "확인/기록/통지/기한" 포함)
3) 권한범위(할 수 있는 것/없는 것 각 4~6개)
4) 민원인 설명 포인트(오해 줄이는 문장 4~6개)
"""
    return llm.generate_text(prompt, prefer=prefer, temp=0.1)


def draft_document_json(dept: str, officer: str, case: Dict[str, Any], law_pack: Dict[str, Any], strategy_md: str) -> Dict[str, Any]:
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

사실관계(확정된 범위):
- who: {case.get("facts",{}).get("who","")}
- what: {case.get("facts",{}).get("what","")}
- where: {case.get("facts",{}).get("where","")}
- when: {case.get("facts",{}).get("when","")}
- 민원요구: {case.get("request",{}).get("user_wants","")}
- 제약/기한: {case.get("request",{}).get("constraints","")}

법적 근거(원문 확보된 범위):
- 법령: {law_pack.get("law_name","")}
- 조문: {law_pack.get("article_title","")}
- 원문: {truncate_text(law_pack.get("article_text","") , 1400)}

처리 전략(요약):
{truncate_text(strategy_md, 900)}

작성 원칙:
- 문서 톤: 건조/정중, 추측 금지
- 구조: [경위]→[법적 근거]→[조치/안내]→[권리구제/문의]
- 개인정보는 OOO로 마스킹
- 법령 검증이 WEAK/FAIL이면 "추가 확인 필요" 문구를 '법적 근거' 문단에 포함
"""
    js = llm.generate_json(prompt, prefer="strict", max_retry=3) or {}
    out = ensure_doc_shape(js)
    out["_meta"] = {"doc_num": doc_num, "today": today_str, "dept": dept, "officer": officer}
    return out


def qa_guardrails(doc: Dict[str, Any], law_pack: Dict[str, Any]) -> Dict[str, Any]:
    issues = []
    if not doc.get("title"):
        issues.append("title_missing")
    if not doc.get("receiver"):
        issues.append("receiver_missing")
    if not isinstance(doc.get("body_paragraphs"), list) or len(doc.get("body_paragraphs")) < 3:
        issues.append("body_weak")

    forbidden = ["확실히", "반드시", "100%", "무조건"]
    body = "\n".join(doc.get("body_paragraphs", []))
    if any(x in body for x in forbidden):
        issues.append("overconfident_language")

    if law_pack.get("verdict") in ("WEAK", "FAIL") and ("근거" in body and "추가 확인 필요" not in body):
        issues.append("law_confidence_low_missing_note")

    doc["_qa"] = {"issues": issues}
    return doc


# =========================
# 9) Click-to-Verify UI pieces
# =========================
def render_a4(doc: Dict[str, Any], meta: Dict[str, str]):
    body_html = "".join([f"<p style='margin:0 0 14px 0; text-indent: 12px;'>{safe_html(p)}</p>" for p in doc.get("body_paragraphs", [])])
    html = f"""
<div class="paper-sheet" id="printable-area">
  <div class="stamp">직인생략</div>
  <div class="doc-header">{safe_html(doc.get('title',''))}</div>
  <div class="doc-info">
    <span><b>문서번호</b>: {safe_html(meta.get('doc_num',''))}</span>
    <span><b>시행일자</b>: {safe_html(meta.get('today',''))}</span>
    <span><b>수신</b>: {safe_html(doc.get('receiver',''))}</span>
  </div>
  <div class="doc-body">{body_html}</div>
  <div class="doc-footer">{safe_html(doc.get('department_head',''))}</div>
  <div class="small-muted" style="margin-top:18px;">
    담당: {safe_html(meta.get('officer',''))} · {safe_html(meta.get('dept',''))}
  </div>
</div>
"""
    components.html(html, height=920, scrolling=True)
    st.download_button(
        "📥 공문 HTML로 내보내기",
        data=html,
        file_name=f"공문_{meta.get('doc_num','')}.html",
        mime="text/html",
        use_container_width=True,
    )


def render_law_pack(law_pack: Dict[str, Any]):
    if not law_pack or law_pack.get("error"):
        st.warning(f"법령 원문을 불러오지 못했습니다: {law_pack.get('error')}")
        return

    law_name = law_pack.get("law_name", "")
    article_title = law_pack.get("article_title", "")
    verdict = law_pack.get("verdict", "")
    score = law_pack.get("score", 0)
    link = law_pack.get("link", "")

    st.markdown(f"**선택 법령:** {law_name}  \n**조문:** {article_title}  \n**검증:** {verdict} / score={score}")
    if link:
        st.markdown(f"- 상세 링크: {link}")

    txt = normalize_whitespace(law_pack.get("article_text", "") or "")
    txt = strip_hanja_for_display(txt)
    if not txt:
        st.warning("조문 원문 텍스트가 비어있습니다(다른 후보를 선택하세요).")
        return

    st.markdown("### 조문 원문(정리본)")
    st.code(txt, language="text")

    v = law_pack.get("verify") or {}
    if v:
        st.markdown("### Verifier")
        st.json(v)


def render_examples(case: Dict[str, Any], law_pack: Dict[str, Any]):
    if not (naver.enabled and case and law_pack and law_pack.get("law_name")):
        st.info("네이버 API가 없거나(또는) 케이스/법령 선택이 없어 사례 검색을 할 수 없습니다.")
        return

    q = build_case_query_for_examples(case, law_pack.get("law_name",""), law_pack.get("article_title",""))

    st.caption(f"사례 검색 쿼리: {q}")

    news = cached_naver(q, "news")
    webk = cached_naver(q, "webkr")

    def _item_card(it: Dict[str, Any]):
        title = clean_text(it.get("title","")) or "(제목없음)"
        desc = clean_text(it.get("description","")) or ""
        link = clean_text(it.get("link","")) or ""
        if link:
            st.markdown(
                f"<div class='ev-card'><div class='ev-title'><a href='{link}' target='_blank'>{escape(title)}</a></div><div class='ev-desc'>{escape(desc)}</div></div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div class='ev-card'><div class='ev-title'>{escape(title)}</div><div class='ev-desc'>{escape(desc)}</div></div>",
                unsafe_allow_html=True
            )

    st.markdown("### 📰 뉴스 사례")
    if not news:
        st.caption("뉴스 검색 결과 없음")
    for it in news[:7]:
        _item_card(it)

    st.markdown("### 🌐 웹 문서/판례/해설(검색)")
    if not webk:
        st.caption("웹 검색 결과 없음")
    for it in webk[:7]:
        _item_card(it)

    lines = []
    for it in (news[:5] + webk[:5]):
        t = clean_text(it.get("title","")) or ""
        d = clean_text(it.get("description","")) or ""
        if t:
            lines.append(f"- {t}: {d}")
    st.session_state["examples_text"] = "\n".join(lines).strip()


# =========================
# 10) Performance Lab (눈으로 확인)
# =========================
@dataclass
class BenchResult:
    name: str
    n: int
    unit: str
    mean: float
    p50: float
    p95: float
    min_v: float
    max_v: float
    mem_kb: float


def _percentile(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = int(round((len(xs) - 1) * p))
    k = max(0, min(k, len(xs) - 1))
    return xs[k]


def bench_fn(name: str, fn, n: int = 200, warmup: int = 20, measure_mem: bool = True) -> BenchResult:
    for _ in range(max(0, warmup)):
        fn()

    mem_peak_kb = 0.0
    if measure_mem:
        tracemalloc.start()

    times = []
    for _ in range(n):
        t0 = perf_counter_ns()
        fn()
        t1 = perf_counter_ns()
        times.append((t1 - t0) / 1000.0)  # μs

    if measure_mem:
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mem_peak_kb = peak / 1024.0

    mean = statistics.mean(times)
    p50 = _percentile(times, 0.50)
    p95 = _percentile(times, 0.95)
    return BenchResult(name=name, n=n, unit="μs", mean=mean, p50=p50, p95=p95, min_v=min(times), max_v=max(times), mem_kb=mem_peak_kb)


def render_bench_table(results: List[BenchResult], title: str):
    if not results:
        st.info("측정 결과가 없습니다.")
        return
    if not pd:
        st.warning("pandas 미설치라 표/차트 표시가 제한됩니다.")
        for r in results:
            st.write(r)
        return

    df = pd.DataFrame([{
        "name": r.name,
        "n": r.n,
        "mean(μs)": round(r.mean, 2),
        "p50(μs)": round(r.p50, 2),
        "p95(μs)": round(r.p95, 2),
        "min(μs)": round(r.min_v, 2),
        "max(μs)": round(r.max_v, 2),
        "peak_mem(KB)": round(r.mem_kb, 1),
    } for r in results]).sort_values(["p95(μs)", "mean(μs)"], ascending=[False, False])

    st.subheader(title)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("p95 기준(큰 값일수록 느림)")
    chart_df = df[["name", "p95(μs)", "mean(μs)"]].set_index("name")
    st.bar_chart(chart_df)


def render_performance_lab():
    st.markdown("## 🧪 성능 실험실(Performance Lab)")
    st.caption("버튼 클릭 → 앱의 핵심 연산을 실제로 재서 p50/p95/메모리 피크를 확인합니다.")

    n = st.slider("반복 횟수(n)", min_value=50, max_value=2000, value=300, step=50)
    measure_mem = st.checkbox("메모리 피크(tracemalloc) 측정", value=True)

    sample_text = st.text_area(
        "샘플 텍스트(정규화/한자제거/HTML 안전화 측정용)",
        value="건설기계 주기위반 관련 민원. 현장 확인 결과 이동함. 민원인은 상시 단속 및 과태료 부과 요구. 제33조 적용 여부 검토.",
        height=110
    )

    pack = st.session_state.get("selected_law_pack") or {}
    law_text = (pack.get("article_text") or "")[:3000]

    colA, colB = st.columns(2)
    with colA:
        if st.button("⚡ 로컬 연산 벤치", use_container_width=True):
            res = []
            res.append(bench_fn("clean_text()", lambda: clean_text(sample_text), n=n, measure_mem=measure_mem))
            res.append(bench_fn("normalize_whitespace()", lambda: normalize_whitespace(sample_text), n=n, measure_mem=measure_mem))
            res.append(bench_fn("strip_hanja_for_display()", lambda: strip_hanja_for_display(sample_text), n=n, measure_mem=measure_mem))
            res.append(bench_fn("safe_html()", lambda: safe_html(sample_text), n=n, measure_mem=measure_mem))
            if law_text:
                case = st.session_state.get("case_struct") or {"keywords": [], "issues": [], "facts": {"what": ""}}
                res.append(bench_fn("verifier_score()", lambda: verifier_score(case, pack.get("article_title",""), law_text), n=max(50, n//3), measure_mem=measure_mem))
            render_bench_table(res, "Local Ops")

    with colB:
        if st.button("📦 JSON 직렬화 벤치", use_container_width=True):
            obj = {
                "text": sample_text,
                "kws": extract_keywords_kor(sample_text, 10),
                "pack": pack,
                "ts": datetime.now().isoformat(),
                "nums": list(range(200)),
                "nested": [{"a": i, "b": {"x": i*2, "y": str(i)}} for i in range(50)],
            }
            res = []
            res.append(bench_fn("json.dumps()", lambda: json.dumps(obj, ensure_ascii=False, default=str), n=n, measure_mem=measure_mem))
            if orjson:
                res.append(bench_fn("orjson.dumps()", lambda: orjson.dumps(obj), n=n, measure_mem=measure_mem))
            else:
                st.info("orjson 미설치(선택): pip install orjson")
            if msgspec:
                enc = msgspec.json.Encoder()
                res.append(bench_fn("msgspec.encode()", lambda: enc.encode(obj), n=n, measure_mem=measure_mem))
            else:
                st.info("msgspec 미설치(선택): pip install msgspec")
            render_bench_table(res, "Serialization")

    st.markdown("---")
    st.markdown("### 🌐 I/O 벤치(선택)")
    st.caption("네트워크 영향이 크므로 '최적화 전후 비교' 용도입니다.")
    io_n = st.slider("I/O 반복 횟수", min_value=1, max_value=30, value=5, step=1)

    if st.button("🌐 DRF/네이버 호출 벤치", use_container_width=True):
        res = []
        case = st.session_state.get("case_struct") or {}
        cand = st.session_state.get("law_candidates", [])[:1]
        if cand:
            c = cand[0]
            res.append(bench_fn("load_law_pack_from_candidate()", lambda: load_law_pack_from_candidate(case, c), n=io_n, warmup=0, measure_mem=False))
        else:
            st.warning("먼저 워크플로우 실행 후 후보가 생기면 측정하세요.")

        if naver.enabled:
            q = " ".join(extract_keywords_kor(sample_text, 3)) + " 과태료 처분 사례"
            res.append(bench_fn("naver.search(news)", lambda: cached_naver(q, "news"), n=io_n, warmup=0, measure_mem=False))
            res.append(bench_fn("naver.search(webkr)", lambda: cached_naver(q, "webkr"), n=io_n, warmup=0, measure_mem=False))
        else:
            st.info("네이버 API 미설정이라 제외됨.")

        render_bench_table(res, "Network / I/O (ms급이 정상)")


# =========================
# 11) Workflow Controller
# =========================
def run_workflow(user_input: str, dept: str, officer: str):
    log_area = st.empty()
    logs = []

    def add_log(msg: str, style: str = "sys"):
        logs.append(f"<div class='agent-log log-{style}'>{safe_html(msg)}</div>")
        log_area.markdown("".join(logs), unsafe_allow_html=True)
        time.sleep(0.02)

    add_log("🧾 [INTAKE] 사실관계 구조화(FAST)", "sys")
    case = intake_schema(user_input)
    st.session_state["case_struct"] = case
    add_log(f"✅ [INTAKE] 완료 (quality={case.get('_input_quality',{}).get('score','?')})", "sys")

    add_log("🧩 [LAW-CAND] 법령 후보 생성(FAST)", "legal")
    candidates = generate_law_candidates(case)
    st.session_state["law_candidates"] = candidates
    add_log("📌 후보 생성 완료 — 오른쪽 '법적 근거(클릭)' 탭에서 후보를 눌러 원문/사례 확인", "legal")

    if candidates:
        add_log("📚 [LAW] 1번 후보 원문 로드(캐시/세션 적용)", "legal")
        pack = load_law_pack_from_candidate(case, candidates[0])
        st.session_state["selected_candidate_idx"] = 0
        st.session_state["selected_law_pack"] = pack

    log_area.empty()
    return case


def build_strategy_and_doc(dept: str, officer: str):
    case = st.session_state.get("case_struct") or {}
    law_pack = st.session_state.get("selected_law_pack") or {}
    examples_text = st.session_state.get("examples_text") or ""

    strategy = draft_strategy(case, law_pack, examples_text)
    st.session_state["strategy_md"] = strategy

    doc = draft_document_json(dept, officer, case, law_pack, strategy)
    doc = qa_guardrails(doc, law_pack)
    st.session_state["doc_json"] = ensure_doc_shape(doc)


# =========================
# 12) Main UI
# =========================
def main():
    st.session_state.setdefault("dept", "OO시청 OO과")
    st.session_state.setdefault("officer", "김주무관")
    st.session_state.setdefault("case_struct", None)
    st.session_state.setdefault("law_candidates", [])
    st.session_state.setdefault("selected_candidate_idx", 0)
    st.session_state.setdefault("selected_law_pack", {})
    st.session_state.setdefault("examples_text", "")
    st.session_state.setdefault("strategy_md", "")
    st.session_state.setdefault("doc_json", None)

    col_l, col_r = st.columns([1, 1.25], gap="large")

    with col_l:
        st.title("AI 행정관 Pro")
        st.caption("v8.1 — Click-to-Verify(원문+사례) + A4 공문 + 성능실험실")
        st.markdown("---")

        with st.expander("🧩 부서/담당자 설정", expanded=False):
            st.text_input("부서명", key="dept")
            st.text_input("담당자", key="officer")
            st.caption("※ Groq/Law/Naver 키는 secrets.toml에 설정하세요.")

        user_input = st.text_area(
            "업무 지시 사항(민원 상황 포함)",
            height=220,
            placeholder="예: 건설기계가 차고지 외 장기간 주차(주기위반) 신고가 들어왔고, 현장 확인했더니 이동한 상태. 민원인은 상시 단속을 요구. 담당자가 할 수 있는 조치와 답변 공문 작성.",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚀 1) 분석 시작(후보 생성)", type="primary", use_container_width=True):
                if not user_input.strip():
                    st.warning("내용을 입력하세요.")
                else:
                    with st.spinner("구조화 → 법령 후보 생성 중..."):
                        run_workflow(user_input.strip(), st.session_state["dept"], st.session_state["officer"])
                        st.success("후보 생성 완료! 오른쪽 탭에서 후보 클릭 → 원문/사례 확인하세요.")

        with c2:
            if st.button("✍️ 2) 공문 생성(원문/사례 확인 후)", use_container_width=True):
                if not st.session_state.get("case_struct"):
                    st.warning("먼저 1) 분석 시작을 실행하세요.")
                else:
                    with st.spinner("전략/공문 생성 중..."):
                        build_strategy_and_doc(st.session_state["dept"], st.session_state["officer"])
                        st.success("공문 생성 완료!")

        st.markdown("---")
        st.subheader("📊 세션 사용량")
        m = st.session_state.get("metrics", {})
        calls = m.get("calls", {})
        tokens_total = m.get("tokens_total", 0)
        if calls:
            for k, v in sorted(calls.items(), key=lambda x: (-x[1], x[0])):
                st.write(f"- **{k}**: {v}회")
            st.caption(f"총 토큰(가능한 경우): {tokens_total}")
        else:
            st.info("대기 중...")

        st.markdown("<div class='small-muted'>핵심 사용법: 후보 클릭 → 원문+사례 확인 → 그 다음 공문 생성.</div>", unsafe_allow_html=True)

    with col_r:
        tabs = st.tabs(["📄 공문(A4)", "⚖️ 법적 근거(클릭)", "🧾 사례(클릭)", "🧠 전략/구조화", "🧪 성능실험실"])

        with tabs[0]:
            doc = st.session_state.get("doc_json")
            if not doc:
                st.markdown(
                    """
<div style='text-align:center; padding:120px 20px; color:#9ca3af; border:2px dashed #e5e7eb; border-radius:14px; background:#fff;'>
  <h3 style='margin-bottom:8px;'>📄 A4 미리보기</h3>
  <p>1) 분석 시작 → 2) 후보 클릭으로 근거 확인 → 3) 공문 생성</p>
</div>
""",
                    unsafe_allow_html=True,
                )
            else:
                meta = doc.get("_meta") or {}
                render_a4(doc, meta)

        with tabs[1]:
            case = st.session_state.get("case_struct") or {}
            cands = st.session_state.get("law_candidates") or []
            st.markdown("## ⚖️ 법적 근거 — 후보를 클릭해서 원문을 확인")
            if not cands:
                st.info("왼쪽에서 1) 분석 시작을 실행하면 후보가 생성됩니다.")
            else:
                for i, c in enumerate(cands[:10]):
                    law_name = clean_text(c.get("law_name","")) or "(법령명 없음)"
                    hint = clean_text(c.get("article_hint","")) or "-"
                    conf = float(c.get("confidence", 0.0) or 0.0)
                    label = f"{i+1}. {law_name}"
                    badge = f"<span class='badge'>hint:{hint} · conf:{conf:.2f}</span>"
                    cols = st.columns([0.80, 0.20])
                    with cols[0]:
                        st.markdown(f"<div class='card'><div class='card-title'>{escape(label)} {badge}</div><div class='card-sub'>{escape(clean_text(c.get('reason','')))}</div></div>", unsafe_allow_html=True)
                    with cols[1]:
                        if st.button("원문보기", key=f"pick_{i}", use_container_width=True):
                            pack = load_law_pack_from_candidate(case, c)
                            st.session_state["selected_candidate_idx"] = i
                            st.session_state["selected_law_pack"] = pack
                            st.success(f"선택: {pack.get('law_name','')} / {pack.get('article_title','')}")
                st.markdown("---")
                st.markdown("### 📌 선택된 법령 원문")
                render_law_pack(st.session_state.get("selected_law_pack") or {})

        with tabs[2]:
            st.markdown("## 🧾 사례 — '선택된 법령' 기준으로 사례를 클릭해 확인")
            case = st.session_state.get("case_struct") or {}
            pack = st.session_state.get("selected_law_pack") or {}
            if not case or not pack:
                st.info("먼저 '법적 근거(클릭)'에서 후보를 선택하세요.")
            else:
                render_examples(case, pack)

        with tabs[3]:
            st.markdown("## 🧠 전략/구조화")
            case = st.session_state.get("case_struct")
            if not case:
                st.info("아직 분석 결과가 없습니다.")
            else:
                st.markdown("### 1) 구조화된 사실관계")
                st.json(case)

                st.markdown("### 2) 선택 법령(요약)")
                pack = st.session_state.get("selected_law_pack") or {}
                if pack:
                    st.write(f"- {pack.get('law_name','')} / {pack.get('article_title','')} / {pack.get('verdict','')} (score={pack.get('score',0)})")
                else:
                    st.caption("선택된 법령 없음")

                st.markdown("### 3) 처리 전략(공문 생성 후 표시)")
                strat = st.session_state.get("strategy_md") or ""
                if strat:
                    st.markdown(strat)
                else:
                    st.caption("공문 생성(2)을 누르면 전략이 생성됩니다.")

                doc = st.session_state.get("doc_json")
                if doc:
                    st.markdown("### 4) 공문 JSON(디버그)")
                    st.json(doc)

        with tabs[4]:
            render_performance_lab()


if __name__ == "__main__":
    main()
