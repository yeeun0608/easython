# AED 접근성 개선 시스템

용인시 수지구의 AED 접근성 분석 결과를 보여주는 Streamlit 웹앱입니다.

## 1. 폴더 구성

```text
aed_accessibility_system/
├─ app.py
├─ requirements.txt
├─ README.md
└─ data/
   ├─ greedy_results.json
   └─ greedy_top5.csv
```

## 2. 실행 방법

Python 3.10 이상을 권장합니다.

```bash
cd aed_accessibility_system
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 Streamlit이 안내하는 로컬 주소를 열면 됩니다.

## 3. 제공 데이터 넣기

`data/` 폴더에 다음 파일을 넣습니다.
- `greedy_results.json`
- `greedy_top5.csv`

현재 앱은 제공된 오전 1시 평일 평균 결과를 사용합니다.

## 4. 지도 데이터 형식

격자별 실제 지도 표시를 위해서는 좌표가 포함된 CSV가 추가로 필요합니다.

```csv
lat,lon,access_01,access_13
37.32,127.09,1,0
37.33,127.10,0,1
```

- `lat`, `lon`: 각 100m 격자의 중심 위도·경도
- `access_01`: 오전 1시 접근 가능 여부
- `access_13`: 오후 1시 접근 가능 여부
- `1`: 접근 가능, `0`: 접근 불가능

열 이름은 한글 별칭도 지원합니다. 앱 왼쪽 사이드바의 업로더에서 CSV를 올리면 됩니다.
현재 업로드된 자료만으로는 실제 격자 좌표와 오후 1시 접근 상태를 알 수 없으므로, 지도에 가상의 격자를 만들지 않습니다.

## 5. Gemini AI 연결 (선택)

Gemini API 키를 환경변수로 설정한 뒤 실행합니다.

Windows PowerShell:
```powershell
$env:GEMINI_API_KEY="발급받은_API_키"
streamlit run app.py
```

macOS / Linux:
```bash
export GEMINI_API_KEY="발급받은_API_키"
streamlit run app.py
```

API 키가 없으면 상위 3개 시설에 대해 코드에 포함된 규칙 기반 개선안 미리보기를 표시합니다. 이 미리보기는 Gemini가 생성한 답변이 아닙니다.

## 6. 데이터 해석

현재 결과 기준:
- 전체 격자: 4,221개
- AED 수: 214개
- 기준 시간: 오전 1시
- 평일 평균
- 접근 반경: 200m
- 개선 전 접근 가능 격자: 854개
- TOP 5 개선 후 접근 가능 격자: 912개
- 커버리지: 20.2322% → 21.6063% (약 +1.3741%p)

실제 운영에 적용하기 전에는 시설 운영시간, 출입 가능 여부, AED 위치와 장비 상태를 확인해야 합니다.
