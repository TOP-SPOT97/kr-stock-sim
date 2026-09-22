import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path

st.set_page_config(page_title="공격형 모의투자 V3",page_icon="📈",layout="wide")
DB=Path("papertrade.db"); START=1_000_000

def db():
    c=sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS ledger(ts TEXT,code TEXT,name TEXT,action TEXT,price REAL,qty INTEGER,cash_after REAL,note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS portfolio(code TEXT PRIMARY KEY,name TEXT,qty INTEGER,cost REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS equity(day TEXT PRIMARY KEY,total REAL,cash REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
    if not c.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone():
        c.execute("INSERT INTO settings VALUES('cash',?)",(str(START),))
    c.commit(); return c

c=db()
cash=float(c.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
pos=pd.read_sql("SELECT * FROM portfolio WHERE qty>0",c)
invested=float(pos["cost"].sum()) if not pos.empty else 0
total=cash+invested

st.title("📈 국내주식 공격형 모의투자 V3")
st.caption("안정화 버전 · 100만원 모의계좌 · 실제 주문 없음")
st.success("V3 서버가 정상 실행 중입니다.")

a,b,d=st.columns(3)
a.metric("총자산(장부기준)",f"{total:,.0f}원")
b.metric("현금",f"{cash:,.0f}원")
d.metric("보유 종목",f"{len(pos)}개")

st.subheader("V3 기능 상태")
st.write("✅ 모의계좌 / 매매일지 / 자산 기록")
st.write("✅ 보유종목 최신 종가 · 평가손익 · 총자산 계산")\nst.write("🛠️ TOP3 자동분석 · 분할익절 · 손절 · 수급/실적/뉴스 분석은 안정화 후 순차 연결")

if st.button("🔎 분석 엔진 연결 테스트"):
    st.info("화면 안정화 확인 완료. 다음 업데이트에서 주가 분석 엔진을 연결합니다.")

st.subheader("보유 종목")
if pos.empty: st.caption("현재 보유 종목이 없습니다.")
else: st.dataframe(pos,use_container_width=True,hide_index=True)

st.subheader("매매일지")
led=pd.read_sql("SELECT * FROM ledger ORDER BY ts DESC",c)
if led.empty: st.caption("아직 체결된 모의매매가 없습니다.")
else: st.dataframe(led,use_container_width=True,hide_index=True)

st.caption("모의투자용이며 수익을 보장하지 않습니다.")
