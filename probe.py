"""
진단용 스크립트.
어떤 주소가 응답하고 무엇이 돌아오는지 눈으로 확인한다.
결과를 보고 fetch.py를 고친 뒤에는 지워도 된다.
"""

import urllib.request
import urllib.error

TESTS = [
    # FRED — 두 가지 주소 형식을 모두 시험
    ("FRED graph csv", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS30"),
    ("FRED data page", "https://fred.stlouisfed.org/data/DGS30.txt"),

    # stooq — 여러 심볼 표기를 시험
    ("stooq vix   ^vix", "https://stooq.com/q/d/l/?s=^vix&i=d"),
    ("stooq vix   vi.f", "https://stooq.com/q/d/l/?s=vi.f&i=d"),
    ("stooq spx   ^spx", "https://stooq.com/q/d/l/?s=^spx&i=d"),
    ("stooq kospi ^kospi", "https://stooq.com/q/d/l/?s=^kospi&i=d"),
    ("stooq usdkrw", "https://stooq.com/q/d/l/?s=usdkrw&i=d"),

    # 대체 후보 — 야후 파이낸스 공개 차트 API
    ("yahoo VIX", "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=1mo&interval=1d"),
    ("yahoo KOSPI", "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?range=1mo&interval=1d"),
    ("yahoo USDKRW", "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=1mo&interval=1d"),
    ("yahoo TNX(10Y)", "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1mo&interval=1d"),
]

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def probe(label, url):
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(url)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            code = r.status
            ctype = r.headers.get("Content-Type", "?")
            body = r.read(600).decode("utf-8", errors="replace")
        print(f"  응답코드 {code} / 형식 {ctype}")
        print("  ─── 앞부분 ───")
        for line in body.splitlines()[:6]:
            print(f"  | {line[:150]}")
    except urllib.error.HTTPError as e:
        print(f"  HTTP 오류 {e.code} {e.reason}")
    except Exception as e:
        print(f"  실패: {type(e).__name__} — {e}")


if __name__ == "__main__":
    for label, url in TESTS:
        probe(label, url)
    print(f"\n{'='*60}\n진단 끝")
