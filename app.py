import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
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


# ------------------------------------------------------------
# Page setup
# ------------------------------------------------------------
st.set_page_config(
    page_title="AED 접근성 개선 시스템",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .main { background: #f7f9fc; }
    .block-container { padding-top: 1.7rem; padding-bottom: 3rem; }
    .hero {
        padding: 1.5rem 1.7rem; border-radius: 18px;
        background: linear-gradient(115deg, #102a43 0%, #174c68 58%, #167d83 100%);
        color: white; margin-bottom: 1.1rem;
    }
    .hero h1 { color: white; margin: 0 0 .35rem 0; font-size: 2rem; }
    .hero p { color: #d9edf2; margin: 0; }
    .small-note { color: #64748b; font-size: .86rem; }
    .section-title { font-size: 1.2rem; font-weight: 750; color: #183247; }
    .status-pill {
        display:inline-block; padding:.22rem .6rem; border-radius:99px;
        background:#e8f2f5; color:#17616a; font-size:.78rem; font-weight:700;
    }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e6edf2;
        padding: 14px 16px; border-radius: 14px;
    }
    .recommendation {
        background: white; border: 1px solid #e6edf2;
        border-left: 4px solid #167d83; border-radius: 12px;
        padding: 1rem 1.1rem; margin: .55rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------
# Data loading and validation
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
JSON_PATH = DATA_DIR / "greedy_results.json"
CSV_PATH = DATA_DIR / "greedy_top5.csv"

@st.cache_data
def load_greedy_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_greedy_csv(path: str):
    # utf-8-sig first; cp949 fallback for Korean CSVs saved from Excel
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp949")

def get_greedy_data():
    if JSON_PATH.exists():
        payload = load_greedy_json(str(JSON_PATH))
        baseline = payload.get("baseline", {})
        rows = payload.get("top5", [])
        df = pd.DataFrame([baseline] + rows)
        meta = payload.get("meta", {})
        return df, meta
    if CSV_PATH.exists():
        return load_greedy_csv(str(CSV_PATH)), {
            "grid_count": 4221, "aed_count": None, "time": "01:00",
            "weekday_average": True, "radius_m": 200
        }
    return pd.DataFrame(), {}

def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def normalize_grid_columns(df):
    """Accept a grid CSV with coordinates and separate 01:00 / 13:00 status fields."""
    out = df.copy()
    aliases = {
        "lat": ["lat", "latitude", "위도", "중심위도"],
        "lon": ["lon", "lng", "longitude", "경도", "중심경도"],
        "01": ["access_01", "accessible_01", "01시_접근가능", "오전1시_접근가능", "접근가능_01", "status_01"],
        "13": ["access_13", "accessible_13", "13시_접근가능", "오후1시_접근가능", "접근가능_13", "status_13"],
    }
    chosen = {k: find_col(out, v) for k, v in aliases.items()}
    if not chosen["lat"] or not chosen["lon"]:
        return None, "CSV에는 위도·경도 열이 필요합니다. (예: lat, lon 또는 위도, 경도)"
    if not chosen["01"] and not chosen["13"]:
        return None, "시간대별 접근 상태 열이 필요합니다. (예: access_01, access_13)"
    rename = {}
    for k, col in chosen.items():
        if col:
            rename[col] = {"lat": "lat", "lon": "lon", "01": "access_01", "13": "access_13"}[k]
    out = out.rename(columns=rename)
    return out, None

def truthy_access(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float) > 0
    return series.astype(str).str.strip().str.lower().isin(
        ["1", "true", "yes", "y", "접근가능", "가능", "o"]
    )

def render_grid_map(grid_df, hour):
    if not FOLIUM_AVAILABLE:
        st.error("지도 라이브러리가 설치되지 않았습니다. requirements.txt를 설치해주세요.")
        return
    status_col = "access_01" if hour == "01:00" else "access_13"
    if status_col not in grid_df.columns:
        st.info(f"{hour} 격자 데이터가 아직 없습니다. 해당 시간대의 격자별 접근 상태가 포함된 CSV를 추가하면 지도가 표시됩니다.")
        return

    data = grid_df.dropna(subset=["lat", "lon"]).copy()
    data[status_col] = truthy_access(data[status_col])
    if data.empty:
        st.warning("표시할 좌표 데이터가 없습니다.")
        return

    center = [float(data["lat"].mean()), float(data["lon"].mean())]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")
    for _, row in data.iterrows():
        accessible = bool(row[status_col])
        folium.CircleMarker(
            location=[float(row["lat"]), float(row["lon"])],
            radius=3,
            color="#16836f" if accessible else "#d94b4b",
            fill=True,
            fill_color="#16836f" if accessible else "#d94b4b",
            fill_opacity=0.72,
            weight=0.5,
            tooltip="접근 가능" if accessible else "접근 사각지대",
        ).add_to(m)
    st_folium(m, height=510, use_container_width=True, returned_objects=[])

def build_rule_based_advice(facility, rank, new_grids, coverage):
    common = (
        "실제 운영시간·출입 가능 여부·AED 위치 및 안내 표지 상태를 현장에서 확인한 뒤 "
        "관계 기관과 개선 여부를 결정해야 합니다."
    )
    advice = {
        "아르피아스포츠센터": [
            "야간에도 외부 이용자가 접근할 수 있는 출입 동선과 개방 구역을 우선 점검합니다.",
            "AED 설치 위치를 안내하는 표지를 건물 진입부와 주요 동선에 보강합니다.",
            "관리자 부재 시간에도 접근 가능한 위치인지 확인하고, 운영·관리 책임자를 지정합니다.",
        ],
        "죽전역": [
            "역사 운영시간과 심야 출입 동선을 기준으로 AED 접근 가능 구역을 재점검합니다.",
            "개찰구 안팎 및 주요 출입구에서 AED 위치를 쉽게 찾을 수 있도록 안내를 보강합니다.",
            "역무원·시설관리 인력의 점검 절차와 야간 비상 연락 체계를 확인합니다.",
        ],
        "포스코이앤씨용인다우CDC": [
            "사업장 건물의 야간 출입 통제 범위와 외부인의 접근 가능 여부를 확인합니다.",
            "건물 출입구와 공용 동선에 AED 위치 안내를 보강하고 안내 정보를 최신화합니다.",
            "야간 근무자 대상 AED 위치·사용 절차 교육 및 정기 점검 체계를 마련합니다.",
        ],
        "다우DS스퀘어": [
            "야간 출입이 가능한 출입구와 공용공간을 확인해 접근 동선을 명확히 합니다.",
            "외부 이용자도 AED 위치를 찾을 수 있도록 건물 내·외부 안내를 개선합니다.",
            "시설 관리자와 야간 근무자 간 점검 및 비상 대응 역할을 정리합니다.",
        ],
        "고기초등학교": [
            "야간·휴일 학교 출입 통제와 AED 접근 가능 경로를 우선 확인합니다.",
            "정문 등 실제 개방 출입구에서 AED 위치를 안내하는 표지를 보강합니다.",
            "학교 시설 개방 시간과 AED 접근 가능 시간의 차이를 관리하고 관련 정보를 안내합니다.",
        ],
    }
    items = advice.get(facility, [
        "해당 시설의 야간 출입 가능 여부와 AED가 설치된 공간의 개방 범위를 확인합니다.",
        "시설 진입부와 주요 이동 동선에 AED 위치 안내를 보강합니다.",
        "관리자 점검 주기와 비상 상황 시 접근·안내 책임 체계를 점검합니다.",
    ])
    return (
        f"**분석 결과:** 그리디 우선순위 {rank}위이며, 이번 단계에서 신규 접근 가능 격자 "
        f"{int(new_grids):,}개가 추가됩니다. 누적 커버리지는 {coverage:.2f}%입니다.\n\n"
        + "\n".join([f"{i+1}. {x}" for i, x in enumerate(items)])
        + f"\n\n**현장 확인 사항:** {common}"
    )

def generate_gemini_advice(facility, rank, new_grids, coverage):
    api_key = st.secrets.get("GEMINI_API_KEY", None) if hasattr(st, "secrets") else None
    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return None, "Gemini API가 연결되지 않아 시설별 규칙 기반 예시를 표시합니다."
    prompt = f"""
너는 공공 응급의료 접근성 개선을 지원하는 정책 분석 보조자다.
아래 입력만 근거로 한국어 개선안을 작성하라.
시설명: {facility}
그리디 우선순위: {rank}위
신규 접근 가능 격자: {int(new_grids)}개
누적 커버리지: {coverage:.2f}%
분석 시나리오: 기존 AED 위치에서 야간 이용 가능 상태로 전환
요구사항:
- 시설의 실제 구조, 운영시간, 출입 정책을 알고 있다고 가정하지 말 것.
- 확인되지 않은 사실은 단정하지 말고 '현장 확인 필요'로 표시할 것.
- 실행 가능한 개선안 3개와 현장 확인 항목 2개를 제시할 것.
- AED 신규 설치가 아니라 기존 AED의 야간 접근성 개선에 초점을 둘 것.
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text, "Gemini AI가 생성한 개선안입니다. 실제 적용 전 현장 확인이 필요합니다."
    except Exception as exc:
        return None, f"Gemini 호출에 실패했습니다. 규칙 기반 개선안을 대신 표시합니다. ({type(exc).__name__})"


# ------------------------------------------------------------
# Header and sidebar
# ------------------------------------------------------------
st.markdown("""
<div class="hero">
  <h1>❤️ AED 접근성 개선 시스템</h1>
  <p>용인시 수지구의 시간대별 AED 접근 사각지대를 분석하고, 개선 우선순위를 제안합니다.</p>
</div>
""", unsafe_allow_html=True)

greedy_df, meta = get_greedy_data()
if greedy_df.empty:
    st.error("그리디 결과 파일을 찾지 못했습니다. data/greedy_results.json 또는 data/greedy_top5.csv를 확인해주세요.")
    st.stop()

with st.sidebar:
    st.header("분석 설정")
    selected_hour = st.radio("시간대", ["01:00", "13:00"], horizontal=True)
    st.caption("현재 제공된 그리디 결과는 평일 오전 1시 평균 기준입니다.")
    st.divider()
    st.markdown("**분석 조건**")
    st.write("지역: 용인시 수지구")
    st.write("격자: 100m × 100m")
    st.write(f"접근 반경: {meta.get('radius_m', 200)}m")
    st.write(f"전체 격자: {meta.get('grid_count', 4221):,}개")
    st.divider()
    st.markdown("**지도 데이터 추가**")
    grid_upload = st.file_uploader(
        "격자별 접근성 CSV 업로드",
        type=["csv"],
        help="위도·경도와 access_01/access_13 열을 포함한 격자별 데이터",
    )
    st.caption("CSV 예시 열: lat, lon, access_01, access_13")

# ------------------------------------------------------------
# Metrics
# ------------------------------------------------------------
baseline = greedy_df.iloc[0]
last = greedy_df.iloc[-1]
base_cov = float(baseline.get("누적_커버리지(%)", 20.2322))
top5_cov = float(last.get("누적_커버리지(%)", 21.6063))
base_count = int(float(baseline.get("누적_접근가능격자", 854)))
top5_count = int(float(last.get("누적_접근가능격자", 912)))
increase_pp = top5_cov - base_cov

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 분석 격자", f"{int(meta.get('grid_count', 4221)):,}개")
m2.metric("개선 전 접근 가능", f"{base_count:,}개", f"커버리지 {base_cov:.2f}%")
m3.metric("TOP 5 개선 후", f"{top5_count:,}개", f"+{top5_count-base_count:,}개")
m4.metric("커버리지 증가", f"+{increase_pp:.2f}%p", "개선 전 대비")

st.caption("※ 위 지표는 업로드된 greedy_results.json의 오전 1시 평일 평균 결과를 그대로 사용합니다.")

# ------------------------------------------------------------
# Main: map left, greedy ranking right
# ------------------------------------------------------------
left, right = st.columns([1.12, 0.88], gap="large")

with left:
    st.markdown('<div class="section-title">🗺️ AED 접근성 지도</div>', unsafe_allow_html=True)
    st.caption("초록색: AED 접근 가능 격자 / 빨간색: 접근 사각지대")
    if selected_hour == "13:00":
        st.info("오후 1시의 격자별 접근성 원자료가 아직 제공되지 않았습니다. 13시 데이터 업로드 후 지도에 표시할 수 있습니다.")
    if grid_upload is not None:
        try:
            uploaded_df = pd.read_csv(grid_upload, encoding="utf-8-sig")
            normalized, error = normalize_grid_columns(uploaded_df)
            if error:
                st.warning(error)
            else:
                render_grid_map(normalized, selected_hour)
        except Exception as exc:
            st.error(f"지도 CSV를 읽지 못했습니다: {exc}")
    else:
        st.warning(
            "격자별 좌표 데이터가 없어 실제 사각지대 지도는 아직 표시할 수 없습니다. "
            "위도·경도와 시간대별 접근 여부가 포함된 CSV를 왼쪽 메뉴에서 업로드해주세요."
        )
        st.markdown("""
        **필요한 CSV 열 예시**
        ```csv
        lat,lon,access_01,access_13
        37.32,127.09,1,0
        37.33,127.10,0,1
        ```
        `1`은 접근 가능, `0`은 접근 불가능을 의미하도록 준비하면 됩니다.
        """)

with right:
    st.markdown('<div class="section-title">🏆 그리디 알고리즘 TOP 5</div>', unsafe_allow_html=True)
    display_cols = ["순위", "시설명", "평일평균_신규격자", "누적_커버리지(%)"]
    available_cols = [c for c in display_cols if c in greedy_df.columns]
    table_df = greedy_df[available_cols].copy()
    if "순위" in table_df:
        table_df["순위"] = table_df["순위"].astype(int)
    st.dataframe(
        table_df.rename(columns={
            "평일평균_신규격자": "신규 격자",
            "누적_커버리지(%)": "누적 커버리지(%)",
        }),
        use_container_width=True,
        hide_index=True,
        height=265,
    )
    st.caption("동점일 경우 시설명 오름차순으로 정렬된 결과입니다.")

st.divider()

# ------------------------------------------------------------
# Cumulative coverage chart
# ------------------------------------------------------------
st.markdown('<div class="section-title">📈 개선 단계별 누적 커버리지</div>', unsafe_allow_html=True)
chart_df = greedy_df.copy()
if "순위" in chart_df.columns and "누적_커버리지(%)" in chart_df.columns:
    chart_df["단계"] = chart_df.apply(
        lambda r: "개선 전" if int(r["순위"]) == 0 else f"TOP {int(r['순위'])}", axis=1
    )
    fig = px.line(
        chart_df,
        x="단계",
        y="누적_커버리지(%)",
        markers=True,
        text="누적_커버리지(%)",
        hover_data=["시설명", "누적_접근가능격자", "평일평균_신규격자"],
        labels={"누적_커버리지(%)": "누적 커버리지(%)", "단계": "개선 단계"},
    )
    fig.update_traces(line=dict(width=3), marker=dict(size=10), texttemplate="%{text:.2f}%", textposition="top center")
    fig.update_layout(
        height=360, margin=dict(l=15, r=15, t=35, b=15),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(range=[max(0, base_cov - 1), top5_cov + 1], ticksuffix="%"),
        xaxis=dict(title=None),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.success(
        f"TOP 5 개선 시 접근 가능 격자는 {base_count:,}개에서 {top5_count:,}개로 증가하고, "
        f"커버리지는 {base_cov:.2f}%에서 {top5_cov:.2f}%로 {increase_pp:.2f}%p 상승합니다."
    )

st.divider()

# ------------------------------------------------------------
# Gemini / facility-specific recommendations
# ------------------------------------------------------------
st.markdown('<div class="section-title">✨ Gemini AI 맞춤형 개선안</div>', unsafe_allow_html=True)
st.write("그리디 알고리즘 상위 3개 시설을 중심으로 기존 AED의 야간 접근성을 개선하는 방안을 제안합니다.")

top3 = greedy_df[greedy_df["순위"].astype(int).between(1, 3)].copy()
if top3.empty:
    st.warning("TOP 3 시설 정보가 결과 파일에 없습니다.")
else:
    facility_options = top3["시설명"].tolist()
    selected_facility = st.selectbox("개선안을 확인할 시설 선택", facility_options)
    selected_row = top3[top3["시설명"] == selected_facility].iloc[0]
    rank = int(selected_row["순위"])
    new_grids = float(selected_row["평일평균_신규격자"])
    coverage = float(selected_row["누적_커버리지(%)"])

    c1, c2, c3 = st.columns(3)
    c1.metric("우선순위", f"{rank}위")
    c2.metric("신규 접근 가능 격자", f"{new_grids:,.0f}개")
    c3.metric("누적 커버리지", f"{coverage:.2f}%")

    if st.button("선택한 시설의 AI 개선안 생성", type="primary"):
        with st.spinner("개선안을 생성하고 있습니다..."):
            ai_text, status = generate_gemini_advice(selected_facility, rank, new_grids, coverage)
            st.session_state["ai_advice"] = ai_text
            st.session_state["ai_status"] = status
            st.session_state["ai_facility"] = selected_facility

    if st.session_state.get("ai_facility") == selected_facility and st.session_state.get("ai_advice"):
        st.info(st.session_state.get("ai_status", ""))
        st.markdown(st.session_state["ai_advice"])
    else:
        st.markdown(
            build_rule_based_advice(selected_facility, rank, new_grids, coverage),
            unsafe_allow_html=False,
        )
        st.caption("위 내용은 API 연결 전 미리보기용 규칙 기반 예시입니다. Gemini 생성 결과가 아닙니다.")

st.divider()
with st.expander("데이터 및 해석상 유의사항"):
    st.markdown("""
    - 그리디 결과는 제공된 `greedy_results.json` 및 `greedy_top5.csv`의 값을 사용합니다.
    - 현재 결과의 기준은 **오전 1시 평일 평균**, 전체 4,221개 격자, AED 접근 반경 200m입니다.
    - 제공된 결과에서 TOP 5 누적 커버리지는 21.6063%이며, 개선 전 대비 증가량은 약 1.3741%p입니다.
    - 현재 제공된 파일에는 오후 1시 결과 및 격자별 좌표가 없습니다. 따라서 해당 시간대 지도·가용률을 임의로 계산하지 않습니다.
    - Gemini API 키가 없거나 호출에 실패하면 규칙 기반 개선안 미리보기를 표시합니다.
    - 이 웹사이트는 분석·정책 검토를 위한 시제품이며, 실제 AED 접근 가능 여부는 시설 운영시간·출입 통제·장비 상태를 현장에서 확인해야 합니다.
    """)
st.caption("AED 접근성 개선 시스템 | 용인시 수지구 | 분석 시제품")
