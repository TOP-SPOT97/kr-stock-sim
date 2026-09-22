import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import date, timedelta
import FinanceDataReader as fdr

st.set_page_config(page_title="공격형 모의투자 V3", page_icon="📈", layout="wide")
DB=Path("papertrade.db"); START_CAPITAL=1_000_000

def connect_db():
    con=sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS ledger (ts TEXT, code TEXT, name TEXT, action TEXT, price REAL, qty INTEGER, cash_after REAL, note TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS portfolio (code TEXT PRIMARY KEY, name TEXT, qty INTEGER, cost REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    if not con.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone():
        con.execute("INSERT INTO settings VALUES ('cash',?)",(str(START_CAPITAL),))
    con.commit(); return con

def paper_sell(con, code, name, qty, price, note):
    row=con.execute("SELECT qty,cost FROM portfolio WHERE code=?",(code,)).fetchone()
    if not row:
        return False
    old_qty=int(row[0]); old_cost=float(row[1]); qty=min(int(qty),old_qty)
    if qty<=0:
        return False
    avg=old_cost/old_qty
    new_qty=old_qty-qty
    new_cost=max(0.0,old_cost-avg*qty)
    cash_now=float(con.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
    new_cash=cash_now+qty*float(price)
    con.execute("UPDATE portfolio SET qty=?,cost=? WHERE code=?",(new_qty,new_cost,code))
    con.execute("UPDATE settings SET value=? WHERE key='cash'",(str(new_cash),))
    con.execute("INSERT INTO ledger VALUES(datetime('now','localtime'),?,?,?,?,?,?,?)",(code,name,"매도",float(price),qty,new_cash,note))
    con.commit()
    return True

@st.cache_data(ttl=900,show_spinner=False)
def latest_close(code):
    try:
        x=fdr.DataReader(str(code).zfill(6),(date.today()-timedelta(days=14)).isoformat())
        if x is None or x.empty:return None,None
        return float(x.iloc[-1]["Close"]),str(pd.to_datetime(x.index[-1]).date())
    except Exception:return None,None

@st.cache_data(ttl=3600,show_spinner=False)
def krx_list():
    x=fdr.StockListing("KRX")
    cc="Code" if "Code" in x.columns else "Symbol"
    y=x[[cc,"Name"]].rename(columns={cc:"code","Name":"name"}).dropna()
    y["code"]=y["code"].astype(str).str.zfill(6)
    return y.drop_duplicates("code")

def analyze(code,name):
    try:
        x=fdr.DataReader(code,(date.today()-timedelta(days=180)).isoformat())
        if x is None or len(x)<65:return None
        x=x.tail(120).copy()
        x["ma5"]=x.Close.rolling(5).mean(); x["ma20"]=x.Close.rolling(20).mean(); x["ma60"]=x.Close.rolling(60).mean()
        x["vma20"]=x.Volume.rolling(20).mean(); x["ret20"]=x.Close.pct_change(20)*100
        d=x.Close.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
        rs=up.rolling(14).mean()/dn.rolling(14).mean().replace(0,np.nan); x["rsi"]=100-(100/(1+rs))
        r=x.iloc[-1]; close=float(r.Close); vma=float(r.vma20) if pd.notna(r.vma20) else 0
        if not 1000<=close<=30000 or vma<80000:return None
        trend=(18 if close>r.ma20 else -8)+(12 if r.ma20>r.ma60 else -6)+(8 if r.ma5>r.ma20 else 0)
        volume=min(18,max(-4,((float(r.Volume)/vma)-1)*12)) if vma else 0
        momentum=max(-10,min(18,float(r.ret20)*.7)); rsi=float(r.rsi) if pd.notna(r.rsi) else 50
        heat=-18 if rsi>=75 else(-8 if rsi>=68 else(5 if 42<=rsi<=62 else 0))
        score=max(0,min(100,50+trend+volume+momentum+heat))
        grade="강력관심" if score>=82 else("상승관심" if score>=68 else("중립" if score>=52 else("하락주의" if score>=38 else "고위험")))
        e1=round((min(float(r.ma20),close)*.99)/10)*10; e2=round(e1*.95/10)*10
        return {"종목코드":code,"종목":name,"종가":round(close),"점수":round(score,1),"등급":grade,"RSI":round(rsi,1),"20일수익률%":round(float(r.ret20),1),"거래량배수":round(float(r.Volume)/vma,2),"1차매수":int(e1),"2차매수":int(e2),"추격금지":int(round(close*1.04/10)*10),"1차목표":int(round(e1*1.075/10)*10),"2차목표":int(round(e1*1.15/10)*10),"손절":int(round(e2*.94/10)*10),"기준일":str(pd.to_datetime(x.index[-1]).date())}
    except Exception:return None

@st.cache_data(ttl=1800,show_spinner=False)
def top_scan(n):
    rows=[]
    universe=krx_list().head(max(n*8,160))
    for r in universe.itertuples(index=False):
        z=analyze(r.code,r.name)
        if z is not None:rows.append(z)
        if len(rows)>=n:break
    if not rows:return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["점수","거래량배수"],ascending=[False,False]).head(3)

con=connect_db(); cash=float(con.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
positions=pd.read_sql("SELECT code,name,qty,cost FROM portfolio WHERE qty>0",con)
valuation=[]; market=0.0; latest_day=None
for p in positions.itertuples(index=False):
    avg=float(p.cost)/int(p.qty); cur,day=latest_close(p.code); cur=avg if cur is None else cur
    value=int(p.qty)*cur; pnl=value-float(p.cost); market+=value
    if day and (latest_day is None or day>latest_day):latest_day=day
    valuation.append({"종목코드":str(p.code).zfill(6),"종목":p.name,"수량":int(p.qty),"평균단가":round(avg),"현재가":round(cur),"평가금액":round(value),"평가손익":round(pnl),"수익률%":round((cur/avg-1)*100,2)})
# Automatic paper exits: +6% sell 25%, +8% sell another 25%.
# Use original quantity reconstructed from current holding plus prior staged sales.
auto_msgs=[]
for row in valuation:
    code=row["종목코드"]; name=row["종목"]; rate=float(row["수익률%"]); price=float(row["현재가"])
    pos=con.execute("SELECT qty FROM portfolio WHERE code=?",(code,)).fetchone()
    if not pos or int(pos[0])<=0:continue
    k6=f"exit6_{code}"; k8=f"exit8_{code}"
    r6=con.execute("SELECT value FROM settings WHERE key=?",(k6,)).fetchone()
    r8=con.execute("SELECT value FROM settings WHERE key=?",(k8,)).fetchone()
    sold6=int(r6[0]) if r6 else 0
    sold8=int(r8[0]) if r8 else 0
    current_qty=int(pos[0])
    if rate>=8 and not sold8:
        if not sold6:
            q=max(1,int(round(current_qty*0.25)))
            if paper_sell(con,code,name,q,price,"자동 +6% 25% 분할익절"):
                con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(k6,"1")); con.commit()
                current_qty-=q; auto_msgs.append(f"{name}: +6% 25% 모의익절")
        q=max(1,int(round(current_qty/3))) if current_qty>0 else 0
        if q and paper_sell(con,code,name,q,price,"자동 +8% 추가 25% 분할익절"):
            con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(k8,"1")); con.commit()
            auto_msgs.append(f"{name}: +8% 추가 25% 모의익절")
    elif rate>=6 and not sold6:
        q=max(1,int(round(current_qty*0.25)))
        if paper_sell(con,code,name,q,price,"자동 +6% 25% 분할익절"):
            auto_msgs.append(f"{name}: +6% 25% 모의익절")

if auto_msgs:
    st.toast(" / ".join(auto_msgs))
    st.rerun()

cash=float(con.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
total=cash+market

st.title("📈 국내주식 공격형 모의투자 V3")
st.caption("안정화 3단계 · 최신 종가 평가 + TOP3 분석 · 실제 주문 없음")
st.success("V3 서버가 정상 실행 중입니다.")
st.caption("자동 모의익절 활성화: +6% 25% / +8% 추가 25% · 실제 주문 없음")
a,b,c,d=st.columns(4)
a.metric("총자산",f"{total:,.0f}원"); b.metric("현금",f"{cash:,.0f}원"); c.metric("주식 평가액",f"{market:,.0f}원"); d.metric("누적수익률",f"{(total/START_CAPITAL-1)*100:.2f}%")
if latest_day:st.caption(f"주가 데이터 기준: {latest_day} 장마감")

st.subheader("오늘의 TOP3 분석")
scan_n=st.slider("분석 후보 수",10,40,20,10)
if st.button("🔎 TOP3 분석 실행",type="primary"):
    with st.spinner("후보 종목을 분석 중입니다. 무료 서버에서는 잠시 걸릴 수 있습니다."):
        result=top_scan(scan_n)
    st.session_state["top3"]=result
top3=st.session_state.get("top3",pd.DataFrame())
if isinstance(top3,pd.DataFrame) and not top3.empty:
    st.dataframe(top3,use_container_width=True,hide_index=True)
    st.caption("현재 단계에서는 후보 분석만 하며 자동 매수/매도는 실행하지 않습니다.")
elif "top3" in st.session_state:
    st.warning("조건을 통과한 후보가 없습니다. 분석 후보 수를 늘려 다시 실행해 주세요.")
else:
    st.info("TOP3 분석 실행 버튼을 눌러 후보를 확인하세요.")

st.subheader("보유 종목")
if valuation:st.dataframe(pd.DataFrame(valuation),use_container_width=True,hide_index=True)
else:st.caption("현재 보유 종목이 없습니다.")

st.subheader("매매일지")
ledger=pd.read_sql("SELECT * FROM ledger ORDER BY ts DESC",con)
if ledger.empty:st.caption("아직 체결된 모의매매가 없습니다.")
else:st.dataframe(ledger,use_container_width=True,hide_index=True)
st.caption("모의투자용이며 실제 주문을 실행하지 않고 수익을 보장하지 않습니다.")
