import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import date, timedelta
import FinanceDataReader as fdr

st.set_page_config(page_title="공격형 모의투자 V3", page_icon="📈", layout="wide")
DB = Path("papertrade.db")
START_CAPITAL = 1_000_000

def connect_db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS ledger (ts TEXT, code TEXT, name TEXT, action TEXT, price REAL, qty INTEGER, cash_after REAL, note TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS portfolio (code TEXT PRIMARY KEY, name TEXT, qty INTEGER, cost REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    if not con.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone():
        con.execute("INSERT INTO settings VALUES ('cash', ?)", (str(START_CAPITAL),))
    con.commit()
    return con

@st.cache_data(ttl=900, show_spinner=False)
def latest_close(code):
    try:
        start = (date.today() - timedelta(days=14)).isoformat()
        data = fdr.DataReader(str(code).zfill(6), start)
        if data is None or data.empty:
            return None, None
        return float(data.iloc[-1]["Close"]), str(pd.to_datetime(data.index[-1]).date())
    except Exception:
        return None, None

con = connect_db()
cash = float(con.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
positions = pd.read_sql("SELECT code, name, qty, cost FROM portfolio WHERE qty > 0", con)

valuation_rows = []
market_value = 0.0
latest_day = None
for p in positions.itertuples(index=False):
    avg = float(p.cost) / int(p.qty)
    current, data_day = latest_close(p.code)
    if current is None:
        current = avg
    value = int(p.qty) * current
    pnl = value - float(p.cost)
    rate = (current / avg - 1) * 100 if avg else 0.0
    market_value += value
    if data_day and (latest_day is None or data_day > latest_day):
        latest_day = data_day
    valuation_rows.append({
        "종목코드": str(p.code).zfill(6),
        "종목": p.name,
        "수량": int(p.qty),
        "평균단가": round(avg),
        "현재가": round(current),
        "평가금액": round(value),
        "평가손익": round(pnl),
        "수익률%": round(rate, 2)
    })

total = cash + market_value

st.title("📈 국내주식 공격형 모의투자 V3")
st.caption("안정화 2단계 · 최신 종가 평가 · 100만원 모의계좌 · 실제 주문 없음")
st.success("V3 서버가 정상 실행 중입니다.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("총자산", f"{total:,.0f}원")
c2.metric("현금", f"{cash:,.0f}원")
c3.metric("주식 평가액", f"{market_value:,.0f}원")
c4.metric("누적수익률", f"{(total / START_CAPITAL - 1) * 100:.2f}%")
if latest_day:
    st.caption(f"주가 데이터 기준: {latest_day} 장마감")

st.subheader("V3 기능 상태")
st.write("✅ 모의계좌 · 보유종목 · 매매일지")
st.write("✅ 최신 종가 · 평가손익 · 총자산 계산")
st.write("🛠️ TOP3 분석 · 자동매매 · 수급/실적/뉴스는 다음 단계")

st.subheader("보유 종목")
if valuation_rows:
    st.dataframe(pd.DataFrame(valuation_rows), use_container_width=True, hide_index=True)
else:
    st.caption("현재 보유 종목이 없습니다.")

st.subheader("매매일지")
ledger = pd.read_sql("SELECT * FROM ledger ORDER BY ts DESC", con)
if ledger.empty:
    st.caption("아직 체결된 모의매매가 없습니다.")
else:
    st.dataframe(ledger, use_container_width=True, hide_index=True)

st.caption("모의투자용이며 실제 주문을 실행하지 않고 수익을 보장하지 않습니다.")
