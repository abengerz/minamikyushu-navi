#!/usr/bin/env python3
"""みなみ九州 経営ナビ — 静的サイトの生成。

    python3 build.py            # site/ に出力
    MKN_BASE=/repo MKN_BASE_URL=https://example.com python3 build.py
"""
import datetime
import glob
import json
import os
import re
import shutil

from lib import (
    BASE_URL, MUNIS, OUT, PREFS, ROOT, SITE, TODAY, U, abs_url, esc,
    frontmatter, jp_date, layout, markdown, service_cta, supervisor_box,
    wareki, write, yen,
)

CATS = {c["slug"]: c for c in SITE["categories"]}
PAGES = []          # sitemap 用 (path, lastmod, priority)
ARTICLES = []       # 記事メタ


def reg(path, lastmod=None, priority="0.6"):
    PAGES.append((path, lastmod or TODAY.isoformat(), priority))


# ---------------------------------------------------------------- 記事

def load_articles():
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "articles", "*.md"))):
        fm, body = frontmatter(p)
        fm["body"] = body
        fm.setdefault("updated", fm["date"])
        fm.setdefault("prefs", [])
        ARTICLES.append(fm)
    ARTICLES.sort(key=lambda a: (a["updated"], a["date"]), reverse=True)


def article_hooks():
    """本文中の {{...}} を差し込みに変換する。"""
    h = {}
    for s in SITE["services"]:
        h["cta:" + s["slug"]] = service_cta(s["slug"], compact=True)
    h["cta"] = service_cta(compact=True)
    for t in TOOLS:
        h["tool:" + t["slug"]] = tool_widget(t)
    return h


def article_card(a):
    cat = CATS.get(a["category"], {"label": a["category"]})
    return f"""<a class="card" href="{U('/' + a['category'] + '/' + a['slug'] + '/')}">
  <span class="card-cat">{esc(cat['label'])}</span>
  <span class="card-title">{esc(a['title'])}</span>
  <span class="card-desc">{esc(a['description'][:78])}</span>
  <span class="card-date">{jp_date(a['updated'])} 更新</span>
</a>"""


def side_column(current=None):
    latest = [a for a in ARTICLES if a is not current][:6]
    items = "".join(
        f'<li><a href="{U("/" + a["category"] + "/" + a["slug"] + "/")}">{esc(a["title"])}</a></li>'
        for a in latest
    )
    tools = "".join(
        f'<li><a href="{U("/tools/" + t["slug"] + "/")}">{esc(t["title"])}</a></li>' for t in TOOLS
    )
    prefs = "".join(
        f'<li><a href="{U("/" + v["slug"] + "/")}">{esc(k)}の制度まとめ</a></li>'
        for k, v in PREFS["prefs"].items()
    )
    return f"""<aside class="side">
  <div class="side-box"><h2>計算ツール（無料・登録不要）</h2><ul class="side-list">{tools}</ul></div>
  <div class="side-box"><h2>新着</h2><ul class="side-list">{items}</ul></div>
  <div class="side-box"><h2>地域から探す</h2><ul class="side-list">{prefs}</ul></div>
</aside>"""


def sources_block(sources):
    if not sources:
        return ""
    li = "".join(
        f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["name"])}</a></li>'
        for s in sources
    )
    return f'<div class="sources"><p>出典</p><ul>{li}</ul></div>'


def build_article(a):
    cat = CATS.get(a["category"], {"label": a["category"], "slug": a["category"]})
    path = f"/{a['category']}/{a['slug']}/"
    body_html, toc = markdown(a["body"], article_hooks())

    toc_html = ""
    if len(toc) >= 3:
        li = "".join(f'<li><a href="#{hid}">{esc(t)}</a></li>' for hid, t in toc)
        toc_html = f'<nav class="toc"><p>この記事の内容</p><ol>{li}</ol></nav>'

    schema = {
        "@type": "Article",
        "headline": a["title"][:110],
        "description": a["description"],
        "datePublished": a["date"],
        "dateModified": a["updated"],
        "inLanguage": "ja",
        "mainEntityOfPage": abs_url(path),
        "publisher": {"@id": abs_url("#org")},
        "isAccessibleForFree": True,
    }
    sv = SITE["supervisor"]
    schema["author"] = {"@id": abs_url("#author")} if (SITE.get("author") or {}).get("enabled") \
        else {"@id": abs_url("#org")}
    if sv.get("enabled"):
        schema["reviewedBy"] = {"@id": abs_url("#supervisor")}

    if a.get("faq"):
        schema = [schema, {
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
                for q in a["faq"]
            ],
        }]
        faq_html = "<h2 id=\"faq\">よくある質問</h2>" + "".join(
            f"<h3>{esc(q['q'])}</h3><p>{esc(q['a'])}</p>" for q in a["faq"]
        )
    else:
        faq_html = ""

    body = f"""<div class="page"><div class="doc">
<article class="article">
  <p class="meta">
    <a class="cat" href="{U('/' + cat['slug'] + '/')}">{esc(cat['label'])}</a>
    <time datetime="{a['date']}">公開 {jp_date(a['date'])}</time>
    <time datetime="{a['updated']}">更新 {jp_date(a['updated'])}</time>
  </p>
  <h1>{esc(a['title'])}</h1>
  <p class="lede">{esc(a['description'])}</p>
  {toc_html}
  {body_html}
  {faq_html}
  {sources_block(a.get('sources'))}
  {supervisor_box()}
  {service_cta(a.get('service'))}
</article>
{side_column(a)}
</div></div>"""

    crumbs = [("/", "ホーム"), (f"/{cat['slug']}/", cat["label"]), (path, a["title"])]
    write(path + "index.html", layout(
        a["title"], a["description"], body, path,
        schema=schema if not isinstance(schema, list) else schema[0],
        active=f"/{cat['slug']}/", crumbs=crumbs,
    ))
    # FAQ は @graph に 2 ノード入れたいので、layout を通さず後から差し込む
    if isinstance(schema, list):
        full = os.path.join(OUT, path.lstrip("/"), "index.html")
        with open(full, encoding="utf-8") as f:
            h = f.read()
        extra = json.dumps(schema[1], ensure_ascii=False, separators=(",", ":"))
        h = h.replace("}]}</script>", "}," + extra + "]}</script>", 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(h)
    reg(path, a["updated"], "0.8")


def build_categories():
    for c in SITE["categories"]:
        arts = [a for a in ARTICLES if a["category"] == c["slug"]]
        path = f"/{c['slug']}/"
        cards = "".join(article_card(a) for a in arts) or \
            '<p class="card-desc">この分類の記事はまだありません。</p>'
        body = f"""<div class="page">
  <h1>{esc(c['label'])}</h1>
  <p class="lede">{esc(c['lead'])}｜宮崎県・鹿児島県の事業者向け（{len(arts)}記事）</p>
  <div class="grid">{cards}</div>
  {service_cta()}
</div>"""
        write(path + "index.html", layout(
            f"{c['label']}の記事一覧",
            f"{c['lead']}。宮崎県・鹿児島県の中小企業・個人事業主向けに、{c['label']}の実務を一次情報の出典つきで解説しています。",
            body, path, active=path,
            crumbs=[("/", "ホーム"), (path, c["label"])],
        ))
        reg(path, priority="0.7")


# ---------------------------------------------------------------- ツール

# 標準報酬月額（健康保険 50 等級／厚生年金 32 等級）。
# 適用区分の境界は隣り合う等級の中間値なので、値だけ持って境界は計算で出す。
KENPO_GRADES = [
    58000, 68000, 78000, 88000, 98000, 104000, 110000, 118000, 126000, 134000,
    142000, 150000, 160000, 170000, 180000, 190000, 200000, 220000, 240000, 260000,
    280000, 300000, 320000, 340000, 360000, 380000, 410000, 440000, 470000, 500000,
    530000, 560000, 590000, 620000, 650000, 680000, 710000, 750000, 790000, 830000,
    880000, 930000, 980000, 1030000, 1090000, 1150000, 1210000, 1270000, 1330000, 1390000,
]
NENKIN_GRADES = KENPO_GRADES[3:35]   # 88,000 〜 650,000

COMMON = PREFS["common"]
PREF_RATE_JS = json.dumps(
    {v["slug"]: {"name": k, "kenpo": v["kenpo"]["r8"],
                 "mw": v["min_wage"]["current"]["amount"],
                 "mwNext": v["min_wage"]["next"]["amount"],
                 "mwNextDate": v["min_wage"]["next"]["wareki"]}
     for k, v in PREFS["prefs"].items()},
    ensure_ascii=False,
)

PREF_OPTIONS = "".join(
    f'<option value="{v["slug"]}">{esc(k)}</option>' for k, v in PREFS["prefs"].items()
)


def _mw_lines():
    out = []
    for k, v in PREFS["prefs"].items():
        mw = v["min_wage"]
        out.append(
            f"{k}は現在 {yen(mw['current']['amount'])}、"
            f"{mw['next']['wareki']}から {yen(mw['next']['amount'])}"
            f"（{mw['next']['diff']}円の引上げ）"
        )
    return "。".join(out) + "。"


TOOLS = [
    {
        "slug": "saitei-chingin",
        "title": "最低賃金チェック（月給の時給換算）",
        "h1": "最低賃金チェックツール｜月給を時給に換算して宮崎・鹿児島の最低賃金と比べる",
        "desc": "月給制の従業員が最低賃金を満たしているかを時給換算で判定します。"
                + _mw_lines() + " 改定後の水準でも同時に判定します。",
        "lead": "月給制でも最低賃金のルールは適用されます。時給に直して比べるとき、"
                "通勤手当や家族手当など算入できない手当を含めたまま計算してしまう誤りが実務で最も多いところです。",
    },
    {
        "slug": "chinage-simulator",
        "title": "最低賃金引上げの人件費シミュレータ",
        "h1": "最低賃金引上げで人件費はいくら増える？｜宮崎・鹿児島の2026年10月改定シミュレータ",
        "desc": "2026年10月の最低賃金改定で、年間の人件費と社会保険料の会社負担がいくら増えるかを試算します。"
                "業務改善助成金で戻せる金額の目安も同時に表示します。",
        "lead": "引上げ額そのものより、社会保険料の会社負担が連動して増える分を見落とすと資金繰りの読みを外します。"
                "ここでは両方あわせて出します。",
        "service": "hojokin",
    },
    {
        "slug": "shakai-hoken",
        "title": "社会保険料の計算（令和8年度・宮崎/鹿児島）",
        "h1": "社会保険料 計算ツール｜令和8年度の宮崎県・鹿児島県の料率で自動計算",
        "desc": "報酬月額から健康保険・介護保険・厚生年金の保険料を、令和8年度の都道府県別料率で計算します。"
                "標準報酬月額の等級に当てはめたうえで、本人負担と会社負担に分けて表示します。",
        "lead": "報酬月額をそのまま料率に掛けると額がずれます。等級表に当てはめてから計算する必要があるので、"
                "このツールは等級への当てはめも含めて処理します。",
    },
    {
        "slug": "zangyo",
        "title": "残業代の計算（割増賃金）",
        "h1": "残業代 計算ツール｜割増賃金の基礎時給から時間外・深夜・休日を自動計算",
        "desc": "月給から割増賃金の基礎となる時給を出し、時間外・深夜・法定休日・月60時間超の割増を計算します。",
        "lead": "割増の基礎になる時給は、基本給だけで計算するものではありません。"
                "除外できる手当は法律で限定列挙されていて、それ以外は全部入れる必要があります。",
    },
]

TOOLS_BY_SLUG = {t["slug"]: t for t in TOOLS}


def tool_widget(t):
    return WIDGETS[t["slug"]]


# --- 各ツールの中身 -------------------------------------------------

def w_saitei_chingin():
    return f"""<div class="tool" id="t-mw">
  <h3>月給を時給に換算して判定する</h3>
  <div class="field">
    <label for="mw-pref">事業場のある県</label>
    <select id="mw-pref" name="pref">{PREF_OPTIONS}</select>
  </div>
  <div class="field-row">
    <div class="field">
      <label for="mw-pay">算入する賃金の月額
        <span class="hint">基本給＋算入できる手当の合計</span></label>
      <input id="mw-pay" name="pay" inputmode="numeric" value="175000">
    </div>
    <div class="field">
      <label for="mw-hours">1か月の平均所定労働時間
        <span class="hint">年間所定労働時間 ÷ 12</span></label>
      <input id="mw-hours" name="hours" inputmode="decimal" value="168">
    </div>
  </div>
  <div class="result" data-result></div>
  <p class="tool-note">最低賃金に算入しない賃金：臨時に支払われる賃金（結婚手当など）、
    1か月を超える期間ごとに支払われる賃金（賞与など）、時間外・休日・深夜の割増賃金、
    精皆勤手当・通勤手当・家族手当。これらは上の「算入する賃金」から除いて入力してください。</p>
</div>
<script>
MKN.tool("t-mw", function (c) {{
  var P = {PREF_RATE_JS};
  var p = P[c.val("pref")] || P["miyazaki"];
  var pay = c.num("pay"), hours = c.num("hours", 0);
  if (hours <= 0) return {{ head: "所定労働時間を入力してください" }};
  var hourly = pay / hours;
  var okNow = hourly >= p.mw, okNext = hourly >= p.mwNext;
  var shortfall = Math.max(0, p.mwNext - hourly);
  return {{
    tone: okNext ? "good" : "bad",
    head: okNext ? "改定後も基準を満たしています"
                 : (okNow ? "現在は適法ですが、改定後は下回ります" : "現在の最低賃金を下回っています"),
    lead: okNext ? "" : p.mwNextDate + "から" + p.name + "の最低賃金は"
          + MKN.yen(p.mwNext) + "になります。時給換算で" + MKN.yen1(shortfall)
          + "、月額で約" + MKN.yen(shortfall * hours) + "の引上げが必要です。",
    rows: [
      ["時給換算額", MKN.yen1(hourly)],
      [p.name + "の最低賃金（現行）", MKN.yen(p.mw) + (okNow ? "　満たす" : "　下回る")],
      [p.name + "の最低賃金（" + p.mwNextDate + "〜）", MKN.yen(p.mwNext) + (okNext ? "　満たす" : "　下回る")],
      ["改定後に必要な月額", MKN.yen(Math.max(pay, p.mwNext * hours))]
    ]
  }};
}});
</script>"""


def w_chinage():
    return f"""<div class="tool" id="t-up">
  <h3>引上げにかかる年間コストを試算する</h3>
  <div class="field">
    <label for="up-pref">事業場のある県</label>
    <select id="up-pref" name="pref">{PREF_OPTIONS}</select>
  </div>
  <div class="field-row">
    <div class="field">
      <label for="up-n">引上げが必要な人数
        <span class="hint">改定後の最低賃金を下回る従業員</span></label>
      <input id="up-n" name="n" inputmode="numeric" value="5">
    </div>
    <div class="field">
      <label for="up-now">その人たちの平均時給（現在）</label>
      <input id="up-now" name="now" inputmode="numeric" value="1030">
    </div>
    <div class="field">
      <label for="up-h">1人あたり月間労働時間</label>
      <input id="up-h" name="h" inputmode="decimal" value="160">
    </div>
  </div>
  <div class="result" data-result></div>
  <p class="tool-note">社会保険料の会社負担は、健康保険（県別料率）・子ども・子育て支援金・厚生年金を
    合計した概算です。実際は標準報酬月額の等級が変わったときだけ動くため、増加額は幅を持って見てください。
    労災保険料率は業種によって異なるため含めていません。</p>
</div>
<script>
MKN.tool("t-up", function (c) {{
  var P = {PREF_RATE_JS};
  var p = P[c.val("pref")] || P["miyazaki"];
  var n = c.num("n"), now = c.num("now"), h = c.num("h");
  var target = p.mwNext;
  var gap = Math.max(0, target - now);
  var wageYear = gap * h * 12 * n;
  // 会社負担率＝健康保険/2 ＋ 子ども子育て/2 ＋ 厚生年金/2
  var employerRate = (p.kenpo + {COMMON['kosodate_rate']}) / 2 / 100 + {COMMON['kosei_nenkin_rate']} / 2 / 100;
  var shaho = wageYear * employerRate;
  var total = wageYear + shaho;
  if (gap <= 0) {{
    return {{ tone: "good", head: "改定後の水準をすでに満たしています",
      lead: p.name + "の改定後の最低賃金は" + MKN.yen(target) + "です。入力された平均時給はこれを上回っています。" }};
  }}
  return {{
    tone: "bad",
    head: "年間で約" + MKN.yen(total) + "の増加",
    lead: p.name + "の最低賃金は" + p.mwNextDate + "から" + MKN.yen(target)
      + "。1人あたり時給を" + MKN.yen(gap) + "引き上げる前提で試算しています。",
    rows: [
      ["賃金の増加（年間）", MKN.yen(wageYear)],
      ["社会保険料の会社負担増（概算）", MKN.yen(shaho)],
      ["合計（年間）", MKN.yen(total)],
      ["1か月あたり", MKN.yen(total / 12)]
    ]
  }};
}});
</script>"""


def w_shakai_hoken():
    return f"""<div class="tool" id="t-sh">
  <h3>報酬月額から保険料を計算する</h3>
  <div class="field-row">
    <div class="field">
      <label for="sh-pref">事業場のある県</label>
      <select id="sh-pref" name="pref">{PREF_OPTIONS}</select>
    </div>
    <div class="field">
      <label for="sh-pay">報酬月額
        <span class="hint">通勤手当や残業手当を含めた総支給額</span></label>
      <input id="sh-pay" name="pay" inputmode="numeric" value="280000">
    </div>
    <div class="field">
      <label for="sh-age">年齢</label>
      <select id="sh-age" name="age">
        <option value="u40">40歳未満</option>
        <option value="kaigo">40歳以上65歳未満（介護保険あり）</option>
        <option value="o65">65歳以上70歳未満</option>
        <option value="o70">70歳以上（厚生年金なし）</option>
      </select>
    </div>
  </div>
  <div class="result" data-result></div>
  <p class="tool-note">令和8年度の料率（健康保険は{esc(COMMON['kenpo_applies_from'])}から適用）で計算しています。
    介護保険料率{COMMON['kaigo_rate']}％・子ども・子育て支援金{COMMON['kosodate_rate']}％・厚生年金{COMMON['kosei_nenkin_rate']}％は全国一律です。
    子ども・子育て支援金は令和8年4月分（5月納付分）からの加算です。
    保険料は標準報酬月額の等級に当てはめてから計算しており、労使折半後の端数処理は切り捨てで表示しています。</p>
</div>
<script>
MKN.tool("t-sh", function (c) {{
  var P = {PREF_RATE_JS};
  var KG = {json.dumps(KENPO_GRADES)};
  var NG = {json.dumps(NENKIN_GRADES)};
  // 等級の境界は隣り合う標準報酬の中間値（その額以上で上の等級）
  function grade(list, pay) {{
    for (var i = 0; i < list.length - 1; i++) {{
      if (pay < (list[i] + list[i + 1]) / 2) return list[i];
    }}
    return list[list.length - 1];
  }}
  var p = P[c.val("pref")] || P["miyazaki"];
  var pay = c.num("pay"), age = c.val("age");
  var sk = grade(KG, pay), sn = grade(NG, pay);
  var rate = p.kenpo + {COMMON['kosodate_rate']} + (age === "kaigo" ? {COMMON['kaigo_rate']} : 0);
  var kenpo = sk * rate / 100;
  var nenkin = (age === "o70") ? 0 : sn * {COMMON['kosei_nenkin_rate']} / 100;
  var half = function (x) {{ return Math.floor(x / 2); }};
  return {{
    head: "本人負担 " + MKN.yen(half(kenpo) + half(nenkin)) + " ／ 月",
    lead: p.name + "の令和8年度料率：健康保険 " + p.kenpo + "％"
      + (age === "kaigo" ? "＋介護 {COMMON['kaigo_rate']}％" : "")
      + "＋子ども・子育て支援金 {COMMON['kosodate_rate']}％。",
    rows: [
      ["標準報酬月額（健保）", MKN.yen(sk)],
      ["標準報酬月額（厚年）", age === "o70" ? "—" : MKN.yen(sn)],
      ["健康保険料（全額）", MKN.yen(kenpo)],
      ["厚生年金保険料（全額）", age === "o70" ? "—" : MKN.yen(nenkin)],
      ["本人負担（合計）", MKN.yen(half(kenpo) + half(nenkin))],
      ["会社負担（合計）", MKN.yen(kenpo - half(kenpo) + nenkin - half(nenkin))]
    ]
  }};
}});
</script>"""


def w_zangyo():
    return """<div class="tool" id="t-ot">
  <h3>割増賃金を計算する</h3>
  <div class="field-row">
    <div class="field">
      <label for="ot-pay">割増の基礎になる月額賃金
        <span class="hint">除外できる手当を引いた後の金額</span></label>
      <input id="ot-pay" name="pay" inputmode="numeric" value="240000">
    </div>
    <div class="field">
      <label for="ot-hours">1か月の平均所定労働時間</label>
      <input id="ot-hours" name="hours" inputmode="decimal" value="168">
    </div>
  </div>
  <div class="field-row">
    <div class="field"><label for="ot-a">法定時間外（月60時間まで）</label>
      <input id="ot-a" name="a" inputmode="decimal" value="20"></div>
    <div class="field"><label for="ot-b">法定時間外（月60時間超）</label>
      <input id="ot-b" name="b" inputmode="decimal" value="0"></div>
    <div class="field"><label for="ot-c">法定休日労働</label>
      <input id="ot-c" name="c" inputmode="decimal" value="0"></div>
    <div class="field"><label for="ot-d">深夜（22時〜5時）</label>
      <input id="ot-d" name="d" inputmode="decimal" value="0"></div>
  </div>
  <div class="result" data-result></div>
  <p class="tool-note">基礎から除外できるのは、家族手当・通勤手当・別居手当・子女教育手当・住宅手当、
    臨時に支払われた賃金、1か月を超える期間ごとに支払われる賃金に限られます。
    役職手当や資格手当は除外できません。深夜割増は時間外割増と重なる場合、合算して割増率が上がります。</p>
</div>
<script>
MKN.tool("t-ot", function (c) {
  var pay = c.num("pay"), hours = c.num("hours", 0);
  if (hours <= 0) return { head: "所定労働時間を入力してください" };
  var base = pay / hours;
  var a = c.num("a"), b = c.num("b"), d = c.num("c"), n = c.num("d");
  var va = base * 1.25 * a, vb = base * 1.5 * b, vc = base * 1.35 * d, vn = base * 0.25 * n;
  return {
    head: "合計 " + MKN.yen(va + vb + vc + vn),
    rows: [
      ["割増の基礎時給", MKN.yen1(base)],
      ["時間外 1.25（" + a + "時間）", MKN.yen(va)],
      ["時間外 1.50（" + b + "時間）", MKN.yen(vb)],
      ["法定休日 1.35（" + d + "時間）", MKN.yen(vc)],
      ["深夜加算 0.25（" + n + "時間）", MKN.yen(vn)]
    ]
  };
});
</script>"""


def _defer(html_):
    """app.js は defer で読み込むため、インラインの MKN.tool 呼び出しは
    DOMContentLoaded まで待たせないと MKN が未定義になる。"""
    return html_.replace(
        "<script>\nMKN.tool(",
        '<script>\ndocument.addEventListener("DOMContentLoaded", function () {\nMKN.tool(',
    ).replace("\n</script>", "\n});\n</script>")


WIDGETS = {
    "saitei-chingin": _defer(w_saitei_chingin()),
    "chinage-simulator": _defer(w_chinage()),
    "shakai-hoken": _defer(w_shakai_hoken()),
    "zangyo": _defer(w_zangyo()),
}


def build_tools():
    cards = "".join(
        f"""<a class="card" href="{U('/tools/' + t['slug'] + '/')}">
  <span class="card-cat">計算ツール</span>
  <span class="card-title">{esc(t['title'])}</span>
  <span class="card-desc">{esc(t['desc'][:88])}</span>
</a>"""
        for t in TOOLS
    )
    body = f"""<div class="page">
  <h1>計算ツール</h1>
  <p class="lede">登録不要・無料。入力した数値はブラウザの中だけで計算しており、サーバーには送信していません。</p>
  <div class="grid">{cards}</div>
  {service_cta()}
</div>"""
    write("/tools/index.html", layout(
        "計算ツール一覧｜最低賃金・社会保険料・残業代",
        "宮崎県・鹿児島県の事業者向けの計算ツール。最低賃金チェック、最低賃金引上げの人件費シミュレータ、"
        "社会保険料の計算、残業代の計算。登録不要・無料で使えます。",
        body, "/tools/", active="/tools/",
        crumbs=[("/", "ホーム"), ("/tools/", "計算ツール")],
    ))
    reg("/tools/", priority="0.8")

    for t in TOOLS:
        path = f"/tools/{t['slug']}/"
        others = "".join(
            f'<li><a href="{U("/tools/" + o["slug"] + "/")}">{esc(o["title"])}</a></li>'
            for o in TOOLS if o["slug"] != t["slug"]
        )
        schema = {
            "@type": "SoftwareApplication",
            "name": t["title"],
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web",
            "description": t["desc"],
            "url": abs_url(path),
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "JPY"},
            "publisher": {"@id": abs_url("#org")},
        }
        body = f"""<div class="page"><div class="doc">
<article class="article">
  <h1>{esc(t['h1'])}</h1>
  <p class="lede">{esc(t['lead'])}</p>
  {WIDGETS[t['slug']]}
  <h2 id="about">このツールについて</h2>
  <p>{esc(t['desc'])}</p>
  <p>入力値はすべてブラウザ内で処理しています。送信も保存もしていないので、
     実際の給与額をそのまま入れて確認していただいて差し支えありません。</p>
  <h2 id="other">ほかの計算ツール</h2>
  <ul>{others}</ul>
  {sources_block([
      {"name": PREFS["prefs"]["宮崎県"]["min_wage"]["source_name"], "url": PREFS["prefs"]["宮崎県"]["min_wage"]["source"]},
      {"name": PREFS["prefs"]["鹿児島県"]["min_wage"]["source_name"], "url": PREFS["prefs"]["鹿児島県"]["min_wage"]["source"]},
      {"name": COMMON["kenpo_source_name"], "url": COMMON["kenpo_source"]},
  ])}
  <p class="updated">データ更新日：{jp_date(TODAY.isoformat())}</p>
  {supervisor_box()}
  {service_cta(t.get('service'))}
</article>
{side_column()}
</div></div>"""
        write(path + "index.html", layout(
            t["title"], t["desc"], body, path, schema=schema, active="/tools/",
            crumbs=[("/", "ホーム"), ("/tools/", "計算ツール"), (path, t["title"])],
        ))
        reg(path, priority="0.9")


# ---------------------------------------------------------------- 県ページ

SUBSIDIES = json.load(open(os.path.join(ROOT, "data", "subsidies.json"), encoding="utf-8"))
JGRANTS = json.load(open(os.path.join(ROOT, "data", "jgrants.json"), encoding="utf-8"))


def pref_subsidies(pref):
    return [s for s in SUBSIDIES if s.get("pref") == pref]


def pref_jgrants(pref):
    key = pref.replace("県", "")
    return [j for j in JGRANTS if j["open"] and (key in (j["area"] or "") or key in (j["title"] or ""))]


def build_prefs():
    for pref, v in PREFS["prefs"].items():
        slug, mw, kp = v["slug"], v["min_wage"], v["kenpo"]
        path = f"/{slug}/"
        munis = [m for m in MUNIS if m["pref"] == pref]

        hist = "".join(
            f"<tr><td>{esc(y)}</td><td class=\"num\">{yen(a)}</td></tr>"
            for y, a in reversed(mw["history"][-8:])
        )
        tokutei = "".join(f"<li>{esc(x)}</li>" for x in mw["tokutei"])
        muni_links = "".join(
            f'<li><a href="{esc(m["site"])}" target="_blank" rel="noopener">{esc(m["name"])}</a></li>'
            for m in munis
        )
        subs = pref_subsidies(pref)
        sub_rows = "".join(
            f'<tr><td><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a></td>'
            f'<td>{esc(s.get("dept") or "—")}</td><td>{esc(s.get("deadline") or "—")}</td></tr>'
            for s in subs[:30]
        ) or '<tr><td colspan="3">現在、収集済みの県単独制度はありません。</td></tr>'
        jg = pref_jgrants(pref)
        jg_rows = "".join(
            f'<tr><td>{esc(j["title"])}</td><td class="num">{yen(j["max"]) if j.get("max") else "—"}</td>'
            f'<td>{esc(j["end"] or "—")}</td></tr>'
            for j in jg[:20]
        ) or '<tr><td colspan="3">受付中の制度は現在ありません。</td></tr>'

        body = f"""<div class="page"><div class="doc">
<article class="article">
  <h1>{esc(pref)}の事業者が押さえておく制度まとめ｜最低賃金・社会保険料・補助金</h1>
  <p class="lede">{esc(pref)}で事業を営む中小企業・個人事業主向けに、金額が決まっている制度を一次情報からまとめています。
     数字が変わるたびに更新しています。</p>

  <h2 id="mw">{esc(pref)}の最低賃金</h2>
  <p>{esc(pref)}の地域別最低賃金は、現在 <strong>{yen(mw['current']['amount'])}</strong>
     （{esc(mw['current']['wareki'])}発効）です。
     <strong>{esc(mw['next']['wareki'])}</strong>からは
     <strong>{yen(mw['next']['amount'])}</strong>に改定されます。引上げ幅は{mw['next']['diff']}円です。</p>
  <div class="table-wrap"><table>
    <thead><tr><th>区分</th><th class="num">時間額</th><th>効力発生日</th></tr></thead>
    <tbody>
      <tr><td>現在</td><td class="num">{yen(mw['current']['amount'])}</td><td>{esc(mw['current']['wareki'])}</td></tr>
      <tr><td>改定後</td><td class="num">{yen(mw['next']['amount'])}</td><td>{esc(mw['next']['wareki'])}</td></tr>
    </tbody>
  </table></div>
  <p>月給制の従業員が基準を満たしているかは、時給に換算して比べます。
     <a href="/tools/saitei-chingin/">最低賃金チェックツール</a>で判定できます。</p>

  <h3>特定（産業別）最低賃金</h3>
  <p>{esc(mw['tokutei_note'])}</p>
  <ul>{tokutei}</ul>

  <h3>{esc(pref)}の最低賃金の推移</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>年度</th><th class="num">時間額</th></tr></thead><tbody>{hist}</tbody>
  </table></div>

  {WIDGETS['chinage-simulator']}

  <h2 id="kenpo">{esc(pref)}の社会保険料率（令和8年度）</h2>
  <p>協会けんぽの健康保険料率は都道府県ごとに違います。{esc(pref)}は
     令和7年度の{kp['r7']}％から<strong>{kp['r8']}％</strong>に改定されました（{esc(kp['rank_note'])}）。
     適用は{esc(COMMON['kenpo_applies_from'])}からです。</p>
  <div class="table-wrap"><table>
    <thead><tr><th>区分</th><th class="num">料率</th><th>負担</th></tr></thead>
    <tbody>
      <tr><td>健康保険（{esc(pref)}）</td><td class="num">{kp['r8']}％</td><td>労使折半</td></tr>
      <tr><td>子ども・子育て支援金（全国一律）</td><td class="num">{COMMON['kosodate_rate']}％</td><td>労使折半</td></tr>
      <tr><td>介護保険（40〜64歳・全国一律）</td><td class="num">{COMMON['kaigo_rate']}％</td><td>労使折半</td></tr>
      <tr><td>厚生年金（全国一律）</td><td class="num">{COMMON['kosei_nenkin_rate']}％</td><td>労使折半</td></tr>
    </tbody>
  </table></div>
  <p>実際の保険料は<a href="/tools/shakai-hoken/">社会保険料の計算ツール</a>で確認できます。</p>

  <h2 id="hojokin">{esc(pref)}で使える補助金・助成金</h2>
  <h3>国の制度（受付中）</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>制度名</th><th class="num">上限額</th><th>締切</th></tr></thead>
    <tbody>{jg_rows}</tbody>
  </table></div>
  <h3>{esc(pref)}の独自制度</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>制度名</th><th>担当</th><th>締切</th></tr></thead>
    <tbody>{sub_rows}</tbody>
  </table></div>

  <h2 id="muni">{esc(pref)}の市町村（{len(munis)}団体）</h2>
  <p>市町村ごとの独自制度は各自治体の公式サイトで公表されています。</p>
  <ul class="muni-list">{muni_links}</ul>

  <h2 id="madoguchi">相談先</h2>
  <ul>
    <li><a href="{esc(v['bureau']['url'])}" target="_blank" rel="noopener">{esc(v['bureau']['name'])}</a>（最低賃金・労務）</li>
    <li><a href="{esc(v['yorozu']['url'])}" target="_blank" rel="noopener">{esc(v['yorozu']['name'])}</a>（経営全般・無料）</li>
  </ul>

  {sources_block([
      {"name": mw["source_name"], "url": mw["source"]},
      {"name": COMMON["kenpo_source_name"], "url": COMMON["kenpo_source"]},
      {"name": "厚生労働省「地域別最低賃金の全国一覧」", "url": COMMON["mw_national_source"]},
  ])}
  <p class="updated">最終更新：{jp_date(TODAY.isoformat())}</p>
  {supervisor_box()}
  {service_cta()}
</article>
{side_column()}
</div></div>"""

        desc = (
            f"{pref}の最低賃金は{mw['next']['wareki']}から{yen(mw['next']['amount'])}。"
            f"協会けんぽの健康保険料率は令和8年度{kp['r8']}％。"
            f"{pref}の事業者が押さえる最低賃金・社会保険料・補助金を一次情報の出典つきでまとめています。"
        )
        write(path + "index.html", layout(
            f"{pref}の事業者向け制度まとめ", desc, body, path, active=path,
            crumbs=[("/", "ホーム"), (path, pref)],
        ))
        reg(path, priority="0.9")


def build_hojokin_list():
    """国の制度（jGrants）と県の独自制度をまとめた一覧。

    受付中を先頭に出す。終了済みも残すのは、制度名で検索して来た人が
    「今は募集していない」ことを確認できるほうが有用なため。
    """
    open_now = [j for j in JGRANTS if j["open"]]
    closed = [j for j in JGRANTS if not j["open"]]

    def jrow(j):
        amount = yen(j["max"]) if j.get("max") else "—"
        return (f'<tr><td>{esc(j["title"] or "")}</td>'
                f'<td>{esc(j["area"] or "—")}</td>'
                f'<td class="num">{amount}</td>'
                f'<td>{esc(j["end"] or "—")}</td></tr>')

    def srow(s):
        return (f'<tr><td><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a></td>'
                f'<td>{esc(s.get("pref") or "—")}</td>'
                f'<td>{esc(s.get("dept") or "—")}</td>'
                f'<td>{esc(s.get("deadline") or "—")}</td></tr>')

    open_rows = "".join(jrow(j) for j in open_now) or '<tr><td colspan="4">受付中の制度はありません。</td></tr>'
    sub_rows = "".join(srow(s) for s in SUBSIDIES) or '<tr><td colspan="4">収集済みの制度はありません。</td></tr>'
    closed_rows = "".join(jrow(j) for j in closed[:120])

    body = f"""<div class="page">
  <h1>宮崎県・鹿児島県で使える補助金・助成金の一覧</h1>
  <p class="lede">デジタル庁のjGrantsに掲載されている国・県の制度のうち、宮崎県・鹿児島県または全国が
     対象のものと、両県が独自に実施している制度をまとめています。金額と締切は必ず公募要領で確認してください。</p>

  <h2 id="open">受付中（{len(open_now)}件）</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>制度名</th><th>対象地域</th><th class="num">上限額</th><th>締切</th></tr></thead>
    <tbody>{open_rows}</tbody>
  </table></div>

  <h2 id="pref">宮崎県・鹿児島県の独自制度（{len(SUBSIDIES)}件）</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>制度名</th><th>県</th><th>担当</th><th>締切</th></tr></thead>
    <tbody>{sub_rows}</tbody>
  </table></div>

  <h2 id="closed">受付を終了した制度</h2>
  <p>次回の公募に備えて要件を確認したい場合の参考として残しています（新しい順に最大120件）。</p>
  <div class="table-wrap"><table>
    <thead><tr><th>制度名</th><th>対象地域</th><th class="num">上限額</th><th>締切</th></tr></thead>
    <tbody>{closed_rows}</tbody>
  </table></div>

  <h2 id="how">申請の前に</h2>
  <p>ほとんどの補助金は、<strong>交付決定を受ける前に発注・契約したものは対象外</strong>です。
     見積りを取るところまでにとどめ、交付決定を待ってから発注してください。</p>
  <p>また、補助金は原則として後払いです。先に全額を支払い、実績報告のあとに補助分が入金されます。
     自己資金または借入で立て替えられるかを、申請前に確認してください。</p>

  {sources_block([
      {"name": "デジタル庁 jGrants（補助金電子申請システム）", "url": "https://www.jgrants-portal.go.jp/"},
      {"name": "九州補助金ナビ", "url": "https://abengerz.github.io/kyushu-hojokin/"},
  ])}
  <p class="updated">データ更新日：{jp_date(TODAY.isoformat())}</p>
  {service_cta("hojokin")}
</div>"""

    desc = (f"宮崎県・鹿児島県の事業者が使える補助金・助成金の一覧。受付中{len(open_now)}件、"
            f"両県の独自制度{len(SUBSIDIES)}件を掲載しています。jGrantsの公開データから自動で更新しています。")
    write("/hojokin/list/index.html", layout(
        "宮崎・鹿児島の補助金・助成金一覧", desc, body, "/hojokin/list/", active="/hojokin/",
        crumbs=[("/", "ホーム"), ("/hojokin/", "補助金・助成金"), ("/hojokin/list/", "一覧")],
    ))
    reg("/hojokin/list/", priority="0.8")


# ---------------------------------------------------------------- 市町村マップ

MUNI_MAP = json.load(open(os.path.join(ROOT, "data", "muni_map.json"), encoding="utf-8"))
MUNI_BY_NAME = {m["name"]: m for m in MUNIS}


def muni_payload():
    """市町村クリック時にパネルへ出す内容。ページを69枚作らずに済ませている。

    市町村ごとの固有データが揃うまで、県の数字＋自治体サイトへの導線で構成する。
    中身のないページを69枚出すとdoorway page扱いになるため、ここで受ける。
    """
    out = {}
    for m in MUNIS:
        pref = PREFS["prefs"][m["pref"]]
        mw = pref["min_wage"]
        out[m["name"]] = {
            "pref": m["pref"],
            "prefSlug": pref["slug"],
            "kind": m["kind"],
            "code": m["code"],
            "site": m["site"],
            "mw": mw["next"]["amount"],
            "mwDate": mw["next"]["wareki"],
            "mwNow": mw["current"]["amount"],
            "kenpo": pref["kenpo"]["r8"],
            "subsidies": len([s for s in SUBSIDIES if s.get("pref") == m["pref"]]),
        }
    return out


def muni_name_list():
    """地図の下に出す市町村名の一覧。

    奄美の小さい島は図形が小さくて押せないので、名前からも選べるようにする。
    ページ内に69件の地名がテキストで載るため、地名検索にも効く。
    """
    blocks = []
    for pref, v in PREFS["prefs"].items():
        names = [m for m in MUNIS if m["pref"] == pref]
        chips = "".join(
            f'<button type="button" class="mm-chip" data-pick="{esc(m["name"])}">{esc(m["name"])}</button>'
            for m in names
        )
        blocks.append(
            f'<div class="mm-names-col"><p class="mm-names-h">'
            f'<a href="{U("/" + v["slug"] + "/")}">{esc(pref)}</a>'
            f'<span>{len(names)}市町村</span></p><div class="mm-chips">{chips}</div></div>'
        )
    return '<div class="mm-names">' + "".join(blocks) + "</div>"


def _map_paths(group, cls):
    parts = []
    for it in group["items"]:
        parts.append(
            f'<path class="{cls}" d="{it["d"]}" data-name="{esc(it["name"])}" '
            f'data-pref="{esc(it["pref"])}" tabindex="0" role="button" '
            f'aria-label="{esc(it["name"])}の情報を見る"><title>{esc(it["name"])}</title></path>'
        )
    return "".join(parts)


def muni_map_html():
    main, isle = MUNI_MAP["main"], MUNI_MAP["isle"]
    counts = {k: len([m for m in MUNIS if m["pref"] == k]) for k in PREFS["prefs"]}
    legend = "".join(
        f'<span class="mm-key mm-key-{PREFS["prefs"][k]["slug"]}">{esc(k)} {v}市町村</span>'
        for k, v in counts.items()
    )
    return f"""<div class="mm" id="muni-map">
  <div class="mm-stage">
    <div class="mm-maps">
      <svg class="mm-svg" viewBox="0 0 {main['w']} {main['h']}" role="img"
           aria-label="宮崎県・鹿児島県の市町村地図">
        <g class="mm-layer">{_map_paths(main, "mm-a")}</g>
      </svg>
      <svg class="mm-svg mm-svg-isle" viewBox="0 0 {isle['w']} {isle['h']}" role="img"
           aria-label="奄美群島・トカラ列島の市町村地図">
        <g class="mm-layer">{_map_paths(isle, "mm-a")}</g>
        <text class="mm-isle-cap" x="6" y="16">奄美・トカラ</text>
      </svg>
    </div>
    <div class="mm-panel" id="mm-panel" aria-live="polite">
      <p class="mm-hint">地図の市町村を選ぶと、その地域の情報が出ます。</p>
    </div>
  </div>
  <p class="mm-legend">{legend}</p>
  {muni_name_list()}
  <p class="mm-credit">{esc(MUNI_MAP["credit"])}</p>
</div>
<script id="mm-data" type="application/json">{json.dumps(muni_payload(), ensure_ascii=False)}</script>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  MKN.muniMap("{U('/')}");
}});
</script>"""


# ---------------------------------------------------------------- サービス

def build_services():
    for s in SITE["services"]:
        path = f"/service/{s['slug']}/"
        fors = "".join(f"<li>{esc(x)}</li>" for x in s["for"])
        others = "".join(
            f'<li><a href="{U("/service/" + o["slug"] + "/")}">{esc(o["label"])}</a></li>'
            for o in SITE["services"] if o["slug"] != s["slug"]
        )
        related = [a for a in ARTICLES if a.get("service") == s["slug"]][:6]
        rel = "".join(article_card(a) for a in related)
        rel_block = f'<h2 id="related">関連する解説記事</h2><div class="grid">{rel}</div>' if rel else ""
        body = f"""<div class="page">
  <h1>{esc(s['label'])}</h1>
  <p class="lede">{esc(s['lead'])}</p>
  <div class="doc"><article class="article">
    <h2 id="what">内容</h2>
    <p>{esc(s['summary'])}</p>
    <h2 id="for">こういう状態の会社向けです</h2>
    <ul>{fors}</ul>
    <h2 id="flow">進め方</h2>
    <ol>
      <li>現状を聞かせてください（オンライン可・費用はかかりません）</li>
      <li>やること・やらないこと・費用を書面でお出しします</li>
      <li>合意できた範囲だけ着手します</li>
    </ol>
    <h2 id="area">対応エリア</h2>
    <p>宮崎県・鹿児島県を中心に対応しています。オンラインのみでの対応も可能です。</p>
    <h2 id="contact">相談する</h2>
    <p><a href="/contact/">お問い合わせフォーム</a>からご連絡ください。
       営業目的のご連絡はお断りしています。</p>
    {rel_block}
    <h2 id="other">ほかのサービス</h2>
    <ul>{others}</ul>
  </article>{side_column()}</div>
</div>"""
        schema = {
            "@type": "Service",
            "name": s["label"],
            "description": s["summary"],
            "provider": {"@id": abs_url("#org")},
            "areaServed": [{"@type": "AdministrativeArea", "name": a} for a in SITE["area"]],
            "url": abs_url(path),
        }
        write(path + "index.html", layout(
            s["label"], s["summary"], body, path, schema=schema,
            crumbs=[("/", "ホーム"), ("/service/", "サービス"), (path, s["label"])],
        ))
        reg(path, priority="0.7")

    cards = "".join(
        f"""<a class="card" href="{U('/service/' + s['slug'] + '/')}">
  <span class="card-cat">サービス</span>
  <span class="card-title">{esc(s['label'])}</span>
  <span class="card-desc">{esc(s['summary'][:92])}</span></a>"""
        for s in SITE["services"]
    )
    body = f'<div class="page"><h1>サービス</h1><p class="lede">記事を読んで終わりにせず、実際に手を動かすところまで引き受けます。</p><div class="grid">{cards}</div></div>'
    write("/service/index.html", layout(
        "サービス", "AI導入・乗り換え支援、補助金の申請支援、経理BPO。宮崎・鹿児島の中小企業向けに提供しています。",
        body, "/service/", crumbs=[("/", "ホーム"), ("/service/", "サービス")]))
    reg("/service/", priority="0.7")


# ---------------------------------------------------------------- 固定ページ

def build_static():
    o = SITE["org"]
    sv = SITE["supervisor"]

    offices = "".join(
        f'<tr><th>{esc(x["label"])}</th><td>{esc(x["pref"])}'
        + (esc(x["city"]) if x.get("city") else "")
        + (f'{esc(x["street"])}' if x.get("street") else "")
        + "</td></tr>"
        for x in o.get("offices", [])
    )
    tel_row = f'<tr><th>電話</th><td>{esc(o["tel"])}</td></tr>' if o.get("tel") else ""

    sv_block = ""
    if sv.get("enabled") and sv.get("name"):
        sv_block = f"""<h2 id="supervisor">監修者</h2>
  <p><strong>{esc(sv['name'])}</strong>（{esc(sv['title'])}
     {'／登録番号 ' + esc(sv['registration']) if sv.get('registration') else ''}）</p>
  <p>{esc(sv.get('bio', ''))}</p>"""
    else:
        sv_block = """<h2 id="supervisor">監修体制について</h2>
  <p>本サイトの記事は、税理士による監修を受けたものではありません。
     制度の内容は、官公庁が公表している一次資料を確認したうえで記載していますが、
     個別の事案についての判断は、顧問の税理士・社会保険労務士・弁護士にご確認ください。</p>
  <p>税務・労務の専門家による監修体制については、準備が整い次第このページに掲載します。</p>"""

    pages = {
        "/about/": ("運営者情報", "このサイトを運営している会社と、書いている人について", f"""
  <h2 id="who">運営会社</h2>
  <div class="table-wrap"><table><tbody>
    <tr><th>会社名</th><td>{esc(o['name'])}（{esc(o.get('name_en',''))}）</td></tr>
    <tr><th>代表者</th><td>{esc(o['ceo'])}</td></tr>
    <tr><th>設立</th><td>2022年7月</td></tr>
    {offices}
    {tel_row}
    <tr><th>連絡先</th><td>{esc(o['email'])}</td></tr>
    <tr><th>事業内容</th><td>{esc(o['business'])}</td></tr>
    <tr><th>コーポレートサイト</th><td><a href="{esc(o['url'])}" target="_blank" rel="noopener">{esc(o['url'])}</a></td></tr>
  </tbody></table></div>

  <h2 id="why">このサイトを作っている理由</h2>
  <p>私たちは沖縄と宮崎の2拠点で、中小企業の経理を代行しています。
     {esc(o.get('track_record',''))}。</p>
  <p>その現場で繰り返し出てくるのが、「制度を知らなかったために損をしていた」という相談です。
     最低賃金がいつからいくらになるのか、使える助成金があったのか、保険料率が変わったのか。
     調べれば分かることでも、本業を回しながら官公庁のサイトを追い続けるのは現実的ではありません。</p>
  <p>このサイトは、その調べる部分を代わりに引き受けるために作っています。
     数字は必ず一次情報から取り、出典を各ページに明記しています。</p>

  <h2 id="author">書いている人</h2>
  <p>記事は{esc(o['name'])}の編集部が作成しています。編集責任者は代表取締役の{esc(o['ceo'])}です。</p>
  <p>経理代行の現場で実際に受けた相談を出発点にして、制度の内容は官公庁の公表資料で
     確認したうえで書いています。下書きの整理に生成AIを使うことがありますが、
     掲載している数字は必ず人が一次資料に当たって確認しています。</p>

  {sv_block}

  <h2 id="contact">お問い合わせ</h2>
  <p><a href="/contact/">お問い合わせページ</a>からご連絡ください。</p>"""),

        "/policy/": ("編集方針", "記事の作り方と、数字の裏取りの方針", f"""
  <h2 id="source">数字は一次情報から取ります</h2>
  <p>金額・料率・期日は、官公庁および公的機関が公表している資料からのみ取得しています。
     具体的には厚生労働省、各都道府県労働局、国税庁、全国健康保険協会、デジタル庁（jGrants）、
     国土交通省、各自治体の公式サイトです。各ページの末尾に出典へのリンクを置いています。</p>

  <h2 id="update">更新の考え方</h2>
  <p>制度が変わったとき、記事の日付だけ触って中身を変えない運用はしていません。
     改定があった箇所を実際に書き換え、更新日を記載します。
     改定前の数値も、いつまで適用されるのかが実務上必要なため、併記して残します。</p>
  <p>最低賃金と健康保険料率については、一次情報を自動で取得し直す仕組みを動かしています。
     変更を検知した場合は、人が出典を確認したうえで反映します。</p>

  <h2 id="limit">このサイトでできないこと</h2>
  <p>記事は一般的な制度の説明であり、個別の事案に対する税務・法務上の判断ではありません。
     また、{esc(o['name'])}は税理士法人ではなく、個別の税務相談をお受けする立場にありません。</p>
  <p>実際の適用は事実関係によって変わります。判断が必要な場面では、
     顧問の税理士・社会保険労務士・弁護士にご確認ください。
     顧問がいない場合、各県のよろず支援拠点や商工会議所・商工会が無料で相談に応じています。</p>

  <h2 id="ai">生成AIの使い方</h2>
  <p>下書きや構成の整理に生成AIを使うことがあります。
     ただし公開している数字は必ず人が一次資料に当たって確認しています。
     AIが出力した数値や法令の条番号をそのまま載せることはありません。</p>

  <h2 id="pr">広告・アフィリエイトについて</h2>
  <p>記事中に広告リンクを含める場合は、その旨をページ内に明示します。
     報酬の有無で紹介する制度や結論を変えることはしません。</p>

  <h2 id="fix">誤りの訂正</h2>
  <p>記載に誤りを見つけられた場合、該当ページのURLを添えて
     {esc(o['email'])} までご連絡ください。確認のうえ訂正し、訂正した旨をページに記載します。</p>"""),

        "/privacy/": ("プライバシーポリシー", "個人情報の取り扱いについて", f"""
  <h2 id="operator">事業者</h2>
  <p>{esc(o['name'])}（代表取締役 {esc(o['ceo'])}）</p>

  <h2 id="info">取得する情報</h2>
  <p>お問い合わせフォームまたはメールでご連絡いただいた場合に、氏名・会社名・メールアドレス・
     お問い合わせ内容を取得します。これらはお問い合わせへの回答およびその後のご連絡にのみ使用します。</p>

  <h2 id="tools">計算ツールに入力した数値</h2>
  <p>当サイトの計算ツールは、入力された数値をブラウザ内だけで処理しています。
     サーバーへの送信も保存も行っていません。実際の給与額をそのまま入力していただいて差し支えありません。</p>

  <h2 id="access">アクセス解析</h2>
  <p>サイトの改善のためアクセス解析を利用する場合があります。
     解析により取得する情報に、個人を特定するものは含まれません。</p>

  <h2 id="third">第三者提供</h2>
  <p>法令に基づく場合を除き、ご本人の同意なく個人情報を第三者に提供することはありません。</p>

  <h2 id="disclose">開示・訂正・削除</h2>
  <p>ご本人からの求めに応じ、保有する個人情報の開示・訂正・削除に対応します。
     {esc(o['email'])} までご連絡ください。</p>

  <h2 id="contact-p">お問い合わせ窓口</h2>
  <p>{esc(o['name'])}／{esc(o['email'])}</p>"""),

        "/contact/": ("お問い合わせ", "ご相談・取材・掲載についてのご連絡先", f"""
  <h2 id="mail">メール</h2>
  <p>{esc(o['email'])} までご連絡ください。2営業日以内に返信しています。</p>

  <h2 id="what">お受けしている内容</h2>
  <ul>
    <li>AI導入・乗り換えのご相談</li>
    <li>補助金・助成金の申請可否のご相談</li>
    <li>経理・バックオフィスの外注のご相談</li>
    <li>記事内容の誤りのご指摘（歓迎します）</li>
  </ul>

  <h2 id="no">お受けしていない内容</h2>
  <ul>
    <li>個別の税務相談（当社は税理士法人ではありません。顧問税理士にご確認ください）</li>
    <li>営業・売り込み</li>
    <li>相互リンク、記事広告、被リンクの依頼</li>
  </ul>

  <h2 id="fix">記事の誤りについて</h2>
  <p>数字や制度の記載に誤りを見つけられた場合、該当ページのURLを添えてご連絡ください。
     確認のうえ訂正し、訂正した旨をページに記載します。</p>

  <h2 id="company">運営会社</h2>
  <p>{esc(o['name'])}（{esc(o.get('name_en',''))}）／代表取締役 {esc(o['ceo'])}<br>
     沖縄本社・宮崎オフィスの2拠点で、中小企業のバックオフィス支援を行っています。<br>
     <a href="{esc(o['url'])}" target="_blank" rel="noopener">コーポレートサイト</a>／
     <a href="/about/">運営者情報</a></p>"""),
    }

    for path, (title, desc, inner) in pages.items():
        body = (f'<div class="page"><div class="doc"><article class="article">'
                f'<h1>{esc(title)}</h1><p class="lede">{esc(desc)}</p>{inner}</article>'
                f'{side_column()}</div></div>')
        write(path + "index.html", layout(
            title, desc, body, path,
            crumbs=[("/", "ホーム"), (path, title)],
        ))
        reg(path, priority="0.4")



# ---------------------------------------------------------------- トップ

# 線画アイコン。外部ライブラリを使わずインラインSVGで持つ。
ICONS = {
    "wallet": "M3 7h15a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zm0 0a2 2 0 0 1 2-2h11M16 13h.01",
    "people": "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 7a3 3 0 1 1 0 6 3 3 0 0 1 0-6zm13 12v-1a4 4 0 0 0-3-3.9M16 4.1a3 3 0 0 1 0 5.8",
    "gift": "M20 12v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8M2 8h20v4H2zM12 21V8M12 8H7.5a2.5 2.5 0 1 1 0-5C10 3 12 8 12 8zm0 0h4.5a2.5 2.5 0 1 0 0-5C14 3 12 8 12 8z",
    "bank": "M3 21h18M4 10h16M5 10V7l7-4 7 4v3M7 10v7M11 10v7M15 10v7M19 10v7",
    "cut": "M6 3v12m12-12v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm12 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM20 4L8.12 15.88M14.47 14.48L20 20M8.12 8.12L12 12",
    "spark": "M12 3v3m0 12v3M5.6 5.6l2.1 2.1m8.6 8.6l2.1 2.1M3 12h3m12 0h3M5.6 18.4l2.1-2.1m8.6-8.6l2.1-2.1M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "shield": "M12 3l8 3v6c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V6l8-3zM9 12l2 2 4-4",
    "calc": "M6 2h12a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM8 6h8v3H8zM8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01M16 17h.01",
    "chart": "M3 3v18h18M7 15l3-4 3 3 5-7",
    "clock": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4.5V12l3 2",
    "check": "M20 6L9 17l-5-5",
    "doc": "M14 2H6a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V7l-5-5zM14 2v5h5M8 13h8M8 17h5",
    "map": "M9 3L3 5v16l6-2 6 2 6-2V3l-6 2-6-2zM9 3v16M15 5v16",
}


def icon(name):
    d = ICONS.get(name, ICONS["doc"])
    paths = "".join(f'<path d="{p}"/>' for p in d.split("|"))
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{paths}</svg>'


# 専門用語ではなく、経営者が実際に口にする言葉で入口を作る。
ASKS = [
    ("wallet", "従業員の給料、いくらまで上げないといけない？",
     "10月から最低賃金が変わります", "/roumu/saitei-chingin-2026/"),
    ("people", "パートは年収いくらまで働いてもらえる？",
     "「103万円の壁」は136万円に変わりました", "/roumu/fuyo-kabe-2026/"),
    ("calc", "今年の年末調整、何が変わった？",
     "基礎控除も扶養の基準も動いています", "/roumu/nencho-2026/"),
    ("gift", "設備を買いたい。使える補助金はある？",
     "宮崎・鹿児島で募集中の制度を一覧に", "/hojokin/list/"),
    ("chart", "黒字なのにお金が残らないのはなぜ？",
     "利益と現金がずれる場所は4つだけです", "/yushi/shikinguri-kihon/"),
    ("bank", "銀行に「決算書を見せて」と言われた",
     "どこを見られているかを先に知る", "/yushi/ginko-kessansho/"),
    ("cut", "固定費を下げたい。どこから手を付ける？",
     "通信費から始めると成果が出ます", "/cost/tsushinhi-sakugen/"),
    ("spark", "AIを入れたが誰も使っていない",
     "原因はツールではなく導入の順序です", "/ai/ai-dounyu-teichaku/"),
    ("doc", "経理担当が1人しかいなくて不安",
     "外に出すか、中で回すかの判断基準", "/zeimu/keiri-naisei-gaichu/"),
    ("shield", "取引先からの請求書、これ本物？",
     "振込先だけ差し替える手口が続いています", "/risk/seikyusho-sagi/"),
]

# トップに出す「いま効く期限」。日付が過ぎたものは自動で落とす。
TODOS = [
    ("2026-10-24", "宮崎県の最低賃金が1,085円に", "62円の引上げです。月給制の人も時給に直して確認してください。",
     "/roumu/saitei-chingin-2026/", "確認する"),
    ("2026-10-25", "鹿児島県の最低賃金が1,090円に", "宮崎と発効日が1日ずれます。給与計算の切替日を分けてください。",
     "/roumu/saitei-chingin-2026/", "確認する"),
    ("2026-10-01", "インボイスの控除が8割から7割へ", "会計ソフトの税区分に「70％控除」があるか確認してください。",
     "/zeimu/invoice-keikasochi-2026/", "変更点を見る"),
    ("2026-12-31", "年末調整の準備", "基礎控除と扶養の基準が変わっています。申告書の配布前に確認を。",
     "/roumu/nencho-2026/", "変更点を見る"),
]

TOOL_ICONS = {
    "saitei-chingin": ("calc", "時給に直して、いくら足りないかが出ます"),
    "chinage-simulator": ("chart", "賃上げで人件費がいくら増えるかを試算します"),
    "shakai-hoken": ("wallet", "本人負担と会社負担を分けて表示します"),
    "zangyo": ("clock", "時間外・深夜・休日の割増をまとめて計算します"),
}


def build_index():
    mz, kg = PREFS["prefs"]["宮崎県"], PREFS["prefs"]["鹿児島県"]
    open_jg = len([j for j in JGRANTS if j["open"]])

    facts = f"""
      <a class="fact" href="{U('/miyazaki/')}">
        <span>宮崎県の最低賃金（10月24日〜）</span>
        <b>{mz['min_wage']['next']['amount']:,}</b>円<i>＋{mz['min_wage']['next']['diff']}円</i></a>
      <a class="fact" href="{U('/kagoshima/')}">
        <span>鹿児島県の最低賃金（10月25日〜）</span>
        <b>{kg['min_wage']['next']['amount']:,}</b>円<i>＋{kg['min_wage']['next']['diff']}円</i></a>
      <a class="fact" href="{U('/hojokin/list/')}">
        <span>いま応募できる補助金</span>
        <b>{open_jg}</b>件<i>宮崎・鹿児島が対象</i></a>
      <a class="fact" href="{U('/tools/')}">
        <span>無料の計算ツール</span>
        <b>{len(TOOLS)}</b>種<i>登録不要</i></a>"""

    asks = "".join(
        f"""<a class="ask" href="{U(href)}">
      <span class="ask-ico">{icon(ic)}</span>
      <span class="ask-body"><span class="ask-q">{esc(q)}</span><span class="ask-a">{esc(a)}</span></span>
    </a>"""
        for ic, q, a, href in ASKS
    )

    todo_items = []
    for date, title, body, href, label in TODOS:
        d = datetime.date.fromisoformat(date)
        if d < TODAY:
            continue
        days = (d - TODAY).days
        soon = " soon" if days <= 45 else ""
        when = "今日" if days == 0 else (f"あと{days}日" if days <= 45 else f"{d.month}月{d.day}日")
        todo_items.append(
            f"""<li><span class="todo-when{soon}">{when}</span>
      <span class="todo-body"><b>{esc(title)}</b>{esc(body)}
      <a href="{U(href)}">{esc(label)} →</a></span></li>"""
        )
    todo = ""
    if todo_items:
        todo = f"""<section class="sec">
    <div class="sec-head"><div><h2>いま期限が近いもの</h2>
      <p>期限の近い順に並べています。日付が過ぎたものは自動で消えます。</p></div></div>
    <div class="todo"><ul class="todo-list">{''.join(todo_items)}</ul></div>
  </section>"""

    tool_cards = "".join(
        f"""<a class="tool-card" href="{U('/tools/' + t['slug'] + '/')}">
      <span class="tool-ico">{icon(TOOL_ICONS.get(t['slug'], ('calc',''))[0])}</span>
      <span class="tool-name">{esc(t['title'].split('（')[0])}</span>
      <span class="tool-desc">{esc(TOOL_ICONS.get(t['slug'], ('', t['desc'][:52]))[1])}</span>
      <span class="tool-tag">無料・登録不要・入力は端末内で処理</span>
    </a>"""
        for t in TOOLS
    )

    latest = "".join(article_card(a) for a in ARTICLES[:6])

    cat_cards = "".join(
        f"""<a class="card" href="{U('/' + c['slug'] + '/')}">
      <span class="card-cat">{esc(c['label'])}</span>
      <span class="card-title">{esc(c['lead'])}</span>
      <span class="card-date">{len([a for a in ARTICLES if a['category'] == c['slug']])}記事</span></a>"""
        for c in SITE["categories"]
    )

    trust = f"""<div class="trust">
    <div class="trust-item"><span class="trust-ico">{icon('check')}</span>
      <div><b>数字は官公庁の資料から</b><span>厚生労働省・国税庁・協会けんぽ・デジタル庁。
        各ページの下に出典へのリンクを置いています。</span></div></div>
    <div class="trust-item"><span class="trust-ico">{icon('clock')}</span>
      <div><b>制度が変わったら書き換えます</b><span>日付だけ新しくして中身を変えない、
        ということはしません。</span></div></div>
    <div class="trust-item"><span class="trust-ico">{icon('shield')}</span>
      <div><b>入力した数字は送信しません</b><span>計算ツールはすべて端末の中だけで動きます。
        保存もしていません。</span></div></div>
  </div>"""

    svc_cards = "".join(
        f"""<a class="cta-card" href="{U('/service/' + s['slug'] + '/')}">
      <span class="cta-label">{esc(s['label'])}</span>
      <span class="cta-lead">{esc(s['summary'][:76])}</span>
      <span class="cta-go">相談内容を見る →</span></a>"""
        for s in SITE["services"]
    )

    body = f"""<div class="hero"><div class="wrap">
  <h1>制度は毎年変わります。<br><em>知らないまま損をしない</em>ために。</h1>
  <p class="hero-lead">宮崎・鹿児島で事業をされている方へ。最低賃金、社会保険、税金、補助金。
     「結局うちは何をすればいいのか」が分かるところまで書いています。</p>
  <div class="hero-btns">
    <a class="btn btn-primary" href="#asks">困りごとから探す</a>
    <a class="btn btn-ghost" href="{U('/tools/')}">無料で計算してみる</a>
  </div>
  <div class="hero-facts">{facts}</div>
</div></div>

<div class="page">
  <section class="sec">
    <div class="sec-head"><div><h2>お住まいの市町村から探す</h2>
      <p>地図から選ぶと、その地域の最低賃金と保険料率が出ます。</p></div>
      <a href="{U('/hojokin/list/')}">補助金の一覧 →</a></div>
    {muni_map_html()}
  </section>

  {todo}

  <section class="sec" id="asks">
    <div class="sec-head"><div><h2>こんなとき、どうすれば</h2>
      <p>専門用語は使っていません。近いものを選んでください。</p></div></div>
    <div class="asks">{asks}</div>
  </section>

  <section class="sec">
    <div class="sec-head"><div><h2>数字を入れるだけの計算ツール</h2>
      <p>登録も会員登録も不要です。そのまま使えます。</p></div>
      <a href="{U('/tools/')}">すべて見る →</a></div>
    <div class="tools-grid">{tool_cards}</div>
  </section>

  <section class="sec">
    <div class="sec-head"><div><h2>新しく書いた記事</h2></div></div>
    <div class="grid">{latest}</div>
  </section>

  <section class="sec">
    <div class="sec-head"><div><h2>分野から探す</h2></div></div>
    <div class="grid">{cat_cards}</div>
  </section>

  <section class="sec">
    {trust}
  </section>

  <section class="sec">
    <div class="svc-band">
      <h2>読むだけで終わらせたくないとき</h2>
      <p>手を動かすところまで引き受けます。相談は無料です。</p>
      <div class="cta-grid">{svc_cards}</div>
    </div>
  </section>
</div>"""

    write("/index.html", layout(SITE["name"], SITE["description"], body, "/", active="/"))
    reg("/", priority="1.0")

# ---------------------------------------------------------------- メタ

def build_meta():
    urls = "".join(
        f"<url><loc>{abs_url(p)}</loc><lastmod>{m}</lastmod><priority>{pr}</priority></url>"
        for p, m, pr in sorted(set(PAGES))
    )
    write("/sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>")

    write("/robots.txt", "User-agent: *\nAllow: /\n\nSitemap: " + BASE_URL + U("/sitemap.xml") + "\n")

    # Search Console の所有権確認ファイル。metaタグと併用しておくと、
    # どちらか一方が消えても確認状態が外れない。
    vfile = (SITE.get("verification") or {}).get("google_file")
    if vfile:
        write("/" + vfile, "google-site-verification: " + vfile + "\n")

    items = "".join(
        f"<item><title>{esc(a['title'])}</title>"
        f"<link>{abs_url('/' + a['category'] + '/' + a['slug'] + '/')}</link>"
        f"<guid>{abs_url('/' + a['category'] + '/' + a['slug'] + '/')}</guid>"
        f"<description>{esc(a['description'])}</description>"
        f"<pubDate>{datetime.datetime.strptime(a['date'], '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0900')}</pubDate>"
        "</item>"
        for a in ARTICLES[:30]
    )
    write("/feed.xml",
          '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
          f"<title>{esc(SITE['name'])}</title><link>{BASE_URL}/</link>"
          f"<description>{esc(SITE['description'])}</description><language>ja</language>"
          + items + "</channel></rss>")

    body = ('<div class="page"><h1>ページが見つかりません</h1>'
            '<p class="lede">URLが変更されたか、削除された可能性があります。</p>'
            f'<div class="grid">{"".join(article_card(a) for a in ARTICLES[:6])}</div></div>')
    write("/404.html", layout("ページが見つかりません", "お探しのページは見つかりませんでした。", body, "/404.html"))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))

    load_articles()
    build_index()
    build_categories()
    for a in ARTICLES:
        build_article(a)
    build_tools()
    build_prefs()
    build_hojokin_list()
    build_services()
    build_static()
    build_meta()

    n = sum(len(files) for _, _, files in os.walk(OUT))
    print(f"生成 {len(PAGES)} ページ／ファイル {n} 件 → {OUT}")
    print(f"  記事 {len(ARTICLES)}／ツール {len(TOOLS)}／県 {len(PREFS['prefs'])}／市町村データ {len(MUNIS)}")


if __name__ == "__main__":
    main()
