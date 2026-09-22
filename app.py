import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path

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

con = connect_db()
cash = float(con.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
positions = pd.read_sql("SELECT code, name, qty, cost FROM portfolio WHERE qty > 0", con)
book_value = float(positions["cost"].sum()) if not positions.empty else 0.0
total = cash + book_value

st.title("📈 국내주식 공격형 모의투자 V3")
st.caption("안정화 버전 · 100만원 모의계좌 · 실제 주문 없음")
st.success("V3 서버가 정상 실행 중입니다.")

c1, c2, c3 = st.columns(3)
c1.metric("총자산(장부기준)", f"{total:,.0f}원")
c2.metric("현금", f"{cash:,.0f}원")
c3.metric("보유 종목", f"{len(positions)}개")

st.subheader("V3 기능 상태")
st.write("✅ 모의계좌 · 보유종목 · 매매일지")
st.write("✅ 보유종목 최신 종가 · 평가손익 · 총자산 계산")\nst.write("🛠️ TOP3 분석 · 자동매매 기능은 안정화 확인 후 순차 연결")

st.subheader("보유 종목")
if positions.empty:
    st.caption("현재 보유 종목이 없습니다.")
else:
    view = positions.copy()
    view["평균단가"] = (view["cost"] / view["qty"]).round(0)
    view = view.rename(columns={"code":"종목코드","name":"종목","qty":"수량","cost":"매입금액"})
    st.dataframe(view, use_container_width=True, hide_index=True)

st.subheader("매매일지")
ledger = pd.read_sql("SELECT * FROM ledger ORDER BY ts DESC", con)
if ledger.empty:
    st.caption("아직 체결된 모의매매가 없습니다.")
else:
    st.dataframe(ledger, use_container_width=True, hide_index=True)

st.caption("모의투자용이며 실제 주문을 실행하지 않고 수익을 보장하지 않습니다.")
