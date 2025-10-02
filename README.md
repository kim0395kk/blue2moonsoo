# A청사 2023년 전력 사용량 분석 및 에너지 절약 수칙

## 프로젝트 개요
A청사의 2023년 전력 사용량 데이터를 분석하고, 누진세를 적용한 전기요금을 계산하여 시각화하는 웹 애플리케이션입니다. 또한 에너지 절약을 위한 10가지 수칙을 아이콘과 함께 카드 형태로 제공합니다.

## 주요 기능
- 📊 **월별 전력 사용량 및 전기요금 시각화**
- 💰 **누진세 적용 전기요금 계산**
- 💡 **에너지 절약 수칙 10가지 (아이콘 + 텍스트 카드)**
- 📱 **반응형 디자인 (모바일 최적화)**
- 🎨 **호버 효과 및 애니메이션**

## 기술 스택
- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **Charts**: Chart.js
- **Backend**: Flask (Python)
- **Deployment**: Netlify

## 데이터 분석 결과
### A청사 2023년 전력 사용량 요약
- **연간 총 사용량**: 1,880,327 kWh
- **연간 총 전기요금**: 526,778,625원
- **월평균 사용량**: 156,694 kWh
- **월평균 전기요금**: 43,898,219원

### 월별 사용량 패턴
- **최대 사용량**: 8월 (202,643 kWh)
- **최소 사용량**: 4월 (132,277 kWh)
- **여름철(7-8월)** 높은 사용량 (냉방 부하)
- **겨울철(1-2월)** 높은 사용량 (난방 부하)

## 파일 구조
```
├── index.html          # 메인 HTML 파일
├── styles.css          # CSS 스타일시트
├── script.js           # JavaScript 파일
├── app.py              # Flask 애플리케이션
├── data_analysis.py    # 데이터 분석 스크립트
├── energy_data.json    # 분석된 에너지 데이터
├── requirements.txt    # Python 의존성
├── runtime.txt         # Python 버전
├── netlify.toml        # Netlify 배포 설정
└── README.md           # 프로젝트 문서
```

## 로컬 실행 방법

### 1. 정적 파일로 실행 (권장)
```bash
# 웹 서버 실행 (Python 내장 서버)
python -m http.server 8000

# 브라우저에서 http://localhost:8000 접속
```

### 2. Flask 애플리케이션으로 실행
```bash
# 의존성 설치
pip install -r requirements.txt

# Flask 애플리케이션 실행
python app.py

# 브라우저에서 http://localhost:5000 접속
```

## Netlify 배포 방법

### 1. GitHub 연동 배포 (권장)
1. GitHub에 저장소 생성 및 코드 업로드
2. Netlify 계정 로그인
3. "New site from Git" 선택
4. GitHub 저장소 연결
5. 빌드 설정:
   - Build command: `echo 'Static site deployment'`
   - Publish directory: `.`
6. Deploy 버튼 클릭

### 2. 드래그 앤 드롭 배포
1. 모든 파일을 zip으로 압축
2. Netlify 대시보드에서 "Deploy manually" 선택
3. zip 파일을 드래그 앤 드롭

## 반응형 디자인
- **데스크톱**: 카드 그리드 레이아웃
- **태블릿**: 2열 카드 배치
- **모바일 (768px 이하)**: 1열 세로 배치
- **작은 모바일 (480px 이하)**: 컴팩트 레이아웃

## 에너지 절약 수칙
1. 💡 LED 조명 사용
2. ❄️ 적정 냉난방 온도 유지
3. 🔌 대기전력 차단
4. 🪟 자연광 활용
5. 🖥️ 컴퓨터 절전모드 설정
6. 🚪 출입문 관리
7. 🌡️ 단열 개선
8. ⏰ 피크타임 사용 자제
9. 🔄 정기적인 설비 점검
10. 📊 에너지 사용량 모니터링

## 브라우저 지원
- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## 라이선스
MIT License

## 개발자
AI 블루 2회차 시험 프로젝트
