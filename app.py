# app.py
# AI 행정관 Pro v9 - 안정 구동 + 클릭형 원문/사례 + 성능 대시보드
# - Streamlit Cloud 단일파일 구동
# - secrets.toml: [general] 또는 [law] 모두 지원
# - LAW.go.kr DRF(XML) 연동 + Naver 사례 검색(옵션)
# - 캐시 + 타이밍 + 실패원인 "눈에 보이게"

from __future__ import annotations

import time
import json
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import streamlit as st

# Optional imports (앱 안죽게)
try:
    import requests
except Exception:
    requests = None

try:
    import xmltodict
except Exception:
    xmltodict = None


# -------------------------
# Page config & styles
# -------------------------
st.set_page_config(page_title="AI 행정관 Pro v9", page_icon="🏛️", layout="wide")

st.markdown(
    """
<style>
.stApp { background-color: #f3f4f6; }
.paper {
  background:#fff;
  width:100%;
  max-width:210mm;
  min-height:297mm;
  padding:25mm;
  margin: 0 auto;
  box-shadow:0 10px 30px rgba(0,0,0,0.10);
  font-family: "Batang", serif;
  color:#111;
  line-height:1.65;
}
.h1 {
  text-align:center;
  font-size:22px;
  font-weight:700;
  margin: 0 0 18px 0;
  padding-bottom: 10px;
  border-bottom: 2px solid #111;
}
.meta {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  color: #444;
  margin-bottom: 14px;
}
.badge {
  display:inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  background: #111;
  color:#fff;
  font-size: 12px;
  margin-left: 8px;
}
.card {
  background:#fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 10px;
}
.small {
  font-size: 12px;
  color: #555;
}
hr.sep { border:none; border-top:1px solid #e5e7eb; margin: 16px 0; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("AI 행정관 Pro v9")
st.caption("클릭형 근거(법령 원문/사례) + Verifier(기본) + 성능 대시보드(눈으로 확인)")


# -------------------------
# Secrets reader (general/law 둘다 지원)
# -------------------------
def _get_secret(paths: List[Tuple[str, str]]) -> Optional[str]:
    """
    paths: [(section, key), ...]
    """
    for section, key in paths:
        try:
            sec = st.secrets.get(section, {})
            val = sec.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass
    return None


@dataclass
class Config:
    law_api_id: Optional[str]
    naver_client_id: Optional[str]
    naver_client_secret: Optional[str]


def load_config() -> Config:
    law_api_id = _get_secret(
        [
            ("law", "LAW_API_ID"),
            ("general", "LAW_API_ID"),
            ("general", "LAW_API_ID "),
        ]
    )
    naver_client_id = _get_secret([("naver", "CLIENT_ID"), ("general", "CLIENT_ID")])
    naver_client_secret = _get_secret([("naver", "CLIENT_SECRET"), ("general", "CLIENT_SECRET")])
    return Config(
        law_api_id=law_api_id,
        naver_client_id=naver_client_id,
        naver_client_secret=naver_client_secret,
    )


cfg = load_config()


# -------------------------
# Perf tracker
# -------------------------
def ss_init():
    if "perf" not in st.session_state:
        st.session_state.perf = {
            "calls": [],  # list of dicts {name, ok, ms}
            "counters": {},  # name -> count
        }


def perf_mark(name: str, ok: bool, ms: float):
    ss_init()
    st.session_state.perf["calls"].append({"name": name, "ok": ok, "ms": ms})
    st.session_state.perf["counters"][name] = st.session_state.perf["counters"].get(name, 0) + 1


class Timer:
    def __init__(self, name: str):
        self.name = name
        self.t0 = None

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = (time.perf_counter() - self.t0) * 1000.0
        perf_mark(self.name, ok=(exc is None), ms=ms)
        return False


# -------------------------
# Diagnostics panel
# -------------------------
with st.expander("🔎 시스템 진단(먼저 여기부터 봐야 함)"):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("requests 설치:", bool(requests))
        st.write("xmltodict 설치:", bool(xmltodict))
    with c2:
        st.write("LAW_API_ID 감지:", bool(cfg.law_api_id))
        st.code(f"LAW_API_ID = {('SET' if cfg.law_api_id else 'MISSING')}")
    with c3:
        st.write("NAVER 키 감지:", bool(cfg.naver_client_id and cfg.naver_client_secret))
        st.code(
            f"NAVER = {('SET' if (cfg.naver_client_id and cfg.naver_client_secret) else 'OPTIONAL/MISSING')}"
        )

    st.info(
        "LAW 검색이 안 되면 거의 99%가 (1) LAW_API_ID 미탑재 (2) requests/xmltodict 누락 (3) DRF 호출 실패(네트워크/OC값) 입니다."
    )


# Hard stop if core deps missing
if not requests or not xmltodict:
    st.error("핵심 의존성 누락: requests 또는 xmltodict가 설치되어야 합니다. requirements.txt 확인.")
    st.stop()

if not cfg.law_api_id:
    st.error("LAW.go.kr DRF 설정이 비었습니다. secrets.toml에 [law] 또는 [general] LAW_API_ID를 넣어주세요.")
    st.stop()


# -------------------------
# LAW.go.kr DRF client
# -------------------------
LAW_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"


def _safe_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


@st.cache_data(ttl=3600, show_spinner=False)
def drf_law_search(oc: str, query: str, display: int = 10) -> Dict[str, Any]:
    params = {
        "OC": oc,
        "target": "law",
        "type": "XML",
        "query": query,
        "display": display,
    }
    r = requests.get(LAW_SEARCH_URL, params=params, timeout=12)
    r.raise_for_status()
    return xmltodict.parse(r.text)


@st.cache_data(ttl=3600, show_spinner=False)
def drf_law_service(oc: str, mst: str) -> Dict[str, Any]:
    params = {"OC": oc, "target": "law", "type": "XML", "MST": mst}
    r = requests.get(LAW_SERVICE_URL, params=params, timeout=12)
    r.raise_for_status()
    return xmltodict.parse(r.text)


def normalize_law_search(parsed: Dict[str, Any]) -> List[Dict[str, str]]:
    root = parsed.get("LawSearch", {}) if isinstance(parsed, dict) else {}
    laws = _safe_list(root.get("law"))
    out = []
    for law in laws:
        if not isinstance(law, dict):
            continue
        name = law.get("법령명한글") or law.get("법령명") or ""
        mst = law.get("법령일련번호") or law.get("MST") or ""
        promulg = law.get("공포일자") or ""
        out.append(
            {
                "name": str(name).strip(),
                "mst": str(mst).strip(),
                "promulg": str(promulg).strip(),
                "lawgo_link": f"https://www.law.go.kr/법령/{quote(str(name).strip())}" if name else "",
            }
        )
    return [x for x in out if x["name"] and x["mst"]]


def extract_articles(service_parsed: Dict[str, Any], max_articles: int = 30) -> List[Dict[str, str]]:
    """
    LAW Service XML 구조는 법령에 따라 약간 다름.
    - 여기선 최대한 '조문 제목/내용'이 나오게 방어적으로 파싱.
    """
    # 가능한 루트들 탐색
    root_candidates = [
        service_parsed.get("법령", {}),
        service_parsed.get("Law", {}),
        service_parsed.get("law", {}),
        service_parsed,
    ]

    articles: List[Dict[str, str]] = []
    for root in root_candidates:
        if not isinstance(root, dict):
            continue

        # 자주 나오는 키 후보들
        for key in ["조문", "조문단위", "Article", "article"]:
            node = root.get(key)
            if not node:
                continue
            for a in _safe_list(node):
                if not isinstance(a, dict):
                    continue
                no = a.get("조문번호") or a.get("ArticleNumber") or a.get("번호") or ""
                title = a.get("조문제목") or a.get("ArticleTitle") or a.get("제목") or ""
                text = a.get("조문내용") or a.get("ArticleContent") or a.get("내용") or ""
                articles.append(
                    {
                        "no": str(no).strip(),
                        "title": str(title).strip(),
                        "text": str(text).strip(),
                    }
                )
        if articles:
            break

    # 후처리
    cleaned = []
    for a in articles:
        t = a["text"].replace("\r", "\n").strip()
        cleaned.append({**a, "text": t})
    return cleaned[:max_articles]


# -------------------------
# NAVER search (examples)
# -------------------------
NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


@st.cache_data(ttl=1800, show_spinner=False)
def naver_news_search(client_id: str, client_secret: str, query: str, display: int = 10) -> Dict[str, Any]:
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": display, "sort": "sim"}
    r = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=12)
    r.raise_for_status()
    return r.json()


def strip_html_tags(s: str) -> str:
    # 간단 제거(뉴스 API title/desc에 <b> 태그가 들어옴)
    import re
    return re.sub(r"<[^>]+>", "", s or "").strip()


# -------------------------
# UI - Settings
# -------------------------
with st.expander("⚙️ 설정", expanded=False):
    st.write("LAW API는 필수, NAVER는 사례검색(옵션)입니다.")
    st.code(
        """# secrets.toml 예시

[general]
LAW_API_ID = "kimve"

[naver]
CLIENT_ID = "..."
CLIENT_SECRET = "..."
"""
    )
    st.write("※ secrets.toml은 반드시 따옴표 닫힘(문자열 끝) 확인")


# -------------------------
# Main workflow
# -------------------------
left, right = st.columns([1.15, 1])

with left:
    st.subheader("1) 민원/업무 상황 입력")
    case_text = st.text_area(
        "상황을 최대한 구체적으로",
        height=160,
        placeholder="예: 사유지에 굴착기(건설기계)가 장기간 주기되었고, 민원인이 이동 조치를 요구함. 현장 확인 시 이미 이동함 등",
    )

    kw_hint = st.text_input("2) (선택) 법령 검색 키워드 힌트", placeholder="예: 건설기계관리법 주기위반")

    colA, colB, colC = st.columns([1, 1, 1])
    with colA:
        do_search = st.button("🔎 법령 검색", use_container_width=True)
    with colB:
        do_examples = st.button("📰 사례(뉴스) 검색", use_container_width=True)
    with colC:
        do_draft = st.button("📄 공문 초안 생성", use_container_width=True)

with right:
    st.subheader("결과")
    st.write("오른쪽은 '원문 클릭'과 '사례 클릭' 중심으로 구성됩니다.")
    st.markdown("<hr class='sep'/>", unsafe_allow_html=True)

    if "selected_law" not in st.session_state:
        st.session_state.selected_law = None
    if "selected_articles" not in st.session_state:
        st.session_state.selected_articles = []
    if "last_laws" not in st.session_state:
        st.session_state.last_laws = []
    if "last_examples" not in st.session_state:
        st.session_state.last_examples = []


# -------------------------
# Actions
# -------------------------
def build_query(case_text: str, hint: str) -> str:
    base = (hint or "").strip()
    if base:
        return base
    # 힌트 없으면 상황에서 핵심 단어만 대충 끌어올림(안전한 기본)
    # 실무상은 사용자가 힌트 넣는게 정확도가 가장 좋음.
    t = (case_text or "").strip()
    if not t:
        return ""
    # 너무 길면 앞부분만
    return t[:60]


if do_search:
    q = build_query(case_text, kw_hint)
    if not q:
        st.warning("검색어가 비었습니다. 상황을 입력하거나 힌트를 넣어주세요.")
    else:
        with st.spinner("LAW.go.kr DRF에서 법령 검색 중..."):
            try:
                with Timer("drf_law_search"):
                    parsed = drf_law_search(cfg.law_api_id, q, display=10)
                laws = normalize_law_search(parsed)
                st.session_state.last_laws = laws

                if not laws:
                    st.error("법령 검색 결과가 0건입니다.")
                    st.info(
                        "원인 후보: (1) 검색어가 너무 구체/이상함 (2) OC(LAW_API_ID) 문제 (3) DRF 응답 구조 변경/일시 장애"
                    )
                else:
                    st.success(f"법령 {len(laws)}건 발견")
            except Exception as e:
                st.error(f"법령 검색 실패: {e}")
                st.code(traceback.format_exc())


if do_examples:
    if not (cfg.naver_client_id and cfg.naver_client_secret):
        st.warning("NAVER API 키가 없어 사례(뉴스) 검색은 스킵합니다. (LAW 검색/원문은 정상)")
    else:
        q = build_query(case_text, kw_hint)
        if not q:
            st.warning("검색어가 비었습니다. 상황을 입력하거나 힌트를 넣어주세요.")
        else:
            # 사례 검색은 "행정처분/단속/조치" 키워드를 섞어줌
            nq = f"{q} 행정처분 OR 단속 OR 과태료 OR 조치"
            with st.spinner("네이버 뉴스에서 사례 검색 중..."):
                try:
                    with Timer("naver_news_search"):
                        j = naver_news_search(cfg.naver_client_id, cfg.naver_client_secret, nq, display=10)
                    items = j.get("items", []) if isinstance(j, dict) else []
                    examples = []
                    for it in items:
                        examples.append(
                            {
                                "title": strip_html_tags(it.get("title", "")),
                                "desc": strip_html_tags(it.get("description", "")),
                                "link": it.get("originallink") or it.get("link") or "",
                                "pubDate": it.get("pubDate", ""),
                            }
                        )
                    st.session_state.last_examples = [x for x in examples if x["title"] and x["link"]]
                    if not st.session_state.last_examples:
                        st.warning("사례 검색 결과가 없습니다.")
                    else:
                        st.success(f"사례 {len(st.session_state.last_examples)}건 확보")
                except Exception as e:
                    st.error(f"사례 검색 실패: {e}")
                    st.code(traceback.format_exc())


def a4_render(title: str, meta: Dict[str, str], body_paragraphs: List[str]):
    body_html = "".join(
        f"<p style='margin:0 0 14px 0; text-indent: 12px;'>{st._utils.escape_markdown(p)}</p>"
        for p in body_paragraphs
    )
    # Streamlit escape_markdown은 HTML 이스케이프가 아님. 그러므로 여기서는 단순 text만 넣음.
    # -> 안전하게 다시 구성:
    import html as _html

    body_html = "".join(
        f"<p style='margin:0 0 14px 0; text-indent: 12px;'>{_html.escape(p)}</p>"
        for p in body_paragraphs
    )

    html = f"""
<div class="paper">
  <div class="h1">{_html.escape(title)}</div>
  <div class="meta">
    문서번호: {_html.escape(meta.get("doc_no",""))} &nbsp; | &nbsp;
    시행일자: {_html.escape(meta.get("date",""))} &nbsp; | &nbsp;
    담당부서: {_html.escape(meta.get("dept",""))}
  </div>
  {body_html}
  <div style="margin-top:80px; text-align:right;">
    {_html.escape(meta.get("date",""))}<br/>
    {_html.escape(meta.get("org","충주시청"))}
  </div>
</div>
"""
    st.components.v1.html(html, height=1000, scrolling=True)
    st.download_button(
        "📥 공문 HTML 다운로드",
        data=html,
        file_name=f"공문_{meta.get('doc_no','draft')}.html",
        mime="text/html",
        use_container_width=True,
    )


if do_draft:
    # 간단 Verifier(기본): “사실확정 전” 문구 자동 삽입
    q = build_query(case_text, kw_hint)
    if not q:
        st.warning("상황 입력이 비었습니다.")
    else:
        # 법령이 없으면 먼저 law search를 자동 수행
        if not st.session_state.last_laws:
            try:
                with Timer("drf_law_search(auto)"):
                    parsed = drf_law_search(cfg.law_api_id, q, display=5)
                st.session_state.last_laws = normalize_law_search(parsed)
            except Exception:
                st.session_state.last_laws = []

        law_line = "관련 법령 검토가 필요합니다."
        if st.session_state.last_laws:
            law_line = f"관련 법령으로는 '{st.session_state.last_laws[0]['name']}' 등이 검토 대상입니다."

        meta = {
            "doc_no": f"draft-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "date": datetime.now().strftime("%Y.%m.%d"),
            "dept": "차량민원과(예시)",
            "org": "충주시청",
        }
        body = [
            "1. 귀하의 민원에 대해 검토한 결과를 아래와 같이 안내드립니다.",
            f"2. 민원 내용(요지): {case_text.strip()[:400] if case_text else q}",
            f"3. 법령 검토(초안): {law_line}",
            "4. 확인 필요사항(Verifier):",
            "- 현장 확인 시점, 주기 사실(기간/장소/사진 등), 차량/건설기계 식별정보, 도로 여부(사유지/공유지) 등 사실관계가 확정되어야 처분 가능 여부 판단이 가능합니다.",
            "5. 처리 방향(초안):",
            "- 사실관계 확인 → 관련 법령 적용 가능 여부 검토 → 행정지도/계도 또는 법령상 조치 절차 진행(해당 시).",
            "6. 추가 문의는 담당부서로 연락주시기 바랍니다.",
        ]
        with right:
            st.subheader("📄 공문(초안) 미리보기")
            a4_render("민원 처리 검토 결과(초안)", meta, body)


# -------------------------
# Render results in right panel
# -------------------------
with right:
    # 법령 목록
    if st.session_state.last_laws:
        st.markdown("### 📚 법령 후보(원문 클릭)")
        for i, law in enumerate(st.session_state.last_laws, start=1):
            st.markdown(
                f"""
<div class="card">
  <div><b>{i}. {law['name']}</b> <span class="badge">MST {law['mst']}</span></div>
  <div class="small">공포일자: {law.get('promulg','')}</div>
  <div style="margin-top:8px;">
    <a href="{law['lawgo_link']}" target="_blank">원문 보기(법령정보센터)</a>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

        # 조문 가져오기
        st.markdown("#### 🔍 조문(요약/확인용) — 선택 법령 1개 기준")
        pick = st.selectbox(
            "조문을 가져올 법령 선택",
            options=list(range(len(st.session_state.last_laws))),
            format_func=lambda idx: st.session_state.last_laws[idx]["name"],
        )
        if st.button("📌 선택 법령 조문 불러오기", use_container_width=True):
            law = st.session_state.last_laws[pick]
            with st.spinner("조문 불러오는 중..."):
                try:
                    with Timer("drf_law_service"):
                        service = drf_law_service(cfg.law_api_id, law["mst"])
                    arts = extract_articles(service, max_articles=30)
                    st.session_state.selected_law = law
                    st.session_state.selected_articles = arts
                    if not arts:
                        st.warning("조문 파싱 결과가 비었습니다(법령 XML 구조 차이 가능). 그래도 원문 링크로 확인 가능.")
                    else:
                        st.success(f"조문 {len(arts)}개 로드")
                except Exception as e:
                    st.error(f"조문 로드 실패: {e}")
                    st.code(traceback.format_exc())

    # 조문 표시
    if st.session_state.selected_law:
        st.markdown("### 🧾 조문(클릭해서 원문 확인 권장)")
        law = st.session_state.selected_law
        st.markdown(f"**선택 법령:** {law['name']}  \n[원문 열기]({law['lawgo_link']})")

        if st.session_state.selected_articles:
            for a in st.session_state.selected_articles:
                title = f"제{a.get('no','?')}조 {a.get('title','')}".strip()
                with st.expander(title):
                    st.write(a.get("text", "")[:5000] if a.get("text") else "(내용 없음)")
        else:
            st.info("조문을 불러오지 않았거나, 구조 차이로 파싱이 비었습니다. 위 원문 링크로 확인하세요.")

    # 사례 표시
    if st.session_state.last_examples:
        st.markdown("### 📰 사례(클릭)")
        for ex in st.session_state.last_examples:
            st.markdown(
                f"""
<div class="card">
  <div><b>{ex['title']}</b></div>
  <div class="small">{ex['desc']}</div>
  <div style="margin-top:8px;">
    <a href="{ex['link']}" target="_blank">원문 보기</a>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

    # 성능 대시보드
    st.markdown("<hr class='sep'/>", unsafe_allow_html=True)
    st.markdown("## ⚡ 성능 대시보드(눈으로 확인)")

    ss_init()
    calls = st.session_state.perf["calls"]
    counters = st.session_state.perf["counters"]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("총 호출", str(len(calls)))
    with c2:
        ok_cnt = sum(1 for x in calls if x["ok"])
        st.metric("성공", str(ok_cnt))
    with c3:
        if calls:
            st.metric("최근 호출(ms)", f"{calls[-1]['ms']:.1f}")
        else:
            st.metric("최근 호출(ms)", "-")

    if calls:
        # 평균/최대 타이밍 테이블
        by_name: Dict[str, List[float]] = {}
        for x in calls:
            by_name.setdefault(x["name"], []).append(float(x["ms"]))
        rows = []
        for name, arr in by_name.items():
            rows.append(
                {
                    "name": name,
                    "count": len(arr),
                    "avg_ms": sum(arr) / len(arr),
                    "max_ms": max(arr),
                }
            )
        rows = sorted(rows, key=lambda r: r["avg_ms"], reverse=True)
        st.dataframe(rows, use_container_width=True)

        # 라인차트(최근 30개)
        tail = calls[-30:]
        st.line_chart(
            {"ms": [x["ms"] for x in tail]},
            height=160,
        )

    if st.button("🧹 성능 기록 초기화", use_container_width=True):
        st.session_state.perf = {"calls": [], "counters": {}}
        st.experimental_rerun()
