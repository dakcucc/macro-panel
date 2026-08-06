name: 지표 수집

on:
  schedule:
    # UTC 기준. 22:00 UTC = 한국시간 아침 7:00
    - cron: "0 22 * * 1-5"
  workflow_dispatch:   # 깃허브 화면에서 손으로 즉시 실행할 때 사용

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 지표 받아오기
        run: python fetch.py

      - name: 결과 저장
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add docs/
          git diff --staged --quiet || git commit -m "지표 갱신 $(date -u +%Y-%m-%d)"
          git push
