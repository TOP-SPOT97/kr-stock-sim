# 국내주식 공격형 모의투자 v2

Streamlit 기반 100만원 모의투자 웹앱입니다.

- KRX 종목 데이터 자동 조회
- 이동평균, RSI, 거래량, 모멘텀 기반 스크리닝
- TOP 후보 및 1/2차 매수가, 목표가, 손절가 표시
- SQLite 기반 모의계좌/매매일지
- 실제 주문 기능 없음

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

무료 배포는 Streamlit Community Cloud에서 이 GitHub 저장소의 `app.py`를 지정하면 됩니다.
