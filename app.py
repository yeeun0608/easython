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


# ------------------------------------------------------------
# 1. 페이지 기본 설정 & 스타일
# ------------------------------------------------------------
st.set_page_config(
    page_title="AED 접근성 개선 시스템",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .main { background: #f8fafc; }
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
    .section-title {
        font-size: 1.25rem; font-weight: 700; color: #0f172a;
        margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.4rem;
    }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e2e8f0;
        padding: 14px 18px; border-radius: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .ai-box {
        background: white; border: 1px solid #cbd5e1;
        border-left: 5px solid #0d9488; border-radius: 12px;
        padding: 1.4rem 1.6rem; margin-top: 0.8rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------
# 2. 데이터 파일 탐색 및 로드 함수
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parent

def find_file(filename: str):
    """현재 폴더 또는 data/ 하위 폴더에서 파일을 자동으로 찾습니다."""
    candidates = [
        ROOT / filename,
        ROOT / "data" / filename,
        Path(filename),
        Path("data") / filename,
    ]
    for p in candidates:
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
        {"시간": "01시", "전체_AED수": 214, "이용가능_AED수": 170.0, "AED이용가능률(%)": 79.44, "전체격자수": 4221, "접근가능격자수": 854.0, "사각지대격자수": 3367.0, "격자접근가능률(%)": 20.23},
        {"시간": "13시", "전체_AED수": 214, "이용가능_AED수": 211.4, "AED이용가능률(%)": 98.79, "전체격자수": 4221, "접근가능격자수": 962.8, "사각지대격자수": 3258.2, "격자접근가능률(%)": 22.81},
    ])

@st.cache_data
def get_greedy_data():
    p_json = find_file("greedy_results.json")
    if p_json:
        payload = load_json_safe(str(p_json))
        baseline = payload.get("baseline", {})
        rows = payload.get("top5", [])
        return pd.DataFrame([baseline] + rows), payload.get("meta", {})

    p_csv = find_file("greedy_top5.csv")
    if p_csv:
        df = load_csv_safe(str(p_csv))
        return df, {"grid_count": 4221, "aed_count": 214, "time": "01:00", "radius_m": 200}

    default_rows = [
        {"순위": 0, "시설명": "개선 전", "평일평균_신규격자": 0.0, "누적_접근가능격자": 854.0, "누적_커버리지(%)": 20.2322, "개선전대비_증가(pp)": 0.0000, "AED_ID_목록": ""},
        {"순위": 1, "시설명": "아르피아스포츠센터", "평일평균_신규격자": 14.0, "누적_접근가능격자": 868.0, "누적_커버리지(%)": 20.5638, "개선전대비_증가(pp)": 0.3317, "AED_ID_목록": "38,57,188,199,200"},
        {"순위": 2, "시설명": "죽전역", "평일평균_신규격자": 13.0, "누적_접근가능격자": 881.0, "누적_커버리지(%)": 20.8718, "개선전대비_증가(pp)": 0.6397, "AED_ID_목록": "147"},
        {"순위": 3, "시설명": "포스코이앤씨용인다우CDC", "평일평균_신규격자": 13.0, "누적_접근가능격자": 894.0, "누적_커버리지(%)": 21.1798, "개선전대비_증가(pp)": 0.9476, "AED_ID_목록": "196,197,198"},
        {"순위": 4, "시설명": "다우DS스퀘어", "평일평균_신규격자": 10.0, "누적_접근가능격자": 904.0, "누적_커버리지(%)": 21.4167, "개선전대비_증가(pp)": 1.1846, "AED_ID_목록": "214"},
        {"순위": 5, "시설명": "고기초등학교", "평일평균_신규격자": 8.0, "누적_접근가능격자": 912.0, "누적_커버리지(%)": 21.6063, "개선전대비_증가(pp)": 1.3741, "AED_ID_목록": "50"},
    ]
    return pd.DataFrame(default_rows), {"grid_count": 4221, "aed_count": 214, "time": "01:00", "radius_m": 200}

@st.cache_data
def get_aed_grid_mapping():
    """AED_ID별로 커버하는 격자_ID 리스트를 딕셔너리로 반환합니다."""
    p = find_file("AED별_커버_격자목록.json")
    mapping = {}
    if p:
        data = load_json_safe(str(p))
        for item in data:
            mapping[int(item["AED_ID"])] = item.get("커버_격자_ID_목록", [])
    else:
        mapping = {
            38: [3674, 3675, 3690, 3691, 3692, 3693, 3706, 3707, 3708, 3709, 3721, 3722, 3723, 3724],
            147: [3687, 3688, 3702, 3703, 3704, 3705, 3717, 3718, 3719, 3720, 3731, 3732, 3733],
            196: [4084, 4085, 4100, 4101, 4102, 4103, 4116, 4117, 4118, 4119, 4133, 4134, 4135],
            214: [4134, 4135, 4136, 4151, 4152, 4153, 4154, 4168, 4169, 4170, 4171, 4186],
            50: [1863, 1864, 1865, 1935, 1936, 2006, 2007, 2078],
        }
    return mapping

@st.cache_data
def get_geojson_data():
    p = find_file("사각지대_지도용.geojson")
    if p:
        return load_json_safe(str(p))
    return None


# ------------------------------------------------------------
# 3. 지도 렌더링 함수 (GeoJSON 폴리곤 기반)
# ------------------------------------------------------------
def render_geojson_map(geojson_data, selected_hour, highlight_grids, only_active_area=True):
    if not FOLIUM_AVAILABLE:
        st.error("folium 또는 streamlit-folium 라이브러리가 설치되지 않았습니다.")
        return

    m = folium.Map(location=[37.325, 127.085], zoom_start=12, tiles="CartoDB positron")

    blind_col = "01시_평일_사각지대" if selected_hour == "오전 1시 (01:00)" else "13시_평일_사각지대"
    rate_col = "01시_평일평균_접근가능률(%)" if selected_hour == "오전 1시 (01:00)" else "13시_평일평균_접근가능률(%)"

    filtered_features = []
    for feat in geojson_data.get("features", []):
        props = feat.get("properties", {})
        gid = int(props.get("격자_ID", -1))
        within_200m = bool(props.get("전체_AED_200m이내", False))
        is_highlighted = gid in highlight_grids

        if only_active_area and not (within_200m or is_highlighted):
            continue

        is_blind = bool(props.get(blind_col, True))
        if is_highlighted and selected_hour == "오전 1시 (01:00)":
            props["상태_설명"] = "🌟 TOP 우선순위 개선으로 신규 커버됨"
        elif not is_blind:
            props["상태_설명"] = "✅ AED 접근 가능 (200m 이내)"
        else:
            props["상태_설명"] = "🚨 시간대별 접근 사각지대 (AED 미운영)"

        filtered_features.append(feat)

    subset_geojson = {"type": "FeatureCollection", "features": filtered_features}

    def style_function(feature):
        props = feature["properties"]
        gid = int(props.get("격자_ID", -1))
        is_blind = bool(props.get(blind_col, True))

        if selected_hour == "오전 1시 (01:00)" and gid in highlight_grids:
            return {
                "fillColor": "#2563eb",
                "color": "#1d4ed8",
                "weight": 1.5,
                "fillOpacity": 0.85,
            }
        if not is_blind:
            return {
                "fillColor": "#10b981",
                "color": "#059669",
                "weight": 0.6,
                "fillOpacity": 0.65,
            }
        within_200m = bool(props.get("전체_AED_200m이내", False))
        return {
            "fillColor": "#ef4444" if within_200m else "#fca5a5",
            "color": "#dc2626" if within_200m else "#f87171",
            "weight": 0.6 if within_200m else 0.2,
            "fillOpacity": 0.65 if within_200m else 0.25,
        }

    folium.GeoJson(
        subset_geojson,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["격자_ID", "상태_설명", rate_col, "가장가까운_AED_거리_m"],
            aliases=["격자 ID:", "상태:", "평일 접근가능률(%):", "최근접 AED 거리(m):"],
            localize=True,
        ),
    ).add_to(m)

    st_folium(m, height=540, use_container_width=True, returned_objects=[])


# ------------------------------------------------------------
# 4. Gemini AI 맞춤형 개선안 (상위 3개 시설 A vs B 비교 및 추천)
# ------------------------------------------------------------
FACILITY_DETAILS = {
    "아르피아스포츠센터": {
        "rank": 1,
        "aed_count": 5,
        "locations": "1층 로비, 2층 로비, 전망타워 1층 로비, 수영장 강사대기실, 테니스장 휴게실 (AED ID: 38, 57, 188, 199, 200)",
        "new_grids": 14,
        "cum_coverage": 20.56,
        "env": "대규모 공공 체육·문화 복합시설 및 인접 수지 레스피아 공원 산책로",
    },
    "죽전역": {
        "rank": 2,
        "aed_count": 1,
        "locations": "죽전역 역무실 옆 (AED ID: 147)",
        "new_grids": 13,
        "cum_coverage": 20.87,
        "env": "심야 유동인구가 많은 광역 철도역사 및 백화점·상업지구 인접 교통 요충지",
    },
    "포스코이앤씨용인다우CDC": {
        "rank": 3,
        "aed_count": 3,
        "locations": "출입컨테이너, 안전교육장, TBM장 현장 내 (AED ID: 196, 197, 198)",
        "new_grids": 13,
        "cum_coverage": 21.18,
        "env": "보안 게이트로 통제되는 대규모 데이터센터 현장 및 인접 도로 구역",
    },
}

def get_prebuilt_ai_report(facility: str) -> str:
    """상위 3개 시설 맞춤형 A vs B 비교 및 최종 추천 리포트"""
    reports = {
        "아르피아스포츠센터": """
#### 💡 [1순위] 아르피아스포츠센터 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** 시설 내 무려 **5대의 AED**(1·2층 로비, 전망타워, 수영장, 테니스장)가 집중 설치되어 있으나, 심야 시간(01시) 건물 폐쇄로 인해 반경 200m 내 **14개 격자가 동시에 사각지대**로 전환됩니다.

---

##### 1. 맞춤형 개선 대안 제시
* **개선안 A (야간 개방 출입구/무인 안내소 인접 이동):** 실내 깊숙이 위치한 AED(수영장 강사대기실 등) 중 1대를 24시간 출입 가능한 1층 현관 풍향실 또는 당직실 창가 쪽으로 재배치
* **개선안 B (실외 스마트 보관함 신규 설치):** 야간 산책객과 인근 주민이 즉시 접근할 수 있도록 아르피아스포츠센터 1층 정문 외부 광장에 항온·항습 실외 보관함 설치 후 기존 기기 1대 이전

##### 2. 개선안 다각도 비교 분석 (A vs B)
| 평가 항목 | 개선안 A (야간 개방 출입구로 이동) | 개선안 B (실외 보관함으로 이동) |
| :--- | :--- | :--- |
| **예상 비용 및 관리 부담** | **매우 낮음** (내부 벽면 브래킷 이전 설치만으로 즉시 가능, 별도 전력 공사 불필요) | **중간** (외부용 항온·항습 스마트 보관함 구매 및 야간 조명·전원 연결 비용 발생) |
| **접근성 개선 효과** | **중상** (건물 출입문 개방 여부에 영향받으나, 당직자 호출 인터폰 연동 시 해소 가능) | **매우 높음** (심야 공원 이용객 및 주변 도로에서 잠금장치 없이 24시간 즉각 접근 가능) |
| **보안성 및 장비 안전** | **높음** (실내 온도 유지 및 기존 로비 CCTV 사각지대 없음) | **중상** (도난 방지 경보음 및 비상시 파손 개방형 케이스 적용으로 보안 보완 가능) |

##### 3. 최종 개선안 추천: **[개선안 B] 실외 스마트 보관함 이전 설치 권장**
> **추천 근거:** 아르피아스포츠센터는 동일 위치에 **AED가 5대나 중복 배치**되어 있어, 1층 로비나 테니스장 휴게실 기기 중 **단 1대만 정문 외부(실외 보관함)로 이동**하더라도 내부 안전 공백 없이 **수지구 내 가장 넓은 14개 격자(+0.33%p)의 심야 사각지대를 단번에 해소**할 수 있습니다. 예산 제약 시 단기적으로는 **개선안 A(1층 외부 직결 로비 이동)**를 즉시 시행하는 단계적 전략을 추천합니다.
""",
        "죽전역": """
#### 💡 [2순위] 죽전역 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** 죽전역은 유동인구가 밀집하는 핵심 거점이지만, AED(147번)가 **역무실 옆(역사 내부)**에 위치해 막차 종료 후 셔터가 내려가는 심야 시간(01시)에는 주변 **13개 격자**에서 접근이 전면 차단됩니다.

---

##### 1. 맞춤형 개선 대안 제시
* **개선안 A (역사 야간 개방 통로/무인 환승 구역으로 이동):** 역무실 옆 기기를 24시간 보행 통행이 허용되는 역사 1층 주 출입구 게이트 바깥쪽 벽면으로 이동
* **개선안 B (역사 외부 광장/버스환승센터 실외 보관함 설치):** 죽전역 출입구 외부 택시·심야버스 승강장 인근에 독립형 실외 AED 부스 설치

##### 2. 개선안 다각도 비교 분석 (A vs B)
| 평가 항목 | 개선안 A (야간 개방 출입구로 이동) | 개선안 B (실외 보관함으로 이동) |
| :--- | :--- | :--- |
| **예상 비용 및 관리 부담** | **낮음** (역사 내부 전기·통신망 그대로 활용, 역무원의 일상 점검 동선 유지) | **높음** (보도 점용 협의 및 실외 내구성 부스 설치, 외부 노출에 따른 정기 점검 부담) |
| **접근성 개선 효과** | **높음** (셔터 바깥쪽 출입구 벽면에 위치하여 심야 보행자 및 운전자 즉시 접근 가능) | **매우 높음** (가시성이 가장 뛰어나며 심야 대중교통 이용객 누구나 즉시 발견 가능) |
| **보안성 및 장비 안전** | **매우 높음** (역사 출입구 고화질 CCTV 상시 녹화 및 야간 당직 역무원 즉각 대응 가능) | **중간** (심야 시간대 취객 등에 의한 훼손 우려가 있어 강화형 스마트 케이스 필수) |

##### 3. 최종 개선안 추천: **[개선안 A] 야간 개방 출입구(셔터 외부 맞닿은 구역)로 이동 추천**
> **추천 근거:** 철도역사 특성상 심야에도 당직 역무원이 상주하지만 셔터로 인해 물리적 접근만 막혀 있는 상태입니다. 따라서 별도의 고비용 실외 부스를 신설하기보다, **출입구 셔터 바깥쪽 반실내(캐노피 하단) 구역이나 24시간 개방 보행 통로로 AED를 소폭 이동(개선안 A)**하는 것이 **최소 비용으로 13개 격자(+0.31%p) 커버리지를 확보**하고 역무원의 관리 효율성까지 지키는 가장 합리적인 솔루션입니다.
""",
        "포스코이앤씨용인다우CDC": """
#### 💡 [3순위] 포스코이앤씨용인다우CDC 맞춤형 야간 접근성 개선 리포트
* **현재 문제점:** 총 **3대의 AED**(출입컨테이너, 안전교육장, TBM장)가 보유되어 있으나 모두 현장 보안 구역 내부에 위치하여, 평일 야간(01시) 미운영 시 인근 **13개 격자**가 사각지대로 남게 됩니다.

---

##### 1. 맞춤형 개선 대안 제시
* **개선안 A (정문 24시간 보안초소/출입 게이트 접점 이동):** 현장 내 3대 중 '출입컨테이너(196번)' 기기를 24시간 경비 인력이 상주하는 정문 외부 접견실 또는 경비초소 외벽 창가로 이동
* **개선안 B (부지 경계선 외부 도로변 실외 보관함 설치):** 일반 시민과 야간 통행 차량이 보안 절차 없이 바로 사용할 수 있도록 정문 바깥쪽 공용 보도 옆에 실외 보관함 설치

##### 2. 개선안 다각도 비교 분석 (A vs B)
| 평가 항목 | 개선안 A (야간 상주 보안초소 접점 이동) | 개선안 B (부지 외부 실외 보관함 설치) |
| :--- | :--- | :--- |
| **예상 비용 및 관리 부담** | **매우 낮음** (기존 출입컨테이너 인접 초소로 위치만 조정, 보안 인력이 상시 관리) | **중상** (외부 전원 인입 공사 및 실외형 함체 설치 비용 발생) |
| **접근성 개선 효과** | **높음** (야간 상주 경비원을 통해 즉시 불출 가능하며 외부 안내 표지판 부착 시 접근 용이) | **매우 높음** (보안 게이트 통과나 경비원 호출 없이 24시간 즉각 개방 가능) |
| **보안성 및 장비 안전** | **매우 높음** (24시간 보안 인력 상주 구역으로 도난·파손 위험 제로) | **중상** (정문 보안 CCTV 감시 반경 내에 설치 시 높은 보안성 유지 가능) |

##### 3. 최종 개선안 추천: **[개선안 A + B 절충형] 정문 경비초소 외벽(도로 방향) 설치 추천**
> **추천 근거:** 해당 시설은 **3대의 AED가 동일한 13개 격자를 중복 커버**하고 있어, 내부 안전교육장·TBM장 기기 2대는 그대로 두고 **'출입컨테이너(196번)' 1대만 정문 경비초소 외벽(외부 도로에서 바로 열 수 있는 위치)으로 재배치**하는 것이 가장 효과적입니다. 이렇게 하면 보안 인력의 24시간 관리를 받으면서도 외부 시민의 심야 접근성을 100% 보장하여 **13개 격자(+0.31%p)를 완벽히 방어**할 수 있습니다.
""",
    }
    return reports.get(facility, "선택한 시설의 상세 분석 리포트가 준비 중입니다.")


def call_gemini_api(facility: str, api_key: str):
    """Gemini API를 실시간 호출하여 A vs B 비교 및 최종 추천 리포트를 생성합니다."""
    info = FACILITY_DETAILS.get(facility, {})
    prompt = f"""
당신은 용인시 수지구 'AED 접근성 개선 시스템'의 AI 정책 컨설턴트입니다.
그리디 알고리즘 분석 결과, 아래 시설이 심야 시간(오전 1시) 사각지대 해소를 위한 핵심 우선순위로 선정되었습니다.

[분석 데이터]
- 시설명: {facility} (그리디 우선순위 {info.get('rank')}위)
- 시설 내 보유 AED 수: {info.get('aed_count')}대 ({info.get('locations')})
- 개선 시 신규 커버되는 사각지대 격자 수: {info.get('new_grids')}개 (100m×100m 격자 기준)
- 개선 후 누적 커버리지: {info.get('cum_coverage')}%
- 주변 환경 특성: {info.get('env')}

[작성 요청사항]
신규 AED 구매가 아니라 '기존 AED의 재배치 및 야간 개방 전환'을 전제로 아래 구조에 맞춰 깔끔한 마크다운 보고서를 작성해 주세요.
1. 맞춤형 개선안 제시:
   - 개선안 A: 야간에 접근할 수 있는 출입구(또는 24시간 상주 초소 접점)로 이동
   - 개선안 B: AED를 건물 외부(실외 스마트 보관함)로 이동
2. A vs B 다각도 비교 분석 (마크다운 표 활용):
   - 비교 기준: ① 예상 비용 및 관리 부담, ② 접근성 개선 효과, ③ 보안성 및 장비 안전
3. 최종 개선안 추천:
   - 해당 시설의 AED 보유 대수(중복 여부)와 위치 특성을 고려해 A와 B 중 가장 합리적인 최종안을 구체적 근거와 함께 추천해 주세요.
"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text


# ------------------------------------------------------------
# 5. 메인 화면 구성 (헤더 & 사이드바)
# ------------------------------------------------------------
summary_df = get_summary_data()
greedy_df, meta = get_greedy_data()
aed_grid_map = get_aed_grid_mapping()
geojson_data = get_geojson_data()

st.markdown("""
<div class="hero">
  <h1>🚑 AED 접근성 개선 시스템</h1>
  <p>용인시 수지구 시간대별(오전 1시 vs 오후 1시) AED 사각지대 분석 및 그리디 알고리즘·Gemini AI 기반 최적 개선안 도출 대시보드</p>
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
        help="오전 1시(심야)와 오후 1시(주간)의 가용률·커버리지 및 사각지대 분포를 비교합니다.",
    )

    st.divider()
    st.subheader("🔍 그리디 개선 시뮬레이션")
    sim_step = st.slider(
        "오전 1시 TOP N 시설 개선 적용",
        min_value=0,
        max_value=5,
        value=5,
        help="0단계(개선 전)부터 TOP 5 시설까지 야간 개방 전환 시 지도에 파란색으로 신규 커버 격자가 표시됩니다.",
    )
    only_active = st.checkbox(
        "AED 반경 200m 인접 격자 중심으로 보기",
        value=True,
        help="체크 시 산림·외곽 등 AED와 무관한 격자를 제외하여 속도와 시인성을 높입니다.",
    )

    st.divider()
    st.subheader("🤖 Gemini API 설정 (선택)")
    user_api_key = st.text_input(
        "Gemini API Key 입력",
        type="password",
        placeholder="AIzaSy...",
        help="키를 입력하면 실시간 Gemini API를 호출하며, 비워두면 사전 생성된 A vs B 분석 리포트를 즉시 표시합니다.",
    )


# ------------------------------------------------------------
# 6. 상단 핵심 지표: 오전 1시 vs 오후 1시 가용률 & 커버리지 비교
# ------------------------------------------------------------
st.markdown('<div class="section-title">📊 시간대별 AED 가용률 & 커버리지 비교 (오전 1시 vs 오후 1시)</div>', unsafe_allow_html=True)

row_01 = summary_df[summary_df["시간"].astype(str).str.contains("01")].iloc[0]
row_13 = summary_df[summary_df["시간"].astype(str).str.contains("13")].iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "🌙 오전 1시 AED 가용률",
    f"{float(row_01['AED이용가능률(%)']):.2f}%",
    f"이용 가능 {int(row_01['이용가능_AED수'])}대 / 214대 (오후 대비 -19.35%p)",
    delta_color="inverse",
)
c2.metric(
    "☀️ 오후 1시 AED 가용률",
    f"{float(row_13['AED이용가능률(%)']):.2f}%",
    f"이용 가능 {float(row_13['이용가능_AED수']):.1f}대 / 214대 (주간 평일 평균)",
)
c3.metric(
    "🌙 오전 1시 격자 커버리지 (개선 전)",
    f"{float(row_01['격자접근가능률(%)']):.2f}%",
    f"접근 가능 {int(row_01['접근가능격자수']):,}개 / 4,221개 (사각지대 3,367개)",
    delta_color="off",
)
c4.metric(
    "🚀 오전 1시 TOP 5 개선 후 커버리지",
    "21.61%",
    "+1.37%p 증가 (854개 → 912개, +58개 격자 해소)",
)

with st.expander("📋 오전 1시 vs 오후 1시 가용률·커버리지 상세 비교표 보기"):
    comp_df = pd.DataFrame([
        {
            "구분": "☀️ 오후 1시 (주간 평일 평균)",
            "전체 AED 수": "214대",
            "가용 AED 수": f"{float(row_13['이용가능_AED수']):.1f}대",
            "AED 가용률(%)": f"{float(row_13['AED이용가능률(%)']):.2f}%",
            "접근 가능 격자 (200m 내)": f"{float(row_13['접근가능격자수']):,.1f}개",
            "사각지대 격자": f"{float(row_13['사각지대격자수']):,.1f}개",
            "격자 커버리지(%)": f"{float(row_13['격자접근가능률(%)']):.2f}%",
        },
        {
            "구분": "🌙 오전 1시 (심야 개선 전)",
            "전체 AED 수": "214대",
            "가용 AED 수": f"{int(row_01['이용가능_AED수'])}대",
            "AED 가용률(%)": f"{float(row_01['AED이용가능률(%)']):.2f}%",
            "접근 가능 격자 (200m 내)": "854개",
            "사각지대 격자": "3,367개",
            "격자 커버리지(%)": "20.23%",
        },
        {
            "구분": "🌟 오전 1시 (그리디 TOP 5 개선 후)",
            "전체 AED 수": "214대",
            "가용 AED 수": "181대 (+11대 개방 효과)",
            "AED 가용률(%)": "84.58% (+5.14%p)",
            "접근 가능 격자 (200m 내)": "912개 (+58개)",
            "사각지대 격자": "3,309개 (-58개)",
            "격자 커버리지(%)": "21.61% (+1.37%p)",
        },
    ])
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

st.divider()


# ------------------------------------------------------------
# 7. 메인 대시보드: 왼쪽(지도) / 오른쪽(그리디 TOP 5 + 누적 커버리지 그래프)
# ------------------------------------------------------------
highlight_grids = set()
if sim_step > 0:
    active_rows = greedy_df[greedy_df["순위"].astype(int).between(1, sim_step)]
    for _, r in active_rows.iterrows():
        aed_ids_str = str(r.get("AED_ID_목록", ""))
        for token in aed_ids_str.split(","):
            token = token.strip()
            if token.isdigit():
                highlight_grids.update(aed_grid_map.get(int(token), []))

left_col, right_col = st.columns([1.15, 0.85], gap="large")

with left_col:
    st.markdown('<div class="section-title">🗺️ 용인시 수지구 AED 접근성 지도 (시간대별 사각지대 비교)</div>', unsafe_allow_html=True)
    st.markdown(
        f"**현재 표시 기준:** `{selected_hour}` | "
        "🟩 **초록색**: 접근 가능 격자 &nbsp; 🟥 **빨간색**: 접근 사각지대 &nbsp; 🟦 **파란색**: 그리디 TOP 우선순위 신규 해소 격자"
    )
    if geojson_data is not None:
        render_geojson_map(geojson_data, selected_hour, highlight_grids, only_active_area=only_active)
    else:
        st.warning("`사각지대_지도용.geojson` 파일을 찾을 수 없습니다. 폴더에 파일을 넣어주세요.")

with right_col:
    st.markdown('<div class="section-title">🏆 그리디 알고리즘 TOP 5 개선 우선순위</div>', unsafe_allow_html=True)
    st.caption("오전 1시 평일 평균 기준, 기존 시설 야간 개방 시 신규 커버 격자 수가 가장 큰 순서")

    table_df = greedy_df.copy()
    table_df["순위_표시"] = table_df["순위"].apply(lambda x: "개선 전" if int(x) == 0 else f"TOP {int(x)}")
    table_df["신규 커버 격자"] = table_df["평일평균_신규격자"].apply(lambda x: "-" if float(x) == 0 else f"+{int(float(x))}개")
    table_df["누적 접근가능 격자"] = table_df["누적_접근가능격자"].apply(lambda x: f"{int(float(x)):,}개")
    table_df["누적 커버리지"] = table_df["누적_커버리지(%)"].apply(lambda x: f"{float(x):.2f}%")
    table_df["증가폭(%p)"] = table_df["개선전대비_증가(pp)"].apply(lambda x: "-" if float(x) == 0 else f"+{float(x):.2f}%p")

    st.dataframe(
        table_df[["순위_표시", "시설명", "신규 커버 격자", "누적 접근가능 격자", "누적 커버리지", "증가폭(%p)"]].rename(
            columns={"순위_표시": "단계"}
        ),
        use_container_width=True,
        hide_index=True,
        height=250,
    )

    st.markdown('<div class="section-title" style="margin-top:0.8rem;">📈 TOP 5 단계별 누적 커버리지 증가 그래프</div>', unsafe_allow_html=True)

    chart_df = greedy_df.copy()
    chart_df["단계"] = chart_df.apply(
        lambda r: "개선 전\n(854개)" if int(r["순위"]) == 0 else f"TOP {int(r['순위'])}\n({r['시설명'][:6]})",
        axis=1,
    )

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_df["단계"],
            y=chart_df["평일평균_신규격자"],
            name="신규 커버 격자 수(개)",
            marker_color="#93c5fd",
            yaxis="y2",
            opacity=0.55,
            text=chart_df["평일평균_신규격자"].apply(lambda v: f"+{int(v)}개" if v > 0 else ""),
            textposition="inside",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df["단계"],
            y=chart_df["누적_커버리지(%)"],
            name="누적 커버리지(%)",
            mode="lines+markers+text",
            line=dict(color="#0d9488", width=3.5),
            marker=dict(size=10, color="#0f766e"),
            text=chart_df["누적_커버리지(%)"].apply(lambda v: f"{v:.2f}%"),
            textposition="top center",
        )
    )

    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=25, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(
            title="누적 커버리지(%)",
            range=[19.8, 22.1],
            ticksuffix="%",
            gridcolor="#f1f5f9",
        ),
        yaxis2=dict(
            title="신규 격자(개)",
            overlaying="y",
            side="right",
            range=[0, 22],
            showgrid=False,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------
# 8. 하단: Gemini AI 맞춤형 개선안 (상위 3개 시설 중심)
# ------------------------------------------------------------
st.divider()
st.markdown('<div class="section-title">✨ Gemini AI 시설별 맞춤형 개선안 (TOP 3 우선순위 집중 분석)</div>', unsafe_allow_html=True)
st.write(
    "그리디 알고리즘으로 도출된 **상위 3개 핵심 시설(아르피아스포츠센터, 죽전역, 포스코이앤씨용인다우CDC)**을 선택하면, "
    "**대안 A(출입구 이동) vs 대안 B(실외 보관함 설치)** 정성 비교 및 최종 추천 솔루션을 확인할 수 있습니다."
)

top3_facilities = ["아르피아스포츠센터", "죽전역", "포스코이앤씨용인다우CDC"]
col_sel, col_btn = st.columns([0.7, 0.3])

with col_sel:
    selected_facility = st.selectbox(
        "🏢 개선안을 확인할 우선순위 시설 선택 (TOP 1 ~ 3)",
        top3_facilities,
        format_func=lambda x: f"TOP {FACILITY_DETAILS[x]['rank']}위 | {x} (신규 커버 +{FACILITY_DETAILS[x]['new_grids']}개 격자, 보유 AED {FACILITY_DETAILS[x]['aed_count']}대)",
    )

info = FACILITY_DETAILS[selected_facility]
k1, k2, k3, k4 = st.columns(4)
k1.metric("그리디 우선순위", f"TOP {info['rank']}위")
k2.metric("시설 내 보유 AED", f"{info['aed_count']}대")
k3.metric("신규 커버 격자 수", f"+{info['new_grids']}개")
k4.metric("적용 후 누적 커버리지", f"{info['cum_coverage']:.2f}%")

st.caption(f"📍 **현재 AED 설치 위치:** {info['locations']}")

api_key_to_use = user_api_key or os.getenv("GEMINI_API_KEY") or (st.secrets.get("GEMINI_API_KEY", None) if hasattr(st, "secrets") else None)

if st.button("🔄 Gemini API로 실시간 맞춤형 개선안 새로 생성하기", type="primary"):
    if api_key_to_use and GEMINI_AVAILABLE:
        with st.spinner(f"Gemini AI가 '{selected_facility}'의 맞춤형 개선안(A vs B)을 분석 중입니다..."):
            try:
                live_text = call_gemini_api(selected_facility, api_key_to_use)
                st.session_state[f"report_{selected_facility}"] = live_text
                st.success("Gemini API 실시간 분석이 완료되었습니다!")
            except Exception as e:
                st.warning(f"API 호출 중 오류가 발생하여 사전 구성된 분석 리포트를 표시합니다. ({e})")
    else:
        st.info("사이드바에 Gemini API Key를 입력하시면 실시간 생성이 가능하며, 현재는 해커톤 발표용으로 최적화된 A vs B 분석 리포트를 표시합니다.")

report_content = st.session_state.get(f"report_{selected_facility}", get_prebuilt_ai_report(selected_facility))
st.markdown(f'<div class="ai-box">{report_content}</div>', unsafe_allow_html=True)
