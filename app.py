import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ============================================================
# 1. 페이지 설정 & 스타일
# ============================================================
st.set_page_config(
    page_title="AED 접근성 개선 시스템",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1450px; }
    .hero {
        padding: 1.6rem 2rem; border-radius: 16px;
        background: linear-gradient(120deg, #0f172a 0%, #1e3a8a 60%, #0d9488 100%);
        color: white; margin-bottom: 1.2rem;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
    }
    .hero h1 { color: white; margin: 0 0 0.4rem 0; font-size: 2.1rem; font-weight: 800; }
    .hero p { color: #e2e8f0; margin: 0; font-size: 1rem; }
    .badge {
        display: inline-block; padding: 0.25rem 0.7rem; border-radius: 99px;
        background: rgba(255,255,255,0.18); color: #f8fafc; font-size: 0.82rem;
        font-weight: 600; margin-right: 0.4rem; margin-top: 0.6rem;
    }
    .section-title { font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem; }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,0.25);
        padding: 14px 18px; border-radius: 14px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 2. 데이터 불러오기
# ============================================================
ROOT = Path(__file__).resolve().parent


def find_file(filename: str):
    """현재 폴더 또는 data/ 폴더에서 파일을 찾습니다."""
    for p in [ROOT / filename, ROOT / "data" / filename, Path(filename), Path("data") / filename]:
        if p.exists():
            return p
    return None


@st.cache_data
def load_csv_safe(filepath: str):
    try:
        return pd.read_csv(filepath, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(filepath, encoding="cp949")


@st.cache_data
def load_json_safe(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def get_summary_data():
    p = find_file("시간대별_커버리지_요약.csv")
    if p:
        return load_csv_safe(str(p))
    return pd.DataFrame([
        {"시간": "01시", "전체_AED수": 214, "이용가능_AED수": 170.0, "AED이용가능률(%)": 79.44,
         "전체격자수": 4221, "접근가능격자수": 854.0, "사각지대격자수": 3367.0, "격자접근가능률(%)": 20.23},
        {"시간": "13시", "전체_AED수": 214, "이용가능_AED수": 211.4, "AED이용가능률(%)": 98.79,
         "전체격자수": 4221, "접근가능격자수": 962.8, "사각지대격자수": 3258.2, "격자접근가능률(%)": 22.81},
    ])


@st.cache_data
def get_greedy_data():
    p_json = find_file("greedy_results.json")
    if p_json:
        payload = load_json_safe(str(p_json))
        return pd.DataFrame([payload.get("baseline", {})] + payload.get("top5", [])), payload.get("meta", {})
    p_csv = find_file("greedy_top5.csv")
    if p_csv:
        return load_csv_safe(str(p_csv)), {}
    st.error("greedy_top5.csv 또는 greedy_results.json 파일을 찾을 수 없습니다.")
    st.stop()


@st.cache_data
def get_aed_grid_mapping():
    """AED_ID -> 그 AED가 200m 안에 커버하는 격자_ID 목록"""
    p = find_file("AED별_커버_격자목록.json")
    if not p:
        return {}
    return {int(item["AED_ID"]): item.get("커버_격자_ID_목록", []) for item in load_json_safe(str(p))}


@st.cache_data
def get_geojson_data():
    """전체 4,221개 격자 파일을 우선 사용합니다. (없으면 기존 사각지대 파일 사용)"""
    p = find_file("격자_전체_지도용.geojson")
    if p:
        return load_json_safe(str(p)), True
    p = find_file("사각지대_지도용.geojson")
    if p:
        return load_json_safe(str(p)), False
    return None, False


# ============================================================
# 3. 지도 그리기 (GeoJSON 폴리곤)
# ============================================================
def render_geojson_map(geojson_data, is_night, highlight_grids, only_active_area=True):
    if not FOLIUM_AVAILABLE:
        st.error("folium / streamlit-folium 이 설치되지 않았습니다. (pip install folium streamlit-folium)")
        return

    blind_col = "01시_평일_사각지대" if is_night else "13시_평일_사각지대"
    rate_col = "01시_평일평균_접근가능률(%)" if is_night else "13시_평일평균_접근가능률(%)"

    features = []
    for feat in geojson_data.get("features", []):
        props = dict(feat.get("properties", {}))      # 원본이 바뀌지 않도록 복사
        gid = int(props.get("격자_ID", -1))
        within_200m = bool(props.get("전체_AED_200m이내", False))
        is_new = is_night and gid in highlight_grids
        is_blind = bool(props.get(blind_col, True))

        if only_active_area and not (within_200m or is_new or not is_blind):
            continue

        if is_new:
            status, color = "🌟 개선 적용으로 신규 커버됨", "new"
        elif not is_blind:
            status, color = "✅ AED 접근 가능 (200m 이내)", "ok"
        elif within_200m:
            status, color = "🚨 200m 안에 AED는 있지만 이 시간대 미운영", "blind_near"
        else:
            status, color = "⬜ 200m 안에 AED 없음", "blind_far"

        props["상태_설명"] = status
        props["_color"] = color
        props.setdefault(rate_col, 0)
        props.setdefault("가장가까운_AED_거리_m", 0)
        features.append({"type": "Feature", "geometry": feat["geometry"], "properties": props})

    styles = {
        "new":        {"fillColor": "#2563eb", "color": "#1d4ed8", "weight": 1.5, "fillOpacity": 0.85},
        "ok":         {"fillColor": "#10b981", "color": "#059669", "weight": 0.6, "fillOpacity": 0.65},
        "blind_near": {"fillColor": "#ef4444", "color": "#dc2626", "weight": 0.6, "fillOpacity": 0.65},
        "blind_far":  {"fillColor": "#fca5a5", "color": "#f87171", "weight": 0.2, "fillOpacity": 0.25},
    }

    m = folium.Map(location=[37.325, 127.085], zoom_start=12, tiles="CartoDB positron")
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda f: styles[f["properties"]["_color"]],
        tooltip=folium.GeoJsonTooltip(
            fields=["격자_ID", "상태_설명", rate_col, "가장가까운_AED_거리_m"],
            aliases=["격자 ID:", "상태:", "평일 접근가능률(%):", "최근접 AED 거리(m):"],
            localize=True,
        ),
    ).add_to(m)
    st_folium(m, height=540, use_container_width=True, returned_objects=[])


# ============================================================
# 4. Gemini AI 개선안 (상위 3개 시설)
# ============================================================
FACILITY_DETAILS = {
    "아르피아스포츠센터": {
        "rank": 1, "aed_count": 5, "new_grids": 14, "cum_coverage": 20.56,
        "locations": "1층 로비, 2층 로비, 전망타워 1층 로비, 수영장 강사대기실, 테니스장 휴게실 (AED ID: 38, 57, 188, 199, 200)",
        "env": "대규모 공공 체육·문화 복합시설 및 인접 공원 산책로",
    },
    "죽전역": {
        "rank": 2, "aed_count": 1, "new_grids": 13, "cum_coverage": 20.87,
        "locations": "죽전역 역무실 옆 (AED ID: 147)",
        "env": "심야 유동인구가 많은 광역 철도역사 및 상업지구 인접 교통 요충지",
    },
    "포스코이앤씨용인다우CDC": {
        "rank": 3, "aed_count": 3, "new_grids": 13, "cum_coverage": 21.18,
        "locations": "출입컨테이너, 안전교육장, TBM장 현장 내 (AED ID: 196, 197, 198)",
        "env": "보안 게이트로 통제되는 대규모 현장 및 인접 도로 구역",
    },
}


def get_prebuilt_ai_report(facility: str) -> str:
    reports = {
        "아르피아스포츠센터": """
#### 💡 [1순위] 아르피아스포츠센터 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** 시설 내 **5대의 AED**가 설치되어 있지만, 심야(01시) 건물이 닫히면 반경 200m 안의 **14개 격자가 사각지대**가 됩니다.

##### 1. 개선안 제시
* **개선안 A (야간 출입 가능 구역으로 이동):** 5대 중 1대를 24시간 출입 가능한 현관·당직실 쪽으로 이전
* **개선안 B (실외 보관함 설치):** 정문 외부 광장에 실외 보관함을 설치하고 기존 기기 1대를 이전

##### 2. A vs B 비교
| 평가 항목 | 개선안 A | 개선안 B |
| :--- | :--- | :--- |
| **비용·관리 부담** | **매우 낮음** (내부 이전만으로 가능) | **중간** (보관함·조명·전원 설치 비용) |
| **접근성 개선 효과** | **중상** (출입문 개방 여부에 영향) | **매우 높음** (24시간 누구나 접근) |
| **보안성·장비 안전** | **높음** (실내 온도 유지, CCTV) | **중상** (경보음·강화 케이스로 보완) |

##### 3. 최종 추천: **[개선안 B] 실외 보관함 이전 설치**
> 같은 시설에 AED가 5대나 중복 배치되어 있어, **1대만 정문 외부로 옮겨도** 내부 안전 공백 없이 **14개 격자(+0.33%p)의 심야 사각지대를 해소**할 수 있습니다. 예산이 부족하면 개선안 A를 먼저 시행하는 단계적 전략을 권장합니다.
""",
        "죽전역": """
#### 💡 [2순위] 죽전역 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** AED(147번)가 **역무실 옆(역사 내부)**에 있어, 막차 후 셔터가 내려가면 주변 **13개 격자**에서 접근이 막힙니다.

##### 1. 개선안 제시
* **개선안 A (야간 통행 가능한 출입구 바깥쪽으로 이동):** 24시간 보행 가능한 역사 출입구 바깥 벽면으로 이동
* **개선안 B (역사 외부 광장 실외 보관함 설치):** 택시·심야버스 승강장 인근에 독립형 실외 AED 부스 설치

##### 2. A vs B 비교
| 평가 항목 | 개선안 A | 개선안 B |
| :--- | :--- | :--- |
| **비용·관리 부담** | **낮음** (역사 전기·통신망 활용) | **높음** (보도 점용 협의, 부스 설치·점검) |
| **접근성 개선 효과** | **높음** | **매우 높음** (가시성 최고) |
| **보안성·장비 안전** | **매우 높음** (출입구 CCTV, 당직 역무원) | **중간** (심야 훼손 우려, 강화 케이스 필수) |

##### 3. 최종 추천: **[개선안 A] 출입구 바깥쪽 이동**
> 역사에는 심야에도 당직 역무원이 있고 셔터 때문에 물리적 접근만 막혀 있습니다. 고비용 부스를 새로 만들기보다 **셔터 바깥쪽(캐노피 아래) 등 24시간 열린 구역으로 이동**하는 것이 최소 비용으로 **13개 격자(+0.31%p)**를 확보하는 합리적인 방법입니다.
""",
        "포스코이앤씨용인다우CDC": """
#### 💡 [3순위] 포스코이앤씨용인다우CDC 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** **3대의 AED**(출입컨테이너, 안전교육장, TBM장)가 모두 보안 구역 안에 있어, 야간 미운영 시 인근 **13개 격자**가 사각지대로 남습니다.

##### 1. 개선안 제시
* **개선안 A (24시간 경비초소 접점으로 이동):** '출입컨테이너(196번)' 기기를 경비 인력이 상주하는 정문 초소로 이동
* **개선안 B (부지 외부 실외 보관함 설치):** 정문 바깥 공용 보도 옆에 실외 보관함 설치

##### 2. A vs B 비교
| 평가 항목 | 개선안 A | 개선안 B |
| :--- | :--- | :--- |
| **비용·관리 부담** | **매우 낮음** (위치 조정만) | **중상** (전원 공사, 함체 설치) |
| **접근성 개선 효과** | **높음** (경비원 불출, 외부 안내 표지 필요) | **매우 높음** (보안 게이트 통과 불필요) |
| **보안성·장비 안전** | **매우 높음** (24시간 인력 상주) | **중상** (정문 CCTV 반경 내 설치 시 양호) |

##### 3. 최종 추천: **[개선안 A + B 절충형] 정문 경비초소 외벽(도로 방향) 설치**
> 3대가 같은 13개 격자를 중복 커버하므로 **196번 1대만 정문 경비초소 외벽(외부 도로에서 열 수 있는 위치)으로 옮기는 것**이 효과적입니다. 보안 인력의 상시 관리를 받으면서 외부 시민의 심야 접근성도 높여 **13개 격자(+0.31%p)**를 해소할 수 있습니다.
""",
    }
    return reports.get(facility, "선택한 시설의 분석 리포트가 준비 중입니다.")


def call_gemini_api(facility: str, api_key: str):
    info = FACILITY_DETAILS.get(facility, {})
    prompt = f"""
당신은 용인시 수지구 'AED 접근성 개선 시스템'의 AI 정책 컨설턴트입니다.
그리디 알고리즘 분석 결과, 아래 시설이 심야(오전 1시) 사각지대 해소의 핵심 우선순위로 선정되었습니다.

[분석 데이터]
- 시설명: {facility} (그리디 우선순위 {info.get('rank')}위)
- 시설 내 보유 AED 수: {info.get('aed_count')}대 ({info.get('locations')})
- 개선 시 신규 커버되는 사각지대 격자 수: {info.get('new_grids')}개 (100m×100m 격자 기준)
- 개선 후 누적 커버리지: {info.get('cum_coverage')}%
- 주변 환경 특성: {info.get('env')}

[작성 요청]
신규 AED 구매가 아니라 '기존 AED의 재배치 및 야간 개방 전환'을 전제로, 아래 구조의 마크다운 보고서를 작성해 주세요.
1. 맞춤형 개선안 제시
   - 개선안 A: 야간에 접근할 수 있는 출입구(또는 24시간 상주 초소 접점)로 이동
   - 개선안 B: AED를 건물 외부(실외 스마트 보관함)로 이동
2. A vs B 비교 분석 (마크다운 표): ① 예상 비용 및 관리 부담 ② 접근성 개선 효과 ③ 보안성 및 장비 안전
3. 최종 개선안 추천: AED 보유 대수(중복 여부)와 위치 특성을 고려해 A와 B 중 하나를 근거와 함께 추천
"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


def get_secret_key():
    """secrets.toml 이 없어도 에러가 나지 않도록 안전하게 읽습니다."""
    try:
        return st.secrets.get("GEMINI_API_KEY", None)
    except Exception:
        return None


# ============================================================
# 5. 데이터 준비 & 사이드바
# ============================================================
summary_df = get_summary_data()
greedy_df, meta = get_greedy_data()
aed_grid_map = get_aed_grid_mapping()
geojson_data, is_full_geojson = get_geojson_data()

greedy_df = greedy_df.copy()
greedy_df["순위"] = greedy_df["순위"].astype(int)
base_row = greedy_df[greedy_df["순위"] == 0].iloc[0]
last_rank = int(greedy_df["순위"].max())

row_01 = summary_df[summary_df["시간"].astype(str).str.contains("01")].iloc[0]
row_13 = summary_df[summary_df["시간"].astype(str).str.contains("13")].iloc[0]
TOTAL_AED = int(row_01["전체_AED수"])
TOTAL_GRID = int(row_01["전체격자수"])

st.markdown("""
<div class="hero">
  <h1>🚑 AED 접근성 개선 시스템</h1>
  <p>용인시 수지구 시간대별(오전 1시 vs 오후 1시) AED 사각지대 분석 및 그리디 알고리즘·Gemini AI 기반 개선안 도출 대시보드</p>
  <div>
    <span class="badge">📍 대상 지역: 용인시 수지구</span>
    <span class="badge">📐 격자 단위: 100m × 100m (총 4,221개)</span>
    <span class="badge">🎯 AED 유효 반경: 200m (총 214대)</span>
    <span class="badge">🌙 최적화 기준: 평일 오전 1시 평균</span>
  </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 분석 및 지도 설정")
    selected_hour = st.radio(
        "🕒 비교 시간대 선택",
        ["오전 1시 (01:00)", "오후 1시 (13:00)"],
        index=0,
        help="심야(01시)와 주간(13시)의 사각지대 분포를 지도에서 비교합니다.",
    )
    is_night = selected_hour.startswith("오전")

    st.divider()
    st.subheader("🔍 그리디 개선 시뮬레이션")
    sim_step = st.slider(
        "오전 1시 TOP N 시설 개선 적용", min_value=0, max_value=last_rank, value=last_rank,
        help="0단계(개선 전)부터 TOP 5까지. 오전 1시 지도에서 신규 커버 격자가 파란색으로 표시됩니다.",
    )
    only_active = st.checkbox(
        "AED 반경 200m 인접 격자 중심으로 보기", value=True,
        help="AED와 멀리 떨어진 산림·외곽 격자를 숨겨 지도를 빠르고 보기 쉽게 만듭니다.",
    )

    st.divider()
    st.subheader("🤖 Gemini API 설정 (선택)")
    user_api_key = st.text_input(
        "Gemini API Key 입력", type="password", placeholder="AIzaSy...",
        help="키를 입력하면 실시간으로 생성하고, 비워두면 미리 만들어 둔 리포트를 보여줍니다.",
    )

# ---- 시뮬레이션 계산: 선택한 단계까지 개선했을 때 새로 커버되는 격자 ----
blind_01 = set()
if geojson_data is not None:
    blind_01 = {int(f["properties"]["격자_ID"]) for f in geojson_data["features"]
                if f["properties"].get("01시_평일_사각지대", True)}

highlight_grids, opened_aed = set(), 0
for _, r in greedy_df[greedy_df["순위"].between(1, sim_step)].iterrows():
    for token in str(r.get("AED_ID_목록", "")).split(","):
        token = token.strip()
        if token.isdigit():
            opened_aed += 1
            highlight_grids.update(aed_grid_map.get(int(token), []))
if blind_01:  # 원래 사각지대였던 격자만 '신규 커버'로 인정
    highlight_grids &= blind_01

sim_row = greedy_df[greedy_df["순위"] == sim_step].iloc[0]


# ============================================================
# 6. 핵심 지표 (오전 1시 vs 오후 1시)
# ============================================================
st.markdown('<div class="section-title">📊 시간대별 AED 가용률 & 커버리지 비교 (오전 1시 vs 오후 1시)</div>', unsafe_allow_html=True)

rate_gap = float(row_01["AED이용가능률(%)"]) - float(row_13["AED이용가능률(%)"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("🌙 오전 1시 AED 가용률", f"{float(row_01['AED이용가능률(%)']):.2f}%",
          f"이용 가능 {float(row_01['이용가능_AED수']):.0f}대 / {TOTAL_AED}대 (오후 대비 {rate_gap:+.2f}%p)",
          delta_color="inverse")
c2.metric("☀️ 오후 1시 AED 가용률", f"{float(row_13['AED이용가능률(%)']):.2f}%",
          f"이용 가능 {float(row_13['이용가능_AED수']):.1f}대 / {TOTAL_AED}대 (평일 평균)")
c3.metric("🌙 오전 1시 격자 커버리지 (개선 전)", f"{float(row_01['격자접근가능률(%)']):.2f}%",
          f"접근 가능 {int(row_01['접근가능격자수']):,}개 / {TOTAL_GRID:,}개 (사각지대 {int(row_01['사각지대격자수']):,}개)",
          delta_color="off")
gain_pp = float(sim_row["누적_커버리지(%)"]) - float(base_row["누적_커버리지(%)"])
gain_grid = int(float(sim_row["누적_접근가능격자"]) - float(base_row["누적_접근가능격자"]))
c4.metric(f"🚀 오전 1시 TOP {sim_step} 개선 후 커버리지" if sim_step else "🚀 개선 전 커버리지 (슬라이더 0단계)",
          f"{float(sim_row['누적_커버리지(%)']):.2f}%",
          f"{gain_pp:+.2f}%p ({int(float(base_row['누적_접근가능격자'])):,}개 → {int(float(sim_row['누적_접근가능격자'])):,}개, {gain_grid:+d}개 격자)")

with st.expander("📋 오전 1시 vs 오후 1시 가용률·커버리지 상세 비교표 보기"):
    after_avail = float(row_01["이용가능_AED수"]) + opened_aed
    comp_df = pd.DataFrame([
        {"구분": "☀️ 오후 1시 (주간 평일 평균)", "전체 AED 수": f"{TOTAL_AED}대",
         "가용 AED 수": f"{float(row_13['이용가능_AED수']):.1f}대",
         "AED 가용률(%)": f"{float(row_13['AED이용가능률(%)']):.2f}%",
         "접근 가능 격자 (200m 내)": f"{float(row_13['접근가능격자수']):,.1f}개",
         "사각지대 격자": f"{float(row_13['사각지대격자수']):,.1f}개",
         "격자 커버리지(%)": f"{float(row_13['격자접근가능률(%)']):.2f}%"},
        {"구분": "🌙 오전 1시 (심야 개선 전)", "전체 AED 수": f"{TOTAL_AED}대",
         "가용 AED 수": f"{float(row_01['이용가능_AED수']):.0f}대",
         "AED 가용률(%)": f"{float(row_01['AED이용가능률(%)']):.2f}%",
         "접근 가능 격자 (200m 내)": f"{int(row_01['접근가능격자수']):,}개",
         "사각지대 격자": f"{int(row_01['사각지대격자수']):,}개",
         "격자 커버리지(%)": f"{float(row_01['격자접근가능률(%)']):.2f}%"},
        {"구분": f"🌟 오전 1시 (그리디 TOP {sim_step} 개선 후)", "전체 AED 수": f"{TOTAL_AED}대",
         "가용 AED 수": f"{after_avail:.0f}대 (+{opened_aed}대 개방)",
         "AED 가용률(%)": f"{after_avail / TOTAL_AED * 100:.2f}%",
         "접근 가능 격자 (200m 내)": f"{int(float(sim_row['누적_접근가능격자'])):,}개 ({gain_grid:+d}개)",
         "사각지대 격자": f"{TOTAL_GRID - int(float(sim_row['누적_접근가능격자'])):,}개 ({-gain_grid:+d}개)",
         "격자 커버리지(%)": f"{float(sim_row['누적_커버리지(%)']):.2f}% ({gain_pp:+.2f}%p)"},
    ])
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

st.divider()


# ============================================================
# 7. 왼쪽: 지도 / 오른쪽: TOP 5 표 + 누적 커버리지 그래프
# ============================================================
left_col, right_col = st.columns([1.15, 0.85], gap="large")

with left_col:
    st.markdown('<div class="section-title">🗺️ 용인시 수지구 AED 접근성 지도 (시간대별 사각지대 비교)</div>', unsafe_allow_html=True)
    st.markdown(
        f"**현재 표시 기준:** `{selected_hour}`  \n"
        "🟩 접근 가능 &nbsp; 🟥 AED는 근처에 있지만 미운영(사각지대) &nbsp; 🟦 그리디 개선으로 신규 해소 &nbsp; 🩷 200m 안에 AED 없음"
    )
    if geojson_data is None:
        st.warning("`격자_전체_지도용.geojson` 파일을 찾을 수 없습니다. app.py와 같은 폴더(또는 data/)에 넣어주세요.")
    else:
        if not is_full_geojson:
            st.warning("기존 `사각지대_지도용.geojson`에는 오전 1시 접근 가능 격자(854개)가 없어 초록색이 일부만 표시됩니다. "
                       "`격자_전체_지도용.geojson`을 사용해 주세요.")
        render_geojson_map(geojson_data, is_night, highlight_grids, only_active_area=only_active)

with right_col:
    st.markdown('<div class="section-title">🏆 그리디 알고리즘 TOP 5 개선 우선순위</div>', unsafe_allow_html=True)
    st.caption("오전 1시 평일 평균 기준, 기존 시설을 야간 개방했을 때 신규 커버 격자 수가 큰 순서")

    table_df = greedy_df.copy()
    table_df["단계"] = table_df["순위"].apply(lambda x: "개선 전" if x == 0 else f"TOP {x}")
    table_df["신규 커버 격자"] = table_df["평일평균_신규격자"].apply(lambda x: "-" if float(x) == 0 else f"+{int(float(x))}개")
    table_df["누적 접근가능 격자"] = table_df["누적_접근가능격자"].apply(lambda x: f"{int(float(x)):,}개")
    table_df["누적 커버리지"] = table_df["누적_커버리지(%)"].apply(lambda x: f"{float(x):.2f}%")
    table_df["증가폭(%p)"] = table_df["개선전대비_증가(pp)"].apply(lambda x: "-" if float(x) == 0 else f"+{float(x):.2f}%p")
    st.dataframe(
        table_df[["단계", "시설명", "신규 커버 격자", "누적 접근가능 격자", "누적 커버리지", "증가폭(%p)"]],
        use_container_width=True, hide_index=True, height=250,
    )

    st.markdown('<div class="section-title" style="margin-top:0.8rem;">📈 TOP 5 단계별 누적 커버리지 증가 그래프</div>', unsafe_allow_html=True)

    chart_df = greedy_df.copy()
    chart_df["라벨"] = chart_df.apply(
        lambda r: f"개선 전<br>({int(float(r['누적_접근가능격자']))}개)" if r["순위"] == 0 else f"TOP {r['순위']}<br>({str(r['시설명'])[:6]})",
        axis=1,
    )
    y_min = float(chart_df["누적_커버리지(%)"].min()) - 0.5
    y_max = float(chart_df["누적_커버리지(%)"].max()) + 0.6

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=chart_df["라벨"], y=chart_df["평일평균_신규격자"], name="신규 커버 격자 수(개)",
        marker_color="#93c5fd", yaxis="y2", opacity=0.55,
        text=chart_df["평일평균_신규격자"].apply(lambda v: f"+{int(v)}개" if v > 0 else ""),
        textposition="inside",
    ))
    fig.add_trace(go.Scatter(
        x=chart_df["라벨"], y=chart_df["누적_커버리지(%)"], name="누적 커버리지(%)",
        mode="lines+markers+text", line=dict(color="#0d9488", width=3.5),
        marker=dict(size=10, color="#0f766e"),
        text=chart_df["누적_커버리지(%)"].apply(lambda v: f"{v:.2f}%"), textposition="top center",
    ))
    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=25, b=10),
        yaxis=dict(title="누적 커버리지(%)", range=[y_min, y_max], ticksuffix="%", gridcolor="rgba(128,128,128,0.2)"),
        yaxis2=dict(title="신규 격자(개)", overlaying="y", side="right", range=[0, 22], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 8. 하단: Gemini AI 맞춤형 개선안 (상위 3개 시설)
# ============================================================
st.divider()
st.markdown('<div class="section-title">✨ Gemini AI 시설별 맞춤형 개선안 (TOP 3 집중 분석)</div>', unsafe_allow_html=True)
st.write("상위 3개 시설을 선택하면 **개선안 A(출입구 이동) vs 개선안 B(실외 보관함 설치)** 비교와 최종 추천을 볼 수 있습니다.")

selected_facility = st.selectbox(
    "🏢 개선안을 확인할 시설 선택 (TOP 1 ~ 3)",
    list(FACILITY_DETAILS.keys()),
    format_func=lambda x: f"TOP {FACILITY_DETAILS[x]['rank']}위 | {x} (신규 커버 +{FACILITY_DETAILS[x]['new_grids']}개 격자, 보유 AED {FACILITY_DETAILS[x]['aed_count']}대)",
)

info = FACILITY_DETAILS[selected_facility]
k1, k2, k3, k4 = st.columns(4)
k1.metric("그리디 우선순위", f"TOP {info['rank']}위")
k2.metric("시설 내 보유 AED", f"{info['aed_count']}대")
k3.metric("신규 커버 격자 수", f"+{info['new_grids']}개")
k4.metric("적용 후 누적 커버리지", f"{info['cum_coverage']:.2f}%")
st.caption(f"📍 **현재 AED 설치 위치:** {info['locations']}")

api_key_to_use = user_api_key or os.getenv("GEMINI_API_KEY") or get_secret_key()

if st.button("🔄 Gemini API로 실시간 맞춤형 개선안 새로 생성하기", type="primary"):
    if api_key_to_use and GEMINI_AVAILABLE:
        with st.spinner(f"Gemini가 '{selected_facility}' 개선안을 분석 중입니다..."):
            try:
                st.session_state[f"report_{selected_facility}"] = call_gemini_api(selected_facility, api_key_to_use)
                st.success("Gemini API 실시간 분석이 완료되었습니다!")
            except Exception as e:
                st.warning(f"API 호출 중 오류가 발생해 미리 준비된 리포트를 표시합니다. ({e})")
    else:
        st.info("사이드바에 Gemini API Key를 입력하면 실시간 생성이 가능합니다. 지금은 미리 준비된 리포트를 표시합니다.")

# 마크다운 표가 제대로 보이도록 HTML div 대신 st.container를 사용합니다.
with st.container(border=True):
    st.markdown(st.session_state.get(f"report_{selected_facility}", get_prebuilt_ai_report(selected_facility)))
