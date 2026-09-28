/* サイト共通の最小限のスクリプト。フレームワークは使わない。 */
(function () {
  "use strict";

  // モバイルのメニュー開閉
  var btn = document.querySelector(".menu-btn");
  var nav = document.getElementById("gnav");
  if (btn && nav) {
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // 計算ツール共通の土台。
  // data-tool を持つ要素の中で、入力が変わるたびに calc を呼び直す。
  window.MKN = window.MKN || {};

  window.MKN.tool = function (id, calc) {
    var root = document.getElementById(id);
    if (!root) return;
    var out = root.querySelector("[data-result]");

    function num(name, fallback) {
      var el = root.querySelector('[name="' + name + '"]');
      if (!el) return fallback === undefined ? 0 : fallback;
      var v = el.value.replace(/[,\s]/g, "");
      // 全角数字で入力されることが実際に多いので半角に寄せる
      v = v
        .replace(/[０-９]/g, function (c) {
          return String.fromCharCode(c.charCodeAt(0) - 0xfee0);
        })
        .replace(/[．]/g, ".");
      var n = parseFloat(v);
      return isFinite(n) ? n : fallback === undefined ? 0 : fallback;
    }

    function val(name) {
      var el = root.querySelector('[name="' + name + '"]');
      return el ? el.value : "";
    }

    function run() {
      var r;
      try {
        r = calc({ num: num, val: val, root: root });
      } catch (e) {
        return;
      }
      if (!r || !out) return;
      out.className = "result" + (r.tone ? " " + r.tone : "");
      var rows = (r.rows || [])
        .map(function (x) {
          return "<dt>" + x[0] + "</dt><dd>" + x[1] + "</dd>";
        })
        .join("");
      out.innerHTML =
        (r.head ? '<p class="result-head">' + r.head + "</p>" : "") +
        (r.lead ? "<p>" + r.lead + "</p>" : "") +
        (rows ? "<dl>" + rows + "</dl>" : "");
    }

    root.addEventListener("input", run);
    root.addEventListener("change", run);
    run();
  };

  window.MKN.yen = function (n) {
    return Math.round(n).toLocaleString("ja-JP") + "円";
  };
  window.MKN.yen1 = function (n) {
    return (Math.round(n * 10) / 10).toLocaleString("ja-JP") + "円";
  };
})();

/* 市町村マップ。トップページでのみ使う。 */
(function () {
  "use strict";
  window.MKN = window.MKN || {};

  window.MKN.muniMap = function (base) {
    var root = document.getElementById("muni-map");
    var raw = document.getElementById("mm-data");
    var panel = document.getElementById("mm-panel");
    if (!root || !raw || !panel) return;

    var DATA;
    try {
      DATA = JSON.parse(raw.textContent);
    } catch (e) {
      return;
    }

    var selected = null;
    var HINT = panel.innerHTML;

    function hint() {
      panel.innerHTML = HINT;
    }

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function render(name) {
      var d = DATA[name];
      if (!d) return;
      panel.innerHTML =
        '<p class="mm-pref">' + esc(d.pref) + "</p>" +
        '<h3 class="mm-name">' + esc(name) + "</h3>" +
        '<dl class="mm-dl">' +
        "<dt>最低賃金</dt><dd>" + d.mw.toLocaleString("ja-JP") + "円" +
          '<span class="mm-sub">' + esc(d.mwDate) + "〜／現在 " +
          d.mwNow.toLocaleString("ja-JP") + "円</span></dd>" +
        "<dt>健康保険料率</dt><dd>" + d.kenpo + "％" +
          '<span class="mm-sub">令和8年度・協会けんぽ</span></dd>' +
        "<dt>県の独自制度</dt><dd>" + d.subsidies + "件</dd>" +
        "<dt>団体コード</dt><dd>" + esc(d.code) + "</dd>" +
        "</dl>" +
        '<div class="mm-links">' +
        '<a class="mm-go" href="' + base + d.prefSlug + '/">' +
          esc(d.pref) + "の制度まとめ</a>" +
        '<a class="mm-go" href="' + base + 'hojokin/list/">補助金の一覧</a>' +
        '<a class="mm-go mm-ext" href="' + esc(d.site) +
          '" target="_blank" rel="noopener">' + esc(name) + "の公式サイト</a>" +
        "</div>";
    }

    function select(name) {
      var path = root.querySelector('path.mm-a[data-name="' + name + '"]');
      var chip = root.querySelector('.mm-chip[data-pick="' + name + '"]');
      Array.prototype.forEach.call(root.querySelectorAll(".on"), function (e) {
        e.classList.remove("on");
      });
      if (path) path.classList.add("on");
      if (chip) chip.classList.add("on");
      selected = name;
      render(name);
    }

    root.addEventListener("click", function (e) {
      var chip = e.target.closest(".mm-chip");
      if (chip) {
        select(chip.getAttribute("data-pick"));
        return;
      }
      var el = e.target.closest("path.mm-a");
      if (el) select(el.getAttribute("data-name"));
    });

    root.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var el = e.target.closest("path.mm-a");
      if (!el) return;
      e.preventDefault();
      select(el.getAttribute("data-name"));
    });

    // ホバーだけでも中身が出たほうが速い。選択中はそのまま残す。
    root.addEventListener("mouseover", function (e) {
      var el = e.target.closest("path.mm-a");
      if (el && !selected) render(el.getAttribute("data-name"));
    });

    root.addEventListener("mouseout", function (e) {
      if (selected) return;
      if (e.target.closest("path.mm-a")) hint();
    });
  };
})();
