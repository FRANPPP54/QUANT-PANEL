"""
Quant Panel Web v3.5 — Render / Streamlit Cloud
KuCoin → CoinPaprika → CoinGecko · EN/ES · Hot Tokens · Donaciones visibles
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
    st.error("pip install requests"); st.stop()

st.set_page_config(page_title="Quant Panel",page_icon="⚡",layout="centered",initial_sidebar_state="collapsed")

def get_secret(key, default=""):
    try: return st.secrets.get(key, default)
    except Exception: return os.environ.get(key, default)

ANTHROPIC_KEY = get_secret("ANTHROPIC_KEY", "")
KUCOIN_BASE = "https://api.kucoin.com/api/v1"
CP_BASE     = "https://api.coinpaprika.com/v1"
CG_BASE     = "https://api.coingecko.com/api/v3"
MIN_VOL     = 25_000
MAX_TOKENS  = 604
API_DELAY   = 0.08
STABLECOINS = {"usdt","usdc","busd","dai","tusd","fdusd","usdd","usdp","frax","eur","gbp","try","brl","usde","pyusd","gusd","lusd","susd","usd1","usdb","usdttrc20"}
EMA_LEN=50; RSI_LEN=10; RSI_OS=45; RSI_OB=65
VOL_LEN=14; VOL_MULT=1.5; ATR_LEN=14; SL_M=3.0; TP_M=4.5
SESSION = requests.Session()

# ── Donaciones — configurar aquí ──────────────────────────────────
DONATE_COFFEE  = "https://buymeacoffee.com/CryptoQuantPanel"
DONATE_BTC     = "bc1qw9rae7d76duwmew7ujyqxujxle6qn0pawl2thm"
DONATE_ETH     = "0xD3A27fD8D9d805Df38Ea9a5e5453E5d5A8a34F94"
DONATE_TRC20   = "TNv78ZEFXFtsbezvzosnoS5gH3gGjUYXHh"
PIONEX_REF     = "https://www.pionex.com/es/signUp?r=oCNuZqFw"

# ── Traducciones ES / EN ──────────────────────────────────────────
T = {
    "es": {
        "title": "⚡ Quant Panel",
        "subtitle": "Screener de Grid Bots · Pionex · v3.5",
        "tabs": ["📡 Scanner","📊 Análisis","🔥 Hot","🌟 Potencial","☕ Apoyo","⚙️ Ajustes","❓ Ayuda"],
        "scan_title": "Mejores tokens para Grid Bot",
        "scan_sub": "KuCoin · Price Action · Smart Entry 4 fases",
        "scan_btn": "🔍 Escanear ahora",
        "scan_vol": "💧 Volumen mínimo 24h",
        "scan_top": "Mostrar top resultados",
        "hot_title": "🔥 Hot Tokens",
        "hot_trending": "Trending últimas 24h (CoinGecko)",
        "hot_gainers": "Top Gainers del último scan",
        "hot_sub": "Tokens con mayor movimiento ahora",
        "analysis_title": "Análisis Individual",
        "analysis_ticker": "Ticker",
        "analysis_btn": "Analizar",
        "analysis_cp": "⚡ Corto Plazo (1H · días)",
        "analysis_lp": "📅 Largo Plazo (1D · semanas/meses)",
        "disclaimer": "⚠️ No es recomendación de inversión.",
        "donate_title": "☕ Apoyar el proyecto",
        "donate_sub": "Quant Panel es 100% gratuito y sin publicidad.",
        "coffee_btn": "☕ Invitame un café",
        "pionex_btn": "📈 Abrir en Pionex",
        "pionex_ref": "📈 Registrate en Pionex",
        "vol_opts": {"25K — todos":25_000,"250K — activos":250_000,"500K — balance":500_000,"1M — líquidos":1_000_000,"5M — grandes":5_000_000},
    },
    "en": {
        "title": "⚡ Quant Panel",
        "subtitle": "Grid Bot Screener · Pionex · v3.5",
        "tabs": ["📡 Scanner","📊 Analysis","🔥 Hot","🌟 Potential","☕ Support","⚙️ Settings","❓ Help"],
        "scan_title": "Best tokens for Grid Bot",
        "scan_sub": "KuCoin · Price Action · Smart Entry 4 phases",
        "scan_btn": "🔍 Scan now",
        "scan_vol": "💧 Minimum 24h volume",
        "scan_top": "Show top results",
        "hot_title": "🔥 Hot Tokens",
        "hot_trending": "Trending last 24h (CoinGecko)",
        "hot_gainers": "Top Gainers from last scan",
        "hot_sub": "Tokens with biggest movement now",
        "analysis_title": "Individual Analysis",
        "analysis_ticker": "Ticker",
        "analysis_btn": "Analyze",
        "analysis_cp": "⚡ Short Term (1H · days)",
        "analysis_lp": "📅 Long Term (1D · weeks/months)",
        "disclaimer": "⚠️ Not financial advice.",
        "donate_title": "☕ Support the project",
        "donate_sub": "Quant Panel is 100% free and ad-free.",
        "coffee_btn": "☕ Buy me a coffee",
        "pionex_btn": "📈 Open in Pionex",
        "pionex_ref": "📈 Sign up on Pionex",
        "vol_opts": {"25K — all":25_000,"250K — active":250_000,"500K — balanced":500_000,"1M — liquid":1_000_000,"5M — large":5_000_000},
    }
}

# Inicializar idioma
if "lang" not in st.session_state:
    st.session_state.lang = "es"
L = T[st.session_state.lang]  # shortcut

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

# ── Indicadores ──────────────────────────────────────────────────────
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

# ── Pump/Dump ─────────────────────────────────────────────────────────
def detectar_pump_dump(closes,volumes,change_24h):
    if len(closes)<24 or len(volumes)<24: return None
    try:
        c_now=closes[-1]; c_1h=closes[-2] if len(closes)>1 else c_now
        c_4h=closes[-4] if len(closes)>4 else c_now
        move_1h=(c_now-c_1h)/max(c_1h,1e-9)*100
        move_4h=(c_now-c_4h)/max(c_4h,1e-9)*100
        vol_now=sum(volumes[-3:])/3; vol_base=sum(volumes[-24:-3])/21
        vol_ratio=vol_now/max(vol_base,1e-9)
        res={"tipo":None,"fase":None,"move_1h":round(move_1h,1),"move_4h":round(move_4h,1),"vol_ratio":round(vol_ratio,1)}
        if move_1h>5 and vol_ratio>2.0: res["tipo"]="PUMP"; res["fase"]="EN CURSO"
        elif move_4h>10 and move_1h<2 and vol_ratio>1.3: res["tipo"]="PUMP"; res["fase"]="CONSOLIDANDO"
        elif change_24h>15 and vol_ratio<0.7 and move_1h<0: res["tipo"]="PUMP"; res["fase"]="AGOTADO"
        elif move_1h<-5 and vol_ratio>2.0: res["tipo"]="DUMP"; res["fase"]="EN CURSO"
        elif move_4h<-10 and move_1h>-2 and vol_ratio>1.3: res["tipo"]="DUMP"; res["fase"]="FRENANDO"
        elif change_24h<-15 and vol_ratio<0.7 and move_1h>0: res["tipo"]="DUMP"; res["fase"]="POSIBLE SUELO"
        return res if res["tipo"] else None
    except: return None

# ── Price Action ──────────────────────────────────────────────────────
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

# ── Smart Entry ───────────────────────────────────────────────────────
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

# ── ML ────────────────────────────────────────────────────────────────
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

# ── APIs ──────────────────────────────────────────────────────────────
def api_get(url,params=None,timeout=25,retries=3):
    headers={"User-Agent":"Mozilla/5.0 (compatible; QuantPanel/3.4)"}
    for attempt in range(retries):
        try:
            r=SESSION.get(url,params=params,headers=headers,timeout=timeout)
            if r.status_code==429:
                wait=8*(attempt+1)  # reducido de 15 a 8 segundos
                time.sleep(wait)
                continue
            if r.status_code in (400,404): return None
            r.raise_for_status(); return r
        except requests.exceptions.Timeout: time.sleep(1*(attempt+1))
        except Exception: time.sleep(0.5)
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
            vol=float(t.get("volValue",0) or 0); price=float(t.get("last",0) or 0)
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

# ── Hot Tokens: trending CoinGecko ────────────────────────────────
@st.cache_data(ttl=300)
def get_trending_tokens():
    """Top trending de CoinGecko últimas 24h — gratis, sin rate limit severo."""
    r=api_get(f"{CG_BASE}/search/trending",timeout=8,retries=1)
    if r is None: return []
    try:
        coins=r.json().get("coins",[])
        result=[]
        for c in coins[:10]:
            item=c.get("item",{})
            data=item.get("data",{})
            price_str=data.get("price","")
            change=data.get("price_change_percentage_24h",{})
            change_24h=change.get("usd",0) if isinstance(change,dict) else 0
            result.append({
                "symbol":  item.get("symbol","").upper(),
                "name":    item.get("name",""),
                "rank":    item.get("market_cap_rank"),
                "change_24h": round(change_24h,1),
                "price_str": price_str,
                "thumb":   item.get("thumb",""),
            })
        return result
    except Exception: return []

@st.cache_data(ttl=300)
def get_top_gainers_kucoin(limit=10):
    """Top gainers de KuCoin últimas 24h."""
    r=api_get(f"{KUCOIN_BASE}/market/allTickers",timeout=15,retries=1)
    if r is None: return []
    try:
        tickers=r.json().get("data",{}).get("ticker",[])
        gainers=[]
        for t in tickers:
            sym=t.get("symbol","")
            if not sym.endswith("-USDT"): continue
            base=sym[:-5].lower()
            if base in STABLECOINS: continue
            vol=float(t.get("volValue",0) or 0)
            if vol<500_000: continue
            change=float(t.get("changeRate",0) or 0)*100
            price=float(t.get("last",0) or 0)
            if change>5 and price>0:
                gainers.append({"symbol":base.upper(),"change_24h":round(change,1),"price":price,"vol_m":round(vol/1e6,1)})
        gainers.sort(key=lambda x:x["change_24h"],reverse=True)
        return gainers[:limit]
    except Exception: return []

@st.cache_data(ttl=900)
def get_new_gems(limit=20):
    """Tokens nuevos con supply <100M y fundamentos sólidos.
    Fuente principal: CoinPaprika (sin rate limit en Render).
    Fallback: CoinGecko gecko_desc.
    Criterios:
    - Supply total < 100M tokens
    - MC entre $500K y $500M
    - Volumen > $100K
    - FDV/MC bajo (poca dilución)
    - No stablecoins, no meme coins
    """
    MEME_EXCL = {"doge","shib","pepe","floki","bonk","wif","meme","babydoge",
                 "safepal","grok","turbo","coq","pnut","neiro","popcat",
                 "cat","dog","inu","elon","moon","safe","cum"}

    def fmt_s(v):
        if not v: return "N/A"
        if v>=1e6: return f"{v/1e6:.1f}M"
        if v>=1e3: return f"{v/1e3:.0f}K"
        return str(int(v))

    results = []

    # ── CoinPaprika: tickers con supply y market data ────────────
    r = api_get(f"{CP_BASE}/tickers",
        params={"quotes":"USD","limit":500},
        timeout=15, retries=2)

    if r:
        try:
            coins = r.json()
            for c in coins:
                sym = (c.get("symbol") or "").lower()
                if sym in STABLECOINS or any(m in sym for m in MEME_EXCL): continue

                q   = c.get("quotes",{}).get("USD",{})
                mc  = q.get("market_cap")  or 0
                vol = q.get("volume_24h")  or 0
                price = q.get("price")     or 0
                c24 = q.get("percent_change_24h") or 0
                c7d = q.get("percent_change_7d")  or 0
                ath = q.get("ath_price")          or 0

                # Supply desde el ticker de CP
                total_supply = c.get("total_supply")       or 0
                circ_supply  = c.get("circulating_supply") or 0
                supply_check = total_supply or circ_supply

                # Filtros
                if supply_check > 100_000_000 and supply_check != 0: continue
                if mc < 500_000 or mc > 500_000_000: continue
                if vol < 100_000 or price <= 0: continue

                # Fecha de listing desde CP
                first_data = c.get("first_data_at","")
                listed_date = "N/A"; days_old = None
                if first_data:
                    try:
                        dt = datetime.fromisoformat(first_data.replace("Z","+00:00"))
                        listed_date = dt.strftime("%d/%m/%Y")
                        days_old = (datetime.now(timezone.utc) - dt).days
                    except Exception: pass

                # Score de calidad
                circ_pct = round(circ_supply/total_supply*100,1) if total_supply>0 and circ_supply>0 else None
                pct_ath  = round((price-ath)/ath*100,1) if ath and price else None
                quality  = 10
                if circ_pct and circ_pct < 20: quality -= 2
                if days_old and days_old > 365:  quality -= 1  # no tan nuevo
                if vol/mc < 0.01:                quality -= 1  # volumen bajo vs MC

                results.append({
                    "symbol":     c.get("symbol","").upper(),
                    "name":       c.get("name",""),
                    "price":      price,
                    "change_24h": round(c24,1),
                    "change_7d":  round(c7d,1),
                    "mc":         mc,
                    "vol":        vol,
                    "supply_fmt": fmt_s(supply_check),
                    "fdv_mc":     None,
                    "circ_pct":   circ_pct,
                    "rank":       c.get("rank"),
                    "quality":    quality,
                    "listed_date":listed_date,
                    "days_old":   days_old,
                    "pct_ath":    pct_ath,
                })
        except Exception: pass

    # ── Fallback CoinGecko si CP falló ───────────────────────────
    if not results:
        r2 = api_get(f"{CG_BASE}/coins/markets",
            params={"vs_currency":"usd","order":"gecko_desc",
                    "per_page":100,"page":1,"sparkline":"false",
                    "price_change_percentage":"24h,7d"},
            timeout=8, retries=1)
        if r2:
            try:
                for c in r2.json():
                    sym=(c.get("symbol") or "").lower()
                    if sym in STABLECOINS or any(m in sym for m in MEME_EXCL): continue
                    total_supply = c.get("total_supply") or c.get("circulating_supply") or 0
                    circ_supply  = c.get("circulating_supply") or 0
                    mc  = c.get("market_cap") or 0
                    fdv = c.get("fully_diluted_valuation") or 0
                    vol = c.get("total_volume") or 0
                    price = c.get("current_price") or 0
                    if total_supply > 100_000_000 and total_supply!=0: continue
                    if mc < 500_000 or mc > 500_000_000: continue
                    if vol < 100_000 or price <= 0: continue
                    fdv_mc = round(fdv/mc,1) if fdv and mc>0 else None
                    circ_pct = round(circ_supply/total_supply*100,1) if total_supply>0 and circ_supply>0 else None
                    quality = 10
                    if fdv_mc and fdv_mc>5: quality-=3
                    if circ_pct and circ_pct<20: quality-=2
                    c24=round(c.get("price_change_percentage_24h") or 0,1)
                    c7d=round(c.get("price_change_percentage_7d_in_currency") or 0,1)
                    results.append({
                        "symbol":c.get("symbol","").upper(),"name":c.get("name",""),
                        "price":price,"change_24h":c24,"change_7d":c7d,
                        "mc":mc,"vol":vol,"supply_fmt":fmt_s(total_supply),
                        "fdv_mc":fdv_mc,"circ_pct":circ_pct,"rank":c.get("market_cap_rank"),
                        "quality":quality,"listed_date":"N/A","days_old":None,"pct_ath":None,
                    })
            except Exception: pass

    # Ordenar: primero los más nuevos con mayor calidad
    results.sort(key=lambda x: (
        x["quality"],
        -x.get("days_old",9999) if x.get("days_old") else 0,
        x["vol"]
    ), reverse=True)

    seen=set(); unique=[]
    for r in results:
        if r["symbol"] not in seen: seen.add(r["symbol"]); unique.append(r)
    return unique[:limit]
    MEME_EXCL = {"doge","shib","pepe","floki","bonk","wif","meme","babydoge",
                 "safepal","grok","turbo","dogwifhat","coq","pnut","neiro","popcat",
                 "cat","dog","inu","elon","moon","safe","cum","xxx"}
    results = []

    # ── Paso 1: obtener lista de coins recientes de CoinGecko ────
    r_new = api_get(f"{CG_BASE}/coins/list/new", timeout=8, retries=1)
    new_ids = []
    if r_new:
        try:
            new_coins = r_new.json()
            new_ids = [c.get("id") for c in new_coins[:60] if c.get("id")]
        except Exception:
            new_ids = []

    # ── Paso 2: si /coins/list/new falla, usar gecko_desc como fallback ─
    if not new_ids:
        r_fb = api_get(f"{CG_BASE}/coins/markets",
            params={"vs_currency":"usd","order":"gecko_desc",
                    "per_page":100,"page":1,"sparkline":"false",
                    "price_change_percentage":"24h,7d"},
            timeout=10, retries=1)
        if r_fb:
            try:
                for c in r_fb.json():
                    sym=(c.get("symbol") or "").lower()
                    if sym in STABLECOINS or any(m in sym for m in MEME_EXCL): continue
                    total_supply = c.get("total_supply") or c.get("circulating_supply") or 0
                    circ_supply  = c.get("circulating_supply") or 0
                    mc  = c.get("market_cap") or 0
                    fdv = c.get("fully_diluted_valuation") or 0
                    vol = c.get("total_volume") or 0
                    price = c.get("current_price") or 0
                    if total_supply > 100_000_000 and total_supply != 0: continue
                    if mc < 500_000 or mc > 500_000_000: continue
                    if vol < 100_000 or price <= 0: continue
                    fdv_mc = round(fdv/mc,1) if fdv and mc>0 else None
                    circ_supply2 = c.get("circulating_supply") or 0
                    circ_pct = round(circ_supply2/total_supply*100,1) if total_supply>0 and circ_supply2>0 else None
                    quality = 10
                    if fdv_mc and fdv_mc>5:  quality-=3
                    if fdv_mc and fdv_mc>10: quality-=3
                    if circ_pct and circ_pct<20: quality-=2
                    c24=round(c.get("price_change_percentage_24h") or 0,1)
                    c7d=round(c.get("price_change_percentage_7d_in_currency") or 0,1)
                    def fmt_s(v):
                        if v>=1e6: return f"{v/1e6:.1f}M"
                        if v>=1e3: return f"{v/1e3:.0f}K"
                        return str(int(v))
                    results.append({
                        "symbol":c.get("symbol","").upper(),"name":c.get("name",""),
                        "price":price,"change_24h":c24,"change_7d":c7d,
                        "mc":mc,"vol":vol,"supply_fmt":fmt_s(total_supply) if total_supply else "N/A",
                        "fdv_mc":fdv_mc,"circ_pct":circ_pct,"rank":c.get("market_cap_rank"),
                        "quality":quality,"listed_date":"N/A","days_old":None,
                    })
            except Exception: pass
        results.sort(key=lambda x:(x["quality"],x["vol"]),reverse=True)
        seen=set(); unique=[]
        for r in results:
            if r["symbol"] not in seen: seen.add(r["symbol"]); unique.append(r)
        return unique[:limit]

    # ── Paso 3: obtener datos de mercado para los coins nuevos ────
    # CoinGecko permite hasta 50 IDs por llamada
    for batch_start in range(0, min(len(new_ids), 60), 50):
        batch = new_ids[batch_start:batch_start+50]
        ids_str = ",".join(batch)
        r_mkt = api_get(f"{CG_BASE}/coins/markets",
            params={"vs_currency":"usd","ids":ids_str,
                    "order":"market_cap_desc","per_page":50,
                    "sparkline":"false",
                    "price_change_percentage":"24h,7d"},
            timeout=10, retries=1)
        if r_mkt is None: continue
        try:
            for c in r_mkt.json():
                sym=(c.get("symbol") or "").lower()
                if sym in STABLECOINS or any(m in sym for m in MEME_EXCL): continue
                total_supply = c.get("total_supply") or c.get("circulating_supply") or 0
                circ_supply  = c.get("circulating_supply") or 0
                mc  = c.get("market_cap") or 0
                fdv = c.get("fully_diluted_valuation") or 0
                vol = c.get("total_volume") or 0
                price = c.get("current_price") or 0
                if total_supply > 100_000_000 and total_supply != 0: continue
                if mc < 500_000 or mc > 500_000_000: continue
                if vol < 100_000 or price <= 0: continue
                fdv_mc = round(fdv/mc,1) if fdv and mc>0 else None
                circ_pct = round(circ_supply/total_supply*100,1) if total_supply>0 and circ_supply>0 else None
                quality = 10
                if fdv_mc and fdv_mc>5:  quality-=3
                if fdv_mc and fdv_mc>10: quality-=3
                if circ_pct and circ_pct<20: quality-=2
                c24=round(c.get("price_change_percentage_24h") or 0,1)
                c7d=round(c.get("price_change_percentage_7d_in_currency") or 0,1)
                # Fecha de listado desde /coins/list/new
                r_new2=r_new.json() if r_new else []
                listed_date="N/A"; days_old=None
                for nc in r_new2:
                    if nc.get("id")==c.get("id"):
                        activated=nc.get("activated_at")
                        if activated:
                            try:
                                dt=datetime.fromtimestamp(activated,tz=timezone.utc)
                                listed_date=dt.strftime("%d/%m/%Y")
                                days_old=(datetime.now(timezone.utc)-dt).days
                            except Exception: pass
                        break
                def fmt_s(v):
                    if v>=1e6: return f"{v/1e6:.1f}M"
                    if v>=1e3: return f"{v/1e3:.0f}K"
                    return str(int(v))
                results.append({
                    "symbol":c.get("symbol","").upper(),"name":c.get("name",""),
                    "price":price,"change_24h":c24,"change_7d":c7d,
                    "mc":mc,"vol":vol,"supply_fmt":fmt_s(total_supply) if total_supply else "N/A",
                    "fdv_mc":fdv_mc,"circ_pct":circ_pct,"rank":c.get("market_cap_rank"),
                    "quality":quality,"listed_date":listed_date,"days_old":days_old,
                })
        except Exception: continue

    results.sort(key=lambda x:(x["quality"],x["vol"]),reverse=True)
    seen=set(); unique=[]
    for r in results:
        if r["symbol"] not in seen: seen.add(r["symbol"]); unique.append(r)
    return unique[:limit]

# ── CoinPaprika: fundamentals fallback (sin rate limit, funciona en Render) ──
@st.cache_data(ttl=3600)
def cp_get_coin_info(cp_id):
    """Descarga info completa del token desde CoinPaprika /coins/{id}"""
    if not cp_id: return None
    r=api_get(f"{CP_BASE}/coins/{cp_id}",timeout=10,retries=2)
    if r is None: return None
    try: return r.json()
    except Exception: return None

@st.cache_data(ttl=1800)
def cp_get_ticker(cp_id):
    """Descarga precio, market cap, supply desde CoinPaprika /tickers/{id}"""
    if not cp_id: return None
    r=api_get(f"{CP_BASE}/tickers/{cp_id}",params={"quotes":"USD"},timeout=10,retries=2)
    if r is None: return None
    try: return r.json()
    except Exception: return None

def get_supply_cp(cp_id):
    """Supply y ATH desde CoinPaprika — fallback cuando CoinGecko falla."""
    coin_info=cp_get_coin_info(cp_id)
    ticker=cp_get_ticker(cp_id)
    if not coin_info and not ticker: return None
    try:
        def fmt(v):
            if v is None: return "N/A"
            if v>=1e12: return f"{v/1e12:.2f}T"
            if v>=1e9: return f"{v/1e9:.2f}B"
            if v>=1e6: return f"{v/1e6:.2f}M"
            return f"{v:,.0f}"
        q=ticker.get("quotes",{}).get("USD",{}) if ticker else {}
        mc=q.get("market_cap") or 0
        price=q.get("price") or 0
        ath=q.get("ath_price")
        pct=round((price-ath)/ath*100,1) if ath and price else None
        # Supply desde coin_info
        total_supply=coin_info.get("total_supply") if coin_info else None
        circ_supply=coin_info.get("circulating_supply") if coin_info else None
        # Categorías
        tags=coin_info.get("tags",[]) if coin_info else []
        cats=", ".join([t.get("name","") for t in tags[:2]]) if tags else "N/A"
        return {
            "max":  fmt(total_supply) if total_supply else "N/A",
            "circ": fmt(circ_supply)  if circ_supply else "N/A",
            "ath":  f"${ath:,.4f}"   if ath else "N/A",
            "ath_date": "N/A",
            "pct_ath": f"{pct}%"     if pct is not None else "N/A",
            "cats": cats,
            "source": "CoinPaprika",
        }
    except Exception: return None

def get_fundamentals_cp(cp_id):
    """Fundamentos desde CoinPaprika — fallback cuando CoinGecko falla."""
    ticker=cp_get_ticker(cp_id)
    coin_info=cp_get_coin_info(cp_id)
    if not ticker: return None
    try:
        def fmt_usd(v):
            if v is None: return "N/A"
            if v>=1e9: return f"${v/1e9:.2f}B"
            if v>=1e6: return f"${v/1e6:.2f}M"
            if v>=1e3: return f"${v/1e3:.0f}K"
            return f"${v:,.0f}"
        q=ticker.get("quotes",{}).get("USD",{})
        mc=q.get("market_cap"); vol=q.get("volume_24h")
        rank=ticker.get("rank")
        total=coin_info.get("total_supply") if coin_info else None
        circ=coin_info.get("circulating_supply") if coin_info else None
        supply_pct=round(circ/total*100,1) if circ and total and total>0 else None
        tags=coin_info.get("tags",[]) if coin_info else []
        cats=", ".join([t.get("name","") for t in tags[:2]]) if tags else "N/A"
        return {
            "mc": fmt_usd(mc),
            "fdv": "N/A",
            "fdv_mc": None,
            "rank": rank,
            "supply_pct": supply_pct,
            "cats": cats,
            "exchanges": [],
            "mc_raw": mc or 0,
        }
    except Exception: return None

def get_utility_cp(cp_id, coin_info=None):
    """Utilidad básica desde CoinPaprika — fallback cuando CoinGecko falla."""
    if not coin_info: coin_info=cp_get_coin_info(cp_id)
    if not coin_info: return None
    try:
        desc=coin_info.get("description","") or ""
        desc_clean=re.sub(r'<[^>]+>','',desc)[:500]
        tags=coin_info.get("tags",[]) or []
        cats=[t.get("name","") for t in tags[:3]]
        utility_cats=["defi","infrastructure","layer","oracle","exchange","lending","yield","gaming","ai","nft","bridge","payment","privacy"]
        score=3 if any(any(u in c.lower() for u in utility_cats) for c in cats) else 1
        score=min(score,10)
        return {
            "desc": desc_clean,
            "commits_4w": 0,
            "stars": 0,
            "forks": 0,
            "twitter": "0",
            "reddit": "0",
            "cats": cats,
            "utility_score": score,
        }
    except Exception: return None

CG_MAP={"AAVE":"aave","UNI":"uniswap","LINK":"chainlink","MKR":"maker","BTC":"bitcoin","ETH":"ethereum","BNB":"binancecoin","SOL":"solana","ADA":"cardano","DOT":"polkadot","AVAX":"avalanche-2","MATIC":"matic-network","ATOM":"cosmos","NEAR":"near","FTM":"fantom","ALGO":"algorand","XLM":"stellar","XRP":"ripple","TRX":"tron","ARB":"arbitrum","OP":"optimism","APT":"aptos","SUI":"sui","INJ":"injective-protocol","TIA":"celestia","DOGE":"dogecoin","SHIB":"shiba-inu","PEPE":"pepe","LTC":"litecoin","BCH":"bitcoin-cash","HBAR":"hedera-hashgraph","SYN":"synapse-2","RUNE":"thorchain","HYPE":"hyperliquid","TAO":"bittensor","WIF":"dogwifcoin","BONK":"bonk","JUP":"jupiter-exchange-solana","FET":"fetch-ai","RENDER":"render-token","SEI":"sei-network","JTO":"jito-governance-token","PYTH":"pyth-network","WLD":"worldcoin-wld","GMX":"gmx","DYDX":"dydx"}

@st.cache_data(ttl=3600)
def get_cg_id(sym):
    if sym.upper() in CG_MAP: return CG_MAP[sym.upper()]
    try:
        r=api_get(f"{CG_BASE}/coins/list",timeout=12)
        if r is None: return None
        coins=r.json(); m=[c for c in coins if c.get("symbol","").lower()==sym.lower()]
        if len(m)==1: return m[0]["id"]
        if len(m)>1:
            ids=",".join(c["id"] for c in m[:15]); time.sleep(2)
            r2=api_get(f"{CG_BASE}/coins/markets",params={"vs_currency":"usd","ids":ids,"order":"market_cap_desc"})
            if r2:
                d=r2.json()
                if d: return d[0]["id"]
    except Exception: pass
    return None

# FIX v3.4: sin sleep, timeout 8s, 1 reintento — no congela la UI
@st.cache_data(ttl=3600)
def get_cg_full(cg_id):
    if not cg_id: return None
    r=api_get(f"{CG_BASE}/coins/{cg_id}",
        params={"localization":"false","tickers":"true","market_data":"true",
                "community_data":"true","developer_data":"true"},
        timeout=8, retries=1)
    if r is None: return None
    try: return r.json()
    except Exception: return None

def get_supply(d):
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
        rank = d.get("market_cap_rank")
        cats = d.get("categories", [])
        fdv_mc = round(fdv/mc, 1) if fdv and mc and mc>0 else None
        supply_pct = round(circ/total*100, 1) if circ and total and total>0 else None
        tickers = d.get("tickers", [])[:5]
        exchanges = list(dict.fromkeys([t.get("market", {}).get("name","") for t in tickers if t.get("market",{}).get("name")]))[:3]
        return {"mc": fmt_usd(mc),"fdv": fmt_usd(fdv),"fdv_mc": fdv_mc,"rank": rank,"supply_pct": supply_pct,"cats": ", ".join(cats[:2]) or "N/A","exchanges": exchanges,"mc_raw": mc or 0}
    except Exception: return None

def get_utility_data(d):
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
        return {"desc": desc_clean,"commits_4w": commits_4w,"stars": stars,"forks": forks,"twitter": fmt_k(twitter),"reddit": fmt_k(reddit),"cats": cats[:3],"utility_score": score}
    except Exception: return None

def get_utility_ai(sym, desc, cats, news):
    if not ANTHROPIC_KEY: return None
    cats_txt = ", ".join(cats) if cats else "N/A"
    news_txt = "\n".join(f"- {n['title']}" for n in news[:3]) if news else "Sin noticias recientes"
    prompt = (f"Token: {sym}\nSector: {cats_txt}\nDescripcion: {desc[:300]}\nNoticias:\n{news_txt}\n\n"
              f"Responde en espanol:\nUTILIDAD: [que problema resuelve]\nADOPCION: [Baja/Media/Alta + razon]\nFUTURO: [Negativo/Neutral/Positivo + razon]\nRIESGO: [principal riesgo]")
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

# FIX v3.4: feeds RSS en paralelo con threading → más noticias, más rápido
@st.cache_data(ttl=1800)
def get_news(sym, name=""):
    import threading
    feeds=[
        ("CoinDesk","https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("CoinTelegraph","https://cointelegraph.com/rss"),
        ("Decrypt","https://decrypt.co/feed"),
        ("TheBlock","https://www.theblock.co/rss.xml"),
        ("BeInCrypto","https://beincrypto.com/feed/"),
        ("CryptoSlate","https://cryptoslate.com/feed/"),
        ("AMBCrypto","https://ambcrypto.com/feed/"),
        ("NewsBTC","https://www.newsbtc.com/feed/"),
    ]
    pos_words=["surge","rally","pump","gain","rise","bull","high","record","launch","approved","listing","upgrade","partnership","growth","soars","jumps","eyes","stake","acquire"]
    neg_words=["crash","drop","fall","plunge","bear","hack","exploit","scam","delist","decline","warning","ban","lawsuit","sec","slump","loses"]
    s=sym.lower()
    name_lower=name.lower().strip()
    name_words=[w for w in name_lower.split() if len(w)>=4]
    found=[]
    lock=threading.Lock()

    def fetch_feed(src, url):
        try:
            r=SESSION.get(url,timeout=6,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code!=200: return
            root=ET.fromstring(r.content)
            items=root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items:
                t=(item.findtext("title") or "").strip()
                desc=(item.findtext("description") or "").strip()
                blob=(t+" "+desc).lower()
                match=(re.search(r'\b'+re.escape(s)+r'\b',blob) or
                       (len(name_lower)>=4 and re.search(r'\b'+re.escape(name_lower)+r'\b',blob)) or
                       any(re.search(r'\b'+re.escape(w)+r'\b',blob) for w in name_words))
                if not match: continue
                tl=t.lower()
                pos=sum(1 for k in pos_words if k in tl)
                neg=sum(1 for k in neg_words if k in tl)
                sent="🟢" if pos>neg else("🔴" if neg>pos else "⚪")
                with lock:
                    found.append({"title":t[:90],"src":src,"sent":sent})
        except Exception: pass

    threads=[threading.Thread(target=fetch_feed,args=(src,url)) for src,url in feeds]
    for t in threads: t.daemon=True; t.start()
    for t in threads: t.join(timeout=8)

    seen,uniq=set(),[]
    for n2 in found:
        k=n2["title"][:30].lower()
        if k not in seen: seen.add(k); uniq.append(n2)
    return uniq[:10]

def get_ai(sym,news):
    if not ANTHROPIC_KEY: return None
    txt="\n".join(f"- {n['title']}" for n in news)
    prompt=f"Token: {sym}\nTitulares: {txt}\nResponde en espanol:\nPOSITIVO: punto1 | punto2\nNEGATIVO: riesgo1 | riesgo2\nEVENTO: evento clave"
    try:
        r=SESSION.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},json={"model":"claude-sonnet-4-6","max_tokens":250,"tools":[{"type":"web_search_20250305","name":"web_search"}],"messages":[{"role":"user","content":prompt}]},timeout=25)
        blocks=r.json().get("content",[])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except Exception: return None

# ── Scoring ───────────────────────────────────────────────────────────
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

def get_potencial_ai(tokens_data):
    if not ANTHROPIC_KEY or not tokens_data: return None
    resumen = ""
    for t in tokens_data[:8]:
        resumen += (f"Token: {t['token']} | Precio: {fmt_p(t['price'])} | "
                   f"Cambio24h: {t['change_24h']:+.1f}% | Score: {t['best_score']} | "
                   f"Bot: {t['best']} | PA: {t['pa']['veredicto'][:30]} | "
                   f"Fases: {t['se']['fases_ok']}/4\n")
    prompt = (f"Eres un analista de criptomonedas experto en bots de trading.\n"
              f"Analiza estos tokens y selecciona los 3 con mayor potencial:\n\n{resumen}\n"
              f"Para cada seleccionado:\nTOKEN: [simbolo]\nRAZON: [por que tiene potencial]\nESTRATEGIA: [Grid/DCA/Infinity + parametros]\nRIESGO: [Bajo/Medio/Alto + razon]\n---\nResponde en espanol.")
    try:
        r = SESSION.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":500,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]},timeout=35)
        blocks = r.json().get("content",[])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except Exception: return None

# ══════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════

# ── Toggle de idioma ──────────────────────────────────────────────
col_title, col_lang = st.columns([4, 1])
with col_title:
    st.markdown(f"# {L['title']}")
    st.markdown(f'<p class="t-sub">{L["subtitle"]}</p>', unsafe_allow_html=True)
with col_lang:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🇬🇧 EN" if st.session_state.lang=="es" else "🇪🇸 ES", use_container_width=True):
        st.session_state.lang = "en" if st.session_state.lang=="es" else "es"
        st.rerun()

# ── Barra de donación visible ─────────────────────────────────────
st.markdown(f"""
<div style="background:linear-gradient(135deg,#1c1400,#2d1f00);border:1px solid #854d0e;
     border-radius:10px;padding:8px 14px;margin-bottom:12px;
     display:flex;justify-content:space-between;align-items:center">
  <span style="color:#f59e0b;font-size:12px">
    ☕ {'¿Te resulta útil? Apoyá el proyecto' if st.session_state.lang=='es' else 'Find it useful? Support the project'}
  </span>
  <span style="display:flex;gap:8px">
    <a href="{DONATE_COFFEE}" target="_blank"
       style="background:#FFDD00;color:#000;border-radius:6px;padding:4px 10px;
              font-size:11px;font-weight:700;text-decoration:none">☕ Café</a>
    <a href="{PIONEX_REF}" target="_blank"
       style="background:#f59e0b;color:#000;border-radius:6px;padding:4px 10px;
              font-size:11px;font-weight:700;text-decoration:none">📈 Pionex</a>
  </span>
</div>
""", unsafe_allow_html=True)

tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(L["tabs"])

with tab1:
    st.markdown(f"### {L['scan_title']}")
    st.caption(L["scan_sub"])
    vol_opciones = L["vol_opts"]
    vol_label=st.selectbox(L["scan_vol"],list(vol_opciones.keys()),index=2)
    vol_min=vol_opciones[vol_label]

    # Selector límite 10/20/50
    top_n = st.select_slider(
        L["scan_top"],
        options=[10, 20, 50],
        value=10
    )
    st.session_state.setdefault("scan_results",[])
    st.session_state.setdefault("scan_total",0)
    st.session_state.setdefault("scan_source","")
    st.session_state.setdefault("last_scan",0)

    refresh_opciones = {"⏸️ Manual":0, "🔄 5 min":300, "🔄 15 min":900, "🔄 30 min":1800}
    refresh_label = st.selectbox("⏱️ Auto-refresh", list(refresh_opciones.keys()), index=0)
    refresh_sec = refresh_opciones[refresh_label]

    if st.session_state.last_scan > 0:
        elapsed_since = int(time.time() - st.session_state.last_scan)
        mins = elapsed_since // 60; secs = elapsed_since % 60
        st.caption(f"🕐 Ultimo scan hace {mins}m {secs}s")

    if refresh_sec > 0 and st.session_state.last_scan > 0:
        time_left = refresh_sec - int(time.time() - st.session_state.last_scan)
        if time_left > 0:
            st.caption(f"🔄 Proximo refresh en {time_left//60}m {time_left%60}s")
        else:
            st.caption("🔄 Listo para escanear")

    if st.session_state.scan_source:
        st.markdown(f'<div class="info-box">Fuente: <strong>{st.session_state.scan_source}</strong> · vol ≥ {fmt_vol(vol_min)} · PA · Smart Entry 4F</div>',unsafe_allow_html=True)

    c1,c2=st.columns([2,1])
    with c1: run_btn=st.button("🔍 Escanear ahora",use_container_width=True,type="primary")
    with c2:
        if st.session_state.scan_results: st.caption(f"✅ {st.session_state.scan_total} tokens")

    if run_btn:
        with st.status("Escaneando mercado...",expanded=True) as status:
            st.write("📡 Conectando a KuCoin...")
            pool_raw,src=kucoin_get_pool()
            if not pool_raw: pool_raw,src=coinpaprika_get_pool()
            if not pool_raw: st.error("❌ KuCoin y CoinPaprika fallaron."); st.stop()
            pool=[c for c in pool_raw if c["vol"]>=vol_min][:MAX_TOKENS]
            if not pool: st.error(f"❌ Ningun token con vol ≥ {fmt_vol(vol_min)}."); st.stop()
            src_label="🟢 KuCoin" if "kucoin" in src else "🔵 CoinPaprika"
            st.write(f"✅ {src_label} · {len(pool)} pares")
            bar=st.progress(0); results=[]; errores=0; t_start=time.time()
            for i,coin in enumerate(pool):
                bar.progress((i+1)/len(pool))
                if i%40==0:
                    elapsed=time.time()-t_start
                    rem=elapsed/(i+1)*(len(pool)-i-1) if i>0 else 0
                    st.write(f"⏳ {i+1}/{len(pool)} · {len(results)} validos · ~{int(rem)}s")
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
        card_class="card-green" if pdet else "card"
        card_html=('<div class="'+card_class+'">'
            '<div style="display:flex;justify-content:space-between;align-items:center">'
            '<span style="font-size:17px;font-weight:700;color:#f1f5f9">'+r["token"]+'</span>'
            '<span style="display:flex;gap:6px;align-items:center"><span class="'+cc+'">'+f"{c24:+.1f}%"+'</span>'+pt+'</span>'
            '</div>'
            '<div style="color:#f59e0b;font-size:15px;margin:2px 0">'+fmt_p(r["price"])+'</div>'
            '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">'
            '<span class="tag-bot">'+r["best"]+'</span>'
            '<span class="tag-score">Score '+str(r["best_score"])+'</span>'+se_h+'</div>'
            '<div style="color:'+pac+';font-size:12px">'+pa["veredicto"]+'</div>'
            +pd_html+
            '<div class="t-sub">Chop '+str(r["chop"])+' · Vol '+f"{r['vol_h']:.1f}"+'% · '+str(r["liq_m"])+'M$</div>'
            +slt+'</div>')
        st.markdown(card_html,unsafe_allow_html=True)
        st.markdown(f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:6px;font-size:12px;font-weight:700;margin-bottom:4px;text-decoration:none;">📈 Abrir {r["token"]} en Pionex</a>',unsafe_allow_html=True)
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

    auto_sym = st.session_state.get("analisis_sym", "") if st.session_state.get("analisis_trigger") else ""
    if st.session_state.get("analisis_trigger"):
        st.session_state["analisis_trigger"] = False
    if do_analyze and sym_input: pass
    elif auto_sym: sym_input = auto_sym; do_analyze = True

    if do_analyze and sym_input:
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
            st.write("Datos supply + fundamentos...")
            cg_id_val=get_cg_id(sym_input)
            cg_data=None; cg_name=""
            try:
                if cg_id_val:
                    cg_data=get_cg_full(cg_id_val)
                    cg_name=cg_data.get("name","") if cg_data else ""
            except Exception:
                cg_data=None; cg_name=""

            # Intentar con CoinGecko primero, fallback a CoinPaprika
            if cg_data:
                supply=get_supply(cg_data)
                fundamentals=get_fundamentals(cg_data, sym_input)
                utility=get_utility_data(cg_data)
                data_source="CoinGecko"
            else:
                # Fallback: CoinPaprika (no tiene rate limit en Render)
                st.write("CoinGecko no disponible — usando CoinPaprika...")
                cp_id_val=coinpaprika_search_coin_id(sym_input)
                cp_info=cp_get_coin_info(cp_id_val) if cp_id_val else None
                supply=get_supply_cp(cp_id_val)
                fundamentals=get_fundamentals_cp(cp_id_val)
                utility=get_utility_cp(cp_id_val, coin_info=cp_info)
                cg_name=cp_info.get("name","") if cp_info else sym_input
                data_source="CoinPaprika"

            st.write("Noticias RSS..."); news=get_news(sym_input, name=cg_name)
            unlocks=get_unlocks(sym_input)
            ai_text=None; utility_ai=None
            if ANTHROPIC_KEY:
                st.write("IA noticias..."); ai_text=get_ai(sym_input,news)
                if utility:
                    st.write("IA utilidad..."); utility_ai=get_utility_ai(sym_input, utility.get("desc",""), utility.get("cats",[]), news)
            status.update(label=f"✅ {sym_input} analizado · {data_source}",state="complete")

        modo_txt="📅 Largo Plazo · 1D" if es_lp else "⚡ Corto Plazo · 1H"
        st.markdown(f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-size:22px;font-weight:700;color:#f1f5f9">{sym_input}</span><span class="t-yellow" style="font-size:20px">{fmt_p(c[-1])}</span></div><div class="t-sub">{modo_txt} · {fuente_analisis} · Supply: {data_source}</div></div>',unsafe_allow_html=True)
        st.markdown(pa_card_html(pa),unsafe_allow_html=True)
        st.markdown(f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:8px;font-size:13px;font-weight:700;margin-bottom:10px;text-decoration:none;">📈 Tradear {sym_input} en Pionex</a>',unsafe_allow_html=True)
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
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📊 FUNDAMENTOS</div><div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px"><div><div class="t-sub">Market Cap</div><div style="color:#f1f5f9">{fundamentals["mc"]}</div></div><div><div class="t-sub">FDV</div><div style="color:#f1f5f9">{fundamentals["fdv"]}</div></div><div><div class="t-sub">Ranking</div><div style="color:#f59e0b">{rank_txt}</div></div></div><div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px"><div><div class="t-sub">FDV/MC ratio</div><div style="color:{fdv_mc_col};font-weight:600">{fdv_mc_txt}</div><div class="t-sub">{"⚠️ Alta dilución" if (fundamentals["fdv_mc"] or 0)>3 else "✅ Ok"}</div></div><div><div class="t-sub">Supply circ</div><div style="color:#f1f5f9">{supply_txt}</div></div></div><div class="divider"></div><div class="t-sub">🏦 {exchanges_txt}</div><div class="t-sub">🏷️ {fundamentals["cats"]}</div></div>',unsafe_allow_html=True)
        if utility:
            score = utility["utility_score"]
            score_col = "#10b981" if score>=7 else ("#f59e0b" if score>=4 else "#ef4444")
            score_label = "Alta" if score>=7 else ("Media" if score>=4 else "Baja")
            cats_txt = " · ".join(utility["cats"]) if utility["cats"] else "N/A"

            # Dev Activity — solo mostrar si tiene datos reales
            commits = utility["commits_4w"]
            stars   = utility["stars"]
            twitter_raw = utility["twitter"]
            reddit_raw  = utility["reddit"]

            if commits > 0:
                dev_col = "#10b981" if commits>20 else ("#f59e0b" if commits>5 else "#ef4444")
                dev_html = ('<div><div class="t-sub">Dev Activity</div>'
                           '<div style="color:'+dev_col+'">'+str(commits)+' commits/4w</div>'
                           '<div class="t-sub">⭐ '+str(stars)+' stars</div></div>')
            elif stars > 0:
                dev_html = ('<div><div class="t-sub">GitHub Stars</div>'
                           '<div style="color:#f59e0b">⭐ '+str(stars)+'</div>'
                           '<div class="t-sub">datos dev no disp.</div></div>')
            else:
                dev_html = ('<div><div class="t-sub">Dev Activity</div>'
                           '<div class="t-sub" style="font-size:11px">No disponible<br>vía API gratuita</div></div>')

            # Comunidad — solo mostrar si tiene datos reales
            tw_val = twitter_raw if twitter_raw not in ("0","") else None
            rd_val = reddit_raw  if reddit_raw  not in ("0","") else None
            if tw_val or rd_val:
                comm_html = ('<div><div class="t-sub">Comunidad</div>'
                            +(f'<div style="color:#f1f5f9">🐦 {tw_val}</div>' if tw_val else '')
                            +(f'<div class="t-sub">Reddit: {rd_val}</div>' if rd_val else '')
                            +'</div>')
            else:
                comm_html = ('<div><div class="t-sub">Comunidad</div>'
                            '<div class="t-sub" style="font-size:11px">Sin datos<br>API gratuita</div></div>')

            util_html = ('<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔬 UTILIDAD Y ADOPCION</div>'
                '<div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px">'
                '<div><div class="t-sub">Score Utilidad</div><div style="color:'+score_col+';font-size:18px;font-weight:700">'+str(score)+'/10</div><div class="t-sub">'+score_label+'</div></div>'
                + dev_html + comm_html +
                '</div><div class="divider"></div><div class="t-sub" style="margin-bottom:4px">🏷️ '+cats_txt+'</div>')
            if utility["desc"]:
                util_html += '<div class="t-sub" style="font-style:italic;margin-top:4px">'+utility["desc"][:200]+'...</div>'
            util_html += '</div>'
            st.markdown(util_html, unsafe_allow_html=True)
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
        elif ANTHROPIC_KEY and not utility and not cg_data:
            st.info("ℹ️ Fundamentos IA no disponibles — CoinGecko sin respuesta. Intenta de nuevo en 1 minuto.")
        if unlocks:
            rows="".join(f'<div style="color:{"#ef4444" if u["urgent"] else "#f1f5f9"};font-size:12px;margin-bottom:4px">{"⚠️" if u["urgent"] else "📅"} {u["date"]} ({u["days"]}d) {u["cat"]}</div>' for u in unlocks)
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔓 TOKEN UNLOCKS (90d)</div>{rows}</div>',unsafe_allow_html=True)
        if news:
            rows="".join(f'<div style="font-size:12px;color:#f1f5f9;margin-bottom:5px">{n["sent"]} <span class="t-sub">[{n["src"]}]</span> {n["title"]}</div>' for n in news)
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📰 NOTICIAS ({len(news)} fuentes)</div>{rows}</div>',unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:4px">📰 NOTICIAS</div><div class="t-sub">Sin titulares recientes sobre {sym_input}{" / "+cg_name if cg_name else ""} en los feeds monitoreados.</div></div>',unsafe_allow_html=True)
        if ai_text:
            rows=""
            for line in ai_text.splitlines():
                if not line.strip(): continue
                col="#10b981" if "POSITIVO" in line else("#ef4444" if "NEGATIVO" in line else "#f59e0b")
                rows+=f'<div style="color:{col};font-size:12px;margin-bottom:5px">{line}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🤖 ANALISIS IA</div>{rows}</div>',unsafe_allow_html=True)
        elif not ANTHROPIC_KEY:
            st.info("💡 Agrega ANTHROPIC_KEY para activar el analisis IA.")
    elif do_analyze:
        st.warning("Ingresa un ticker primero.")

# ── TAB 3: HOT TOKENS ─────────────────────────────────────────────
with tab3:
    st.markdown(f"### {L['hot_title']}")
    st.caption(L["hot_sub"])

    hot_limit = st.select_slider(
        "Mostrar" if st.session_state.lang=="es" else "Show",
        options=[10, 20],
        value=10
    )

    col_r, col_g = st.columns(2)

    with col_r:
        st.markdown(f"**{L['hot_trending']}**")
        with st.spinner("Cargando..." if st.session_state.lang=="es" else "Loading..."):
            trending = get_trending_tokens()
        if trending:
            for t in trending[:hot_limit]:
                cc = "t-green" if t["change_24h"] >= 0 else "t-red"
                rank_txt = f"#{t['rank']}" if t["rank"] else "—"
                st.markdown(f"""
                <div class="card" style="padding:8px 12px;margin-bottom:6px">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="color:#f1f5f9;font-weight:700;font-size:14px">{t['symbol']}</span>
                    <span class="{cc}">{t['change_24h']:+.1f}%</span>
                  </div>
                  <div style="display:flex;justify-content:space-between" class="t-sub">
                    <span>{t['name'][:18]}</span>
                    <span>{rank_txt}</span>
                  </div>
                </div>""", unsafe_allow_html=True)
                if st.button(f"📊 {t['symbol']}", key=f"hot_tr_{t['symbol']}", use_container_width=True):
                    st.session_state["analisis_sym"] = t["symbol"]
                    st.session_state["analisis_trigger"] = True
        else:
            st.caption("CoinGecko trending no disponible")

    with col_g:
        st.markdown(f"**{L['hot_gainers']}**")
        with st.spinner("Cargando..." if st.session_state.lang=="es" else "Loading..."):
            gainers = get_top_gainers_kucoin(limit=hot_limit)
        if gainers:
            for g in gainers[:hot_limit]:
                st.markdown(f"""
                <div class="card" style="padding:8px 12px;margin-bottom:6px">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="color:#f1f5f9;font-weight:700;font-size:14px">{g['symbol']}</span>
                    <span class="t-green">+{g['change_24h']}%</span>
                  </div>
                  <div style="display:flex;justify-content:space-between" class="t-sub">
                    <span>{fmt_p(g['price'])}</span>
                    <span>{g['vol_m']}M$</span>
                  </div>
                </div>""", unsafe_allow_html=True)
                if st.button(f"📊 {g['symbol']}", key=f"hot_gn_{g['symbol']}", use_container_width=True):
                    st.session_state["analisis_sym"] = g["symbol"]
                    st.session_state["analisis_trigger"] = True
        else:
            st.caption("Escanea primero para ver gainers" if st.session_state.lang=="es" else "Run a scan first to see gainers")

    # ── New Gems ───────────────────────────────────────────────────
    st.divider()
    gems_title = "💎 New Gems — Supply < 100M · Proyectos sólidos" if st.session_state.lang=="es" else "💎 New Gems — Supply < 100M · Solid projects"
    st.markdown(f"**{gems_title}**")
    gems_sub = "Tokens con baja dilución, respaldo financiero y menos de 100M tokens en circulación" if st.session_state.lang=="es" else "Low dilution tokens with financial backing and less than 100M circulating supply"
    st.caption(gems_sub)

    with st.spinner("Buscando gems..." if st.session_state.lang=="es" else "Searching gems..."):
        gems = get_new_gems(limit=hot_limit)

    if gems:
        def fmt_mc(v):
            if v>=1e9: return f"${v/1e9:.1f}B"
            if v>=1e6: return f"${v/1e6:.1f}M"
            if v>=1e3: return f"${v/1e3:.0f}K"
            return f"${v:.0f}"

        for g in gems:
            c24=g["change_24h"]; c7d=g["change_7d"]
            cc24="t-green" if c24>=0 else "t-red"
            cc7d ="t-green" if c7d >=0 else "t-red"
            fdv_mc_txt = f"FDV/MC: {g['fdv_mc']}x" if g["fdv_mc"] else ""
            fdv_mc_col = "#10b981" if (g["fdv_mc"] or 99)<3 else ("#f59e0b" if (g["fdv_mc"] or 99)<6 else "#ef4444")
            circ_txt = f"Circ: {g['circ_pct']}%" if g["circ_pct"] else ""
            q = g["quality"]
            q_col = "#10b981" if q>=8 else ("#f59e0b" if q>=5 else "#ef4444")
            rank_txt = f"#{g['rank']}" if g["rank"] else "—"

            st.markdown(f"""
            <div class="card" style="border-color:#1e3a5f">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                  <span style="color:#f1f5f9;font-weight:700;font-size:15px">{g['symbol']}</span>
                  <span class="t-sub" style="margin-left:6px">{g['name'][:20]}</span>
                </div>
                <span style="color:#f59e0b;font-weight:600">{fmt_p(g['price'])}</span>
              </div>
              <div style="display:flex;gap:10px;flex-wrap:wrap;margin:5px 0">
                <span class="{cc24}">24h: {c24:+.1f}%</span>
                <span class="{cc7d}">7d: {c7d:+.1f}%</span>
                <span class="t-sub">{rank_txt}</span>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin:4px 0">
                <span style="background:#0f172a;border-radius:5px;padding:2px 6px;font-size:11px;color:#93c5fd">
                  Supply: {g['supply_fmt']}
                </span>
                <span style="background:#0f172a;border-radius:5px;padding:2px 6px;font-size:11px;color:#64748b">
                  MC: {fmt_mc(g['mc'])}
                </span>
                {f'<span style="background:#0f172a;border-radius:5px;padding:2px 6px;font-size:11px;color:{fdv_mc_col}">{fdv_mc_txt}</span>' if fdv_mc_txt else ""}
                {f'<span style="background:#0f172a;border-radius:5px;padding:2px 6px;font-size:11px;color:#64748b">{circ_txt}</span>' if circ_txt else ""}
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
                <span style="font-size:11px;color:#64748b">Vol 24h: {fmt_mc(g['vol'])}</span>
                <span style="font-size:11px;color:{q_col}">Calidad: {q}/10</span>
              </div>
              {f'<div style="margin-top:4px"><span style="background:#1e3a5f;border-radius:5px;padding:2px 6px;font-size:11px;color:#93c5fd">📅 Listado: {g["listed_date"]} ({g["days_old"]}d)</span></div>' if g.get("days_old") is not None else ''}
            </div>""", unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"📊 Analizar {g['symbol']}", key=f"gem_{g['symbol']}", use_container_width=True):
                    st.session_state["analisis_sym"] = g["symbol"]
                    st.session_state["analisis_trigger"] = True
            with c2:
                st.markdown(
                    f'<a href="{PIONEX_REF}" target="_blank" style="display:block;text-align:center;'
                    f'background:#f59e0b;color:#000;border-radius:8px;padding:6px;'
                    f'font-size:12px;font-weight:700;text-decoration:none;">{L["pionex_btn"]}</a>',
                    unsafe_allow_html=True)
    else:
        st.info("CoinGecko no respondió — intentá de nuevo en 1 minuto." if st.session_state.lang=="es" else "CoinGecko unavailable — try again in 1 minute.")

with tab4:
    st.markdown("### 🌟 Tokens con Potencial")
    if not st.session_state.get("scan_results"):
        st.info("💡 Primero ejecuta un escaneo en el tab Scanner.")
    else:
        results = st.session_state["scan_results"]
        top_tecnico = [r for r in results if r["se"]["fases_ok"] >= 3]
        top_tecnico = sorted(top_tecnico, key=lambda x: x["best_score"], reverse=True)[:10]
        st.markdown(f"**Top tecnicos del ultimo scan** — {len(top_tecnico)} candidatos con 3-4/4 fases")
        for r in top_tecnico[:5]:
            pa = r["pa"]; se = r["se"]; c24 = r["change_24h"]
            cc = "t-green" if c24 >= 0 else "t-red"
            n = se["fases_ok"]; se_col = "#10b981" if n==4 else "#f59e0b"
            pac = {"green":"#10b981","red":"#ef4444","yellow":"#f59e0b"}.get(pa["color"],"#64748b")
            pd = r.get("pd"); pd_badge = ""
            if pd:
                pd_icon = "🚀" if pd["tipo"]=="PUMP" else "💥"
                pd_badge = f' {pd_icon} {pd["tipo"]} {pd["fase"]}'
            card = ('<div class="card" style="border-color:#166534">'
                '<div style="display:flex;justify-content:space-between;align-items:center">'
                '<span style="font-size:16px;font-weight:700;color:#f1f5f9">'+r["token"]+'</span>'
                '<span class="'+cc+'">'+f"{c24:+.1f}%"+'</span></div>'
                '<div style="color:#f59e0b;font-size:14px">'+fmt_p(r["price"])+'</div>'
                '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0">'
                '<span class="tag-bot">'+r["best"]+'</span>'
                '<span class="tag-score">Score '+str(r["best_score"])+'</span>'
                '<span style="color:'+se_col+';font-size:11px">✅ '+str(n)+'/4 fases</span></div>'
                '<div style="color:'+pac+';font-size:12px">'+pa["veredicto"]+pd_badge+'</div></div>')
            st.markdown(card, unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"🔍 Analizar {r['token']}", key=f"pot_analisis_{r['token']}", use_container_width=True):
                    st.session_state["analisis_sym"] = r["token"]
                    st.session_state["analisis_trigger"] = True
            with col2:
                st.markdown(f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:6px;font-size:12px;font-weight:700;text-decoration:none;">📈 Pionex</a>',unsafe_allow_html=True)
        st.divider()
        if ANTHROPIC_KEY:
            if st.button("🤖 Evaluar con IA — Top 3 con mayor potencial", use_container_width=True, type="primary"):
                with st.spinner("Claude analizando el mercado..."):
                    pot_ai = get_potencial_ai(top_tecnico)
                if pot_ai:
                    st.session_state["potencial_ai"] = pot_ai
            if st.session_state.get("potencial_ai"):
                st.markdown("#### 🤖 Seleccion IA — Mejores oportunidades")
                bloques = st.session_state["potencial_ai"].split("---")
                for bloque in bloques:
                    lines = [l.strip() for l in bloque.strip().splitlines() if l.strip()]
                    if not lines: continue
                    token_name = ""
                    bloque_html = '<div class="card" style="border-color:#4c1d95">'
                    for line in lines:
                        if line.startswith("TOKEN:"): token_name=line.replace("TOKEN:","").strip(); bloque_html+=f'<div style="color:#f1f5f9;font-size:16px;font-weight:700;margin-bottom:6px">⭐ {token_name}</div>'
                        elif line.startswith("RAZON:"): bloque_html+=f'<div style="color:#93c5fd;font-size:12px;margin-bottom:4px">{line}</div>'
                        elif line.startswith("ESTRATEGIA:"): bloque_html+=f'<div style="color:#10b981;font-size:12px;margin-bottom:4px">{line}</div>'
                        elif line.startswith("RIESGO:"):
                            risk_col="#ef4444" if "Alto" in line else("#f59e0b" if "Medio" in line else "#10b981")
                            bloque_html+=f'<div style="color:{risk_col};font-size:12px;margin-bottom:4px">{line}</div>'
                    bloque_html += '</div>'
                    st.markdown(bloque_html, unsafe_allow_html=True)
                    if token_name:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(f"🔍 Analizar {token_name}", key=f"ia_analisis_{token_name}", use_container_width=True):
                                st.session_state["analisis_sym"] = token_name
                                st.session_state["analisis_trigger"] = True
                        with c2:
                            st.markdown(f'<a href="https://www.pionex.com/es/signUp?r=oCNuZqFw" target="_blank" style="display:block;text-align:center;background:#f59e0b;color:#000;border-radius:8px;padding:6px;font-size:12px;font-weight:700;text-decoration:none;">📈 Pionex</a>',unsafe_allow_html=True)
        else:
            st.info("💡 Agrega ANTHROPIC_KEY para activar la evaluacion IA.")

# ── TAB 5: APOYO / SUPPORT ────────────────────────────────────────
with tab5:
    is_es = st.session_state.lang == "es"
    st.markdown(f"### {L['donate_title']}")
    st.markdown(L["donate_sub"])

    # Buy Me a Coffee
    st.markdown("---")
    st.markdown("#### ☕ Buy Me a Coffee" if is_es else "#### ☕ Buy Me a Coffee")
    st.markdown("La forma más simple — acepta tarjeta y crypto." if is_es else "Simplest way — accepts card and crypto.")
    st.markdown(
        f'<a href="{DONATE_COFFEE}" target="_blank" '
        f'style="display:block;text-align:center;background:#FFDD00;color:#000;'
        f'border-radius:10px;padding:14px;font-size:15px;font-weight:700;'
        f'text-decoration:none;margin-bottom:12px;">'
        f'☕ {L["coffee_btn"]}</a>',
        unsafe_allow_html=True)

    # Crypto directo
    st.markdown("---")
    st.markdown("#### 🪙 Donación directa en Crypto" if is_es else "#### 🪙 Direct Crypto Donation")
    st.markdown("Sin intermediarios — cero comisiones de plataforma." if is_es else "No middlemen — zero platform fees.")

    def crypto_card(icon, label, address, color):
        st.markdown(f"""
        <div class="card" style="border-color:{color}">
          <div style="color:{color};font-size:13px;font-weight:700;margin-bottom:6px">{icon} {label}</div>
          <div style="font-family:monospace;font-size:11px;color:#f1f5f9;
                      word-break:break-all;background:#0f172a;
                      padding:8px;border-radius:6px">{address}</div>
        </div>""", unsafe_allow_html=True)
        st.code(address, language=None)

    crypto_card("₿", "Bitcoin (BTC)", DONATE_BTC, "#f59e0b")
    crypto_card("Ξ", "Ethereum / USDT ERC-20", DONATE_ETH, "#10b981")
    crypto_card("💵", "USDT TRC-20 (Tron — menores fees)" if is_es else "USDT TRC-20 (Tron — lowest fees)", DONATE_TRC20, "#3b82f6")

    st.caption("⚠️ Verificá siempre la dirección antes de enviar. Las transacciones crypto son irreversibles." if is_es else "⚠️ Always verify the address before sending. Crypto transactions are irreversible.")

    # Pionex
    st.markdown("---")
    st.markdown("#### 📈 " + ("Registrate en Pionex con mi link" if is_es else "Sign up on Pionex with my link"))
    st.markdown("Sin costo para vos — recibo una pequeña comisión cuando operás." if is_es else "Free for you — I earn a small commission when you trade.")
    st.markdown(
        f'<a href="{PIONEX_REF}" target="_blank" '
        f'style="display:block;text-align:center;background:#f59e0b;color:#000;'
        f'border-radius:10px;padding:12px;font-size:14px;font-weight:700;'
        f'text-decoration:none;">{L["pionex_ref"]}</a>',
        unsafe_allow_html=True)

with tab6:
    st.markdown("### Ajustes")
    st.code('# Render → Environment Variables:\nANTHROPIC_KEY = "sk-ant-..."')
    st.info("En Render la key va en Environment, no en Secrets.")
    st.divider()
    st.markdown("""**Fuentes de datos v3.4**
- 🟢 **KuCoin** — velas y precios (primario)
- 🔵 **CoinPaprika** — fallback velas + supply/fundamentos
- ⚪ **CoinGecko** — supply/ATH cuando está disponible
- 📰 **8 feeds RSS** — noticias en paralelo
- 🤖 **Claude API** — análisis IA (requiere key)
    """)
    st.caption("⚠️ Informacion de mercado. No es recomendacion de inversion.")

with tab7:
    st.markdown("### ❓ " + ("Preguntas Frecuentes" if st.session_state.lang=="es" else "FAQ"))
    with st.expander("📊 ¿Qué es el Score y cómo se calcula?" if st.session_state.lang=="es" else "📊 What is the Score and how is it calculated?"):
        st.markdown("""
El **Score** es un número que indica qué tan adecuado es un token para cada tipo de bot.

Se calcula combinando:
- **Choppiness** — qué tan lateral se mueve el precio (ideal para Grid)
- **Volatilidad horaria** — amplitud de los movimientos
- **Liquidez** — volumen en dólares (más volumen = más seguro)
- **Cambio 24h** — favorece subidas para Long, bajadas para Short
- **Penalización** — si el token cae más del 15% se penaliza para Grid Long

**Rango típico:** 10–120. Más alto = mejor candidato para ese bot.
            """)

    with st.expander("🔢 ¿Qué es el Choppiness Index?"):
        st.markdown("""
El **Choppiness Index** mide si el precio se mueve en tendencia o lateralmente.

- **Alto (>5)** → mercado lateral = ideal para Grid Bot
- **Bajo (<2)** → mercado en tendencia fuerte = mejor para DCA o Infinity

El Grid Bot gana dinero cuando el precio sube y baja dentro de un rango. Un Choppiness alto indica que eso está pasando.
            """)

    with st.expander("🚦 ¿Qué significa el Semáforo Smart Entry?"):
        st.markdown("""
El **Smart Entry** evalúa 4 condiciones antes de entrar en una posición:

| Fase | Condición | Qué significa |
|------|-----------|---------------|
| F1 | Precio > EMA50 | Tendencia alcista de corto plazo |
| F2 | RSI(10) entre 45–65 | Momentum sin sobrecompra/sobreventa |
| F3 | Volumen > media×1.5 | Hay dinero real entrando (whale inflow) |
| F4 | Price Action alcista | La estructura de velas confirma |

- 🟢 **4/4** → entrada válida con SL y TP calculados
- 🟡 **3/4** → casi listo, monitorear
- 🔴 **≤2/4** → esperar mejor momento
            """)

    with st.expander("📐 ¿Qué es el Price Action?"):
        st.markdown("""
**Price Action** analiza la **forma** del gráfico, no solo los números.

- **Estructura HH/HL** (Higher Highs / Higher Lows) → tendencia alcista
- **Estructura LH/LL** (Lower Highs / Lower Lows) → tendencia bajista
- **Calidad del movimiento** → ¿las velas alcistas son más grandes que las bajistas?
- **Soporte y Resistencia** → niveles donde el precio rebotó antes

La calidad va de 0 a 1. Un valor ≥ 0.55 indica un movimiento sólido.
            """)

    with st.expander("🤖 ¿Qué es la Señal ML Lorentziana?"):
        st.markdown("""
Es una señal de **Machine Learning** basada en el algoritmo k-NN (k vecinos más cercanos) con distancia Lorentziana.

Funciona así:
1. Toma las últimas ~150 velas como historial
2. Calcula RSI y EMA de cada vela
3. Busca los 8 momentos históricos más similares al actual
4. Si en esos momentos el precio subió → COMPRA, si bajó → VENTA

⚠️ Es una **aproximación simplificada** — no es el indicador original de TradingView. Úsala como una señal adicional, no como la única.
            """)

    with st.expander("💥 ¿Qué es el detector Pump/Dump?"):
        st.markdown("""
Detecta movimientos inusuales de precio comparando:

- **Movimiento 1h y 4h** — qué tan fuerte fue el cambio reciente
- **Ratio de volumen** — si el volumen actual es 2× el promedio

**Fases del PUMP:**
- 🚀 EN CURSO → está subiendo ahora con volumen
- 📊 CONSOLIDANDO → subió fuerte, ahora descansa
- ⚠️ AGOTADO → ya subió mucho, volumen bajando

**Fases del DUMP:**
- 💥 EN CURSO → está cayendo con volumen
- 🛑 FRENANDO → la caída se desacelera
- 🟢 POSIBLE SUELO → caída grande, volumen bajo = posible rebote
            """)

    with st.expander("📊 ¿Qué bot usar según el mercado?"):
        st.markdown("""
| Situación | Bot recomendado |
|-----------|----------------|
| Precio lateral, sin tendencia clara | **Grid Long/Short** |
| Tendencia alcista fuerte | **Infinity Long** |
| Tendencia bajista fuerte | **Infinity Short** |
| Precio cayó mucho (dip) | **DCA Long** |
| Precio subió mucho (pump reciente) | **DCA Short** |

**Regla general:** Grid Bot = lateral · Infinity = tendencia · DCA = correcciones
            """)

    with st.expander("⚠️ Aviso legal"):
        st.markdown("""
Quant Panel es una herramienta de **análisis técnico automatizado**.

- No es asesoramiento financiero
- Los resultados pasados no garantizan rendimientos futuros
- El trading de criptomonedas conlleva riesgo de pérdida total del capital
- Siempre usá gestión de riesgo y stop loss

**Usá esta herramienta como apoyo a tu propio análisis, no como señal automática de entrada.**
            """)

