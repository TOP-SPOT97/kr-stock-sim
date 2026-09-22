import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import date, timedelta
import FinanceDataReader as fdr

st.set_page_config(page_title='공격형 모의투자 v2', page_icon='📈', layout='wide')
DB = Path('papertrade.db')
START_CAPITAL = 1_000_000

@st.cache_data(ttl=3600)
def listing():
    df = fdr.StockListing('KRX')
    code_col = next(c for c in ['Code','Symbol'] if c in df.columns)
    out = df[[code_col,'Name']].rename(columns={code_col:'code','Name':'name'}).dropna()
    out['code'] = out['code'].astype(str).str.zfill(6)
    return out.drop_duplicates('code')

@st.cache_data(ttl=1800)
def price(code, days=140):
    start = (date.today()-timedelta(days=days*2)).isoformat()
    df = fdr.DataReader(code, start)
    if df is None or df.empty: return pd.DataFrame()
    return df.rename_axis('Date').reset_index().tail(days).copy()

def indicators(df):
    x=df.copy()
    for n in (5,20,60): x[f'ma{n}']=x['Close'].rolling(n).mean()
    x['vma20']=x['Volume'].rolling(20).mean()
    d=x['Close'].diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    rs=up.rolling(14).mean()/dn.rolling(14).mean().replace(0,np.nan)
    x['rsi']=100-(100/(1+rs)); x['ret20']=x['Close'].pct_change(20)*100
    return x

def score_one(code,name):
    try:
        x=indicators(price(code))
        if len(x)<65: return None
        r=x.iloc[-1]; close=float(r.Close); vol=float(r.Volume); vma=float(r.vma20 or 0)
        if not (1000 <= close <= 30000) or vma < 80000: return None
        trend=(18 if close>r.ma20 else -8)+(12 if r.ma20>r.ma60 else -6)+(8 if r.ma5>r.ma20 else 0)
        volume=min(18,max(-4,((vol/vma)-1)*12)) if vma else 0
        momentum=max(-10,min(18,float(r.ret20)*.7)); rsi=float(r.rsi) if pd.notna(r.rsi) else 50
        heat=-18 if rsi>=75 else (-8 if rsi>=68 else (5 if 42<=rsi<=62 else 0))
        pullback=8 if close<r.ma5 and close>r.ma60 else 0
        score=max(0,min(100,50+trend+volume+momentum+heat+pullback))
        support=min(float(r.ma20),close)*.99 if pd.notna(r.ma20) else close*.96
        e1=round(support/10)*10; e2=round((min(float(r.ma60),e1*.95) if pd.notna(r.ma60) else e1*.94)/10)*10
        stop=round(min(e2*.94,close*.90)/10)*10
        chase=round(max(close*1.04,float(x['High'].tail(20).max())*1.01)/10)*10
        return {'code':code,'종목':name,'종가':int(close),'점수':round(score,1),'RSI':round(rsi,1),'20일수익률%':round(float(r.ret20),1),'거래량배수':round(vol/vma,2),'1차매수':int(e1),'2차매수':int(e2),'추격금지':int(chase),'1차목표':int(round(e1*1.075/10)*10),'2차목표':int(round(e1*1.15/10)*10),'손절':int(stop),'date':str(pd.to_datetime(r.Date).date())}
    except Exception: return None

def init_db():
    con=sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS ledger (ts TEXT, code TEXT, name TEXT, action TEXT, price REAL, qty INTEGER, cash_after REAL, note TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS portfolio (code TEXT PRIMARY KEY, name TEXT, qty INTEGER, cost REAL)')
    con.execute('CREATE TABLE IF NOT EXISTS equity (day TEXT PRIMARY KEY, total REAL, cash REAL)')
    con.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    if not con.execute("SELECT 1 FROM settings WHERE key='cash'").fetchone(): con.execute("INSERT INTO settings VALUES ('cash',?)",(str(START_CAPITAL),))
    con.commit(); return con
def get_cash(c): return float(c.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])
def set_cash(c,v): c.execute("UPDATE settings SET value=? WHERE key='cash'",(str(v),)); c.commit()
def positions(c): return pd.read_sql('SELECT * FROM portfolio WHERE qty>0',c)
def buy(c,r,budget):
    cash=get_cash(c); px=float(r['1차매수']); qty=int(min(budget,cash)//px)
    if qty<=0:return
    old=c.execute('SELECT qty,cost FROM portfolio WHERE code=?',(r['code'],)).fetchone(); oq,oc=old if old else (0,0)
    cash-=qty*px; c.execute('INSERT OR REPLACE INTO portfolio VALUES (?,?,?,?)',(r['code'],r['종목'],oq+qty,oc+qty*px))
    c.execute('INSERT INTO ledger VALUES (datetime("now","localtime"),?,?,?,?,?,?,?)',(r['code'],r['종목'],'매수',px,qty,cash,'TOP 스크리너 1차 진입')); c.commit(); set_cash(c,cash)

con=init_db()
st.title('📈 국내주식 공격형 모의투자 v2')
st.caption('장 마감 데이터 자동수집 · 기술점수 스크리닝 · 100만원 모의계좌 · 실제 주문 없음')
with st.sidebar:
    universe_n=st.slider('검색 종목 수',30,200,80,10); top_n=st.slider('TOP 후보',2,10,5)
    order_budget=st.number_input('종목당 1차 주문금액',50000,400000,200000,10000)
@st.cache_data(ttl=1800,show_spinner=False)
def screen(n):
    ls=listing().head(n); rows=[]
    for r in ls.itertuples(index=False):
        z=score_one(r.code,r.name)
        if z: rows.append(z)
    return pd.DataFrame(rows).sort_values('점수',ascending=False) if rows else pd.DataFrame()
if st.button('🔎 장마감 스크리닝 실행',type='primary'):
    st.cache_data.clear(); st.session_state['screen']=screen(universe_n)
scr=st.session_state.get('screen',pd.DataFrame())
if not scr.empty:
    show=scr.head(top_n).copy(); show.insert(0,'순위',range(1,len(show)+1))
    st.subheader(f"자동 후보 TOP {top_n} · 데이터 기준 {show.iloc[0]['date']}")
    st.dataframe(show[['순위','종목','종가','점수','RSI','20일수익률%','거래량배수','1차매수','2차매수','추격금지','1차목표','2차목표','손절']],use_container_width=True,hide_index=True)
    pick=st.selectbox('모의매수 후보',show['종목']); prow=show[show['종목']==pick].iloc[0]
    if st.button(f'{pick} 1차 모의매수'): buy(con,prow,order_budget); st.rerun()
else: st.info('「장마감 스크리닝 실행」을 누르면 KRX 종목을 자동 분석합니다.')
pos=positions(con); cash=get_cash(con); rows=[]; mv=0
for p in pos.itertuples(index=False):
    h=price(p.code,10); cur=float(h.iloc[-1].Close) if not h.empty else p.cost/p.qty
    avg=p.cost/p.qty; value=p.qty*cur; mv+=value
    rows.append({'종목':p.name,'수량':p.qty,'평균단가':round(avg),'현재가':round(cur),'평가금액':round(value),'평가손익':round(value-p.cost),'수익률%':round((cur/avg-1)*100,2)})
total=cash+mv
a,b,c,d=st.columns(4); a.metric('총자산',f'{total:,.0f}원'); b.metric('현금',f'{cash:,.0f}원'); c.metric('주식 평가액',f'{mv:,.0f}원'); d.metric('누적수익률',f'{(total/START_CAPITAL-1)*100:.2f}%')
st.subheader('보유 종목')
if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
st.subheader('매매일지'); led=pd.read_sql('SELECT * FROM ledger ORDER BY ts DESC',con)
if not led.empty: st.dataframe(led,use_container_width=True,hide_index=True)
st.caption('모의투자용이며 수익을 보장하지 않습니다.')
