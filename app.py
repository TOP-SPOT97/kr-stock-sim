import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import date, timedelta, datetime
import FinanceDataReader as fdr

st.set_page_config(page_title="공격형 모의투자 v3", page_icon="📈", layout="wide")
DB=Path("papertrade.db"); START_CAPITAL=1_000_000

@st.cache_data(ttl=3600)
def listing():
    df=fdr.StockListing("KRX")
    cc=next(c for c in ["Code","Symbol"] if c in df.columns)
    out=df[[cc,"Name"]].rename(columns={cc:"code","Name":"name"}).dropna()
    out["code"]=out["code"].astype(str).str.zfill(6)
    return out.drop_duplicates("code")

@st.cache_data(ttl=1800)
def price(code,days=140):
    start=(date.today()-timedelta(days=days*2)).isoformat()
    x=fdr.DataReader(code,start)
    if x is None or x.empty:return pd.DataFrame()
    return x.rename_axis("Date").reset_index().tail(days).copy()

def indicators(x):
    x=x.copy()
    for n in (5,20,60):x[f"ma{n}"]=x["Close"].rolling(n).mean()
    x["vma20"]=x["Volume"].rolling(20).mean()
    d=x["Close"].diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    rs=up.rolling(14).mean()/dn.rolling(14).mean().replace(0,np.nan)
    x["rsi"]=100-(100/(1+rs)); x["ret20"]=x["Close"].pct_change(20)*100
    return x

def score_one(code,name):
    try:
        x=indicators(price(code))
        if len(x)<65:return None
        r=x.iloc[-1]; close=float(r.Close); vol=float(r.Volume); vma=float(r.vma20 or 0)
        if not(1000<=close<=30000) or vma<80000:return None
        trend=(18 if close>r.ma20 else -8)+(12 if r.ma20>r.ma60 else -6)+(8 if r.ma5>r.ma20 else 0)
        volume=min(18,max(-4,((vol/vma)-1)*12)) if vma else 0
        momentum=max(-10,min(18,float(r.ret20)*.7))
        rsi=float(r.rsi) if pd.notna(r.rsi) else 50
        heat=-18 if rsi>=75 else(-8 if rsi>=68 else(5 if 42<=rsi<=62 else 0))
        pullback=8 if close<r.ma5 and close>r.ma60 else 0
        score=max(0,min(100,50+trend+volume+momentum+heat+pullback))
        e1=round((min(float(r.ma20),close)*.99)/10)*10
        e2=round((min(float(r.ma60),e1*.95) if pd.notna(r.ma60) else e1*.94)/10)*10
        stop=round(min(e2*.94,close*.90)/10)*10
        chase=round(max(close*1.04,float(x["High"].tail(20).max())*1.01)/10)*10
        label="강력관심" if score>=82 else("상승관심" if score>=68 else("중립" if score>=52 else("하락주의" if score>=38 else "고위험")))
        return {"code":code,"종목":name,"종가":int(close),"점수":round(score,1),"등급":label,"RSI":round(rsi,1),
        "20일수익률%":round(float(r.ret20),1),"거래량배수":round(vol/vma,2),"1차매수":int(e1),"2차매수":int(e2),
        "추격금지":int(chase),"1차목표":int(round(e1*1.075/10)*10),"2차목표":int(round(e1*1.15/10)*10),"손절":int(stop),
        "date":str(pd.to_datetime(r.Date).date())}
    except:return None

def init_db():
    c=sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS ledger(ts TEXT,code TEXT,name TEXT,action TEXT,price REAL,qty INTEGER,cash_after REAL,note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS portfolio(code TEXT PRIMARY KEY,name TEXT,qty INTEGER,cost REAL,base_qty INTEGER DEFAULT 0,sold6 INTEGER DEFAULT 0,sold8 INTEGER DEFAULT 0,stop REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS equity(day TEXT PRIMARY KEY,total REAL,cash REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
    if not c.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone():c.execute("INSERT INTO settings VALUES('cash',?)",(str(START_CAPITAL),))
    # V2 DB migration: add V3 portfolio columns when an existing SQLite file is reused\n    cols={r[1] for r in c.execute("PRAGMA table_info(portfolio)").fetchall()}\n    for col,ddl in [("base_qty","INTEGER DEFAULT 0"),("sold6","INTEGER DEFAULT 0"),("sold8","INTEGER DEFAULT 0"),("stop","REAL DEFAULT 0")]:\n        if col not in cols:c.execute(f"ALTER TABLE portfolio ADD COLUMN {col} {ddl}")\n    c.commit();return c

def cash(c):return float(c.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
def setcash(c,v):c.execute("UPDATE settings SET value=? WHERE key='cash'",(str(v),));c.commit()
def positions(c):return pd.read_sql("SELECT * FROM portfolio WHERE qty>0",c)

def trade(c,code,name,action,px,qty,note):
    ca=cash(c)
    row=c.execute("SELECT qty,cost,base_qty,sold6,sold8,stop FROM portfolio WHERE code=?",(code,)).fetchone()
    oq,oc,bq,s6,s8,sp=row if row else(0,0,0,0,0,0)
    if action=="매수":
        qty=int(min(qty,ca//px))
        if qty<=0:return
        ca-=qty*px; nq=oq+qty; nc=oc+qty*px
        c.execute("INSERT OR REPLACE INTO portfolio VALUES(?,?,?,?,?,?,?,?)",(code,name,nq,nc,bq+qty,s6,s8,sp))
    else:
        qty=min(int(qty),oq)
        if qty<=0:return
        avg=oc/oq if oq else 0; ca+=qty*px; nq=oq-qty; nc=max(0,oc-avg*qty)
        c.execute("UPDATE portfolio SET qty=?,cost=? WHERE code=?",(nq,nc,code))
    c.execute("INSERT INTO ledger VALUES(datetime('now','localtime'),?,?,?,?,?,?,?)",(code,name,action,px,qty,ca,note))
    c.commit();setcash(c,ca)

@st.cache_data(ttl=1800,show_spinner=False)
def screen(n):
    rows=[]
    for r in listing().head(n).itertuples(index=False):
        z=score_one(r.code,r.name)
        if z:rows.append(z)
    return pd.DataFrame(rows).sort_values("점수",ascending=False) if rows else pd.DataFrame()

def manage_positions(c):
    msgs=[]
    for p in positions(c).itertuples(index=False):
        h=price(p.code,10)
        if h.empty:continue
        cur=float(h.iloc[-1].Close); avg=p.cost/p.qty if p.qty else 0
        if cur<=p.stop and p.stop>0:
            trade(c,p.code,p.name,"매도",cur,p.qty,"자동 손절");msgs.append(f"🔻 {p.name} 자동 손절")
        elif cur>=avg*1.08 and not p.sold8:
            q=max(1,int(p.base_qty*.25));trade(c,p.code,p.name,"매도",cur,q,"+8% 25% 분할익절")
            c.execute("UPDATE portfolio SET sold8=1 WHERE code=?",(p.code,));c.commit();msgs.append(f"✅ {p.name} +8% 분할익절")
        elif cur>=avg*1.06 and not p.sold6:
            q=max(1,int(p.base_qty*.25));trade(c,p.code,p.name,"매도",cur,q,"+6% 25% 분할익절")
            c.execute("UPDATE portfolio SET sold6=1 WHERE code=?",(p.code,));c.commit();msgs.append(f"✅ {p.name} +6% 분할익절")
    return msgs

con=init_db()
st.title("📈 국내주식 공격형 모의투자 v3")
st.caption("자동 스크리닝 · TOP3 모의매매 · +6%/+8% 분할익절 · 자동손절 · 자산곡선 · 실제 주문 없음")
with st.sidebar:
    universe_n=st.slider("검색 종목 수",30,200,80,10)
    order_budget=st.number_input("종목당 진입 한도",50000,400000,250000,10000)
    auto_trade=st.toggle("TOP3 자동 모의매매",True)
    st.caption("무료판: 앱을 열거나 새로고침할 때 최신 데이터로 자동 실행")

with st.spinner("최신 장마감 데이터 자동 분석 중..."):
    scr=screen(universe_n)
for m in manage_positions(con):st.toast(m)

if not scr.empty:
    top=scr.head(3).copy();top.insert(0,"순위",range(1,len(top)+1))
    st.subheader(f"오늘의 자동 TOP3 · 데이터 기준 {top.iloc[0]['date']}")
    st.dataframe(top[["순위","종목","등급","종가","점수","RSI","20일수익률%","거래량배수","1차매수","2차매수","추격금지","1차목표","2차목표","손절"]],use_container_width=True,hide_index=True)
    if auto_trade:
        held=set(positions(con)["code"].astype(str))
        for _,r in top.iterrows():
            if str(r["code"]) not in held and len(positions(con))<3 and r["점수"]>=68 and r["종가"]<=r["추격금지"]:
                qty=int(order_budget//r["종가"])
                trade(con,str(r["code"]),r["종목"],"매수",float(r["종가"]),qty,"TOP3 자동 진입")
                con.execute("UPDATE portfolio SET stop=? WHERE code=?",(float(r["손절"]),str(r["code"])));con.commit()
                held.add(str(r["code"]))
else:st.warning("스크리닝 데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.")

pos=positions(con); ca=cash(con); rows=[]; mv=0
for p in pos.itertuples(index=False):
    h=price(p.code,10);cur=float(h.iloc[-1].Close) if not h.empty else p.cost/p.qty
    avg=p.cost/p.qty;value=p.qty*cur;mv+=value
    rows.append({"종목":p.name,"수량":p.qty,"평균단가":round(avg),"현재가":round(cur),"평가금액":round(value),"평가손익":round(value-p.cost),"수익률%":round((cur/avg-1)*100,2),"손절가":round(p.stop)})
total=ca+mv
con.execute("INSERT OR REPLACE INTO equity VALUES(?,?,?)",(str(date.today()),total,ca));con.commit()
a,b,c,d=st.columns(4);a.metric("총자산",f"{total:,.0f}원");b.metric("현금",f"{ca:,.0f}원");c.metric("주식 평가액",f"{mv:,.0f}원");d.metric("누적수익률",f"{(total/START_CAPITAL-1)*100:.2f}%")

st.subheader("보유 종목")
if rows:st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
else:st.caption("현재 보유 종목이 없습니다.")
eq=pd.read_sql("SELECT * FROM equity ORDER BY day",con)
st.subheader("자산 변화")
if not eq.empty:
    eq["day"]=pd.to_datetime(eq["day"]);st.line_chart(eq.set_index("day")["total"])
st.subheader("매매일지")
led=pd.read_sql("SELECT * FROM ledger ORDER BY ts DESC",con)
if not led.empty:st.dataframe(led,use_container_width=True,hide_index=True)

with st.expander("V3 데이터 확장 상태"):
    st.write("✅ 가격·거래량·추세·RSI·모멘텀 / 자동 TOP3 / 자동 분할익절·손절 / 자산곡선")
    st.write("🟡 외국인·기관 수급 / 실적·PER·PBR / 뉴스 호재·악재는 무료 데이터 소스 연동을 다음 단계에서 추가")
    st.info("Streamlit 무료 서버는 상시 실행 서버가 아니므로, 현재 자동화는 앱 접속/새로고침 시 실행됩니다. 완전 무인 장마감 실행은 별도 무료 스케줄러와 영구 DB를 연결해야 합니다.")
st.caption("모의투자용이며 실제 주문을 실행하지 않고 수익을 보장하지 않습니다.")
