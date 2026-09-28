#!/usr/bin/env python3
"""宮崎県・鹿児島県の市区町村境界から、トップページ用のSVGパスを作る。

    python3 make_map.py     # → data/muni_map.json

生成物はコミットするので、通常のビルドでは実行不要。

データ元：国土交通省 国土数値情報（行政区域データ）を
スマートニュース メディア研究所が軽量化したもの（0.1％に簡素化）。
商用利用可・クレジット不要だが、国土交通省のクレジット表示は必要。
"""
import json
import math
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, ".cache")
SRC = ("https://raw.githubusercontent.com/smartnews-smri/japan-topography"
       "/main/data/municipality/geojson/s0010/N03-21_{code}_210101.json")
PREFS = [("45", "宮崎県"), ("46", "鹿児島県")]

# 奄美群島・トカラ列島は本土から遠いので別枠に描く。
# 最北端の緯度がこの値より南なら島嶼グループ。
ISLAND_LAT = 30.0
# 十島村は口之島が北緯30度をわずかに超えるが、本土枠に入れると
# 地図全体が南へ1度以上伸びて本土が小さくなるので島嶼側に固定する。
ISLAND_FORCE = {"十島村"}

# 描画サイズ（SVGのユーザー座標）
MAIN_W, MAIN_H = 640, 760
ISLE_W, ISLE_H = 180, 300

RDP_EPS = 0.0016      # 度。小さいほど精密で重くなる
MIN_RING_AREA = 6e-5  # これより小さい島は落とす（ただし各市町村の最大リングは必ず残す）


def load(code):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"N03-21_{code}_210101.json")
    if not os.path.exists(path):
        print(f"  ダウンロード: {code}", file=sys.stderr)
        urllib.request.urlretrieve(SRC.format(code=code), path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rings(geom):
    """外周リングだけ取り出す（穴は使わない）。"""
    t, c = geom["type"], geom["coordinates"]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return [c[0]]


def ring_area(r):
    s = 0.0
    for i in range(len(r) - 1):
        s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
    return abs(s) / 2


def rdp(pts, eps):
    """Douglas–Peucker。閉リングは始点と最遠点で割ってから処理する
    （始点＝終点だと全点の距離が0になり2点に潰れるため）。"""
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1]:
        i = max(range(1, len(pts) - 1),
                key=lambda k: (pts[k][0] - pts[0][0]) ** 2 + (pts[k][1] - pts[0][1]) ** 2)
        return rdp(pts[: i + 1], eps)[:-1] + rdp(pts[i:], eps)
    x0, y0 = pts[0]
    x1, y1 = pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-12
    imax, dmax = 0, 0.0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dy * px - dx * py + x1 * y0 - y1 * x0) / n
        if d > dmax:
            imax, dmax = i, d
    if dmax <= eps:
        return [pts[0], pts[-1]]
    return rdp(pts[: imax + 1], eps)[:-1] + rdp(pts[imax:], eps)


def collect():
    out = []
    for code, pref in PREFS:
        data = load(code)
        for f in data["features"]:
            p = f["properties"]
            rs = rings(f["geometry"])
            if not rs:
                continue
            biggest = max(rs, key=ring_area)
            kept = [r for r in rs if ring_area(r) >= MIN_RING_AREA]
            if biggest not in kept:
                kept.append(biggest)
            lats = [pt[1] for r in kept for pt in r]
            out.append({
                "pref": pref,
                "name": p["N03_004"],
                "code": p["N03_007"],
                "rings": kept,
                "north": max(lats),
                "group": ("isle" if (max(lats) < ISLAND_LAT
                                     or p["N03_004"] in ISLAND_FORCE) else "main"),
            })
    return out


def project(items, width, height, pad=8):
    """等距円筒図法。経度は平均緯度のcosで縮める。"""
    pts = [pt for it in items for r in it["rings"] for pt in r]
    lat0 = sum(p[1] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    xs = [p[0] * k for p in pts]
    ys = [-p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    sx = (width - pad * 2) / (maxx - minx)
    sy = (height - pad * 2) / (maxy - miny)
    s = min(sx, sy)
    ox = pad + (width - pad * 2 - (maxx - minx) * s) / 2
    oy = pad + (height - pad * 2 - (maxy - miny) * s) / 2

    def path(ring):
        simple = rdp(ring, RDP_EPS)
        if len(simple) < 3:
            return ""
        d = []
        for i, (lon, lat) in enumerate(simple):
            x = ox + (lon * k - minx) * s
            y = oy + (-lat - miny) * s
            d.append(("M" if i == 0 else "L") + f"{x:.1f} {y:.1f}")
        return "".join(d) + "Z"

    for it in items:
        it["d"] = "".join(p for p in (path(r) for r in it["rings"]) if p)
        # ラベル位置は最大リングの重心
        big = max(it["rings"], key=ring_area)
        cx = sum(p[0] for p in big) / len(big)
        cy = sum(p[1] for p in big) / len(big)
        it["cx"] = round(ox + (cx * k - minx) * s, 1)
        it["cy"] = round(oy + (-cy - miny) * s, 1)
        del it["rings"]


def main():
    items = collect()
    main_g = [i for i in items if i["group"] == "main"]
    isle_g = [i for i in items if i["group"] == "isle"]
    print(f"本土 {len(main_g)} / 島嶼 {len(isle_g)} = 計 {len(items)}")
    project(main_g, MAIN_W, MAIN_H)
    project(isle_g, ISLE_W, ISLE_H)

    for it in items:
        it.pop("north", None)

    doc = {
        "main": {"w": MAIN_W, "h": MAIN_H, "items": main_g},
        "isle": {"w": ISLE_W, "h": ISLE_H, "items": isle_g},
        "credit": "国土交通省 国土数値情報（行政区域データ）を加工して作成",
    }
    path = os.path.join(ROOT, "data", "muni_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"書き出し: {path}（{os.path.getsize(path):,} バイト）")
    print("島嶼グループ:", "、".join(i["name"] for i in isle_g))


if __name__ == "__main__":
    main()
