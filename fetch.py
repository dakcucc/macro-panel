"""
매크로 지표 수집기
야후 파이낸스 공개 차트 API에서 데이터를 받아 docs/index.html 을 만든다.
표준 라이브러리만 사용 — pip install 불필요.

FRED와 stooq는 깃허브 서버에서 차단되어 쓰지 않는다. (2026-08 확인)
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
OUT_DIR = "docs"
HISTORY = os.path.join(OUT_DIR, "history.json")

# ─────────────────────────────────────────────────────────────
# 지표 설정
#   trigger    : 반증 조건. 값이 이 선을 넘으면 점등된다.
#   direction  : "above" = 크면 점등, "below" = 작으면 점등
#   core       : True 면 핵심 지표, False 면 참고 지표
#   여기 숫자만 고치면 조건이 바뀐다.
# ─────────────────────────────────────────────────────────────

METRICS = [
    # ── 핵심 6 ──
    {
        "kind": "yahoo", "sym": "^VIX", "core": True,
        "name": "VIX (미국 변동성)", "unit": "",
        "note": "코스피 카드와 대조할 것. 미국이 조용한데 한국만 흔들리면 업황이 아니라 수급 문제다.",
        "trigger": 25, "direction": "above",
    },
    {
        "kind": "yahoo", "sym": "^KS11", "core": True,
        "name": "코스피", "unit": "",
        "note": "VIX와 나란히 볼 것. 둘의 괴리가 한국 고유 리스크의 크기다.",
        "trigger": None, "direction": None,
    },
    {
        "kind": "yahoo", "sym": "^TYX", "core": True,
        "name": "미 30년 국채금리", "unit": "%",
        "note": "5.28% 상향 돌파 후 고착이 가설 #1의 반증 조건. 성장주 할인율의 뿌리.",
        "trigger": 5.28, "direction": "above",
    },
    {
        "kind": "yahoo", "sym": "KRW=X", "core": True,
        "name": "원/달러", "unit": "원",
        "note": "급등하면 외국인 이탈 압력. 환노출 ETF 수익률도 여기 걸린다.",
        "trigger": 1450, "direction": "above",
    },
    {
        "kind": "ratio", "sym": ("HYG", "IEF"), "core": True,
        "name": "신용 스트레스 (HYG/IEF)", "unit": "",
        "note": "하이일드 ETF ÷ 국채 ETF. 내려갈수록 신용 경계. 주식보다 먼저 움직이는 경우가 많다.",
        "trigger": None, "direction": None,
    },
    {
        "kind": "yahoo", "sym": "^GSPC", "core": True,
        "name": "S&P 500", "unit": "",
        "note": "보유 중인 지수추종의 기초자산.",
        "trigger": None, "direction": None,
    },

    # ── 참고 ──
    {
        "kind": "yahoo", "sym": "^TNX", "core": False,
        "name": "미 10년 국채금리", "unit": "%",
        "note": "30년물과 함께 커브 모양을 본다.",
        "trigger": None, "direction": None,
    },
    {
        "kind": "yahoo", "sym": "SOXX", "core": False,
        "name": "미국 반도체 ETF (SOXX)", "unit": "$",
        "note": "코스피와 대조. 미국 반도체는 멀쩡한데 한국만 빠지면 업황 문제가 아니다.",
        "trigger": None, "direction": None,
    },
    {
        "kind": "yahoo", "sym": "GC=F", "core": False,
        "name": "금 (온스당 달러)", "unit": "$",
        "note": "실질금리와 역상관. 야후로는 실질금리를 못 받아서 금 가격으로 대신 본다.",
        "trigger": None, "direction": None,
    },
    {
        "kind": "yahoo", "sym": "JPY=X", "core": False,
        "name": "엔/달러", "unit": "엔",
        "note": "엔캐리 청산은 한국 증시를 직격한 전례가 있다.",
        "trigger": None, "direction": None,
    },
]

TIMEOUT = 25
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_cache = {}


def yahoo_series(symbol, rng="1y"):
    """야후 차트 API에서 (날짜, 종가) 목록을 받는다."""
    if symbol in _cache:
        return _cache[symbol]

    quoted = urllib.parse.quote(symbol, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))

    res = (data.get("chart") or {}).get("result")
    if not res:
        raise ValueError("결과가 비어 있음")

    r0 = res[0]
    stamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    out = []
    for ts, c in zip(stamps, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append((d, float(c)))

    if not out:
        raise ValueError("종가가 전부 비어 있음")

    _cache[symbol] = out
    time.sleep(0.6)   # 야후에 부담 주지 않기 위한 간격
    return out


def ratio_series(sym_a, sym_b):
    """두 종목의 같은 날짜끼리 나눈 비율 시계열."""
    a = dict(yahoo_series(sym_a))
    b = dict(yahoo_series(sym_b))
    days = sorted(set(a) & set(b))
    out = [(d, a[d] / b[d]) for d in days if b[d]]
    if not out:
        raise ValueError("겹치는 날짜가 없음")
    return out


def summarize(series, cfg):
    if not series:
        return {**cfg, "ok": False, "err": "데이터가 비어 있음"}

    series = series[-400:]
    date, last = series[-1]

    def back(n):
        return series[-1 - n][1] if len(series) > n else None

    d1, d5, d20 = back(1), back(5), back(20)
    vals = [v for _, v in series[-250:]]

    lit = False
    if cfg.get("trigger") is not None:
        if cfg["direction"] == "above":
            lit = last > cfg["trigger"]
        elif cfg["direction"] == "below":
            lit = last < cfg["trigger"]

    def pct(prev):
        if prev in (None, 0):
            return None
        return (last - prev) / abs(prev) * 100

    return {
        **cfg,
        "ok": True,
        "date": date,
        "last": last,
        "pct1": pct(d1), "pct5": pct(d5), "pct20": pct(d20),
        "hi52": max(vals) if vals else None,
        "lo52": min(vals) if vals else None,
        "spark": [v for _, v in series[-60:]],
        "lit": lit,
    }


def collect():
    out = []
    for cfg in METRICS:
        try:
            if cfg["kind"] == "ratio":
                series = ratio_series(*cfg["sym"])
            else:
                series = yahoo_series(cfg["sym"])
            out.append(summarize(series, cfg))
        except Exception as e:
            out.append({**cfg, "ok": False, "err": f"{type(e).__name__} {str(e)[:100]}"})
    return out


# ─────────────────────────────────────────────────────────────
# 화면
# ─────────────────────────────────────────────────────────────

def fmt(v, unit=""):
    if v is None:
        return "—"
    a = abs(v)
    s = f"{v:,.0f}" if a >= 1000 else (f"{v:,.1f}" if a >= 100 else f"{v:,.2f}")
    return f"{s}{unit}"


def pct_html(v):
    if v is None:
        return '<span class="d flat">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "flat")
    sign = "+" if v > 0 else ""
    return f'<span class="d {cls}">{sign}{v:.1f}%</span>'


def spark(vals, lit):
    if not vals or len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    w, h = 120, 28
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i*step:.1f},{h - (v - lo) / rng * h:.1f}"
                   for i, v in enumerate(vals))
    color = "#fbbf24" if lit else "#64748b"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/></svg>')


def card(m):
    if not m.get("ok"):
        return (f'<div class="card err"><div class="nm">{m["name"]}</div>'
                f'<div class="note">데이터를 받지 못했습니다. {m.get("err","")}</div></div>')

    trig = ""
    if m.get("trigger") is not None:
        arrow = "＞" if m["direction"] == "above" else "＜"
        on = " 점등" if m["lit"] else ""
        trig = (f'<div class="trig{" on" if m["lit"] else ""}">'
                f'반증 조건 {arrow} {fmt(m["trigger"])}{on}</div>')

    return f"""<div class="card{' lit' if m.get('lit') else ''}">
  <div class="top"><div class="nm">{m['name']}</div><div class="dt">{m['date']}</div></div>
  <div class="val">{fmt(m['last'], m['unit'])}</div>
  <div class="row">
    <span class="lb">1일</span>{pct_html(m['pct1'])}
    <span class="lb">5일</span>{pct_html(m['pct5'])}
    <span class="lb">20일</span>{pct_html(m['pct20'])}
  </div>
  {spark(m['spark'], m.get('lit'))}
  <div class="rng">52주 {fmt(m['lo52'])} ~ {fmt(m['hi52'])}</div>
  {trig}
  <div class="note">{m['note']}</div>
</div>"""


def render(metrics):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    lit = [m for m in metrics if m.get("lit")]
    banner = ""
    if lit:
        names = ", ".join(m["name"] for m in lit)
        banner = f'<div class="banner">반증 조건 {len(lit)}개 점등 — {names}</div>'

    core = "".join(card(m) for m in metrics if m.get("core"))
    ref = "".join(card(m) for m in metrics if not m.get("core"))

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0f172a">
<title>지표판</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:16px;max-width:720px;margin:0 auto}}
header{{border-bottom:1px solid #334155;padding-bottom:14px;margin-bottom:16px}}
h1{{font-size:20px;font-weight:600;letter-spacing:-.02em}}
.eyebrow{{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.15em;color:#64748b;text-transform:uppercase}}
.stamp{{font-family:ui-monospace,monospace;font-size:11px;color:#64748b;margin-top:8px}}
.banner{{background:#450a0a;border:1px solid #b91c1c;color:#fecaca;padding:10px 12px;border-radius:4px;font-size:13px;margin-bottom:16px}}
.sect{{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.15em;color:#64748b;text-transform:uppercase;margin:20px 0 10px}}
.sect:first-of-type{{margin-top:0}}
.grid{{display:grid;gap:10px}}
@media(min-width:560px){{.grid{{grid-template-columns:1fr 1fr}}}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:6px;padding:14px}}
.card.lit{{border-color:#b45309;background:#221c14}}
.card.err{{opacity:.5}}
.top{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.nm{{font-size:13px;color:#cbd5e1}}
.dt{{font-family:ui-monospace,monospace;font-size:10px;color:#64748b}}
.val{{font-family:ui-monospace,monospace;font-size:26px;font-weight:600;margin:6px 0 8px;letter-spacing:-.02em}}
.row{{display:flex;align-items:center;gap:6px;font-family:ui-monospace,monospace;font-size:11px;flex-wrap:wrap}}
.lb{{color:#64748b}}
.d{{margin-right:8px}}
.d.up{{color:#f87171}}
.d.down{{color:#4ade80}}
.d.flat{{color:#64748b}}
.spark{{width:100%;height:28px;margin:10px 0 6px;display:block}}
.rng{{font-family:ui-monospace,monospace;font-size:10px;color:#64748b}}
.trig{{font-family:ui-monospace,monospace;font-size:10px;color:#64748b;margin-top:6px;padding-top:6px;border-top:1px solid #334155}}
.trig.on{{color:#fbbf24}}
.note{{font-size:11px;color:#64748b;margin-top:6px;line-height:1.5}}
footer{{margin-top:24px;padding-top:14px;border-top:1px solid #1e293b;font-size:11px;color:#475569;line-height:1.6}}
</style></head><body>
<header>
  <div class="eyebrow">Macro Panel</div>
  <h1>지표판</h1>
  <div class="stamp">갱신 {now} KST</div>
</header>
{banner}
<div class="sect">핵심</div>
<div class="grid">{core}</div>
<div class="sect">참고</div>
<div class="grid">{ref}</div>
<footer>
변화율의 색은 방향만 나타냅니다. 빨강이 나쁘다는 뜻이 아닙니다.<br>
반증 조건은 fetch.py 상단에서 고칠 수 있습니다.<br>
출처 Yahoo Finance. 투자 판단과 책임은 본인에게 있습니다.
</footer>
</body></html>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    metrics = collect()

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(metrics))

    log = []
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY, encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append({
        "at": datetime.now(KST).strftime("%Y-%m-%d"),
        "values": {m["name"]: m.get("last") for m in metrics if m.get("ok")},
        "lit": [m["name"] for m in metrics if m.get("lit")],
    })
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(log[-400:], f, ensure_ascii=False, indent=1)

    ok = sum(1 for m in metrics if m.get("ok"))
    print(f"===== {ok}/{len(metrics)} 지표 수집 완료 =====")
    for m in metrics:
        if m.get("ok"):
            print(f"  성공: {m['name']} = {m['last']:.2f}  ({m['date']})")
        else:
            print(f"  실패: {m['name']} — {m.get('err','')}")


if __name__ == "__main__":
    main()
