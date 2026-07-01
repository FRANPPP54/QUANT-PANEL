"""
Quant Panel Web v3.2 — Streamlit Cloud
Fuentes: KuCoin (primario) → CoinPaprika (fallback) → CoinGecko (supply/ATH)
"""
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import os

import streamlit as st

try:
    import requests
except ImportError:
    st.error("pip install requests")
    st.stop()

st.set_page_config(page_title="Quant Panel",page_icon="⚡",layout="centered",initial_sidebar_state="collapsed")

# Funciona en Streamlit Cloud (st.secrets) Y en Render/otros (variables de entorno)
def get_secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)

ANTHROPIC_KEY = get_secret("ANTHROPIC_KEY", "")
KUCOIN_BASE = "https://api.kucoin.com/api/v1"
CP_BASE = "https://api.coinpaprika.com/v1"
CG_BASE = "https://api.coingecko.com/api/v3"
MIN_VOL = 25_000
MAX_TOKENS = 604
API_DELAY = 0.08
STABLECOINS = {"usdt","usdc","busd","dai","tusd","fdusd","usdd","usdp","frax","eur","gbp","try","brl","usde","pyusd","gusd","lusd","susd","usd1","usdb","usdttrc20"}
EMA_LEN=50; RSI_LEN=10; RSI_OS=45; RSI_OB=65
VOL_LEN=14; VOL_MULT=1.5; ATR_LEN=14; SL_M=3.0; TP_M=4.5
SESSION = requests.Session()

st.markdown("""<style>
.main .block-container{padding:1rem 1rem 2rem 1rem;max-width:480px}
.stTabs [data-baseweb="tab-list"]{gap:2px}
.stTabs [data-baseweb="tab"]{padding:8px 14px;font-size:13px}
.card{background:#111827;border-radius:12px;padding:12px 14px;margin-bottom:10px;border:1px solid #1e293b}
.card-green{background:#052e16;border-radius:12px;padding:12px 14px;margin-bottom:10px;border:1px solid #166534}
.tag-pump{background:#7c2020;color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}
.tag-bot{background:#4c1d95;color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600}
.tag-score{background:#1c1917;color:#f59e0b;border-radius:6px;padding:2px 8px;font-size:11px}
.tag-green{background:#064e3b;color:#10b981;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}
.tag-yellow{background:#422006;color:#f59e0b;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}
.tag-red{background:#450a0a;color:#ef4444;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}
.t-green{color:#10b981;font-weight:600}.t-red{color:#ef4444;font-weight:600}
.t-yellow{color:#f59e0b;font-weight:600}.t-sub{color:#64748b;font-size:12px}
.divider{border-top:1px solid #1e293b;margin:8px 0}
h1{font-size:1.5rem!important}h3{font-size:1rem!important;margin-bottom:4px!important}
.info-box{background:#0f172a;border:1px solid #1e3a5f;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:12px;color:#93c5fd}
</style>""", unsafe_allow_html=True)

# ── Indicadores ──
def calc_ema(v,p):
    if len(v)<p: return []
    k=2.0/(p+1); r=[sum(v[:p])/p]
    for x in v[p:]: r.append(x*k+r[-1]*(1-k))
    return r

def calc_rsi(c,p):
    if len(c)<p+2: return []
    d=[c[i]-c[i-1] for i in range(1,len(c))]
    g=[max(x,0.) for x in d]; l=[abs(min(x,0.)) for x in d]
    ag=sum(g[:p])/p; al=sum(l[:p])/p; r=[]
    for i in range(p,len(d)):
        ag=(ag*(p-1)+g[i])/p; al=(al*(p-1)+l[i])/p
        r.append(100. if al==0 else 100.-100./(1.+ag/al))
    return r

def calc_sma(v,p):
    if len(v)<p: return []
    return [sum(v[i-p:i])/p for i in range(p,len(v)+1)]

def calc_atr(c,p):
    d=[abs(c[i]-c[i-1]) for i in range(1,len(c))]
    if len(d)<p: return None
    a=sum(d[:p])/p
    for x in d[p:]: a=(a*(p-1)+x)/p
    return a

def chop_metrics(c):
    if len(c)<20: return None
    d=[abs(c[i+1]-c[i]) for i in range(len(c)-1)]
    path=sum(d); net=abs(c[-1]-c[0]); p0=c[0]
    eps=max(p0*0.001,1e-9); chop=min(path/max(net,eps),8.)
    ret=[(c[i+1]-c[i])/c[i] for i in range(len(c)-1)]
    m=sum(ret)/len(ret); vol=(sum((r-m)**2 for r in ret)/len(ret))**.5*100
    return {"chop":round(chop,2),"vol":round(vol,2),"range":round((max(c)-min(c))/p0*100,2),"net":round((c[-1]-c[0])/c[0]*100,2)}

# ── Pump/Dump ──
def detectar_pump_dump(closes,volumes,change_24h):
    if len(closes)<24 or len(volumes)<24: return None
    try:
        c_now=closes[-1]
        c_1h=closes[-2] if len(closes)>1 else c_now
        c_4h=closes[-4] if len(closes)>4 else c_now
        move_1h=(c_now-c_1h)/max(c_1h,1e-9)*100
        move_4h=(c_now-c_4h)/max(c_4h,1e-9)*100
        vol_now=sum(volumes[-3:])/3
        vol_base=sum(volumes[-24:-3])/21
        vol_ratio=vol_now/max(vol_base,1e-9)
        res={"tipo":None,"fase":None,"move_1h":round(move_1h,1),"move_4h":round(move_4h,1),"vol_ratio":round(vol_ratio,1)}
        if move_1h>5 and vol_ratio>2.0:
            res["tipo"]="PUMP"; res["fase"]="EN CURSO"
        elif move_4h>10 and move_1h<2 and vol_ratio>1.3:
            res["tipo"]="PUMP"; res["fase"]="CONSOLIDANDO"
        elif change_24h>15 and vol_ratio<0.7 and move_1h<0:
            res["tipo"]="PUMP"; res["fase"]="AGOTADO"
        elif move_1h<-5 and vol_ratio>2.0:
            res["tipo"]="DUMP"; res["fase"]="EN CURSO"
        elif move_4h<-10 and move_1h>-2 and vol_ratio>1.3:
            res["tipo"]="DUMP"; res["fase"]="FRENANDO"
        elif change_24h<-15 and vol_ratio<0.7 and move_1h>0:
            res["tipo"]="DUMP"; res["fase"]="POSIBLE SUELO"
        return res if res["tipo"] else None
    except: return None

# ── Price Action ──
def pa_estructura(closes,n=20):
    if len(closes)<n: return "INDEFINIDA",0.0
    c=closes[-n:]
    highs=[c[i] for i in range(1,len(c)-1) if c[i]>c[i-1] and c[i]>c[i+1]]
    lows=[c[i] for i in range(1,len(c)-1) if c[i]<c[i-1] and c[i]<c[i+1]]
    if len(highs)<2 or len(lows)<2: return "LATERAL",0.3
    ht=highs[-1]>highs[-2]; lt=lows[-1]>lows[-2]
    if ht and lt:
        f=min((highs[-1]-highs[-2])/highs[-2]*10+(lows[-1]-lows[-2])/lows[-2]*10,1.0)
        return "ALCISTA (HH/HL)",round(f,2)
    if not ht and not lt:
        f=min((highs[-2]-highs[-1])/highs[-2]*10+(lows[-2]-lows[-1])/lows[-2]*10,1.0)
        return "BAJISTA (LH/LL)",round(f,2)
    return "LATERAL",0.3

def pa_patron_velas(closes):
    try:
        if len(closes)<5: return "Sin datos","⚪"
        c=closes[-4:]; d=[c[i+1]-c[i] for i in range(3)]
        if len(d)<3 or d[1]==0: return "Sin patron claro","⚪"
        patrones=[]
        if abs(d[2])<abs(d[1])*0.1 and abs(d[2])<abs(d[0])*0.1: patrones.append(("Doji","⚪"))
        if d[0]>0 and d[1]>0 and d[2]>0: patrones.append(("3 velas verdes","🟢"))
        if d[0]<0 and d[1]<0 and d[2]<0: patrones.append(("3 velas rojas","🔴"))
        if d[1]<0 and d[2]>0 and abs(d[2])>abs(d[1])*1.2: patrones.append(("Envolvente alcista","🟢"))
        if d[1]>0 and d[2]<0 and abs(d[2])>abs(d[1])*1.2: patrones.append(("Envolvente bajista","🔴"))
        if d[1]<0 and d[2]>abs(d[1])*1.5: patrones.append(("Rebote fuerte","🟢"))
        if d[1]>0 and abs(d[2])>d[1]*1.5 and d[2]<0: patrones.append(("Rechazo bajista","🔴"))
        return patrones[0] if patrones else ("Sin patron claro","⚪")
    except: return "Sin datos","⚪"

def pa_calidad(closes,n=10):
    if len(closes)<n+3: return 0.5
    imp=closes[-n:]
    verdes=[imp[i+1]-imp[i] for i in range(len(imp)-1) if imp[i+1]>imp[i]]
    rojas=[imp[i]-imp[i+1] for i in range(len(imp)-1) if imp[i+1]<imp[i]]
    tv=sum(verdes)/len(verdes) if verdes else 0
    tr=sum(rojas)/len(rojas) if rojas else 0
    rv=tv/max(tr,1e-9)
    path=sum(abs(imp[i+1]-imp[i]) for i in range(len(imp)-1))
    net=abs(imp[-1]-imp[0])
    ef=net/max(path,1e-9)
    return round(min(rv*0.5+ef*0.5,1.0),2)

def pa_sr(closes,n=40):
    if len(closes)<10: return [],[]
    cur=closes[-1]; niveles=[]
    for i in range(1,min(n,len(closes))-1):
        idx=-(i+1); h=closes[idx]; hp=closes[idx-1]; hn=closes[idx+1]
        if h>hp and h>hn: niveles.append(("R",h))
        if h<hp and h<hn: niveles.append(("S",h))
    agr=[]
    for t,p in sorted(niveles,key=lambda x:x[1]):
        merged=False
        for g in agr:
            if abs(p-g[1])/max(g[1],1e-9)<0.015: merged=True; break
        if not merged: agr.append([t,p])
    sop=sorted([p for t,p in agr if p<cur],reverse=True)[:2]
    res=sorted([p for t,p in agr if p>cur])[:2]
    return sop,res

def analizar_pa(closes,modo_rapido=False):
    est,fuerza=pa_estructura(closes)
    cal=pa_calidad(closes)
    patron,patron_emoji=("--","⚪") if modo_rapido else pa_patron_velas(closes)
    sop,res=([],[]) if modo_rapido else pa_sr(closes)
    alcista="ALCISTA" in est; bajista="BAJISTA" in est
    if alcista and cal>=0.55: v,c,col="✅ Impulso alcista de calidad","Alta","green"
    elif alcista: v,c,col="⚠️ Alcista pero movimiento debil","Media","yellow"
    elif bajista and cal>=0.55: v,c,col="🔴 Tendencia bajista confirmada","Alta","red"
    elif bajista: v,c,col="⚠️ Bajista — rebote posible","Media","yellow"
    elif "LATERAL" in est: v,c,col="↔️ Lateral — ideal para Grid","Media","yellow"
    else: v,c,col="⚪ Estructura indefinida","Baja","sub"
    return {"veredicto":v,"confianza":c,"color":col,"estructura":est,"fuerza":fuerza,"calidad":cal,"patron":patron,"patron_emoji":patron_emoji,"soportes":sop,"resistencias":res}

# ── Smart Entry ──
def fmt_p(v):
    if v is None: return "N/A"
    if v<0.0001: return f"${v:.8f}"
    if v<1: return f"${v:.4f}"
    return f"${v:,.2f}"

def smart_entry_cp(closes,volumes,pa=None):
    base={"fases":{1:False,2:False,3:False,4:False},"vals":{},"fases_ok":0,"ok":False,"sl":None,"tp":None,"atr":None,"precio":None}
    if not closes or len(closes)<EMA_LEN+RSI_LEN+5: return base
    cur=closes[-1]; base["precio"]=cur
    e50s=calc_ema(closes,EMA_LEN); e50=e50s[-1] if e50s else None
    f1=bool(e50 and cur>e50)
    base["fases"][1]=f1; base["vals"][1]=f"Precio {fmt_p(cur)} | EMA50 {fmt_p(e50)}"
    r10s=calc_rsi(closes,RSI_LEN); r10=r10s[-1] if r10s else None
    f2=bool(r10 and RSI_OS<r10<RSI_OB)
    base["fases"][2]=f2; base["vals"][2]=f"RSI(10)={r10:.1f}" if r10 else "N/A"
    if len(volumes)>=VOL_LEN+24:
        vol_24h=sum(volumes[-24:])/24; vol_prev=sum(volumes[-VOL_LEN-24:-24])/VOL_LEN
        vr=round(vol_24h/vol_prev,2) if vol_prev>0 else 0
        f3=vr>=1.1; base["vals"][3]=f"Vol 24h={vr}x vs historico (min 1.1x)"
    else:
        vsma=calc_sma(volumes,VOL_LEN); vm=vsma[-1] if vsma else None
        vr=round(volumes[-1]/vm,2) if vm and vm>0 else 0
        f3=vr>=VOL_MULT; base["vals"][3]=f"Vol ratio={vr}x (min {VOL_MULT}x)"
    base["fases"][3]=f3
    pa_l=pa or analizar_pa(closes[-50:],modo_rapido=True)
    f4="ALCISTA" in pa_l["estructura"] and pa_l["calidad"]>=0.55
    base["fases"][4]=f4; base["vals"][4]=f"{pa_l['estructura']} cal={pa_l['calidad']}"
    atr=calc_atr(closes,ATR_LEN)
    if atr: base["atr"]=round(atr,8); base["sl"]=round(cur-atr*SL_M,8); base["tp"]=round(cur+atr*TP_M,8)
    n=sum(1 for v in base["fases"].values() if v)
    base["fases_ok"]=n; base["ok"]=(n==4)
    return base

def smart_entry_lp(closes,pa=None):
    base={"fases":{1:False,2:False,3:False},"vals":{},"fases_ok":0,"ok":False,"sl":None,"tp":None,"atr":None,"precio":None}
    if not closes or len(closes)<210: return base
    cur=closes[-1]; base["precio"]=cur
    sma50s=calc_sma(closes,50); sma200s=calc_sma(closes,200)
    sma50=sma50s[-1] if sma50s else None; sma200=sma200s[-1] if sma200s else None
    f1=bool(sma50 and sma200 and sma50>sma200)
    if sma50 and sma200:
        dist=round((sma50-sma200)/sma200*100,2)
        base["vals"][1]=f"SMA50={fmt_p(sma50)} SMA200={fmt_p(sma200)} dist={dist:+.2f}%"
    else: base["vals"][1]="Sin datos suficientes"
    base["fases"][1]=f1
    rsi14s=calc_rsi(closes,14); r14=rsi14s[-1] if rsi14s else None
    f2=bool(r14 and 40<r14<70)
    base["fases"][2]=f2; base["vals"][2]=f"RSI(14d)={r14:.1f}" if r14 else "N/A"
    pa_l=pa or analizar_pa(closes[-50:],modo_rapido=True)
    f3="ALCISTA" in pa_l["estructura"] and pa_l["calidad"]>=0.50
    base["fases"][3]=f3; base["vals"][3]=f"{pa_l['estructura']} cal={pa_l['calidad']}"
    atr=calc_atr(closes,14)
    if atr: base["atr"]=round(atr,4); base["sl"]=round(cur-atr*2.0,4); base["tp"]=round(cur+atr*3.0,4)
    n=sum(1 for v in base["fases"].values() if v)
    base["fases_ok"]=n; base["ok"]=(n==3)
    return base

# ── ML ──
def senal_lorentziana(closes,lookahead=4,k=8):
    if len(closes)<60: return None
    rsi14=calc_rsi(closes,14); ema20=calc_ema(closes,20)
    n=min(len(rsi14),len(ema20),len(closes))
    if n<lookahead+k+5: return None
    def norm(lst):
        mn,mx=min(lst),max(lst); r=mx-mn
        return [0.5 if r==0 else (x-mn)/r for x in lst]
    c_al=closes[-n:]; rsi_al=norm(rsi14[-n:]); ema_al=norm(ema20[-n:])
    muestras=n-lookahead
    etiquetas=[1 if c_al[i+lookahead]>c_al[i] else -1 for i in range(muestras)]
    actual=[rsi_al[-1],ema_al[-1]]; distancias=[]
    for i in range(muestras):
        v=[rsi_al[i],ema_al[i]]
        d=sum(math.log(1+abs(a-b)) for a,b in zip(actual,v))
        distancias.append((d,etiquetas[i]))
    distancias.sort(key=lambda x:x[0])
    pred=sum(lbl for _,lbl in distancias[:k])
    if pred>=k*0.5: senal="🟢 COMPRA (ML)"
    elif pred<=-k*0.5: senal="🔴 VENTA (ML)"
    else: senal="⚪ NEUTRAL (ML)"
    return {"senal":senal,"pred":pred,"k":k}

# ── APIs ──
def api_get(url,params=None,timeout=25,retries=3):
    headers={"User-Agent":"Mozilla/5.0 (compatible; QuantPanel/3.2)"}
    for attempt in range(retries):
        try:
            r=SESSION.get(url,params=params,headers=headers,timeout=timeout)
            if r.status_code==429: time.sleep(6*(attempt+1)); continue
            if r.status_code in (400,404): return None
            r.raise_for_status(); return r
        except requests.exceptions.Timeout: time.sleep(1.5*(attempt+1))
        except Exception: time.sleep(0.6)
    return None

@st.cache_data(ttl=60)
def kucoin_get_pool():
    r=api_get(f"{KUCOIN_BASE}/market/allTickers",timeout=30)
    if r is None: return None,"kucoin_fail"
    try:
        data=r.json(); tickers=data.get("data",{}).get("ticker",[])
        pool=[]
        for t in tickers:
            sym=t.get("symbol","")
            if not sym.endswith("-USDT"): continue
            base=sym[:-5].lower()
            if base in STABLECOINS: continue
            vol=float(t.get("volValue",0) or 0)
            price=float(t.get("last",0) or 0)
            if vol<MIN_VOL or price<=0: continue
            change=float(t.get("changeRate",0) or 0)*100
            pool.append({"symbol":base.upper(),"kucoin_sym":sym,"price":price,"vol":vol,"change_24h":change})
        pool.sort(key=lambda x:x["vol"],reverse=True)
        return pool[:MAX_TOKENS],"kucoin"
    except Exception: return None,"kucoin_parse"

@st.cache_data(ttl=180)
def kucoin_ohlcv(symbol,interval="1hour",limit=168):
    now=int(time.time())
    start=now-(168*3600 if interval=="1hour" else 200*86400)
    r=api_get(f"{KUCOIN_BASE}/market/candles",params={"symbol":symbol,"type":interval,"startAt":start,"endAt":now},timeout=10)
    if r is None: return None,None
    try:
        klines=r.json().get("data",[])
        if not klines: return None,None
        klines=list(reversed(klines))
        return [float(k[2]) for k in klines],[float(k[5]) for k in klines]
    except Exception: return None,None

@st.cache_data(ttl=300)
def coinpaprika_get_pool():
    r=api_get(f"{CP_BASE}/tickers",params={"quotes":"USD","limit":MAX_TOKENS},timeout=20)
    if r is None: return None,"cp_fail"
    try:
        data=r.json(); pool=[]
        for coin in data:
            sym=(coin.get("symbol") or "").lower()
            if sym in STABLECOINS: continue
            q=coin.get("quotes",{}).get("USD",{})
            vol=q.get("volume_24h") or 0; price=q.get("price") or 0
            if vol<MIN_VOL or price<=0: continue
            pool.append({"symbol":coin["symbol"].upper(),"cp_id":coin["id"],"kucoin_sym":coin["symbol"].upper()+"-USDT","price":price,"vol":vol,"change_24h":q.get("percent_change_24h") or 0})
        pool.sort(key=lambda x:x["vol"],reverse=True)
        return pool[:MAX_TOKENS],"coinpaprika"
    except Exception: return None,"cp_parse"

@st.cache_data(ttl=600)
def coinpaprika_ohlcv(cp_id,days=7):
    end=datetime.utcnow().strftime("%Y-%m-%d")
    start=(datetime.utcnow()-timedelta(days=days)).strftime("%Y-%m-%d")
    r=api_get(f"{CP_BASE}/coins/{cp_id}/ohlcv/historical",params={"start":start,"end":end,"quote":"usd"},timeout=15)
    if r is None: return None,None
    try:
        data=r.json()
        if not data or isinstance(data,dict): return None,None
        return [float(d["close"]) for d in data],[float(d["volume"]) for d in data]
    except Exception: return None,None

@st.cache_data(ttl=1800)
def coinpaprika_search_coin_id(sym):
    r=api_get(f"{CP_BASE}/search",params={"q":sym,"c":"currencies"},timeout=12)
    if r is None: return None
    try:
        data=r.json(); currencies=data.get("currencies",[])
        exact=[c for c in currencies if (c.get("symbol") or "").upper()==sym.upper()]
        if len(exact)==1: return exact[0].get("id")
        if exact:
            ranked=sorted(exact,key=lambda x:x.get("rank",10**9) or 10**9)
            return ranked[0].get("id")
        return currencies[0].get("id") if currencies else None
    except Exception: return None

def get_ohlcv(coin,largo_plazo=False):
    if largo_plazo:
        c,v=kucoin_ohlcv(coin.get("kucoin_sym",""),interval="1day",limit=200)
        if c and len(c)>=20: return c,v
        if coin.get("cp_id"):
            c,v=coinpaprika_ohlcv(coin["cp_id"],days=200)
            if c and len(c)>=20: return c,v
    else:
        c,v=kucoin_ohlcv(coin.get("kucoin_sym",""),interval="1hour",limit=168)
        if c and len(c)>=20: return c,v
        if coin.get("cp_id"):
            c,v=coinpaprika_ohlcv(coin["cp_id"],days=7)
            if c and len(c)>=20: return c,v
    return None,None

CG_MAP={"AAVE":"aave","UNI":"uniswap","LINK":"chainlink","MKR":"maker","BTC":"bitcoin","ETH":"ethereum","BNB":"binancecoin","SOL":"solana","ADA":"cardano","DOT":"polkadot","AVAX":"avalanche-2","MATIC":"matic-network","ATOM":"cosmos","NEAR":"near","FTM":"fantom","ALGO":"algorand","XLM":"stellar","XRP":"ripple","TRX":"tron","ARB":"arbitrum","OP":"optimism","APT":"aptos","SUI":"sui","INJ":"injective-protocol","TIA":"celestia","DOGE":"dogecoin","SHIB":"shiba-inu","PEPE":"pepe","LTC":"litecoin","BCH":"bitcoin-cash","HBAR":"hedera-hashgraph","SYN":"synapse-2","RUNE":"thorchain","HYPE":"hyperliquid","TAO":"bittensor","WIF":"dogwifcoin","BONK":"bonk","JUP":"jupiter-exchange-solana"}

@st.cache_data(ttl=3600)
def get_cg_id(sym):
    if sym.upper() in CG_MAP: return CG_MAP[sym.upper()]
    try:
        r=api_get(f"{CG_BASE}/coins/list",timeout=12)
        if r is None: return None
        coins=r.json(); m=[c for c in coins if c.get("symbol","").lower()==sym.lower()]
        if len(m)==1: return m[0]["id"]
        if len(m)>1:
            ids=",".join(c["id"] for c in m[:15]); time.sleep(1.2)
            r2=api_get(f"{CG_BASE}/coins/markets",params={"vs_currency":"usd","ids":ids,"order":"market_cap_desc"})
            if r2:
                d=r2.json()
                if d: return d[0]["id"]
    except Exception: pass
    return None

# ── CoinGecko: 1 sola llamada consolidada por token (evita 429 del plan publico) ──
@st.cache_data(ttl=900)
def get_cg_full(cg_id):
    """Trae TODO lo de CoinGecko en una sola llamada: market_data, tickers, community, developer, description."""
    if not cg_id: return None
    r=api_get(f"{CG_BASE}/coins/{cg_id}",
        params={"localization":"false","tickers":"true","market_data":"true",
                "community_data":"true","developer_data":"true"},timeout=20,retries=4)
    if r is None: return None
    try: return r.json()
    except Exception: return None

def get_supply(d):
    """Ahora recibe el JSON ya descargado por get_cg_full (no hace fetch propio)."""
    if not d: return None
    try:
        md=d.get("market_data",{})
        def fmt(v):
            if v is None: return "N/A"
            if v>=1e12: return f"{v/1e12:.2f}T"
            if v>=1e9: return f"{v/1e9:.2f}B"
            if v>=1e6: return f"{v/1e6:.2f}M"
            return f"{v:,.0f}"
        def pdate(s):
            if not s: return "N/A"
            try: return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%d/%m/%Y")
            except: return "N/A"
        circ=md.get("circulating_supply"); maxi=md.get("max_supply"); total=md.get("total_supply")
        ath=md.get("ath",{}).get("usd"); cur=md.get("current_price",{}).get("usd")
        pct=round((cur-ath)/ath*100,1) if ath and cur else None
        return {"max":fmt(maxi) if maxi else("∞" if not total else fmt(total)),"circ":fmt(circ),"ath":f"${ath:,.4f}" if ath else "N/A","ath_date":pdate(md.get("ath_date",{}).get("usd")),"pct_ath":f"{pct}%" if pct is not None else "N/A","cats":", ".join(d.get("categories",[])[:2]) or "N/A"}
    except Exception: return None

def get_fundamentals(d, sym):
    """Recibe el JSON ya descargado por get_cg_full (no hace fetch propio)."""
    if not d: return None
    try:
        md = d.get("market_data", {})
        def fmt_usd(v):
            if v is None: return "N/A"
            if v >= 1e9: return f"${v/1e9:.2f}B"
            if v >= 1e6: return f"${v/1e6:.2f}M"
            if v >= 1e3: return f"${v/1e3:.0f}K"
            return f"${v:,.0f}"
        mc   = md.get("market_cap", {}).get("usd")
        fdv  = md.get("fully_diluted_valuation", {}).get("usd")
        circ = md.get("circulating_supply")
        total= md.get("total_supply")
        maxi = md.get("max_supply")
        rank = d.get("market_cap_rank")
        cats = d.get("categories", [])
        fdv_mc = round(fdv/mc, 1) if fdv and mc and mc>0 else None
        supply_pct = round(circ/total*100, 1) if circ and total and total>0 else None
        tickers = d.get("tickers", [])[:5]
        exchanges = list(dict.fromkeys([t.get("market", {}).get("name","") for t in tickers if t.get("market",{}).get("name")]))[:3]
        return {
            "mc": fmt_usd(mc),
            "fdv": fmt_usd(fdv),
            "fdv_mc": fdv_mc,
            "rank": rank,
            "supply_pct": supply_pct,
            "cats": ", ".join(cats[:2]) or "N/A",
            "exchanges": exchanges,
            "mc_raw": mc or 0,
        }
    except Exception: return None

def get_utility_data(d):
    """Recibe el JSON ya descargado por get_cg_full (no hace fetch propio)."""
    if not d: return None
    try:
        desc = d.get("description", {}).get("en", "") or ""
        desc_clean = re.sub(r'<[^>]+>', '', desc)[:500]
        dev = d.get("developer_data", {})
        commits_4w = dev.get("commit_count_4_weeks") or 0
        stars = dev.get("stars") or 0
        forks = dev.get("forks") or 0
        comm = d.get("community_data", {})
        twitter = comm.get("twitter_followers") or 0
        reddit = comm.get("reddit_subscribers") or 0
        cats = d.get("categories", [])
        score = 0
        utility_cats = ["defi","infrastructure","layer","oracle","exchange","lending","yield","gaming","ai","nft","bridge","payment","privacy"]
        if any(any(u in c.lower() for u in utility_cats) for c in cats): score += 3
        if commits_4w > 50: score += 3
        elif commits_4w > 20: score += 2
        elif commits_4w > 5: score += 1
        if twitter > 500_000: score += 2
        elif twitter > 100_000: score += 1
        if stars > 1000: score += 2
        elif stars > 200: score += 1
        score = min(score, 10)
        def fmt_k(v):
            if v>=1e6: return f"{v/1e6:.1f}M"
            if v>=1e3: return f"{v/1e3:.0f}K"
            return str(v)
        return {
            "desc": desc_clean,
            "commits_4w": commits_4w,
            "stars": stars,
            "forks": forks,
            "twitter": fmt_k(twitter),
            "reddit": fmt_k(reddit),
            "cats": cats[:3],
            "utility_score": score,
        }
    except Exception: return None

def get_utility_ai(sym, desc, cats, news):
    """Usa Claude IA para evaluar utilidad y futuro del token."""
    if not ANTHROPIC_KEY: return None
    cats_txt = ", ".join(cats) if cats else "N/A"
    news_txt = "\n".join(f"- {n['title']}" for n in news[:3]) if news else "Sin noticias recientes"
    prompt = (
        f"Token: {sym}\n"
        f"Sector: {cats_txt}\n"
        f"Descripcion: {desc[:300]}\n"
        f"Noticias recientes:\n{news_txt}\n\n"
        f"Responde en espanol con exactamente este formato:\n"
        f"UTILIDAD: [que problema resuelve en 1 linea]\n"
        f"ADOPCION: [nivel actual: Baja/Media/Alta + razon breve]\n"
        f"FUTURO: [perspectiva 6-12 meses: Negativo/Neutral/Positivo + razon]\n"
        f"RIESGO: [principal riesgo en 1 linea]"
    )
    try:
        r = SESSION.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":300,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]},timeout=30)
        blocks = r.json().get("content", [])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except Exception: return None

@st.cache_data(ttl=1800)
def get_unlocks(sym):
    try:
        r=api_get(f"https://token.unlocks.app/api/token/{sym.lower()}",timeout=10)
        if r is None: return []
        evs=r.json().get("unlockEvents") or r.json().get("events") or []
        now=datetime.now(timezone.utc).timestamp(); result=[]
        for ev in evs:
            ts=ev.get("timestamp") or ev.get("date")
            if ts is None: continue
            if isinstance(ts,str):
                try: ts=datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()
                except: continue
            days=(ts-now)/86400
            if 0<days<=90:
                result.append({"date":datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%d/%m/%Y"),"days":round(days),"cat":ev.get("category") or "Unlock","urgent":days<=14})
        result.sort(key=lambda x:x["days"]); return result[:5]
    except Exception: return []

@st.cache_data(ttl=1800)
def get_news(sym, name=""):
    feeds=[("CoinDesk","https://www.coindesk.com/arc/outboundfeeds/rss/"),("CoinTelegraph","https://cointelegraph.com/rss"),("Decrypt","https://decrypt.co/feed"),("TheBlock","https://www.theblock.co/rss.xml")]
    pos_words=["surge","rally","pump","gain","rise","bull","high","record","launch","approved"]
    neg_words=["crash","drop","fall","plunge","bear","hack","exploit","scam","delist","decline"]
    s=sym.lower(); n=name.lower().strip(); found=[]
    for src,url in feeds:
        try:
            r=SESSION.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code!=200: continue
            root=ET.fromstring(r.content)
            items=root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items:
                t=(item.findtext("title") or "").strip(); desc=(item.findtext("description") or "").strip()
                blob=(t+" "+desc).lower()
                match_sym=re.search(r'\b'+re.escape(s)+r'\b',blob)
                match_name=bool(n) and len(n)>=3 and re.search(r'\b'+re.escape(n)+r'\b',blob)
                if not match_sym and not match_name: continue
                tl=t.lower()
                pos=sum(1 for k in pos_words if k in tl); neg=sum(1 for k in neg_words if k in tl)
                sent="🟢" if pos>neg else("🔴" if neg>pos else "⚪")
                found.append({"title":t[:85],"src":src,"sent":sent})
        except Exception: continue
    seen,uniq=set(),[]
    for n2 in found:
        k=n2["title"][:30].lower()
        if k not in seen: seen.add(k); uniq.append(n2)
    return uniq[:5]

def get_ai(sym,news):
    if not ANTHROPIC_KEY: return None
    txt="\n".join(f"- {n['title']}" for n in news)
    prompt=f"Token: {sym}\nTitulares: {txt}\nResponde en espanol:\nPOSITIVO: punto1 | punto2\nNEGATIVO: riesgo1 | riesgo2\nEVENTO: evento clave"
    try:
        r=SESSION.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},json={"model":"claude-sonnet-4-6","max_tokens":250,"tools":[{"type":"web_search_20250305","name":"web_search"}],"messages":[{"role":"user","content":prompt}]},timeout=25)
        blocks=r.json().get("content",[])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except Exception: return None

# ── Scoring ──
def score_token(coin,closes,volumes):
    m=chop_metrics(closes[-100:] if len(closes)>100 else closes)
    if not m: return None
    liq=math.log10(max(coin["vol"],1)); chop=m["chop"]; vol=m["vol"]; net=m["net"]; c24=coin["change_24h"]
    e50s=calc_ema(closes,EMA_LEN); trend_ok=closes[-1]>e50s[-1] if e50s else None
    bajada=max(0,-c24); subida=max(0,c24)
    pen_b=bajada*.5 if bajada<=15 else 7.5+(bajada-15)
    pen_s=subida*.5 if subida<=15 else 7.5+(subida-15)
    gl=chop*8+vol*2+liq*2+subida*.3-pen_b; gs=chop*8+vol*2+liq*2+bajada*.3-pen_s
    bil=max(net,0)*5+vol*1.5+liq*2; bis=max(-net,0)*5+vol*1.5+liq*2
    il=bil if trend_ok is None or trend_ok else bil*.3
    is_=bis if trend_ok is None or not trend_ok else bis*.3
    dip=min(max(-c24,0),30); pmp=min(max(c24,0),30)
    dl=dip*3+vol*1.5+liq*2+chop; ds=pmp*3+vol*1.5+liq*2+chop
    if net<-15: dl*=.4
    if net>15: ds*=.4
    scores={"GRID LONG":round(gl,1),"GRID SHORT":round(gs,1),"INF LONG":round(il,1),"INF SHORT":round(is_,1),"DCA LONG":round(dl,1),"DCA SHORT":round(ds,1)}
    best=max(scores,key=scores.get)
    pa=analizar_pa(closes[-50:],modo_rapido=True)
    se=smart_entry_cp(closes,volumes,pa=pa)
    pd=detectar_pump_dump(closes,volumes,c24)
    return {"token":coin["symbol"],"price":coin["price"],"change_24h":c24,"chop":chop,"vol_h":vol,"range":m["range"],"liq_m":round(coin["vol"]/1e6,1),"trend_ok":trend_ok,"pa":pa,"se":se,"pd":pd,"best":best,"best_score":round(scores[best],1),"vol_raw":coin["vol"]}

# ── UI Helpers ──
def fmt_vol(v):
    if v>=1e9: return f"${v/1e9:.1f}B"
    if v>=1e6: return f"${v/1e6:.1f}M"
    if v>=1e3: return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"

def pa_card_html(pa):
    col_map={"green":"#10b981","red":"#ef4444","yellow":"#f59e0b","sub":"#64748b"}
    col=col_map.get(pa["color"],"#64748b")
    sop=" | ".join(fmt_p(s) for s in pa["soportes"]) if pa["soportes"] else "N/A"
    res=" | ".join(fmt_p(r) for r in pa["resistencias"]) if pa["resistencias"] else "N/A"
    patron_html=""
    if pa.get("patron") and pa["patron"] not in ("--","Sin datos"):
        patron_html=f'<div style="margin-top:4px;font-size:12px">{pa["patron_emoji"]} {pa["patron"]}</div>'
    return (f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📐 PRICE ACTION</div>'
            f'<div style="color:{col};font-size:13px;font-weight:600;margin-bottom:6px">{pa["veredicto"]}</div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap" class="t-sub"><span>Est: {pa["estructura"]}</span><span>Cal: {pa["calidad"]}</span><span>Conf: {pa["confianza"]}</span></div>'
            f'{patron_html}<div class="divider"></div>'
            f'<div style="font-size:12px"><span class="t-green">Sop: {sop}</span></div>'
            f'<div style="font-size:12px"><span class="t-red">Res: {res}</span></div></div>')

def se_card_html(se,fases_total=4):
    n=se["fases_ok"]
    if n==fases_total: cab,bdr=f"🟢 ENTRADA VALIDA — {n}/{fases_total}","#166534"
    elif n==fases_total-1: cab,bdr=f"🟡 CASI LISTO — {n}/{fases_total}","#854d0e"
    else: cab,bdr=f"🔴 ESPERAR — {n}/{fases_total}","#7c2020"
    nombres_cp={1:"Tendencia > EMA50",2:"Momentum RSI 45-65",3:"Volumen sostenido",4:"Price Action"}
    nombres_lp={1:"SMA50 > SMA200",2:"RSI(14d) 40-70",3:"Price Action alcista"}
    nombres=nombres_lp if fases_total==3 else nombres_cp
    filas=""
    for num in range(1,fases_total+1):
        ok=se["fases"][num]; ic="✅" if ok else "❌"; col="#10b981" if ok else "#ef4444"
        filas+=f'<div style="margin-bottom:4px"><span style="color:{col}">{ic} F{num}: {nombres.get(num,"")}</span><br><span class="t-sub" style="padding-left:16px">{se["vals"].get(num,"")}</span></div>'
    sl_tp=""
    if n==fases_total and se.get("sl") and se.get("tp") and se.get("precio"):
        rr=round((se["tp"]-se["precio"])/max(se["precio"]-se["sl"],1e-9),1)
        sl_tp=(f'<div class="divider"></div><div style="display:flex;justify-content:space-around">'
               f'<span class="t-red">SL {fmt_p(se["sl"])}</span><span class="t-green">TP {fmt_p(se["tp"])}</span></div>'
               f'<div style="text-align:center;margin-top:4px" class="t-sub">ATR={fmt_p(se.get("atr"))} · R/R=1:{rr}</div>')
    return (f'<div class="card" style="border-color:{bdr}"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🚦 SMART ENTRY — {fases_total} FASES</div>'
            f'<div style="font-weight:700;font-size:14px;margin-bottom:8px">{cab}</div><div class="divider"></div>{filas}{sl_tp}</div>')

# ── Potencial IA ──
def get_potencial_ai(tokens_data):
    """Claude evalúa los mejores tokens por potencial de inversión."""
    if not ANTHROPIC_KEY or not tokens_data: return None
    resumen = ""
    for t in tokens_data[:8]:
        resumen += (f"Token: {t['token']} | Precio: {fmt_p(t['price'])} | "
                   f"Cambio24h: {t['change_24h']:+.1f}% | Score: {t['best_score']} | "
                   f"Bot: {t['best']} | PA: {t['pa']['veredicto'][:30]} | "
                   f"Fases: {t['se']['fases_ok']}/4\n")
    prompt = (
        f"Eres un analista de criptomonedas experto en bots de trading.\n"
        f"Analiza estos tokens escaneados del mercado y selecciona los 3 con mayor potencial:\n\n"
        f"{resumen}\n"
        f"Para cada seleccionado responde exactamente asi:\n"
        f"TOKEN: [simbolo]\n"
        f"RAZON: [por que tiene potencial en 1 linea]\n"
        f"ESTRATEGIA: [Grid/DCA/Infinity Long/Short + parametros clave]\n"
        f"RIESGO: [Bajo/Medio/Alto + razon]\n"
        f"---\n"
        f"Responde en espanol. Solo los 3 mejores."
    )
    try:
        r = SESSION.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":500,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]},timeout=35)
        blocks = r.json().get("content",[])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except Exception: return None

# ── UI Principal ──
st.markdown("# ⚡ Quant Panel")
st.markdown('<p class="t-sub">Screener · Pionex · v3.2 — KuCoin + CoinPaprika</p>',unsafe_allow_html=True)
tab1,tab2,tab3,tab4=st.tabs(["📡 Scanner","📊 Analisis","🌟 Potencial","⚙️ Ajustes"])

with tab1:
    st.markdown("### Mejores tokens para Grid Bot")
    vol_opciones={"25K  — todos los tokens":25_000,"250K — tokens activos":250_000,"500K — balance":500_000,"1M   — mayor liquidez":1_000_000,"5M   — solo grandes":5_000_000}
    vol_label=st.selectbox("💧 Volumen minimo 24h",list(vol_opciones.keys()),index=2)
    vol_min=vol_opciones[vol_label]
    top_n=st.slider("Top resultados a mostrar",min_value=5,max_value=50,value=10,step=5)
    st.session_state.setdefault("scan_results",[])
    st.session_state.setdefault("scan_total",0)
    st.session_state.setdefault("scan_source","")
    st.session_state.setdefault("last_scan",0)

    # Auto-refresh selector
    refresh_opciones = {"⏸️ Manual":0, "🔄 5 min":300, "🔄 15 min":900, "🔄 30 min":1800}
    refresh_label = st.selectbox("⏱️ Auto-refresh", list(refresh_opciones.keys()), index=0)
    refresh_sec = refresh_opciones[refresh_label]

    # Mostrar tiempo desde ultimo scan
    if st.session_state.last_scan > 0:
        elapsed_since = int(time.time() - st.session_state.last_scan)
        mins = elapsed_since // 60; secs = elapsed_since % 60
        st.caption(f"🕐 Ultimo scan hace {mins}m {secs}s")

    # Auto-trigger si paso el intervalo
    auto_trigger = (refresh_sec > 0 and
                    st.session_state.last_scan > 0 and
                    time.time() - st.session_state.last_scan >= refresh_sec)

    c1,c2=st.columns([2,1])
    with c1: run_btn=st.button("🔍 Escanear ahora",use_container_width=True,type="primary")
    with c2:
        if st.session_state.scan_results: st.caption(f"✅ {st.session_state.scan_total} tokens")

    # Auto-refresh — solo muestra contador, no hace rerun automático en Render
    if refresh_sec > 0 and st.session_state.last_scan > 0:
        time_left = refresh_sec - int(time.time() - st.session_state.last_scan)
        if time_left > 0:
            st.caption(f"🔄 Próximo refresh en {time_left//60}m {time_left%60}s")
        else:
            st.caption("🔄 Listo para escanear — toca Escanear ahora")
    if st.session_state.scan_source:
        st.markdown(f'<div class="info-box">Fuente: <strong>{st.session_state.scan_source}</strong> · vol ≥ {fmt_vol(vol_min)} · PA · Smart Entry 4F</div>',unsafe_allow_html=True)

    if run_btn:
        with st.status("Escaneando mercado...",expanded=True) as status:
            st.write("📡 Conectando a KuCoin...")
            pool_raw,src=kucoin_get_pool()
            if not pool_raw: pool_raw,src=coinpaprika_get_pool()
            if not pool_raw: st.error("❌ KuCoin y CoinPaprika fallaron."); st.stop()
            pool=[c for c in pool_raw if c["vol"]>=vol_min][:MAX_TOKENS]
            if not pool: st.error(f"❌ Ningun token con vol ≥ {fmt_vol(vol_min)}."); st.stop()
            src_label="🟢 KuCoin" if "kucoin" in src else "🔵 CoinPaprika"
            st.write(f"✅ {src_label} · {len(pool)} pares (vol ≥ {fmt_vol(vol_min)})")
            bar=st.progress(0); results=[]; errores=0; t_start=time.time()
            for i,coin in enumerate(pool):
                bar.progress((i+1)/len(pool))
                if i%40==0:
                    elapsed=time.time()-t_start
                    rem=elapsed/(i+1)*(len(pool)-i-1) if i>0 else 0
                    st.write(f"⏳ {i+1}/{len(pool)} · {len(results)} validos · ~{int(rem)}s restantes")
                closes,volumes=get_ohlcv(coin)
                if closes is None or len(closes)<20: errores+=1; continue
                r=score_token(coin,closes,volumes)
                if r: results.append(r)
                if API_DELAY: time.sleep(API_DELAY)
            results.sort(key=lambda x:x["best_score"],reverse=True)
            st.session_state.scan_results=results
            st.session_state.scan_total=len(pool)
            st.session_state.scan_source=src_label
            st.session_state.last_scan=time.time()
            elapsed=round(time.time()-t_start)
            status.update(label=f"✅ {len(results)} tokens en {elapsed}s · {errores} sin datos",state="complete")

    for r in st.session_state.scan_results[:top_n]:
        pa=r["pa"]; se=r["se"]; pdet=se["ok"]; c24=r["change_24h"]; pd=r.get("pd")
        cc="t-green" if c24>=0 else "t-red"
        pt='<span class="tag-pump">🔥 PUMP</span>' if pdet else ""
        # Pump/Dump badge — construido como string simple sin f-string anidado
        if pd:
            pd_color="#10b981" if pd["tipo"]=="PUMP" else "#ef4444"
            pd_bg="#052e16" if pd["tipo"]=="PUMP" else "#450a0a"
            pd_icon="🚀" if pd["tipo"]=="PUMP" else "💥"
            pd_html='<div style="background:'+pd_bg+';border-radius:6px;padding:4px 8px;margin:4px 0;font-size:11px">'+pd_icon+' <strong style="color:'+pd_color+'">'+pd["tipo"]+" "+pd["fase"]+'</strong> <span style="color:#94a3b8">· 1h:'+str(pd["move_1h"])+'% 4h:'+str(pd["move_4h"])+'% Vol:'+str(pd["vol_ratio"])+'x</span></div>'
        else:
            pd_html=""
        n=se["fases_ok"]
        se_h=f'<span class="tag-green">🟢x{n}</span>' if n==4 else f'<span class="tag-yellow">🟡{n}/4</span>' if n==3 else f'<span class="tag-red">🔴{n}/4</span>'
        pac={"green":"#10b981","red":"#ef4444","yellow":"#f59e0b"}.get(pa["color"],"#64748b")
        slt=""
        if pdet:
            slt='<div class="divider"></div><div style="display:flex;justify-content:space-around"><span class="t-red">SL '+fmt_p(se.get("sl"))+'</span><span class="t-green">TP '+fmt_p(se.get("tp"))+'</span></div>'
        # Card construido con concatenacion — sin f-string multilinea
        card_class="card-green" if pdet else "card"
        card_html=(
            '<div class="'+card_class+'">'
            '<div style="display:flex;justify-content:space-between;align-items:center">'
            '<span style="font-size:17px;font-weight:700;color:#f1f5f9">'+r["token"]+'</span>'
            '<span style="display:flex;gap:6px;align-items:center"><span class="'+cc+'">'+f"{c24:+.1f}%"+'</span>'+pt+'</span>'
            '</div>'
            '<div style="color:#f59e0b;font-size:15px;margin:2px 0">'+fmt_p(r["price"])+'</div>'
            '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">'
            '<span class="tag-bot">'+r["best"]+'</span>'
            '<span class="tag-score">Score '+str(r["best_score"])+'</span>'+se_h
            +'</div>'
            '<div style="color:'+pac+';font-size:12px">'+pa["veredicto"]+'</div>'
            +pd_html+
            '<div class="t-sub">Chop '+str(r["chop"])+' · Vol '+f"{r['vol_h']:.1f}"+'% · '+str(r["liq_m"])+'M$</div>'
            +slt+'</div>'
        )
        st.markdown(card_html,unsafe_allow_html=True)
        # Botón afiliado Pionex
        pionex_url = f"https://www.pionex.com/es/signUp?r=oCNuZqFw"
        st.markdown(
            f'<a href="{pionex_url}" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:6px;font-size:12px;font-weight:700;margin-bottom:4px;text-decoration:none;">📈 Abrir {r["token"]} en Pionex</a>',
            unsafe_allow_html=True
        )
        if st.button(f"🔍 Analizar {r['token']}", key=f"btn_analisis_{r['token']}", use_container_width=True):
            st.session_state["analisis_sym"] = r["token"]
            st.session_state["analisis_trigger"] = True

with tab2:
    st.markdown("### Analisis Individual")
    modo=st.radio("Modo",["⚡ Corto Plazo (1H · dias)","📅 Largo Plazo (1D · semanas/meses)"],horizontal=True,label_visibility="collapsed")
    es_lp="Largo" in modo
    c1,c2=st.columns([3,1])
    with c1: sym_input=st.text_input("Ticker",placeholder="BTC, SOL, SYN...",label_visibility="collapsed").upper().strip()
    with c2: do_analyze=st.button("Analizar",type="primary",use_container_width=True)

    # Auto-trigger desde scanner
    auto_sym = st.session_state.get("analisis_sym", "") if st.session_state.get("analisis_trigger") else ""
    if st.session_state.get("analisis_trigger"):
        st.session_state["analisis_trigger"] = False

    if do_analyze and sym_input:
        pass
    elif auto_sym:
        sym_input = auto_sym
        do_analyze = True

    if do_analyze and sym_input:
        cargar_extra = True
        with st.status(f"Analizando {sym_input}...",expanded=True) as status:
            kucoin_symbol=sym_input+"-USDT"
            if es_lp:
                st.write("Velas diarias KuCoin (200d)...")
                c,v=kucoin_ohlcv(kucoin_symbol,interval="1day",limit=200)
            else:
                st.write("Velas 1h KuCoin (7d)...")
                c,v=kucoin_ohlcv(kucoin_symbol,interval="1hour",limit=168)
            fuente_analisis="KuCoin"
            if c is None or len(c)<20:
                st.write("KuCoin sin datos — probando CoinPaprika...")
                cp_id=coinpaprika_search_coin_id(sym_input)
                if cp_id:
                    days=200 if es_lp else 7
                    c,v=coinpaprika_ohlcv(cp_id,days=days)
                    if c and len(c)>=20: fuente_analisis="CoinPaprika"
            if c is None or len(c)<20: st.error(f"Sin datos para {sym_input}."); st.stop()
            st.write("Price Action..."); pa=analizar_pa(c[-50:],modo_rapido=False)
            if es_lp:
                st.write("Smart Entry largo plazo..."); se=smart_entry_lp(c,pa=pa)
            else:
                st.write("Smart Entry corto plazo..."); se=smart_entry_cp(c,v,pa=pa)
            st.write("Señal ML..."); ml=senal_lorentziana(c)

            # ── CoinGecko: 1 sola llamada consolidada (supply + fundamentos + utilidad) ──
            st.write("Datos CoinGecko...")
            cg_id_val=get_cg_id(sym_input)
            cg_data=get_cg_full(cg_id_val) if cg_id_val else None
            cg_name = cg_data.get("name","") if cg_data else ""
            supply=get_supply(cg_data)
            fundamentals=get_fundamentals(cg_data, sym_input)
            utility=get_utility_data(cg_data)
            if cg_id_val and not cg_data:
                st.write("⚠️ CoinGecko sin respuesta (posible limite de tasa) — se omiten supply/fundamentos/utilidad")

            st.write("Noticias..."); news=get_news(sym_input, name=cg_name)
            unlocks=[]; ai_text=None; utility_ai=None
            st.write("Unlocks..."); unlocks=get_unlocks(sym_input)
            if ANTHROPIC_KEY:
                st.write("IA noticias..."); ai_text=get_ai(sym_input,news)
                if utility:
                    st.write("IA utilidad...")
                    utility_ai=get_utility_ai(sym_input, utility.get("desc",""), utility.get("cats",[]), news)
            status.update(label=f"✅ {sym_input} analizado",state="complete")

        modo_txt="📅 Largo Plazo · 1D" if es_lp else "⚡ Corto Plazo · 1H"
        st.markdown(f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-size:22px;font-weight:700;color:#f1f5f9">{sym_input}</span><span class="t-yellow" style="font-size:20px">{fmt_p(c[-1])}</span></div><div class="t-sub">{modo_txt} · {fuente_analisis}</div></div>',unsafe_allow_html=True)
        st.markdown(pa_card_html(pa),unsafe_allow_html=True)
        # Botón afiliado Pionex en análisis individual
        st.markdown(
            f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:8px;font-size:13px;font-weight:700;margin-bottom:10px;text-decoration:none;">📈 Tradear {sym_input} en Pionex</a>',
            unsafe_allow_html=True
        )
        fases_total=3 if es_lp else 4
        st.markdown(se_card_html(se,fases_total=fases_total),unsafe_allow_html=True)
        if ml:
            ml_col="#10b981" if "COMPRA" in ml["senal"] else("#ef4444" if "VENTA" in ml["senal"] else "#64748b")
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:6px">🤖 SEÑAL ML LORENTZIANA</div><div style="color:{ml_col};font-size:14px;font-weight:600">{ml["senal"]}</div><div class="t-sub">Prediccion: {ml["pred"]} sobre {ml["k"]} vecinos</div></div>',unsafe_allow_html=True)
        if supply:
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">💎 SUPPLY &amp; ATH</div><div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px"><div><div class="t-sub">Supply Max</div><div style="color:#f1f5f9">{supply["max"]}</div></div><div><div class="t-sub">Circulante</div><div style="color:#f1f5f9">{supply["circ"]}</div></div></div><div style="display:flex;justify-content:space-around;text-align:center"><div><div class="t-sub">ATH</div><div class="t-red">{supply["ath"]}</div><div class="t-sub">{supply["ath_date"]}</div></div><div><div class="t-sub">vs ATH</div><div style="color:#f1f5f9;font-size:15px">{supply["pct_ath"]}</div></div></div><div class="divider"></div><div class="t-sub">{supply["cats"]}</div></div>',unsafe_allow_html=True)
        if fundamentals:
            fdv_mc_txt = f'{fundamentals["fdv_mc"]}x' if fundamentals["fdv_mc"] else "N/A"
            fdv_mc_col = "#ef4444" if (fundamentals["fdv_mc"] or 0) > 3 else "#10b981"
            supply_txt = f'{fundamentals["supply_pct"]}% circulante' if fundamentals["supply_pct"] else "N/A"
            exchanges_txt = " · ".join(fundamentals["exchanges"]) if fundamentals["exchanges"] else "N/A"
            rank_txt = f'#{fundamentals["rank"]}' if fundamentals["rank"] else "N/A"
            st.markdown(
                f'<div class="card">'
                f'<div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📊 FUNDAMENTOS</div>'
                f'<div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px">'
                f'<div><div class="t-sub">Market Cap</div><div style="color:#f1f5f9">{fundamentals["mc"]}</div></div>'
                f'<div><div class="t-sub">FDV</div><div style="color:#f1f5f9">{fundamentals["fdv"]}</div></div>'
                f'<div><div class="t-sub">Ranking</div><div style="color:#f59e0b">{rank_txt}</div></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px">'
                f'<div><div class="t-sub">FDV/MC ratio</div><div style="color:{fdv_mc_col};font-weight:600">{fdv_mc_txt}</div><div class="t-sub">{"⚠️ Alta dilución" if (fundamentals["fdv_mc"] or 0)>3 else "✅ Ok"}</div></div>'
                f'<div><div class="t-sub">Supply circ</div><div style="color:#f1f5f9">{supply_txt}</div></div>'
                f'</div>'
                f'<div class="divider"></div>'
                f'<div class="t-sub">🏦 {exchanges_txt}</div>'
                f'<div class="t-sub">🏷️ {fundamentals["cats"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        # Card utilidad y adopcion
        if utility:
            score = utility["utility_score"]
            score_col = "#10b981" if score>=7 else ("#f59e0b" if score>=4 else "#ef4444")
            score_label = "Alta" if score>=7 else ("Media" if score>=4 else "Baja")
            dev_col = "#10b981" if utility["commits_4w"]>20 else ("#f59e0b" if utility["commits_4w"]>5 else "#ef4444")
            cats_txt = " · ".join(utility["cats"]) if utility["cats"] else "N/A"
            util_html = (
                '<div class="card">'
                '<div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔬 UTILIDAD Y ADOPCION</div>'
                '<div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px">'
                '<div><div class="t-sub">Score Utilidad</div>'
                '<div style="color:'+score_col+';font-size:18px;font-weight:700">'+str(score)+'/10</div>'
                '<div class="t-sub">'+score_label+'</div></div>'
                '<div><div class="t-sub">Dev Activity</div>'
                '<div style="color:'+dev_col+'">'+str(utility["commits_4w"])+' commits/4w</div>'
                '<div class="t-sub">⭐ '+str(utility["stars"])+' stars</div></div>'
                '<div><div class="t-sub">Comunidad</div>'
                '<div style="color:#f1f5f9">🐦 '+utility["twitter"]+'</div>'
                '<div class="t-sub">Reddit: '+utility["reddit"]+'</div></div>'
                '</div>'
                '<div class="divider"></div>'
                '<div class="t-sub" style="margin-bottom:4px">🏷️ '+cats_txt+'</div>'
            )
            if utility["desc"]:
                util_html += '<div class="t-sub" style="font-style:italic;margin-top:4px">'+utility["desc"][:200]+'...</div>'
            util_html += '</div>'
            st.markdown(util_html, unsafe_allow_html=True)

        # Card IA utilidad
        if utility_ai:
            lines = [l.strip() for l in utility_ai.splitlines() if l.strip()]
            ai_util_html = '<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🤖 EVALUACION IA — UTILIDAD Y FUTURO</div>'
            for line in lines:
                if line.startswith("UTILIDAD:"): col="#93c5fd"
                elif line.startswith("ADOPCION:"): col="#10b981"
                elif line.startswith("FUTURO:"): col="#f59e0b"
                elif line.startswith("RIESGO:"): col="#ef4444"
                else: col="#94a3b8"
                ai_util_html += '<div style="color:'+col+';font-size:12px;margin-bottom:6px">'+line+'</div>'
            ai_util_html += '</div>'
            st.markdown(ai_util_html, unsafe_allow_html=True)
        elif ANTHROPIC_KEY and not utility:
            st.caption("ℹ️ Utilidad IA no disponible: sin datos de CoinGecko para este token.")

        if unlocks:
            rows="".join(f'<div style="color:{"#ef4444" if u["urgent"] else "#f1f5f9"};font-size:12px;margin-bottom:4px">{"⚠️" if u["urgent"] else "📅"} {u["date"]} ({u["days"]}d) {u["cat"]}</div>' for u in unlocks)
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔓 TOKEN UNLOCKS (90d)</div>{rows}</div>',unsafe_allow_html=True)
        if news:
            rows="".join(f'<div style="font-size:12px;color:#f1f5f9;margin-bottom:5px">{n["sent"]} <span class="t-sub">[{n["src"]}]</span> {n["title"]}</div>' for n in news)
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📰 NOTICIAS</div>{rows}</div>',unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:4px">📰 NOTICIAS</div><div class="t-sub">Sin titulares recientes que mencionen {sym_input}{" / " + cg_name if cg_name else ""} en los feeds monitoreados.</div></div>',unsafe_allow_html=True)
        if ai_text:
            rows=""
            for line in ai_text.splitlines():
                if not line.strip(): continue
                col="#10b981" if "POSITIVO" in line else("#ef4444" if "NEGATIVO" in line else "#f59e0b")
                rows+=f'<div style="color:{col};font-size:12px;margin-bottom:5px">{line}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🤖 ANALISIS IA</div>{rows}</div>',unsafe_allow_html=True)
        elif not ANTHROPIC_KEY:
            st.info("💡 Agrega ANTHROPIC_KEY en Streamlit Secrets para activar el analisis IA.")
    elif do_analyze:
        st.warning("Ingresa un ticker primero.")

with tab3:
    st.markdown("### 🌟 Tokens con Potencial")

    if not st.session_state.get("scan_results"):
        st.info("💡 Primero ejecuta un escaneo en el tab Scanner.")
    else:
        results = st.session_state["scan_results"]

        # Filtro: mejores por score técnico + fases
        top_tecnico = [r for r in results if r["se"]["fases_ok"] >= 3]
        top_tecnico = sorted(top_tecnico, key=lambda x: x["best_score"], reverse=True)[:10]

        # Mostrar top técnicos
        st.markdown(f"**Top técnicos del último scan** — {len(top_tecnico)} candidatos con 3-4/4 fases")
        for r in top_tecnico[:5]:
            pa = r["pa"]; se = r["se"]; c24 = r["change_24h"]
            cc = "t-green" if c24 >= 0 else "t-red"
            n = se["fases_ok"]
            se_col = "#10b981" if n==4 else "#f59e0b"
            pac = {"green":"#10b981","red":"#ef4444","yellow":"#f59e0b"}.get(pa["color"],"#64748b")
            pd = r.get("pd")
            pd_badge = ""
            if pd:
                pd_icon = "🚀" if pd["tipo"]=="PUMP" else "💥"
                pd_badge = f' {pd_icon} {pd["tipo"]} {pd["fase"]}'
            card = (
                '<div class="card" style="border-color:#166534">'
                '<div style="display:flex;justify-content:space-between;align-items:center">'
                '<span style="font-size:16px;font-weight:700;color:#f1f5f9">'+r["token"]+'</span>'
                '<span class="'+cc+'">'+f"{c24:+.1f}%"+'</span>'
                '</div>'
                '<div style="color:#f59e0b;font-size:14px">'+fmt_p(r["price"])+'</div>'
                '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0">'
                '<span class="tag-bot">'+r["best"]+'</span>'
                '<span class="tag-score">Score '+str(r["best_score"])+'</span>'
                '<span style="color:'+se_col+';font-size:11px">✅ '+str(n)+'/4 fases</span>'
                '</div>'
                '<div style="color:'+pac+';font-size:12px">'+pa["veredicto"]+pd_badge+'</div>'
                '</div>'
            )
            st.markdown(card, unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"🔍 Analizar {r['token']}", key=f"pot_analisis_{r['token']}", use_container_width=True):
                    st.session_state["analisis_sym"] = r["token"]
                    st.session_state["analisis_trigger"] = True
            with col2:
                st.markdown(
                    f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" '
                    f'style="display:block;text-align:center;background:#f59e0b;color:#000;'
                    f'border-radius:8px;padding:6px;font-size:12px;font-weight:700;text-decoration:none;">'
                    f'📈 Pionex</a>',
                    unsafe_allow_html=True
                )

        st.divider()

        # Evaluación IA
        if ANTHROPIC_KEY:
            if st.button("🤖 Evaluar con IA — Top 3 con mayor potencial", use_container_width=True, type="primary"):
                with st.spinner("Claude analizando el mercado..."):
                    pot_ai = get_potencial_ai(top_tecnico)
                if pot_ai:
                    st.session_state["potencial_ai"] = pot_ai

            if st.session_state.get("potencial_ai"):
                st.markdown("#### 🤖 Selección IA — Mejores oportunidades")
                bloques = st.session_state["potencial_ai"].split("---")
                for bloque in bloques:
                    lines = [l.strip() for l in bloque.strip().splitlines() if l.strip()]
                    if not lines: continue
                    token_name = ""
                    bloque_html = '<div class="card" style="border-color:#4c1d95">'
                    for line in lines:
                        if line.startswith("TOKEN:"):
                            token_name = line.replace("TOKEN:","").strip()
                            bloque_html += f'<div style="color:#f1f5f9;font-size:16px;font-weight:700;margin-bottom:6px">⭐ {token_name}</div>'
                        elif line.startswith("RAZON:"):
                            bloque_html += f'<div style="color:#93c5fd;font-size:12px;margin-bottom:4px">{line}</div>'
                        elif line.startswith("ESTRATEGIA:"):
                            bloque_html += f'<div style="color:#10b981;font-size:12px;margin-bottom:4px">{line}</div>'
                        elif line.startswith("RIESGO:"):
                            risk_col = "#ef4444" if "Alto" in line else ("#f59e0b" if "Medio" in line else "#10b981")
                            bloque_html += f'<div style="color:{risk_col};font-size:12px;margin-bottom:4px">{line}</div>'
                    bloque_html += '</div>'
                    st.markdown(bloque_html, unsafe_allow_html=True)
                    if token_name:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(f"🔍 Analizar {token_name}", key=f"ia_analisis_{token_name}", use_container_width=True):
                                st.session_state["analisis_sym"] = token_name
                                st.session_state["analisis_trigger"] = True
                        with c2:
                            st.markdown(
                                f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" '
                                f'style="display:block;text-align:center;background:#f59e0b;color:#000;'
                                f'border-radius:8px;padding:6px;font-size:12px;font-weight:700;text-decoration:none;">'
                                f'📈 Pionex</a>',
                                unsafe_allow_html=True
                            )
        else:
            st.info("💡 Agrega ANTHROPIC_KEY en Secrets para activar la evaluación IA.")

with tab4:
    st.markdown("### Ajustes")
    st.code('# Streamlit Cloud → Settings → Secrets:\nANTHROPIC_KEY = "sk-ant-..."')
    st.info("La key se configura en el dashboard de Streamlit Cloud.")
    st.divider()
    st.markdown(f"""**Quant Panel v3.2**
- 🟢 **KuCoin** — primario, sin auth, sin bloqueo AWS
- 🔵 **CoinPaprika** — fallback automatico
- ⚪ **CoinGecko** — Supply/ATH en Analisis
- 🔍 Scanner hasta {MAX_TOKENS} tokens · vol ≥ {fmt_vol(MIN_VOL)}
- 📐 PA · 🚦 Smart Entry 4F/3F · 🤖 ML · 💥 Pump/Dump
    """)
    st.caption("⚠️ Informacion de mercado. No es recomendacion de inversion.")
