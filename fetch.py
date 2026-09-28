#!/usr/bin/env python3
"""一次ソースから数字を取り直して data/prefs.json を更新する。

    python3 fetch.py            # 取得して差分があれば書き込む
    python3 fetch.py --dry-run  # 取得するが書き込まない

制度の改定はサイトの生命線なので、人が気づくのを待たずに機械で追う。
取得元は厚生労働省・各労働局・全国健康保険協会。いずれも政府標準利用規約に沿って
出典を明示したうえで利用している。
"""
import html
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (compatible; minamikyushu-navi/1.0; +https://github.com/)"

SOURCES = {
    "宮崎県": "https://jsite.mhlw.go.jp/miyazaki-roudoukyoku/jirei_toukei/chingin_kanairoudou/tingin.html",
    "鹿児島県": "https://jsite.mhlw.go.jp/kagoshima-roudoukyoku/hourei_seido_tetsuzuki/kane/saitin01.html",
}
KENPO_URL = "https://www.kyoukaikenpo.or.jp/g7/cat330/sb3130/r08/"

ZEN = str.maketrans("０１２３４５６７８９．", "0123456789.")


def _decode(raw):
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def get(url):
    """urllib で取りに行き、TLS で弾かれたら curl に落とす。

    協会けんぽのサーバは macOS 同梱 Python の LibreSSL と折り合いが悪く
    TLSV1_ALERT_PROTOCOL_VERSION を返す。curl では通るのでそちらを使う。
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return _decode(r.read())
    except Exception as e:
        out = subprocess.run(
            ["curl", "-sL", "--max-time", "40", "-A", UA, url],
            capture_output=True,
        )
        if out.returncode != 0 or not out.stdout:
            raise RuntimeError(f"{url} を取得できませんでした（urllib: {e}）")
        return _decode(out.stdout)


def text_of(page):
    page = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
    page = re.sub(r"<style.*?</style>", " ", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return re.sub(r"\s+", " ", t).translate(ZEN)


def fetch_min_wage(pref):
    """労働局のページから「時間額」と「効力発生日」を拾う。

    ページの書式は県ごとに違うので、金額と和暦日付をそれぞれ全部拾ってから
    最大値・最新日を採る。先頭一致で取ると改定前の額を掴んでしまう。
    """
    t = text_of(get(SOURCES[pref]))
    amounts = sorted({int(x.replace(",", "")) for x in re.findall(r"([1-9],\d{3})\s*円", t)})
    dates = re.findall(r"令和(\d+)年\s*(\d+)月\s*(\d+)日", t)
    if not amounts or not dates:
        raise RuntimeError(f"{pref}: 金額または日付を抽出できなかった")

    iso = sorted({f"{2018 + int(y)}-{int(m):02d}-{int(d):02d}" for y, m, d in dates})
    return {
        "amount_candidates": amounts,
        "date_candidates": iso,
        "latest_amount": amounts[-1],
        "latest_date": iso[-1],
    }


def fetch_kenpo():
    """協会けんぽの都道府県別料率。表が『令和7年度 → 令和8年度』の並びで出る。"""
    t = text_of(get(KENPO_URL))
    rows = re.findall(r"([一-龥]{2,4}[都道府県])\s*([\d.]+)％\s*[↓↑→]\s*([\d.]+)％", t)
    out = {p: {"prev": float(a), "curr": float(b)} for p, a, b in rows}
    kaigo = re.search(r"介護保険料率（([\d.]+)％）", t)
    kosodate = re.search(r"子ども・子育て支援金（([\d.]+)％）", t)
    return out, (float(kaigo.group(1)) if kaigo else None), (float(kosodate.group(1)) if kosodate else None)


def main():
    dry = "--dry-run" in sys.argv
    path = os.path.join(ROOT, "data", "prefs.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = []

    for pref in SOURCES:
        try:
            got = fetch_min_wage(pref)
        except Exception as e:
            print(f"  [警告] {pref} の最低賃金を取得できませんでした: {e}")
            continue
        cur = data["prefs"][pref]["min_wage"]
        print(f"  {pref}: 金額候補 {got['amount_candidates']} / 日付候補 {got['date_candidates']}")
        if got["latest_amount"] != cur["next"]["amount"]:
            changed.append(
                f"{pref} 最低賃金 {cur['next']['amount']}円 → {got['latest_amount']}円"
                f"（{got['latest_date']}）※自動判定なので必ず出典で確認すること"
            )

    try:
        rates, kaigo, kosodate = fetch_kenpo()
        for pref in SOURCES:
            if pref in rates:
                now = data["prefs"][pref]["kenpo"]["r8"]
                got = rates[pref]["curr"]
                print(f"  {pref}: 健康保険料率 {got}％（登録値 {now}％）")
                if abs(got - now) > 1e-9:
                    changed.append(f"{pref} 健康保険料率 {now}％ → {got}％")
                    if not dry:
                        data["prefs"][pref]["kenpo"]["r7"] = rates[pref]["prev"]
                        data["prefs"][pref]["kenpo"]["r8"] = got
        if kaigo and abs(kaigo - data["common"]["kaigo_rate"]) > 1e-9:
            changed.append(f"介護保険料率 {data['common']['kaigo_rate']}％ → {kaigo}％")
            if not dry:
                data["common"]["kaigo_rate"] = kaigo
        if kosodate and abs(kosodate - data["common"]["kosodate_rate"]) > 1e-9:
            changed.append(f"子ども・子育て支援金 {data['common']['kosodate_rate']}％ → {kosodate}％")
            if not dry:
                data["common"]["kosodate_rate"] = kosodate
    except Exception as e:
        print(f"  [警告] 協会けんぽの料率を取得できませんでした: {e}")

    print()
    if not changed:
        print("変更はありません。")
        return 0

    print("■ 変更の候補")
    for c in changed:
        print("  -", c)
    if dry:
        print("\n--dry-run のため書き込んでいません。")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("\ndata/prefs.json を更新しました。")
    print("最低賃金は発効日と特定最低賃金の扱いを人が確認してから反映してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
