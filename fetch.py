"""
매크로 지표 수집기
매일 실행되어 지표를 받아오고 docs/index.html 로 대시보드를 만든다.
표준 라이브러리만 사용 — pip install 불필요.
"""

import csv
import io
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
OUT_DIR = "docs"
HISTORY = os.path.join(OUT_DIR, "history.json")

# ─────────────────────────────────────────────────────────────
# 지표 설정
#   trigger: 반증 조건. 값이 이 선을 넘으면 점등된다.
#   direction: "above" = 이 값보다 크면 점등, "below" = 작으면 점등
#   여기 숫자만 고치면 조건이 바뀐다.
# ─────────────────────────────────────────────────────────────

FRED = [
    {
        "id": "DFII10",
        "name": "미 10년 실질금리",
        "unit": "%",
        "note": "금과 역상관. 내려가면 금에 유리.",
        "trigger": None,
        "direction": None,
    },
    {
        "id": "BAMLH0A0HYM2",
        "name": "하이일드 스프레드",
        "unit": "%p",
        "note": "신용 경보. 주식보다 먼저 벌어지는 경우가 많다.",
        "trigger": 4.5,
        "direction": "above",
    },
    {
        "id": "DGS30",
        "name": "미 30년 국채금리",
        "unit": "%",
        "note": "5.28% 상향 돌파 후 고착이 가설 #1의 반증 조건.",
        "trigger": 5.28,
        "direction": "above",
    },
    {
        "id": "T10Y2Y",
        "name": "장단기 금리차 10Y-2Y",
        "unit": "%p",
        "note": "역전 시 침체 선행. 다만 리드타임이 길다.",
        "trigger": 0.0,
        "direction": "below",
    },
]

STOOQ = [
    {
        "sym": "^vix",
        "name": "VIX (미국 변동성)",
        "unit": "",
        "note": "코스피 카드와 대조할 것. 미국이 조용한데 한국만 흔들리면 업황이 아니라 수급 문제다.",
        "trigger": 25,
        "direction": "above",
    },
    {
        "sym": "^kospi",
        "name": "코스피",
        "unit": "",
        "note": "VIX와 나란히 볼 것. 둘의 괴리가 한국 고유 리스크의 크기다.",
        "trigger": None,
        "direction": None,
    },
    {
        "sym": "usdkrw",
        "name": "원/달러",
        "unit": "원",
        "note": "급등하면 외국인 이탈 압력. 환노출 ETF의 수익률도 여기 걸린다.",
        "trigger": 1450,
        "direction": "above",
    },
    {
        "sym": "usdjpy",
        "name": "엔/달러",
        "unit": "엔",
        "note": "엔캐리 청산은 한국 증시를 직격한 전례가 있다.",
        "trigger": None,
        "direction": None,
    },
    {
        "sym": "^spx",
        "name": "S&P 500",
        "unit": "",
        "note": "보유 중인 지수추종의 기초자산.",
        "trigger": None,
        "direction": None,
    },
    {
        "sym": "xauusd",
        "name": "금 (온스당 달러)",
        "unit": "$",
        "note": "실질금리와 함께 볼 것.",
        "trigger": None,
        "direction": None,
    },
]

TIMEOUT = 30
UA = {"User-Agent": "Mozilla/5.0 (macro-log)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def fred_series(series_id):
    """FRED 공개 CSV. API 키 불필요."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    rows = list(csv.reader(io.StringIO(get(url))))
    out = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        date, val = row[0].strip(), row[1].strip()
        if val in (".", "", "NA"):
            continue
        try:
            out.append((date, float(val)))
        except ValueError:
            continue
    return out


def stooq_series(symbol):
    """stooq 공개 CSV."""
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    rows = list(csv.reader(io.StringIO(get(url))))
    if not rows or rows[0][0].lower() != "date":
        return []
    idx = {k.lower(): i for i, k in enumerate(rows[0])}
    ci = idx.get("close")
    out = []
    for row in rows[1:]:
        if ci is None or len(row) <= ci:
            continue
        try:
            out.append((row[0], float(row[ci])))
        except ValueError:
            continue
    return out


def summarize(series, cfg):
    """최신값, 변화량, 점등 여부를 계산한다."""
    if not series:
        return {**cfg, "ok": False, "err": "데이터가 비어 있음"}

    series = series[-400:]
    date, last = series[-1]

    def back(n):
        if len(series) > n:
            return series[-1 - n][1]
        return None

    d1, d5, d20 = back(1), back(5), back(20)
    vals = [v for _, v in series[-250:]]

    lit = False
    if cfg.get("trigger") is not None:
        if cfg["direction"] == "above":
            lit = last > cfg["trigger"]
        elif cfg["direction"] == "below":
            lit = last < cfg["trigger"]

    return {
        **cfg,
        "ok": True,
        "date": date,
        "last": last,
        "chg1": None if d1 is None else last - d1,
        "chg5": None if d5 is None else last - d5,
        "chg20": None if d20 is None else last - d20,
        "hi52": max(vals) if vals else None,
        "lo52": min(vals) if vals else None,
        "spark": [v for _, v in series[-60:]],
        "lit": lit,
    }


def collect():
    out = []
    for cfg in FRED:
        try:
            out.append(summarize(fred_series(cfg["id"]), cfg))
        except Exception as e:
            out.append({**cfg, "ok": False, "err": str(e)[:120]})
    for cfg in STOOQ:
        try:
            out.append(summarize(stooq_series(cfg["sym"]), cfg))
        except Exception as e:
            out.append({**cfg, "ok": False, "err": str(e)[:120]})
    return out


# ─────────────────────────────────────────────────────────────
# 화면
# ─────────────────────────────────────────────────────────────

def fmt(v, unit=""):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1000:
        s = f"{v:,.0f}"
    elif a >= 100:
        s = f"{v:,.1f}"
    else:
        s = f"{v:,.2f}"
    return f"{s}{unit}"


def delta(v):
    if v is None:
        return '<span class="d flat">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "flat")
    sign = "+" if v > 0 else ""
    a = abs(v)
    s = f"{v:,.0f}" if a >= 100 else f"{v:,.2f}"
    return f'<span class="d {cls}">{sign}{s}</span>'


def spark(vals, lit):
    if not vals or len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    w, h = 120, 28
    step = w / (len(vals) - 1)
    pts = " ".join(
        f"{i*step:.1f},{h - (v - lo) / rng * h:.1f}" for i, v in enumerate(vals)
    )
    color = "#fbbf24" if lit else "#64748b"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/></svg>'
    )


def card(m):
    if not m.get("ok"):
        return (
            f'<div class="card err"><div class="nm">{m["name"]}</div>'
            f'<div class="note">데이터를 받지 못했습니다. {m.get("err","")}</div></div>'
        )

    trig = ""
    if m.get("trigger") is not None:
        arrow = "＞" if m["direction"] == "above" else "＜"
        trig = f'<div class="trig{" on" if m["lit"] else ""}">반증 조건 {arrow} {fmt(m["trigger"])}{"  점등" if m["lit"] else ""}</div>'

    return f"""<div class="card{' lit' if m.get('lit') else ''}">
  <div class="top">
    <div class="nm">{m['name']}</div>
    <div class="dt">{m['date']}</div>
  </div>
  <div class="val">{fmt(m['last'], m['unit'])}</div>
  <div class="row">
    <span class="lb">1일</span>{delta(m['chg1'])}
    <span class="lb">5일</span>{delta(m['chg5'])}
    <span class="lb">20일</span>{delta(m['chg20'])}
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

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0f172a">
<title>지표판</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:16px;max-width:720px;margin:0 auto}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
header{{border-bottom:1px solid #334155;padding-bottom:14px;margin-bottom:16px}}
h1{{font-size:20px;font-weight:600;letter-spacing:-.02em}}
.eyebrow{{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.15em;color:#64748b;text-transform:uppercase}}
.stamp{{font-family:ui-monospace,monospace;font-size:11px;color:#64748b;margin-top:8px}}
.banner{{background:#450a0a;border:1px solid #b91c1c;color:#fecaca;padding:10px 12px;border-radius:4px;font-size:13px;margin-bottom:16px}}
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
<div class="grid">
{"".join(card(m) for m in metrics)}
</div>
<footer>
가격 변화의 색은 방향만 나타냅니다. 빨강이 나쁘다는 뜻이 아닙니다.<br>
반증 조건은 fetch.py 상단에서 고칠 수 있습니다.<br>
출처 FRED · stooq. 투자 판단과 책임은 본인에게 있습니다.
</footer>
</body></html>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    metrics = collect()

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(metrics))

    # 점등 이력 축적 — 나중에 "이 조건이 언제 켜졌었나"를 되돌아보기 위함
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
            print(f"  성공: {m['name']} = {m['last']}")
        else:
            print(f"  실패: {m['name']} — {m.get('err','')}")


if __name__ == "__main__":
    main()
