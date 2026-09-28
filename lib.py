#!/usr/bin/env python3
"""共通ユーティリティ・Markdownレンダラ・HTMLレイアウト。

Python 標準ライブラリのみで動く。外部依存を足さないこと
（kyushu-hojokin と同じ方針。CI が軽く、壊れる箇所が減る）。
"""
import datetime
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "site")
# GitHub Pages のプロジェクトページに置く場合は MKN_BASE=/リポジトリ名 を渡す
BASE = os.environ.get("MKN_BASE", "").rstrip("/")
BASE_URL = os.environ.get("MKN_BASE_URL", "https://minamikyushu-navi.example").rstrip("/")
TODAY = datetime.date.today()

WAREKI_BASE = 2018  # 令和1年 = 2019年


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


SITE = load("site.json")
PREFS = load("prefs.json")
MUNIS = load("municipalities.json")


def esc(s):
    return html.escape(s or "", quote=True)


def U(path=""):
    """サイト内パスを BASE 付きの絶対パスに直す。"""
    path = path.lstrip("/")
    return f"{BASE}/{path}" if path else (BASE + "/")


def abs_url(path=""):
    return BASE_URL + U(path)


def wareki(d):
    """ISO 日付 → 「令和8年10月24日」。和暦は検索需要があるので必ず併記する。"""
    y, m, day = (int(x) for x in d.split("-"))
    return f"令和{y - WAREKI_BASE}年{m}月{day}日"


def jp_date(d):
    y, m, day = (int(x) for x in d.split("-"))
    return f"{y}年{m}月{day}日"


def yen(n):
    return f"{n:,}円"


def write(path, content):
    full = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------- Markdown

_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_INTERNAL = re.compile(r"^/")


def inline(t):
    """インライン記法。エスケープしてから置換するので順序を変えないこと。"""
    t = esc(t)
    t = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)

    def link(m):
        label, href = m.group(1), m.group(2)
        if _INTERNAL.match(href):
            return f'<a href="{U(href)}">{label}</a>'
        return f'<a href="{href}" target="_blank" rel="noopener">{label}</a>'

    t = _LINK.sub(link, t)
    t = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", t)
    return t


def heading_id(text, used):
    base = re.sub(r"[^\w぀-ヿ一-鿿-]+", "-", text).strip("-")[:40] or "s"
    hid, n = base, 2
    while hid in used:
        hid, n = f"{base}-{n}", n + 1
    used.add(hid)
    return hid


def markdown(src, hooks=None):
    """使う記法だけに絞った Markdown。返り値は (html, 見出し一覧)。

    対応: ## / ### 見出し、箇条書き、番号付き、表、引用、:::callout、
          {{hook}} による埋め込み（ツール・CTA など）。
    """
    hooks = hooks or {}
    lines = src.split("\n")
    out, toc, used = [], [], set()
    i, n = 0, len(lines)

    def flush_para(buf):
        if buf:
            out.append("<p>" + inline(" ".join(buf)) + "</p>")
            buf.clear()

    para = []
    while i < n:
        ln = lines[i]
        s = ln.strip()

        if not s:
            flush_para(para)
            i += 1
            continue

        m = re.match(r"^\{\{([a-z0-9_:-]+)\}\}$", s)
        if m:
            flush_para(para)
            key = m.group(1)
            if key in hooks:
                out.append(hooks[key])
            i += 1
            continue

        m = re.match(r"^(#{2,4})\s+(.*)$", s)
        if m:
            flush_para(para)
            level, text = len(m.group(1)), m.group(2).strip()
            hid = heading_id(text, used)
            if level == 2:
                toc.append((hid, text))
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
            i += 1
            continue

        if s.startswith(":::"):
            flush_para(para)
            kind = s[3:].strip() or "note"
            body = []
            i += 1
            while i < n and not lines[i].strip().startswith(":::"):
                body.append(lines[i])
                i += 1
            i += 1
            inner, _ = markdown("\n".join(body), hooks)
            out.append(f'<aside class="callout callout-{esc(kind)}">{inner}</aside>')
            continue

        if s.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            flush_para(para)
            head = [c.strip() for c in s.strip("|").split("|")]
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tr = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in body
            )
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead>'
                f"<tbody>{tr}</tbody></table></div>"
            )
            continue

        if re.match(r"^[-*]\s+", s):
            flush_para(para)
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", s):
            flush_para(para)
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        if s.startswith(">"):
            flush_para(para)
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote><p>" + inline(" ".join(quote)) + "</p></blockquote>")
            continue

        para.append(s)
        i += 1

    flush_para(para)
    return "\n".join(out), toc


def frontmatter(path):
    """--- で囲んだ JSON 風ヘッダ + 本文。YAML パーサを入れたくないので JSON にしている。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if not raw.startswith("---"):
        return {}, raw
    _, head, body = raw.split("---", 2)
    return json.loads(head), body.strip()


# ---------------------------------------------------------------- レイアウト

NAV = [("/", "ホーム")] + [(f"/{c['slug']}/", c["label"]) for c in SITE["categories"]]
PREF_NAV = [(f"/{v['slug']}/", k) for k, v in PREFS["prefs"].items()]


def org_schema():
    """運営法人。住所・電話は未設定なら出さない（空の項目を出すと逆効果になる）。"""
    o = SITE["org"]
    d = {
        "@type": "Organization",
        "@id": abs_url("#org"),
        "name": o["name"],
        "alternateName": o.get("name_en") or None,
        "url": BASE_URL + "/",
        "sameAs": [o["url"]] if o.get("url") else None,
        "email": o.get("email") or None,
        "foundingDate": o.get("founded") or None,
        "description": o.get("business") or None,
        "areaServed": [{"@type": "AdministrativeArea", "name": a} for a in SITE["area"]],
    }
    if o.get("ceo"):
        d["founder"] = {"@type": "Person", "name": o["ceo"]}
    if o.get("tel"):
        d["telephone"] = o["tel"]
    addrs = []
    for off in o.get("offices", []):
        if not off.get("city"):
            continue
        a = {"@type": "PostalAddress", "addressCountry": "JP",
             "addressRegion": off["pref"], "addressLocality": off["city"]}
        if off.get("street"):
            a["streetAddress"] = off["street"]
        if off.get("zip"):
            a["postalCode"] = off["zip"]
        addrs.append(a)
    if addrs:
        d["address"] = addrs[0] if len(addrs) == 1 else addrs
    return {k: v for k, v in d.items() if v is not None}


def author_schema():
    """執筆主体。監修者が決まるまでの間も、書き手を名指しできるようにする。"""
    a = SITE.get("author") or {}
    if not a.get("enabled"):
        return None
    return {
        "@type": "Organization",
        "@id": abs_url("#author"),
        "name": a["name"],
        "parentOrganization": {"@id": abs_url("#org")},
    }


def person_schema():
    """監修者。有効化されるまで出さない（空の肩書きを出すと逆効果になる）。"""
    s = SITE["supervisor"]
    if not s.get("enabled"):
        return None
    return {
        "@type": "Person",
        "@id": abs_url("#supervisor"),
        "name": s["name"],
        "jobTitle": s["title"],
        "worksFor": {"@id": abs_url("#org")},
    }


def jsonld(*nodes):
    graph = [n for n in nodes if n]
    doc = {"@context": "https://schema.org", "@graph": graph}
    return (
        '<script type="application/ld+json">'
        + json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
    )


def breadcrumb(trail):
    """trail = [(パス, ラベル), ...] 末尾が現在地。"""
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": label,
            "item": abs_url(path),
        }
        for i, (path, label) in enumerate(trail)
    ]
    return {"@type": "BreadcrumbList", "itemListElement": items}


def crumb_html(trail):
    parts = []
    for i, (path, label) in enumerate(trail):
        last = i == len(trail) - 1
        parts.append(
            f'<span aria-current="page">{esc(label)}</span>'
            if last
            else f'<a href="{U(path)}">{esc(label)}</a>'
        )
    return '<nav class="crumb" aria-label="パンくず">' + '<span class="sep">›</span>'.join(parts) + "</nav>"


def supervisor_box():
    """記事末に出す「誰が書き、誰が見ているか」。

    監修者が未設定でも、執筆体制と責任者は出す。ここを空にすると
    競合と同じ匿名運営になり、税金・お金の分野では評価されない。
    """
    sv, au, o = SITE["supervisor"], SITE.get("author") or {}, SITE["org"]
    blocks = []

    if sv.get("enabled") and sv.get("name"):
        photo = (
            f'<img src="{U(sv["photo"])}" alt="{esc(sv["name"])}" width="76" height="76" loading="lazy">'
            if sv.get("photo") else '<div class="sv-photo-ph" aria-hidden="true"></div>'
        )
        reg = f'<p class="sv-reg">登録番号 {esc(sv["registration"])}／{esc(sv["office"])}</p>' if sv.get("registration") else ""
        blocks.append(f"""<aside class="supervisor">
  {photo}
  <div>
    <p class="sv-role">この記事の監修</p>
    <p class="sv-name">{esc(sv["name"])}<span class="sv-title">{esc(sv["title"])}</span></p>
    <p class="sv-bio">{esc(sv.get("bio", ""))}</p>
    {reg}
  </div>
</aside>""")

    if au.get("enabled"):
        blocks.append(f"""<aside class="supervisor">
  <div class="sv-photo-ph" aria-hidden="true"></div>
  <div>
    <p class="sv-role">この記事を書いた人</p>
    <p class="sv-name">{esc(au["name"])}<span class="sv-title">{esc(o["name"])}</span></p>
    <p class="sv-bio">{esc(au.get("note", ""))}</p>
    <p class="sv-reg">編集責任者：{esc(au.get("responsible", ""))}／
      <a href="{U('/about/')}">運営者情報</a>・<a href="{U('/policy/')}">編集方針</a></p>
  </div>
</aside>""")

    return "".join(blocks)


def service_cta(slug=None, compact=False):
    """記事末とサイドに置く導線。競合はここが丸ごと無い。"""
    svcs = SITE["services"]
    if slug:
        svcs = [s for s in svcs if s["slug"] == slug] or svcs
    cards = "".join(
        f"""<a class="cta-card" href="{U('/service/' + s['slug'] + '/')}">
      <span class="cta-label">{esc(s['label'])}</span>
      <span class="cta-lead">{esc(s['lead'])}</span>
      <span class="cta-go">相談内容を見る →</span>
    </a>"""
        for s in svcs
    )
    cls = "cta cta-compact" if compact else "cta"
    head = "" if compact else '<p class="cta-head">読むだけで終わらせない</p>'
    return f'<section class="{cls}">{head}<div class="cta-grid">{cards}</div></section>'


def _navlink(path, label, active):
    on = ' class="on"' if path == active else ""
    return f'<a href="{U(path)}"{on}>{esc(label)}</a>'


def header_html(active=""):
    links = "".join(_navlink(p, l, active) for p, l in NAV)
    prefs = "".join(_navlink(p, l, active) for p, l in PREF_NAV)
    return f"""<a class="skip" href="#main">本文へ</a>
<header class="site-head">
  <div class="wrap head-row">
    <a class="brand" href="{U('/')}">
      <span class="brand-mark" aria-hidden="true">南</span>
      <span class="brand-text"><b>{esc(SITE['name'])}</b><i>{esc(SITE['tagline'])}</i></span>
    </a>
    <button class="menu-btn" aria-expanded="false" aria-controls="gnav">メニュー</button>
  </div>
  <nav id="gnav" class="gnav" aria-label="サイト内">
    <div class="wrap gnav-row">{links}</div>
    <div class="wrap gnav-row gnav-pref"><span class="gnav-cap">地域別</span>{prefs}</div>
  </nav>
</header>"""


def footer_html():
    o = SITE["org"]
    cats = "".join(f'<li><a href="{U("/" + c["slug"] + "/")}">{esc(c["label"])}</a></li>' for c in SITE["categories"])
    svcs = "".join(f'<li><a href="{U("/service/" + s["slug"] + "/")}">{esc(s["label"])}</a></li>' for s in SITE["services"])
    prefs = "".join(f'<li><a href="{U(p)}">{esc(l)}</a></li>' for p, l in PREF_NAV)
    return f"""<footer class="site-foot">
  <div class="wrap foot-grid">
    <div class="foot-col">
      <p class="foot-h">カテゴリ</p><ul>{cats}</ul>
    </div>
    <div class="foot-col">
      <p class="foot-h">地域から探す</p><ul>{prefs}
        <li><a href="{U('/tools/')}">計算ツール</a></li>
        <li><a href="{U('/hojokin/list/')}">補助金一覧</a></li>
      </ul>
    </div>
    <div class="foot-col">
      <p class="foot-h">サービス</p><ul>{svcs}</ul>
    </div>
    <div class="foot-col">
      <p class="foot-h">サイトについて</p>
      <ul>
        <li><a href="{U('/about/')}">運営者情報</a></li>
        <li><a href="{U('/policy/')}">編集方針</a></li>
        <li><a href="{U('/privacy/')}">プライバシーポリシー</a></li>
        <li><a href="{U('/contact/')}">お問い合わせ</a></li>
      </ul>
    </div>
  </div>
  <div class="wrap foot-end">
    <p>{esc(o['name'])}</p>
    <p class="copy">© {TODAY.year} {esc(SITE['name'])}</p>
  </div>
</footer>"""


def verification_tags():
    """Search Console 等の所有権確認タグ。data/site.json に値を入れると出力される。"""
    v = SITE.get("verification") or {}
    out = []
    if v.get("google"):
        out.append(f'<meta name="google-site-verification" content="{esc(v["google"])}">')
    if v.get("bing"):
        out.append(f'<meta name="msvalidate.01" content="{esc(v["bing"])}">')
    return "\n".join(out)


def layout(title, desc, body, path="/", schema=None, active="", crumbs=None, css_extra="", js=""):
    full_title = title if title == SITE["name"] else f"{title}｜{SITE['name']}"
    nodes = [
        org_schema(),
        author_schema(),
        person_schema(),
        {
            "@type": "WebSite",
            "@id": abs_url("#website"),
            "url": BASE_URL + "/",
            "name": SITE["name"],
            "publisher": {"@id": abs_url("#org")},
            "inLanguage": "ja",
        },
    ]
    if crumbs:
        nodes.append(breadcrumb(crumbs))
    if schema:
        nodes.append(schema)
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{abs_url(path)}">
<meta property="og:type" content="{'article' if crumbs and len(crumbs) > 2 else 'website'}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{abs_url(path)}">
<meta property="og:site_name" content="{esc(SITE['name'])}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap">
<link rel="stylesheet" href="{U('/assets/style.css')}">
{verification_tags()}
<link rel="alternate" type="application/rss+xml" title="{esc(SITE['name'])}" href="{U('/feed.xml')}">
{css_extra}
{jsonld(*nodes)}
</head>
<body>
{header_html(active)}
<main id="main">
{crumb_html(crumbs) if crumbs else ''}
{body}
</main>
{footer_html()}
<script src="{U('/assets/app.js')}" defer></script>
{js}
</body>
</html>"""
