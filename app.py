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
    # Robust migration: inspect the existing V2 database first, then create/upgrade.
    c.execute("CREATE TABLE IF NOT EXISTS ledger(ts TEXT,code TEXT,name TEXT,action TEXT,price REAL,qty INTEGER,cash_after REAL,note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS portfolio(code TEXT PRIMARY KEY,name TEXT,qty INTEGER,cost REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS equity(day TEXT PRIMARY KEY,total REAL,cash REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
    cols={r[1] for r in c.execute("PRAGMA table_info(portfolio)").fetchall()}
    for col,ddl in [("base_qty","INTEGER DEFAULT 0"),("sold6","INTEGER DEFAULT 0"),("sold8","INTEGER DEFAULT 0"),("stop","REAL DEFAULT 0")]:
        if col not in cols:
            c.execute(f"ALTER TABLE portfolio ADD COLUMN {col} {ddl}")
    # Normalize NULLs in rows created by V2.
    c.execute("UPDATE portfolio SET base_qty=COALESCE(base_qty,qty), sold6=COALESCE(sold6,0), sold8=COALESCE(sold8,0), stop=COALESCE(stop,0)")
    if not c.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone():
        c.execute("INSERT INTO settings VALUES('cash',?)",(str(START_CAPITAL),))
    c.commit()
    return c

