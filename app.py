"""
Quant Panel Web v2.0 — Streamlit Cloud
Screener de Grid Bots para Pionex
Incluye: Price Action + Smart Entry semáforo 4 fases
"""

import streamlit as st
import time, math, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone

try:
    import ccxt
except ImportError:
    st.error("Falta instalar ccxt"); st.stop()

try:
    import requests
except ImportError:
    st.error("Falta instalar requests"); st.stop()

# ── Config ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Quant Panel", page_icon="⚡",
                   layout="centered", initial_sidebar_state="collapsed")

ANTHROPIC_KEY  = st.secrets.get("ANTHROPIC_KEY", "")
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
MIN_VOL        = 1_000_000
MAX_TOKENS     = 25
REQ_DELAY      = 0.35
STABLECOINS    = {"USDT","USDC","BUSD","DAI","TUSD","FDUSD","USDD","USDP","FRAX"}

EMA_LEN=50; RSI_LEN=10; RSI_OS=45; RSI_OB=65
VOL_LEN=14; VOL_MULT=1.8; ATR_LEN=14; SL_M=3.0; TP_M=4.5

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.main .block-container{padding:1rem 1rem 2rem 1rem;max-width:480px}
.stTabs [data-baseweb="tab-list"]{gap:2px}
.stTabs [data-baseweb="tab"]{padding:8px 14px;font-size:13px}
.card{background:#111827;border-radius:12px;padding:12px 14px;
      margin-bottom:10px;border:1px solid #1e293b}
.card-green{background:#052e16;border-radius:12px;padding:12px 14px;
            margin-bottom:10px;border:1px solid #166534}
.card-red{background:#1a0a00;border-radius:12px;padding:12px 14px;
          margin-bottom:10px;border:1px solid #7c2020}
.card-yellow{background:#1c1400;border-radius:12px;padding:12px 14px;
             margin-bottom:10px;border:1px solid #854d0e}
.tag-pump{background:#7c2020;color:#fff;border-radius:6px;
          padding:2px 8px;font-size:11px;font-weight:700}
.tag-bot{background:#4c1d95;color:#fff;border-radius:6px;
         padding:2px 8px;font-size:11px;font-weight:600}
.tag-score{background:#1c1917;color:#f59e0b;border-radius:6px;
           padding:2px 8px;font-size:11px}
.tag-green{background:#064e3b;color:#10b981;border-radius:6px;
           padding:2px 8px;font-size:11px;font-weight:700}
.tag-red{background:#450a0a;color:#ef4444;border-radius:6px;
         padding:2px 8px;font-size:11px;font-weight:700}
.tag-yellow{background:#422006;color:#f59e0b;border-radius:6px;
            padding:2px 8px;font-size:11px;font-weight:700}
.t-green{color:#10b981;font-weight:600}
.t-red{color:#ef4444;font-weight:600}
.t-yellow{color:#f59e0b;font-weight:600}
.t-sub{color:#64748b;font-size:12px}
.divider{border-top:1px solid #1e293b;margin:8px 0}
h1{font-size:1.5rem!important}
h3{font-size:1rem!important;margin-bottom:4px!important}
.fase-ok{color:#10b981;font-size:13px}
.fase-no{color:#ef4444;font-size:13px}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# INDICADORES PURE PYTHON
# ══════════════════════════════════════════════════════════════════

def calc_ema(v, p):
    if len(v)<p: return []
    k=2.0/(p+1); r=[sum(v[:p])/p]
    for x in v[p:]: r.append(x*k+r[-1]*(1-k))
    return r

def calc_rsi(c, p):
    if len(c)<p+2: return []
    d=[c[i]-c[i-1] for i in range(1,len(c))]
    g=[max(x,0.) for x in d]; l=[abs(min(x,0.)) for x in d]
    ag=sum(g[:p])/p; al=sum(l[:p])/p; r=[]
    for i in range(p,len(d)):
        ag=(ag*(p-1)+g[i])/p; al=(al*(p-1)+l[i])/p
        r.append(100. if al==0 else 100.-100./(1.+ag/al))
    return r

def calc_sma(v, p):
    if len(v)<p: return []
    return [sum(v[i-p:i])/p for i in range(p, len(v)+1)]

def calc_atr(c, p):
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
    return {"chop":round(chop,2),"vol":round(vol,2),
            "range":round((max(c)-min(c))/p0*100,2),
            "net":round((c[-1]-c[0])/c[0]*100,2)}

# ══════════════════════════════════════════════════════════════════
# PRICE ACTION
# ══════════════════════════════════════════════════════════════════

def pa_estructura(closes, n=20):
    if len(closes)<n: return "INDEFINIDA", 0.0
    c=closes[-n:]
    highs=[c[i] for i in range(1,len(c)-1) if c[i]>c[i-1] and c[i]>c[i+1]]
    lows =[c[i] for i in range(1,len(c)-1) if c[i]<c[i-1] and c[i]<c[i+1]]
    if len(highs)<2 or len(lows)<2: return "LATERAL", 0.3
    ht=highs[-1]>highs[-2]; lt=lows[-1]>lows[-2]
    if ht and lt:
        f=min((highs[-1]-highs[-2])/highs[-2]*10+(lows[-1]-lows[-2])/lows[-2]*10,1.0)
        return "ALCISTA (HH/HL)", round(f,2)
    elif not ht and not lt:
        f=min((highs[-2]-highs[-1])/highs[-2]*10+(lows[-2]-lows[-1])/lows[-2]*10,1.0)
        return "BAJISTA (LH/LL)", round(f,2)
    return "LATERAL", 0.3

def pa_calidad(closes, n=10):
    if len(closes)<n+3: return 0.5
    imp=closes[-n:]
    verdes=[imp[i+1]-imp[i] for i in range(len(imp)-1) if imp[i+1]>imp[i]]
    rojas =[imp[i]-imp[i+1] for i in range(len(imp)-1) if imp[i+1]<imp[i]]
    tv=sum(verdes)/len(verdes) if verdes else 0
    tr=sum(rojas)/len(rojas)   if rojas  else 0
    rv=tv/max(tr,1e-9)
    path=sum(abs(imp[i+1]-imp[i]) for i in range(len(imp)-1))
    net=abs(imp[-1]-imp[0])
    ef=net/max(path,1e-9)
    return round(min(rv*0.5+ef*0.5,1.0),2)

def pa_sr(closes, n=40):
    if len(closes)<10: return [],[]
    cur=closes[-1]; niveles=[]
    for i in range(1,min(n,len(closes))-1):
        idx=-(i+1)
        h=closes[idx]; hp=closes[idx-1]; hn=closes[idx+1]
        if h>hp and h>hn: niveles.append(("R",h))
        if h<hp and h<hn: niveles.append(("S",h))
    agr=[]
    for t,p in sorted(niveles,key=lambda x:x[1]):
        merged=False
        for g in agr:
            if abs(p-g[1])/g[1]<0.015: merged=True; break
        if not merged: agr.append([t,p])
    sop=sorted([(p) for t,p in agr if p<cur],reverse=True)[:2]
    res=sorted([(p) for t,p in agr if p>cur])[:2]
    return sop, res

def analizar_pa(closes):
    est, fuerza = pa_estructura(closes)
    cal         = pa_calidad(closes)
    sop, res    = pa_sr(closes)
    alcista     = "ALCISTA" in est
    bajista     = "BAJISTA" in est
    if alcista and cal>=0.55:   v,c,col="✅ Impulso alcista de calidad","Alta","green"
    elif alcista:               v,c,col="⚠️ Alcista pero movimiento débil","Media","yellow"
    elif bajista and cal>=0.55: v,c,col="🔴 Tendencia bajista confirmada","Alta","red"
    elif bajista:               v,c,col="⚠️ Bajista pero rebote posible","Media","yellow"
    elif "LATERAL" in est:      v,c,col="↔️ Lateral — ideal para Grid","Media","yellow"
    else:                       v,c,col="⚪ Estructura indefinida","Baja","sub"
    return {"veredicto":v,"confianza":c,"color":col,"estructura":est,
            "fuerza":fuerza,"calidad":cal,"soportes":sop,"resistencias":res}

# ══════════════════════════════════════════════════════════════════
# SMART ENTRY — 4 FASES (corto plazo)
# ══════════════════════════════════════════════════════════════════

def smart_entry(closes, volumes, pa=None):
    resultado = {"fases":{1:False,2:False,3:False,4:False},
                 "vals":{}, "fases_ok":0, "ok":False,
                 "sl":None,"tp":None,"atr":None,"precio":None}
    if not closes or len(closes)<EMA_LEN+RSI_LEN+5: return resultado
    cur=closes[-1]; resultado["precio"]=cur

    # Fase 1: EMA50
    e50s=calc_ema(closes,EMA_LEN)
    e50=e50s[-1] if e50s else None
    f1=bool(e50 and cur>e50)
    resultado["fases"][1]=f1
    resultado["vals"][1]=f"Precio {fmt_p(cur)} | EMA50 {fmt_p(e50)}"

    # Fase 2: RSI 45-65
    r10s=calc_rsi(closes,RSI_LEN)
    r10=r10s[-1] if r10s else None
    f2=bool(r10 and RSI_OS<r10<RSI_OB)
    resultado["fases"][2]=f2
    resultado["vals"][2]=f"RSI(10) = {r10:.1f}" if r10 else "N/A"

    # Fase 3: Volumen spike
    vsma=calc_sma(volumes,VOL_LEN)
    vm=vsma[-1] if vsma else None
    vr=round(volumes[-1]/vm,2) if vm and vm>0 else 0
    f3=vr>=VOL_MULT
    resultado["fases"][3]=f3
    resultado["vals"][3]=f"Ratio vol = {vr}× (mín {VOL_MULT}×)"

    # Fase 4: Price Action
    pa_local=pa or analizar_pa(closes[-50:])
    f4=("ALCISTA" in pa_local["estructura"] and pa_local["calidad"]>=0.55)
    resultado["fases"][4]=f4
    resultado["vals"][4]=f"{pa_local['estructura']} | calidad={pa_local['calidad']}"

    # ATR y SL/TP
    atr=calc_atr(closes,ATR_LEN)
    if atr:
        resultado["atr"]=round(atr,8)
        resultado["sl"]=round(cur-atr*SL_M,8)
        resultado["tp"]=round(cur+atr*TP_M,8)

    n=sum(1 for v in resultado["fases"].values() if v)
    resultado["fases_ok"]=n
    resultado["ok"]=(n==4)
    return resultado

def se_tag(n, total=4):
    if n==total: return '<span class="tag-green">🟢'*total+' ENTRADA</span>'
    if n==total-1: return f'<span class="tag-yellow">🟡 {n}/{total} fases</span>'
    return f'<span class="tag-red">🔴 {n}/{total} fases</span>'

# ══════════════════════════════════════════════════════════════════
# EXCHANGE
# ══════════════════════════════════════════════════════════════════

def _make_ex():  return ccxt.binance({"enableRateLimit":True,"timeout":15000})
def _make_alt(): return ccxt.gateio({"enableRateLimit":True,"timeout":15000})

def fetch_ohlcv(symbol, tf="1h", limit=100):
    sym=f"{symbol}/USDT"
    for mk in [_make_ex,_make_alt]:
        try:
            data=mk().fetch_ohlcv(sym,tf,limit=limit)
            if data and len(data)>=20:
                return [d[4] for d in data],[d[5] for d in data]
        except: continue
    return None,None

@st.cache_data(ttl=300)
def fetch_all_tickers():
    for mk in [_make_ex,_make_alt]:
        try: return mk().fetch_tickers()
        except: continue
    return {}

# ══════════════════════════════════════════════════════════════════
# SCANNER
# ══════════════════════════════════════════════════════════════════

STABLECOINS_SET={"USDT","USDC","BUSD","DAI","TUSD","FDUSD","USDD","USDP","FRAX"}

def build_pool():
    tickers=fetch_all_tickers(); pool=[]
    for sym,t in tickers.items():
        if not sym.endswith("/USDT"): continue
        base=sym.replace("/USDT","")
        if base in STABLECOINS_SET: continue
        vol=t.get("quoteVolume") or 0
        if vol<MIN_VOL: continue
        pool.append({"base":base,"vol":vol,
                     "change_24h":t.get("percentage") or 0,
                     "price":t.get("last") or 0})
    pool.sort(key=lambda x:x["vol"],reverse=True)
    return pool[:MAX_TOKENS]

def score_token(coin, c1h, v1h, c7d, v7d):
    m=chop_metrics(c1h[-100:])
    if not m: return None
    liq=math.log10(max(coin["vol"],1)); chop=m["chop"]
    vol=m["vol"]; net=m["net"]; c24=coin["change_24h"]
    e50s=calc_ema(c1h,50)
    trend_ok=c1h[-1]>e50s[-1] if e50s else None
    bajada=max(0,-c24); subida=max(0,c24)
    pen_b=bajada*.5 if bajada<=15 else 7.5+(bajada-15)
    pen_s=subida*.5 if subida<=15 else 7.5+(subida-15)
    gl=chop*8+vol*2+liq*2+subida*.3-pen_b
    gs=chop*8+vol*2+liq*2+bajada*.3-pen_s
    bil=max(net,0)*5+vol*1.5+liq*2; bis=max(-net,0)*5+vol*1.5+liq*2
    il=bil if trend_ok is None or trend_ok else bil*.3
    is_=bis if trend_ok is None or not trend_ok else bis*.3
    dip=min(max(-c24,0),30); pmp=min(max(c24,0),30)
    dl=dip*3+vol*1.5+liq*2+chop; ds=pmp*3+vol*1.5+liq*2+chop
    if net<-15: dl*=.4
    if net>15:  ds*=.4
    scores={"GRID LONG":round(gl,1),"GRID SHORT":round(gs,1),
            "INF LONG":round(il,1),"INF SHORT":round(is_,1),
            "DCA LONG":round(dl,1),"DCA SHORT":round(ds,1)}
    best=max(scores,key=scores.get)
    pa=analizar_pa(c7d[-50:] if c7d else c1h[-50:])
    se=smart_entry(c7d or c1h, v7d or v1h, pa=pa)
    return {"token":coin["base"],"price":coin["price"],"change_24h":c24,
            "chop":chop,"vol_h":vol,"range":m["range"],
            "liq_m":round(coin["vol"]/1e6,1),"trend_ok":trend_ok,
            "pa":pa,"se":se,"best":best,
            "best_score":round(scores[best],1),"scores":scores}

def run_scan(progress_cb, result_cb):
    try:
        progress_cb("Obteniendo tickers de Binance...",0.0)
        pool=build_pool()
        if not pool: result_cb([],"No se pudo conectar"); return
        results=[]
        for i,coin in enumerate(pool):
            progress_cb(f"Analizando {coin['base']} ({i+1}/{len(pool)})...",(i+1)/len(pool))
            c1h,v1h=fetch_ohlcv(coin["base"],"1h",100)
            if c1h is None: continue
            c7d,v7d=fetch_ohlcv(coin["base"],"1h",168)
            r=score_token(coin,c1h,v1h,c7d,v7d)
            if r: results.append(r)
            time.sleep(REQ_DELAY)
        results.sort(key=lambda x:x["best_score"],reverse=True)
        result_cb(results[:10],None)
    except Exception as e:
        result_cb([],str(e))

# ══════════════════════════════════════════════════════════════════
# COINGECKO + NOTICIAS + IA
# ══════════════════════════════════════════════════════════════════

CG_MAP={"SYN":"synapse-2","FET":"fetch-ai","AGIX":"singularitynet",
        "RUNE":"thorchain","CFX":"conflux-token","GMT":"stepn",
        "PEOPLE":"constitutiondao","ID":"space-id","MANA":"decentraland",
        "SAND":"the-sandbox","AXS":"axie-infinity"}

@st.cache_data(ttl=3600)
def get_cg_id(sym):
    if sym.upper() in CG_MAP: return CG_MAP[sym.upper()]
    try:
        r=requests.get(f"{COINGECKO_BASE}/coins/list",timeout=10)
        coins=r.json()
        m=[c for c in coins if c.get("symbol","").lower()==sym.lower()]
        if len(m)==1: return m[0]["id"]
        if len(m)>1:
            ids=",".join(c["id"] for c in m[:15]); time.sleep(1)
            r2=requests.get(f"{COINGECKO_BASE}/coins/markets",
                params={"vs_currency":"usd","ids":ids,"order":"market_cap_desc"},timeout=10)
            d=r2.json()
            if d: return d[0]["id"]
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_supply(cg_id):
    if not cg_id: return None
    try:
        r=requests.get(f"{COINGECKO_BASE}/coins/{cg_id}",
            params={"localization":"false","tickers":"false","market_data":"true",
                    "community_data":"false","developer_data":"false"},timeout=12)
        d=r.json(); md=d.get("market_data",{})
        def fmt(v):
            if v is None: return "N/A"
            if v>=1e12: return f"{v/1e12:.2f}T"
            if v>=1e9:  return f"{v/1e9:.2f}B"
            if v>=1e6:  return f"{v/1e6:.2f}M"
            return f"{v:,.0f}"
        def pdate(s):
            if not s: return "N/A"
            try: return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%d/%m/%Y")
            except: return "N/A"
        circ=md.get("circulating_supply"); maxi=md.get("max_supply")
        total=md.get("total_supply"); ath=md.get("ath",{}).get("usd")
        cur=md.get("current_price",{}).get("usd")
        pct=round((cur-ath)/ath*100,1) if ath and cur else None
        return {"max":fmt(maxi) if maxi else("∞" if not total else fmt(total)),
                "circ":fmt(circ),"ath":f"${ath:,.4f}" if ath else "N/A",
                "ath_date":pdate(md.get("ath_date",{}).get("usd")),
                "pct_ath":f"{pct}%" if pct is not None else "N/A",
                "cats":", ".join(d.get("categories",[])[:2]) or "N/A"}
    except: return None

@st.cache_data(ttl=1800)
def get_unlocks(sym):
    try:
        r=requests.get(f"https://token.unlocks.app/api/token/{sym.lower()}",
            timeout=10,headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code!=200: return []
        evs=r.json().get("unlockEvents") or r.json().get("events") or []
        now=datetime.now(timezone.utc).timestamp()
        result=[]
        for ev in evs:
            ts=ev.get("timestamp") or ev.get("date")
            if ts is None: continue
            if isinstance(ts,str):
                try: ts=datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()
                except: continue
            days=(ts-now)/86400
            if 0<days<=90:
                result.append({"date":datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%d/%m/%Y"),
                                "days":round(days),
                                "cat":ev.get("category") or ev.get("type") or "Unlock",
                                "pct":ev.get("percentOfSupply") or 0,"urgent":days<=14})
        result.sort(key=lambda x:x["days"])
        return result[:5]
    except: return []

@st.cache_data(ttl=1800)
def get_news(sym):
    FEEDS=[("CoinDesk","https://www.coindesk.com/arc/outboundfeeds/rss/"),
           ("CoinTelegraph","https://cointelegraph.com/rss"),
           ("Decrypt","https://decrypt.co/feed"),
           ("TheBlock","https://www.theblock.co/rss.xml")]
    POS=["surge","rally","pump","gain","rise","bull","high","record","launch","approved","listing"]
    NEG=["crash","drop","fall","plunge","bear","hack","exploit","scam","delist","decline"]
    s=sym.lower(); found=[]
    for src,url in FEEDS:
        try:
            r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code!=200: continue
            root=ET.fromstring(r.content)
            items=root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items:
                t=(item.findtext("title") or "").strip()
                desc=(item.findtext("description") or "").strip()
                if not re.search(r'\b'+re.escape(s)+r'\b',(t+" "+desc).lower()): continue
                tl=t.lower()
                pos=sum(1 for k in POS if k in tl); neg=sum(1 for k in NEG if k in tl)
                sent="🟢" if pos>neg else("🔴" if neg>pos else "⚪")
                found.append({"title":t[:85],"src":src,"sent":sent})
        except: continue
    seen,uniq=set(),[]
    for n in found:
        k=n["title"][:30].lower()
        if k not in seen: seen.add(k); uniq.append(n)
    return uniq[:5]

def get_ai(sym, news):
    if not ANTHROPIC_KEY: return None
    txt="\n".join(f"- {n['title']}" for n in news)
    prompt=(f"Token: {sym}\nTitulares: {txt}\n"
            f"Responde en español, formato exacto:\n"
            f"POSITIVO: punto1 | punto2\nNEGATIVO: riesgo1 | riesgo2\nEVENTO: evento clave")
    try:
        r=requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":250,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]},timeout=25)
        blocks=r.json().get("content",[])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text").strip()
    except: return None

def analyze_token(sym, progress_cb, result_cb):
    try:
        progress_cb("Descargando velas...",0.2)
        c,v=fetch_ohlcv(sym,"1h",168)
        if c is None: result_cb(None,f"No se encontró {sym}/USDT"); return
        progress_cb("Price Action...",0.35)
        pa=analizar_pa(c[-50:])
        progress_cb("Smart Entry...",0.45)
        se=smart_entry(c,v,pa=pa)
        progress_cb("CoinGecko...",0.55)
        supply=get_supply(get_cg_id(sym))
        progress_cb("Token unlocks...",0.65)
        unlocks=get_unlocks(sym)
        progress_cb("Noticias RSS...",0.75)
        news=get_news(sym)
        progress_cb("Análisis IA...",0.9)
        ai=get_ai(sym,news)
        result_cb({"symbol":sym,"price":c[-1],"closes":c,
                   "pa":pa,"se":se,"supply":supply,
                   "unlocks":unlocks,"news":news,"ai":ai},None)
    except Exception as e:
        result_cb(None,str(e))

# ══════════════════════════════════════════════════════════════════
# HELPERS UI
# ══════════════════════════════════════════════════════════════════

def fmt_p(v):
    if v is None: return "N/A"
    if v<0.0001: return f"${v:.8f}"
    if v<1: return f"${v:.4f}"
    return f"${v:,.2f}"

def pa_card_html(pa):
    col_map={"green":"#10b981","red":"#ef4444","yellow":"#f59e0b","sub":"#64748b"}
    col=col_map.get(pa["color"],"#64748b")
    sop_str=" | ".join(fmt_p(s) for s in pa["soportes"]) if pa["soportes"] else "N/A"
    res_str=" | ".join(fmt_p(r) for r in pa["resistencias"]) if pa["resistencias"] else "N/A"
    return f"""
    <div class="card">
        <div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📐 PRICE ACTION</div>
        <div style="color:{col};font-size:13px;font-weight:600;margin-bottom:6px">{pa['veredicto']}</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap" class="t-sub">
            <span>Estructura: {pa['estructura']}</span>
            <span>Calidad: {pa['calidad']}</span>
            <span>Confianza: {pa['confianza']}</span>
        </div>
        <div class="divider"></div>
        <div style="display:flex;gap:12px;font-size:12px">
            <span class="t-green">Soportes: {sop_str}</span>
        </div>
        <div style="display:flex;gap:12px;font-size:12px">
            <span class="t-red">Resistencias: {res_str}</span>
        </div>
    </div>"""

def se_card_html(se):
    n=se["fases_ok"]
    if n==4:   cab,bdr="🟢 ENTRADA VÁLIDA — 4/4 fases","#166534"
    elif n==3: cab,bdr="🟡 CASI LISTO — 3/4 fases","#854d0e"
    elif n==2: cab,bdr="🟠 ESPERAR — 2/4 fases","#7c2020"
    else:      cab,bdr="🔴 NO ENTRAR — 0-1/4 fases","#7c2020"

    filas=""
    nombres={1:"Tendencia (precio > EMA50)",2:"Momentum (RSI 45–65)",
             3:"Volumen spike ×1.8",4:"Price Action alcista"}
    for num in range(1,5):
        ok=se["fases"][num]
        ic="✅" if ok else "❌"
        val=se["vals"].get(num,"")
        filas+=f'<div style="margin-bottom:4px"><span style="color:{"#10b981" if ok else "#ef4444"}">{ic} Fase {num}: {nombres[num]}</span><br><span class="t-sub" style="padding-left:20px">{val}</span></div>'

    sl_tp=""
    if n==4:
        rr=round((se["tp"]-se["precio"])/(se["precio"]-se["sl"]),1) if se["sl"] and se["tp"] and se["precio"] else 0
        sl_tp=f"""
        <div class="divider"></div>
        <div style="display:flex;justify-content:space-around;margin-top:4px">
            <span class="t-red">🔴 SL {fmt_p(se['sl'])}</span>
            <span class="t-green">🟢 TP {fmt_p(se['tp'])}</span>
        </div>
        <div style="text-align:center;margin-top:4px" class="t-sub">⚖️ Ratio R/R = 1:{rr}</div>"""

    return f"""
    <div class="card" style="border-color:{bdr}">
        <div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🚦 SMART ENTRY — SEMÁFORO</div>
        <div style="font-weight:700;font-size:14px;margin-bottom:8px">{cab}</div>
        <div class="divider"></div>
        {filas}
        {sl_tp}
    </div>"""

# ══════════════════════════════════════════════════════════════════
# UI PRINCIPAL
# ══════════════════════════════════════════════════════════════════

import threading

st.markdown("# ⚡ Quant Panel")
st.markdown('<p class="t-sub">Screener de Grid Bots · Pionex · v2.0</p>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📡 Scanner", "📊 Análisis", "⚙️ Ajustes"])

# ─────────────────────────────────────────────────────────────────
# TAB 1 — SCANNER
# ─────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Mejores tokens para Grid Bot")
    st.caption("Top 25 Binance · Price Action · Semáforo Smart Entry 4 fases")

    if "scan_results" not in st.session_state:
        st.session_state.scan_results = []

    col1,col2=st.columns([2,1])
    with col1:
        run_scan_btn=st.button("🔍 Escanear ahora",use_container_width=True,type="primary")
    with col2:
        if st.session_state.scan_results:
            st.caption(f"✅ {len(st.session_state.scan_results)} tokens")

    if run_scan_btn:
        with st.status("Escaneando mercado...",expanded=True) as status:
            st.write("Obteniendo tickers de Binance...")
            pool=build_pool()
            if not pool:
                st.error("No se pudo conectar a Binance"); st.stop()
            bar=st.progress(0); results=[]
            for i,coin in enumerate(pool):
                st.write(f"Analizando {coin['base']} ({i+1}/{len(pool)})...")
                bar.progress((i+1)/len(pool))
                c1h,v1h=fetch_ohlcv(coin["base"],"1h",100)
                if c1h is None: continue
                c7d,v7d=fetch_ohlcv(coin["base"],"1h",168)
                r=score_token(coin,c1h,v1h,c7d,v7d)
                if r: results.append(r)
                time.sleep(REQ_DELAY)
            results.sort(key=lambda x:x["best_score"],reverse=True)
            st.session_state.scan_results=results[:10]
            status.update(label=f"✅ Top {len(results[:10])} tokens",state="complete")

    for r in st.session_state.scan_results:
        pa=r["pa"]; se=r["se"]
        pdet=se["ok"]
        c24=r["change_24h"]
        trend_ic="🟢" if r["trend_ok"] else ("🔴" if r["trend_ok"] is False else "⚪")
        change_class="t-green" if c24>=0 else "t-red"
        pump_tag='<span class="tag-pump">🔥 PUMP</span>' if pdet else ""
        n=se["fases_ok"]
        se_tag_html=f'<span class="tag-green">🟢×{n}</span>' if n==4 else \
                    f'<span class="tag-yellow">🟡{n}/4</span>' if n==3 else \
                    f'<span class="tag-red">🔴{n}/4</span>'
        pa_col={"green":"#10b981","red":"#ef4444","yellow":"#f59e0b"}.get(pa["color"],"#64748b")
        sl_tp=""
        if pdet:
            sl_tp=f"""<div class="divider"></div>
            <div style="display:flex;justify-content:space-around">
                <span class="t-red">SL {fmt_p(se.get('sl'))}</span>
                <span class="t-green">TP {fmt_p(se.get('tp'))}</span>
            </div>"""
        st.markdown(f"""
        <div class="{'card-green' if pdet else 'card'}">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:17px;font-weight:700;color:#f1f5f9">{r['token']}</span>
                <span style="display:flex;gap:6px;align-items:center">
                    <span class="{change_class}">{c24:+.1f}%</span>
                    {pump_tag}
                </span>
            </div>
            <div style="color:#f59e0b;font-size:15px;margin:2px 0">{fmt_p(r['price'])}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">
                <span class="tag-bot">{r['best']}</span>
                <span class="tag-score">Score {r['best_score']}</span>
                {se_tag_html}
                <span class="t-sub">{trend_ic}</span>
            </div>
            <div style="color:{pa_col};font-size:12px">{pa['veredicto']}</div>
            <div class="t-sub">Chop {r['chop']} · Vol {r['vol_h']:.1f}% · Rng {r['range']:.1f}% · {r['liq_m']}M$</div>
            {sl_tp}
        </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# TAB 2 — ANÁLISIS INDIVIDUAL
# ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Análisis Individual")
    st.caption("Price Action · Smart Entry · Supply · Unlocks · Noticias · IA")

    col1,col2=st.columns([3,1])
    with col1:
        sym_input=st.text_input("Ticker",placeholder="BTC, SOL, SYN...",
                                label_visibility="collapsed").upper().strip()
    with col2:
        do_analyze=st.button("Analizar",type="primary",use_container_width=True)

    if do_analyze and sym_input:
        with st.status(f"Analizando {sym_input}...",expanded=True) as status:
            st.write("Descargando velas 1h...")
            c,v=fetch_ohlcv(sym_input,"1h",168)
            if c is None:
                st.error(f"No se encontró {sym_input}/USDT"); st.stop()
            st.write("Price Action...")
            pa=analizar_pa(c[-50:])
            st.write("Smart Entry (4 fases)...")
            se=smart_entry(c,v,pa=pa)
            st.write("CoinGecko...")
            supply=get_supply(get_cg_id(sym_input))
            st.write("Token unlocks...")
            unlocks=get_unlocks(sym_input)
            st.write("Noticias RSS...")
            news=get_news(sym_input)
            ai_text=None
            if ANTHROPIC_KEY:
                st.write("Resumen IA...")
                ai_text=get_ai(sym_input,news)
            status.update(label=f"✅ {sym_input} analizado",state="complete")

        # Precio
        st.markdown(f"""
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:baseline">
                <span style="font-size:22px;font-weight:700;color:#f1f5f9">{sym_input}</span>
                <span class="t-yellow" style="font-size:20px">{fmt_p(c[-1])}</span>
            </div>
        </div>""", unsafe_allow_html=True)

        # Price Action
        st.markdown(pa_card_html(pa), unsafe_allow_html=True)

        # Smart Entry
        st.markdown(se_card_html(se), unsafe_allow_html=True)

        # Supply
        if supply:
            st.markdown(f"""
            <div class="card">
                <div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">💎 SUPPLY &amp; ATH/ATL</div>
                <div style="display:flex;justify-content:space-around;text-align:center;margin-bottom:8px">
                    <div><div class="t-sub">Supply Máx</div>
                         <div style="color:#f1f5f9;font-size:14px">{supply['max']}</div></div>
                    <div><div class="t-sub">Circulante</div>
                         <div style="color:#f1f5f9;font-size:14px">{supply['circ']}</div></div>
                </div>
                <div style="display:flex;justify-content:space-around;text-align:center">
                    <div><div class="t-sub">ATH</div>
                         <div class="t-red">{supply['ath']}</div>
                         <div class="t-sub">{supply['ath_date']}</div></div>
                    <div><div class="t-sub">vs ATH</div>
                         <div style="color:#f1f5f9;font-size:15px">{supply['pct_ath']}</div></div>
                </div>
                <div class="divider"></div>
                <div class="t-sub">{supply['cats']}</div>
            </div>""", unsafe_allow_html=True)

        # Unlocks
        if unlocks:
            rows=""
            for u in unlocks:
                ic="⚠️" if u["urgent"] else "📅"
                col="#ef4444" if u["urgent"] else "#f1f5f9"
                pct=f" ({u['pct']:.1f}% supply)" if u["pct"] else ""
                rows+=f'<div style="color:{col};font-size:12px;margin-bottom:4px">{ic} {u["date"]} ({u["days"]}d) {u["cat"]}{pct}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔓 TOKEN UNLOCKS (90 días)</div>{rows}</div>', unsafe_allow_html=True)

        # Noticias
        if news:
            rows="".join(f'<div style="font-size:12px;color:#f1f5f9;margin-bottom:5px">{n["sent"]} <span class="t-sub">[{n["src"]}]</span> {n["title"]}</div>' for n in news)
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📰 NOTICIAS RECIENTES</div>{rows}</div>', unsafe_allow_html=True)

        # IA
        if ai_text:
            rows=""
            for line in ai_text.splitlines():
                line=line.strip()
                if not line: continue
                col="#10b981" if "POSITIVO" in line else("#ef4444" if "NEGATIVO" in line else "#f59e0b")
                rows+=f'<div style="color:{col};font-size:12px;margin-bottom:5px">{line}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🤖 ANÁLISIS IA</div>{rows}</div>', unsafe_allow_html=True)
        elif not ANTHROPIC_KEY:
            st.info("💡 Agrega ANTHROPIC_KEY en Ajustes para activar el análisis IA.")

    elif do_analyze:
        st.warning("Ingresa un ticker primero.")

# ─────────────────────────────────────────────────────────────────
# TAB 3 — AJUSTES
# ─────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Ajustes")
    st.markdown("**API Key de Anthropic** *(opcional)*")
    st.caption("Activa el análisis IA de noticias. Sin ella todo lo demás funciona igual.")
    st.code('# En Streamlit Cloud → Settings → Secrets:\nANTHROPIC_KEY = "sk-ant-..."')
    st.info("La key se configura en el dashboard de Streamlit Cloud para que no quede expuesta en el código.")
    st.divider()
    st.markdown("""**Fuentes de datos**
- 📊 **Binance API** — precios y velas en tiempo real
- 🦎 **CoinGecko** — supply, ATH/ATL, categorías
- 🔓 **token.unlocks.app** — calendario de vesting
- 📰 **RSS** — CoinDesk · CoinTelegraph · Decrypt · TheBlock
- 🤖 **Claude API** — resumen IA *(requiere key)*
    """)
    st.divider()
    st.markdown("""**Qué hay en v2.0**
- 📐 Price Action — estructura HH/HL, calidad de movimiento, S/R
- 🚦 Smart Entry — semáforo de 4 fases con SL/TP y ratio R/R
- 🔍 Scanner mejorado — PA y SmartEntry en cada resultado
    """)
    st.caption("⚠️ Información de mercado. No es recomendación de inversión.")
