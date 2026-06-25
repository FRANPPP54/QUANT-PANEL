"""
Quant Panel Web — Streamlit Cloud
Screener de Grid Bots para Pionex
"""

import streamlit as st
import time, math, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone

try:
    import ccxt
except ImportError:
    st.error("Falta instalar ccxt")
    st.stop()

try:
    import requests
except ImportError:
    st.error("Falta instalar requests")
    st.stop()

# ── Config ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quant Panel",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Leer key de Anthropic desde Streamlit Secrets (se configura en el dashboard)
ANTHROPIC_KEY  = st.secrets.get("ANTHROPIC_KEY", "")
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
MIN_VOL        = 1_000_000
MAX_TOKENS     = 25
REQ_DELAY      = 0.35
STABLECOINS    = {"USDT","USDC","BUSD","DAI","TUSD","FDUSD","USDD","USDP","FRAX"}

EMA_LEN=50; RSI_LEN=10; RSI_OS=45; RSI_OB=65
VOL_LEN=14; VOL_MULT=1.8; ATR_LEN=14; SL_M=3.0; TP_M=4.5

# ── CSS móvil ─────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { padding: 1rem 1rem 2rem 1rem; max-width: 480px; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 14px; font-size: 13px; }
    .card {
        background: #111827; border-radius: 12px;
        padding: 12px 14px; margin-bottom: 10px;
        border: 1px solid #1e293b;
    }
    .pump-card {
        background: #1a0a00; border-radius: 12px;
        padding: 12px 14px; margin-bottom: 10px;
        border: 1px solid #7c2020;
    }
    .tag-pump   { background:#7c2020; color:#fff; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:700; }
    .tag-bot    { background:#4c1d95; color:#fff; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:600; }
    .tag-score  { background:#1c1917; color:#f59e0b; border-radius:6px; padding:2px 8px; font-size:11px; }
    .t-green { color:#10b981; font-weight:600; }
    .t-red   { color:#ef4444; font-weight:600; }
    .t-yellow{ color:#f59e0b; font-weight:600; }
    .t-sub   { color:#64748b; font-size:12px; }
    .divider { border-top:1px solid #1e293b; margin:8px 0; }
    h1 { font-size: 1.5rem !important; }
    h3 { font-size: 1rem !important; margin-bottom: 4px !important; }
</style>
""", unsafe_allow_html=True)

# ── Indicadores Pure Python ────────────────────────────────────────

def calc_ema(v, p):
    if len(v) < p: return []
    k = 2.0/(p+1); r = [sum(v[:p])/p]
    for x in v[p:]: r.append(x*k + r[-1]*(1-k))
    return r

def calc_rsi(c, p):
    if len(c) < p+2: return []
    d = [c[i]-c[i-1] for i in range(1,len(c))]
    g = [max(x,0.) for x in d]; l = [abs(min(x,0.)) for x in d]
    ag = sum(g[:p])/p; al = sum(l[:p])/p; r = []
    for i in range(p, len(d)):
        ag=(ag*(p-1)+g[i])/p; al=(al*(p-1)+l[i])/p
        r.append(100. if al==0 else 100.-100./(1.+ag/al))
    return r

def calc_sma(v, p):
    if len(v)<p: return []
    return [sum(v[i-p:i])/p for i in range(p, len(v)+1)]

def calc_atr(c, p):
    d = [abs(c[i]-c[i-1]) for i in range(1,len(c))]
    if len(d)<p: return None
    a = sum(d[:p])/p
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

def pump_detector(closes, volumes):
    empty = {"ok":False,"ema50":None,"rsi10":None,"vr":None,
             "trend":False,"rsi_ok":False,"vspike":False,"sl":None,"tp":None}
    if not closes or len(closes)<EMA_LEN+RSI_LEN+5: return empty
    e50s=calc_ema(closes,EMA_LEN); r10s=calc_rsi(closes,RSI_LEN)
    vsma=calc_sma(volumes,VOL_LEN)
    if not e50s or not r10s or not vsma: return empty
    e50=e50s[-1]; r10=r10s[-1]; vm=vsma[-1]
    vr=volumes[-1]/vm if vm>0 else 0
    atr=calc_atr(closes,ATR_LEN); cur=closes[-1]
    trend=cur>e50; rok=RSI_OS<r10<RSI_OB; vsp=vr>VOL_MULT
    ok=trend and rok and vsp
    return {"ok":ok,"ema50":round(e50,8),"rsi10":round(r10,1),"vr":round(vr,2),
            "trend":trend,"rsi_ok":rok,"vspike":vsp,
            "sl":round(cur-atr*SL_M,8) if atr else None,
            "tp":round(cur+atr*TP_M,8) if atr else None}

# ── Exchange ───────────────────────────────────────────────────────
# Sin cache_resource — ccxt no es serializable en Streamlit Cloud

def _make_exchange():
    return ccxt.binance({"enableRateLimit": True, "timeout": 15000})

def _make_alt():
    return ccxt.gateio({"enableRateLimit": True, "timeout": 15000})

def fetch_ohlcv(symbol, tf="1h", limit=100):
    sym = f"{symbol}/USDT"
    for make_ex in [_make_exchange, _make_alt]:
        try:
            e    = make_ex()
            data = e.fetch_ohlcv(sym, tf, limit=limit)
            if data and len(data) >= 20:
                return [d[4] for d in data], [d[5] for d in data]
        except Exception:
            continue
    return None, None

@st.cache_data(ttl=300)
def fetch_all_tickers():
    for make_ex in [_make_exchange, _make_alt]:
        try:
            e = make_ex()
            return e.fetch_tickers()
        except Exception:
            continue
    return {}

# ── Scanner ────────────────────────────────────────────────────────

def build_pool():
    tickers = fetch_all_tickers()
    pool = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT"): continue
        base = sym.replace("/USDT","")
        if base in STABLECOINS: continue
        vol = t.get("quoteVolume") or 0
        if vol < MIN_VOL: continue
        pool.append({"base":base,"vol":vol,
                     "change_24h":t.get("percentage") or 0,
                     "price":t.get("last") or 0})
    pool.sort(key=lambda x:x["vol"],reverse=True)
    return pool[:MAX_TOKENS]

def score_and_pump(coin, c1h, v1h, c7d, v7d):
    m = chop_metrics(c1h[-100:])
    if not m: return None
    liq=math.log10(max(coin["vol"],1)); chop=m["chop"]
    vol=m["vol"]; net=m["net"]; c24=coin["change_24h"]
    e50s=calc_ema(c1h,50)
    trend_ok = c1h[-1]>e50s[-1] if e50s else None
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
    pump=pump_detector(c7d,v7d)
    return {"token":coin["base"],"price":coin["price"],"change_24h":c24,
            "chop":chop,"vol_h":vol,"range":m["range"],
            "liq_m":round(coin["vol"]/1e6,1),"trend_1h":trend_ok,
            "pump":pump,"best":best,"best_score":round(scores[best],1),"scores":scores}

# ── CoinGecko ──────────────────────────────────────────────────────

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
            data=r2.json()
            if data: return data[0]["id"]
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
                                "pct":ev.get("percentOfSupply") or 0,
                                "urgent":days<=14})
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

def get_ai_summary(sym, news):
    if not ANTHROPIC_KEY: return None
    txt="\n".join(f"- {n['title']}" for n in news)
    prompt=(f"Token: {sym}\nTitulares recientes: {txt}\n"
            f"Responde SOLO en este formato (español, conciso):\n"
            f"POSITIVO: punto1 | punto2\nNEGATIVO: riesgo1 | riesgo2\nEVENTO: evento más importante")
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

# ── Helpers UI ─────────────────────────────────────────────────────

def fmt_p(v):
    if v is None: return "N/A"
    if v<0.0001: return f"${v:.8f}"
    if v<1: return f"${v:.4f}"
    return f"${v:,.2f}"

def pct_color(v):
    if v is None: return ""
    return "t-green" if v>=0 else "t-red"

# ══════════════════════════════════════════════════════════════════
# UI PRINCIPAL
# ══════════════════════════════════════════════════════════════════

st.markdown("# ⚡ Quant Panel")
st.markdown('<p class="t-sub">Screener de Grid Bots · Pionex</p>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📡 Scanner", "📊 Análisis", "⚙️ Ajustes"])

# ─────────────────────────────────────────────────────────────────
# TAB 1 — SCANNER
# ─────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Mejores tokens para Grid Bot")
    st.caption("Analiza las top 25 monedas de Binance por volumen y detecta pumps activos.")

    if "scan_results" not in st.session_state:
        st.session_state.scan_results = []

    col1, col2 = st.columns([2,1])
    with col1:
        run_scan = st.button("🔍 Escanear ahora", use_container_width=True, type="primary")
    with col2:
        if st.session_state.scan_results:
            st.caption(f"✅ {len(st.session_state.scan_results)} tokens")

    if run_scan:
        with st.status("Escaneando mercado...", expanded=True) as status:
            st.write("Obteniendo tickers de Binance...")
            pool = build_pool()
            if not pool:
                st.error("No se pudo conectar a Binance. Verifica tu conexión.")
                st.stop()

            bar    = st.progress(0)
            results = []
            for i, coin in enumerate(pool):
                st.write(f"Analizando {coin['base']} ({i+1}/{len(pool)})...")
                bar.progress((i+1)/len(pool))
                c1h, v1h = fetch_ohlcv(coin["base"], "1h", 100)
                if c1h is None: continue
                c7d, v7d = fetch_ohlcv(coin["base"], "1h", 168)
                r = score_and_pump(coin, c1h, v1h, c7d or c1h, v7d or v1h)
                if r: results.append(r)
                time.sleep(REQ_DELAY)

            results.sort(key=lambda x: x["best_score"], reverse=True)
            st.session_state.scan_results = results[:10]
            status.update(label=f"✅ Top {len(results[:10])} tokens encontrados", state="complete")

    for r in st.session_state.scan_results:
        p   = r["pump"]
        pdet = p.get("ok", False)
        c24  = r["change_24h"]
        trend_ic = "🟢" if r["trend_1h"] else ("🔴" if r["trend_1h"] is False else "⚪")
        card_class = "pump-card" if pdet else "card"

        pump_tag = '<span class="tag-pump">🔥 PUMP</span>' if pdet else ""
        change_class = "t-green" if c24>=0 else "t-red"

        sl_tp = ""
        if pdet:
            sl_tp = f"""
            <div class="divider"></div>
            <div style="display:flex;justify-content:space-around;margin-top:4px">
                <span class="t-red">🔴 SL &nbsp;{fmt_p(p.get('sl'))}</span>
                <span class="t-green">🟢 TP &nbsp;{fmt_p(p.get('tp'))}</span>
            </div>"""

        st.markdown(f"""
        <div class="{card_class}">
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
                <span class="t-sub">{trend_ic} Tend &nbsp;|&nbsp; {r['liq_m']}M$</span>
            </div>
            <div class="t-sub">Chop {r['chop']} &nbsp;·&nbsp; Vol {r['vol_h']:.1f}% &nbsp;·&nbsp; Rng {r['range']:.1f}%</div>
            {sl_tp}
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# TAB 2 — ANÁLISIS INDIVIDUAL
# ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Análisis de token")
    st.caption("Supply · ATH/ATL · Unlocks · Noticias · IA")

    col1, col2 = st.columns([3, 1])
    with col1:
        sym_input = st.text_input("Ticker", placeholder="BTC, SOL, SYN...",
                                   label_visibility="collapsed").upper().strip()
    with col2:
        do_analyze = st.button("Analizar", type="primary", use_container_width=True)

    if do_analyze and sym_input:
        with st.status(f"Analizando {sym_input}...", expanded=True) as status:

            st.write("Descargando velas 1h (168 periodos)...")
            c, v = fetch_ohlcv(sym_input, "1h", 168)
            if c is None:
                st.error(f"No se encontró {sym_input}/USDT en Binance")
                st.stop()

            st.write("Calculando indicadores...")
            m    = chop_metrics(c[-100:]) or {}
            pump = pump_detector(c, v)

            st.write("Obteniendo supply y ATH (CoinGecko)...")
            cgid   = get_cg_id(sym_input)
            supply = get_supply(cgid)

            st.write("Consultando token unlocks...")
            unlocks = get_unlocks(sym_input)

            st.write("Buscando noticias RSS...")
            news = get_news(sym_input)

            ai_text = None
            if ANTHROPIC_KEY:
                st.write("Generando resumen IA...")
                ai_text = get_ai_summary(sym_input, news)

            status.update(label=f"✅ {sym_input} analizado", state="complete")

        # — Precio e indicadores ——————————————
        st.markdown(f"""
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:baseline">
                <span style="font-size:22px;font-weight:700;color:#f1f5f9">{sym_input}</span>
                <span class="t-yellow" style="font-size:18px">{fmt_p(c[-1])}</span>
            </div>
            <div class="divider"></div>
            <div style="display:flex;justify-content:space-around;text-align:center">
                <div><div class="t-sub">Choppiness</div>
                     <div style="color:#f1f5f9;font-size:16px;font-weight:600">{m.get('chop','N/A')}</div></div>
                <div><div class="t-sub">Vol Horaria</div>
                     <div style="color:#f1f5f9;font-size:16px;font-weight:600">{m.get('vol','N/A')}%</div></div>
                <div><div class="t-sub">Rango 48h</div>
                     <div style="color:#f1f5f9;font-size:16px;font-weight:600">{m.get('range','N/A')}%</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # — Pump detector ——————————————
        pdet = pump.get("ok", False)
        rsi_str = f"{pump['rsi10']:.1f}" if pump.get("rsi10") is not None else "N/A"
        pump_html = f"""
        <div class="{'pump-card' if pdet else 'card'}">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="{'color:#f59e0b' if pdet else 'color:#64748b'};font-weight:700;font-size:14px">
                    {'🔥 PUMP DETECTADO' if pdet else 'Pump Detector'}
                </span>
                <span style="background:{'#064e3b' if pdet else '#1c1917'};color:{'#10b981' if pdet else '#6b7280'};
                             border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700">
                    {'ACTIVO' if pdet else 'Inactivo'}
                </span>
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px" class="t-sub">
                <span>Precio > EMA50 &nbsp;{'✅' if pump.get('trend') else '❌'}</span>
                <span>RSI={rsi_str} &nbsp;{'✅' if pump.get('rsi_ok') else '❌'}</span>
                <span>Vol×{VOL_MULT} (ratio={pump.get('vr','N/A')}) &nbsp;{'✅' if pump.get('vspike') else '❌'}</span>
            </div>
        """
        if pdet:
            pump_html += f"""
            <div class="divider"></div>
            <div style="display:flex;justify-content:space-around;margin-top:4px">
                <span class="t-red">🔴 SL &nbsp;{fmt_p(pump.get('sl'))}</span>
                <span class="t-green">🟢 TP &nbsp;{fmt_p(pump.get('tp'))}</span>
            </div>"""
        pump_html += "</div>"
        st.markdown(pump_html, unsafe_allow_html=True)

        # — Supply & ATH ——————————————
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
                         <div class="t-red" style="font-size:13px">{supply['ath']}</div>
                         <div class="t-sub">{supply['ath_date']}</div></div>
                    <div><div class="t-sub">vs ATH ahora</div>
                         <div style="color:#f1f5f9;font-size:15px">{supply['pct_ath']}</div></div>
                </div>
                <div class="divider"></div>
                <div class="t-sub">{supply['cats']}</div>
            </div>
            """, unsafe_allow_html=True)

        # — Unlocks ——————————————
        if unlocks:
            rows = ""
            for u in unlocks:
                ic  = "⚠️" if u["urgent"] else "📅"
                col = "#ef4444" if u["urgent"] else "#f1f5f9"
                pct = f"  ({u['pct']:.1f}% supply)" if u["pct"] else ""
                rows += f'<div style="color:{col};font-size:12px;margin-bottom:4px">{ic} {u["date"]} ({u["days"]}d) &nbsp;{u["cat"]}{pct}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🔓 TOKEN UNLOCKS (próximos 90 días)</div>{rows}</div>', unsafe_allow_html=True)

        # — Noticias ——————————————
        if news:
            rows = ""
            for n in news:
                rows += f'<div style="font-size:12px;color:#f1f5f9;margin-bottom:5px">{n["sent"]} <span class="t-sub">[{n["src"]}]</span> {n["title"]}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">📰 NOTICIAS RECIENTES</div>{rows}</div>', unsafe_allow_html=True)

        # — IA ——————————————
        if ai_text:
            rows = ""
            for line in ai_text.splitlines():
                line = line.strip()
                if not line: continue
                col = "#10b981" if "POSITIVO" in line else ("#ef4444" if "NEGATIVO" in line else "#f59e0b")
                rows += f'<div style="color:{col};font-size:12px;margin-bottom:5px">{line}</div>'
            st.markdown(f'<div class="card"><div style="color:#64748b;font-size:12px;font-weight:600;margin-bottom:8px">🤖 ANÁLISIS IA</div>{rows}</div>', unsafe_allow_html=True)
        elif not ANTHROPIC_KEY:
            st.info("💡 Configura ANTHROPIC_KEY en Ajustes para activar el análisis IA.")

    elif do_analyze:
        st.warning("Ingresa un ticker primero.")

# ─────────────────────────────────────────────────────────────────
# TAB 3 — AJUSTES
# ─────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Ajustes")

    st.markdown("**API Key de Anthropic** *(opcional)*")
    st.caption("Activa el análisis IA de noticias por token. Sin ella todo lo demás funciona igual.")
    st.code("""
# En Streamlit Cloud → Settings → Secrets:
ANTHROPIC_KEY = "sk-ant-..."
    """)
    st.info("La key se configura en el dashboard de Streamlit Cloud, no aquí, para que no quede expuesta en el código.")

    st.divider()
    st.markdown("**Fuentes de datos**")
    st.markdown("""
    - 📊 **Binance API** — precios y velas en tiempo real
    - 🦎 **CoinGecko** — supply, ATH/ATL, categorías
    - 🔓 **token.unlocks.app** — calendario de vesting
    - 📰 **RSS** — CoinDesk · CoinTelegraph · Decrypt · TheBlock
    - 🤖 **Claude API** — resumen IA (requiere key)
    """)
    st.divider()
    st.caption("Quant Panel Web v1.0  ·  ⚠️ No es recomendación de inversión.")
