/* Palmarès Savate — the archive as a site.
 *
 * Three rules run through everything below.
 *
 *   Rouge and bleu are CORNERS. The red corner is whoever the document named
 *   first, which is why red "wins" 53.5% of this archive. Nothing here may
 *   colour a result with them. Victory is --vert, and mostly it is ink weight.
 *
 *   A gap is never a zero. Unpublished warnings arrive as -1, unpublished
 *   points as "", an unknown winner as -1, and each renders as la croix with a
 *   numbered note. A croix over one field never erases another: a bout whose
 *   method was not published still names its winner.
 *
 *   The poule tables are not computed here. `export_ui.py` ran them through
 *   savate/rules.py, the same function the tests check against the
 *   federation's printed sheets, and shipped the standings with the rung that
 *   separated each pair. This file draws them; it does not re-decide them.
 */
(function () {
  "use strict";

  var D = window.SAVATE;
  if (!D) return;

  /* Where a data subject writes to consult, correct or erase their data.
     One constant so the address lives in one place; the notice links to it. */
  var CONTACT_EMAIL = "archivist@palmares-savate.example";

  var EVENTS = D.events, PEOPLE = D.people, BOUTS = D.bouts, POULES = D.poules,
      PLACINGS = D.placings, CATS = D.categories, DECS = D.decisions,
      PHASES = D.phases, NATIONS = D.nations, CLUBS = D.clubs;

  /* -- event columns ----------------------------------------------- */
  var E_NAME = 0, E_YEAR = 1, E_LEVEL = 2, E_DISC = 3, E_START = 4, E_END = 5,
      E_CITY = 6, E_NAT = 7, E_SLUG = 8, E_FORMAT = 9, E_AGE = 10, E_LABEL = 11,
      E_SOURCE = 12;

  /* The archive's span, computed from the data rather than printed: the footer
     and the event index quote it, and a hardcoded "2007–2026" goes stale the
     day a new sheet lands. The data is static for the life of the page, so
     this runs once. */
  var YEARS = EVENTS.map(function (e) { return e[E_YEAR]; })
    .filter(function (y) { return y; }).sort();
  var YEAR_SPAN = YEARS.length ? YEARS[0] + "–" + YEARS[YEARS.length - 1] : "";
  var YEAR_FIRST = YEARS.length ? YEARS[0] : "";
  var YEAR_LAST = YEARS.length ? YEARS[YEARS.length - 1] : "";
  /* The figures the notice quotes. They live in the export's report and the
     text only quotes them, so a new wave can never leave the notice stale. */
  var REPORT = D.report || {};
  /* -- person columns ---------------------------------------------- */
  var P_NAME = 0, P_NATS = 1, P_ALIAS = 2, P_CLUB = 3, P_KEY = 4, P_ID = 5,
      P_WEIGHED = 6;
  /* -- bout columns ------------------------------------------------- */
  var B_EV = 0, B_RED = 1, B_BLUE = 2, B_RP = 3, B_BP = 4, B_RW = 5, B_BW = 6,
      B_WIN = 7, B_DEC = 8, B_PHASE = 9, B_POULE = 10, B_CAT = 11, B_DATE = 12,
      B_TIME = 13, B_RING = 14, B_RNAT = 15, B_BNAT = 16,
      // Some sources name the winner without publishing a corner.
      B_WINNER = 17, B_DETAIL = 18;
  /* -- poule columns ------------------------------------------------ */
  var Q_EV = 0, Q_CAT = 1, Q_LETTER = 2, Q_LINES = 3, Q_UNRESOLVED = 4, Q_DONE = 5;
  /* -- placing columns ---------------------------------------------- */
  var L_EV = 0, L_WHO = 1, L_RANK = 2, L_CAT = 3, L_NAT = 4;
  /* -- category columns --------------------------------------------- */
  var C_LABEL = 0, C_GENDER = 1, C_AGE = 2, C_KG = 3, C_WEIGHT = 4;

  function read(k, fallback) {
    try { var v = localStorage.getItem(k); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function write(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  /* ================================================================
     Language. The archive is francophone at its root, anglophone in its
     international paperwork and hispanophone across the Panamerican
     federations, so the interface speaks all three. The reader's own browser
     chooses first; their explicit choice wins and is remembered.
     ================================================================ */

  var STR = window.SAVATE_I18N || {};
  var LANGS = ["fr", "en", "es"];
  var LANG = (function () {
    var saved = read("savate.lang", "");
    if (STR[saved]) return saved;
    var want = String((navigator && navigator.language) || "fr")
      .slice(0, 2).toLowerCase();
    return STR[want] ? want : "fr";
  })();

  /* Values are substituted, never concatenated: word order is exactly what
     differs between these three languages. */
  function t(key, vars) {
    var table = STR[LANG] || {};
    var text = table[key];
    if (text == null) text = (STR.fr || {})[key];
    if (text == null) return key;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        text = text.split("{" + k + "}").join(vars[k]);
      });
    }
    return text;
  }
  function setLang(next) {
    if (!STR[next]) return;
    LANG = next;
    write("savate.lang", next);
    document.documentElement.setAttribute("lang", next);
    boot();
    render();
  }



  /* ================================================================
     Vocabulary. The sport's operational French, not a translation of
     database column names.
     ================================================================ */

  /* The sport's own vocabulary, in whichever language the reader has chosen.
     "Assaut" and "combat" are never translated: they are the names of two
     disciplines, and rendering assaut as "light contact" would name a
     different sport's rule set. */
  function phaseFR(p) { return p ? t("phase." + p) : ""; }
  function phaseShort(p) { return p ? t("phaseShort." + p) : ""; }
  function decFR(d) { return d ? t("dec." + d) : ""; }
  function genderFR(g) { return g ? t("gender." + g) : ""; }
  function ageFR(a) { return a ? t("age." + a) : ""; }
  function rankFR(r) { return t("rank." + r); }

  /* The kinds of thing one query can turn up, in the order they are offered. */
  var ORDER_KINDS = ["tireur", "epreuve", "annee", "nation", "categorie"];
  function kindFR(k) { return t("search." + k); }
  var RANK_SHORT = ["", "1ᵉʳ", "2ᵉ", "3ᵉ"];

  /* The eleven things the archive can fail to know. Each is a numbered note
     rendered once per page, however many crosses point at it. */
  /* The things the archive can fail to know. Each is a numbered note rendered
     once per page, however many crosses point at it. */
  var NOTE_KEYS = ["pays", "podiums", "departage", "methode", "horaire",
                   "avert", "points", "vainqueur", "graphie", "genre",
                   "club", "pesee", "categorie", "discipline", "age", "annee",
                   "coin"];
  function noteText(key) { return t("note." + key); }


  /* ================================================================
     Small helpers
     ================================================================ */

  /* Who won, whether or not the document said which corner they stood in.
     Returns a person index, or -1 where nobody was named. */
  function winnerOf(b) {
    if (b[B_WIN] === 0) return b[B_RED];
    if (b[B_WIN] === 1) return b[B_BLUE];
    return b.length > B_WINNER && b[B_WINNER] >= 0 ? b[B_WINNER] : -1;
  }
  function cornersKnown(b) { return b[B_WIN] === 0 || b[B_WIN] === 1; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fold(s) {
    return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLowerCase().replace(/\s+/g, " ").trim();
  }
  function slug(s) {
    return fold(s).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }
  function num(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
  function pct(a, b) { return b ? Math.round((100 * a) / b) : 0; }
  /* One decimal place, with the separator the language prints. */
  function pctOne(n) {
    if (n == null) return "";
    var s = Number(n).toFixed(1);
    return LANG === "en" ? s : s.replace(".", ",");
  }

  /* Minus sign, not hyphen: "−80 kg" is a weight class, "-80" is arithmetic. */
  function weightFR(label) { return String(label || "").replace(/^-/, "−"); }

  function catFR(i) {
    var c = CATS[i];
    if (!c) return "";
    var parts = [];
    if (c[C_AGE]) parts.push(ageFR(c[C_AGE]) || c[C_AGE].toLowerCase());
    if (c[C_GENDER]) parts.push(genderFR(c[C_GENDER]) || c[C_GENDER].toLowerCase());
    var head = parts.join(" ");
    if (head) head = head.charAt(0).toUpperCase() + head.slice(1);
    var w = weightFR(c[C_WEIGHT]);
    if (head && w) return head + " · " + w;
    return head || w || c[C_LABEL];
  }
  function catShort(i) {
    var c = CATS[i];
    return c ? (weightFR(c[C_WEIGHT]) || c[C_LABEL]) : "";
  }

  function natHTML(i, opts) {
    opts = opts || {};
    if (i == null || i < 0) {
      return opts.bare ? "" : '<span class="nat">' + croix("pays") + "</span>";
    }
    var n = NATIONS[i];
    if (!n) return "";
    var flag = n[2] ? flagOf(n[2]) : "";
    var out = '<span class="nat">';
    if (flag) out += '<span class="flag">' + flag + "</span>";
    if (n[1]) out += '<span class="code">' + esc(n[1]) + "</span>";
    else if (!n[3]) out += croix("graphie");
    if (opts.name !== false) {
      out += '<span class="name">' + esc(nationName(nation[i])) + "</span>";
    }
    return out + "</span>";
  }
  function flagOf(iso) {
    if (!iso || iso.length !== 2) return "";
    return String.fromCodePoint(0x1f1e6 + iso.charCodeAt(0) - 65) +
           String.fromCodePoint(0x1f1e6 + iso.charCodeAt(1) - 65);
  }

  /* -- la croix ------------------------------------------------------
     One glyph, one meaning: the archive does not know. Collected per render
     so the page ends with exactly the notes it used, numbered in order. */
  var usedNotes = [];
  function croix(key) {
    var at = usedNotes.indexOf(key);
    if (at < 0) { usedNotes.push(key); at = usedNotes.length - 1; }
    return '<button class="croix" data-note="' + esc(key) + '" title="' +
      esc(noteText(key)) + '" aria-label="' + esc(noteText(key)) +
      '"></button><sup class="fig" style="font-size:10px;color:var(--ink-3)">' +
      (at + 1) + "</sup>";
  }
  function notesHTML() {
    if (!usedNotes.length) return "";
    var items = usedNotes.map(function (k) {
      return '<li id="note-' + esc(k) + '">' + esc(noteText(k)) + "</li>";
    }).join("");
    return '<div class="notes"><div class="micro">' + esc(t("note.title")) + "</div>" +
      "<ol>" + items + "</ol></div>";
  }

  /* -- avertissements ------------------------------------------------
     Three avertissements is a disqualification, not a running penalty, so the
     third stroke is rouge. Struck strokes read well in a bulletin and turn
     into "//" in a 38px poule cell, where a figure is clearer - so density
     picks the notation, and the meaning stays the same either way. */
  function avertHTML(n, dense) {
    if (n == null || n < 0) return '<span class="avert none">' + croix("avert") + "</span>";
    if (dense) {
      if (n === 0) return '<span class="avert none">0</span>';
      return '<span class="fig"' + (n >= 3 ? ' style="color:var(--rouge);font-weight:600"' : "") +
        ' title="' + n + ' avertissement' + (n > 1 ? "s" : "") +
        (n >= 3 ? " \u2014 disqualification" : "") + '">' + n + "</span>";
    }
    if (n === 0) return '<span class="avert none">0</span>';
    var out = '<span class="avert" title="' + n + ' avertissement' +
      (n > 1 ? "s" : "") + (n >= 3 ? " \u2014 disqualification" : "") + '">';
    for (var i = 0; i < n; i++) {
      out += '<i' + (i === 2 ? ' class="third"' : "") + "></i>";
    }
    return out + "</span>";
  }

  function recordHTML(w, l) {
    return '<span class="record"><span class="w">' + w + '</span>' +
      '<span class="sep">–</span><span class="l">' + l + "</span></span>";
  }
  function medalsHTML(or, ar, br) {
    var out = "";
    if (or) out += '<span class="med or"><i></i>' + or + "</span>";
    if (ar) out += '<span class="med ar"><i></i>' + ar + "</span>";
    if (br) out += '<span class="med br"><i></i>' + br + "</span>";
    return out ? '<span class="medals">' + out + "</span>" : "";
  }

  function dateFR(iso, time) {
    if (!iso) return "";
    var months = ["janv.", "févr.", "mars", "avril", "mai", "juin", "juil.",
                  "août", "sept.", "oct.", "nov.", "déc."];
    var p = iso.split("-");
    if (p.length !== 3) return iso;
    var out = (+p[2]) + " " + (months[+p[1] - 1] || "") + " " + p[0];
    if (time) out += " · " + time.replace(":", " h ");
    return out;
  }

  /* ================================================================
     Derived indices. Built once; everything else reads them.
     ================================================================ */

  var person = PEOPLE.map(function (p, i) {
    return {
      i: i, id: p[P_ID], name: p[P_NAME], key: p[P_KEY],
      slug: slug(p[P_ID]) || "t" + i,
      nats: p[P_NATS] || [], aliases: p[P_ALIAS] || [],
      club: p[P_CLUB] >= 0 ? CLUBS[p[P_CLUB]] : "",
      weighed: p[P_WEIGHED] || [],
      bouts: [], places: [], w: 0, l: 0, or: 0, ar: 0, br: 0,
      years: [], events: {}
    };
  });
  var personBySlug = {};
  person.forEach(function (p) { personBySlug[p.slug] = p; });

  var event = EVENTS.map(function (e, i) {
    return {
      i: i, slug: e[E_SLUG], name: e[E_NAME], year: e[E_YEAR],
      level: e[E_LEVEL], format: e[E_FORMAT], label: e[E_LABEL],
      disc: e[E_DISC], age: e[E_AGE], city: e[E_CITY], nat: e[E_NAT],
      start: e[E_START], end: e[E_END], source: e[E_SOURCE] || "",
      bouts: [], places: [], poules: [], cats: {}
    };
  });
  var eventBySlug = {};
  event.forEach(function (e) { eventBySlug[e.slug] = e; });

  BOUTS.forEach(function (b, i) {
    var e = event[b[B_EV]];
    if (e) { e.bouts.push(i); e.cats[b[B_CAT]] = 1; }
    [b[B_RED], b[B_BLUE]].forEach(function (x) {
      var p = person[x];
      if (!p) return;
      p.bouts.push(i);
      p.events[b[B_EV]] = 1;
    });
    var won = winnerOf(b);
    if (won >= 0) {
      var lost = won === b[B_RED] ? b[B_BLUE] : b[B_RED];
      if (person[won]) person[won].w++;
      if (person[lost]) person[lost].l++;
    }
  });
  PLACINGS.forEach(function (l, i) {
    var e = event[l[L_EV]], p = person[l[L_WHO]];
    if (e) { e.places.push(i); e.cats[l[L_CAT]] = 1; }
    if (p) {
      p.places.push(i);
      p.events[l[L_EV]] = 1;
      if (l[L_RANK] === 1) p.or++;
      else if (l[L_RANK] === 2) p.ar++;
      else if (l[L_RANK] === 3) p.br++;
    }
  });
  POULES.forEach(function (q, i) {
    var e = event[q[Q_EV]];
    if (e) e.poules.push(i);
  });
  person.forEach(function (p) {
    var ys = {};
    Object.keys(p.events).forEach(function (k) {
      var e = event[k]; if (e && e.year) ys[e.year] = 1;
    });
    p.years = Object.keys(ys).sort();
    p.medals = p.or + p.ar + p.br;
  });

  /* Bouts of one poule, by (event, category, letter). */
  var pouleBouts = {};
  BOUTS.forEach(function (b, i) {
    if (PHASES[b[B_PHASE]] !== "poule") return;
    var k = b[B_EV] + "|" + b[B_CAT] + "|" + (b[B_POULE] || "");
    (pouleBouts[k] = pouleBouts[k] || []).push(i);
  });
  function pouleKey(q) { return q[Q_EV] + "|" + q[Q_CAT] + "|" + (q[Q_LETTER] || ""); }

  /* Nations: counted from resolved nations only. An unresolved graphie is
     shown wherever it was printed and never given a row in a ranking. */
  var nation = NATIONS.map(function (n, i) {
    return {
      i: i, code: n[1], iso: n[2], known: !!n[3],
      // The three display names, and every attested spelling for searching.
      names: { en: n[0], fr: n[4] || n[0], es: n[5] || n[0] },
      search: n[6] || fold(n[0]),
      // The slug stays English so a link keeps working in any language.
      slug: slug(n[0]) || "n" + i,
      or: 0, ar: 0, br: 0, people: {}, bouts: 0, wins: 0, years: {}
    };
  });
  var nationBySlug = {};
  nation.forEach(function (n) { if (n.known) nationBySlug[n.slug] = n; });

  function nationName(n) {
    return (n && n.names && (n.names[LANG] || n.names.fr || n.names.en)) || "";
  }

  PLACINGS.forEach(function (l) {
    var n = nation[l[L_NAT]]; if (!n) return;
    if (l[L_RANK] === 1) n.or++; else if (l[L_RANK] === 2) n.ar++;
    else if (l[L_RANK] === 3) n.br++;
    n.people[l[L_WHO]] = 1;
    var e = event[l[L_EV]]; if (e && e.year) n.years[e.year] = 1;
  });
  BOUTS.forEach(function (b) {
    [[b[B_RNAT], b[B_RED], 0], [b[B_BNAT], b[B_BLUE], 1]].forEach(function (x) {
      var n = nation[x[0]]; if (!n) return;
      n.bouts++; n.people[x[1]] = 1;
      if (b[B_WIN] === x[2]) n.wins++;
      var e = event[b[B_EV]]; if (e && e.year) n.years[e.year] = 1;
    });
  });
  nation.forEach(function (n) {
    n.medals = n.or + n.ar + n.br;
    n.tireurs = Object.keys(n.people).length;
    var ys = Object.keys(n.years).sort();
    n.first = ys[0] || ""; n.last = ys[ys.length - 1] || "";
  });

  /* Weight classes, as a competitor names them, across every year. */
  var klass = {}, klasses = [];
  CATS.forEach(function (c, i) {
    if (!c[C_WEIGHT]) return;
    var key = slug((c[C_GENDER] || "x") + "-" + (c[C_AGE] || "x") + "-" + c[C_WEIGHT]);
    if (!klass[key]) {
      klass[key] = {
        key: key, gender: c[C_GENDER], age: c[C_AGE], weight: c[C_WEIGHT],
        // Resolved at render time, not at load: the reader can change
        // language and every label has to follow.
        first: i, cats: [], champs: [], bouts: 0
      };
      klasses.push(klass[key]);
    }
    klass[key].cats.push(i);
  });
  function klassLabel(k) { return catFR(k.first); }

  var catToKlass = {};
  klasses.forEach(function (k) {
    k.cats.forEach(function (c) { catToKlass[c] = k; });
  });
  PLACINGS.forEach(function (l, i) {
    var k = catToKlass[l[L_CAT]];
    if (k && l[L_RANK] === 1) k.champs.push(i);
  });
  BOUTS.forEach(function (b) {
    var k = catToKlass[b[B_CAT]]; if (k) k.bouts++;
  });
  klasses.sort(function (a, b) {
    return (a.gender || "").localeCompare(b.gender || "") ||
      (a.age || "").localeCompare(b.age || "") ||
      (parseFloat(a.weight.replace(/[^\d.]/g, "")) || 0) -
      (parseFloat(b.weight.replace(/[^\d.]/g, "")) || 0);
  });

  var years = {};
  event.forEach(function (e) { if (e.year) years[e.year] = (years[e.year] || 0) + 1; });
  var yearList = Object.keys(years).sort();

  /* ================================================================
     Stored preferences. Every read and write is guarded: an artifact can
     be opened where storage throws outright.
     ================================================================ */

  var titulaire = (function () {
    var v = read("savate.titulaire", null);
    if (v === "aucun") return null;
    var p = v && personBySlug[v];
    if (p) return p;
    return person[D.owner] || null;
  })();
  function setTitulaire(p) {
    titulaire = p;
    write("savate.titulaire", p ? p.slug : "aucun");
  }

  var pinned = (function () {
    var raw = read("savate.epingles", "");
    var out = {};
    raw.split(",").forEach(function (s) { if (s) out[s] = 1; });
    return out;
  })();
  function togglePin(s) {
    if (pinned[s]) delete pinned[s]; else pinned[s] = 1;
    write("savate.epingles", Object.keys(pinned).join(","));
  }

  /* ================================================================
     Layout helpers
     ================================================================ */

  function link(href, text, cls) {
    return '<a href="' + esc(href) + '"' + (cls ? ' class="' + cls + '"' : "") +
      ">" + text + "</a>";
  }
  function pLink(p) {
    return link("#/tireur/" + p.slug, esc(p.name), "linky");
  }
  function eLink(e) {
    return link("#/epreuve/" + e.slug, esc(e.name), "linky");
  }
  function fil(parts) {
    return '<nav class="fil" aria-label="Fil d’Ariane">' + parts.map(function (x, i) {
      return (i ? '<i>›</i>' : "") + (x.href ? link(x.href, esc(x.text)) :
        "<span>" + esc(x.text) + "</span>");
    }).join("") + "</nav>";
  }
  function head(title, sub) {
    return '<div class="pagehead"><h1>' + title + "</h1>" +
      (sub ? '<div class="sub">' + sub + "</div>" : "") + "</div>";
  }
  function section(title, body, note) {
    return '<section class="section"><div class="sectionhead"><h2 class="micro">' +
      esc(title) + "</h2>" + (note ? '<span class="note">' + note + "</span>" : "") +
      "</div>" + body + "</section>";
  }
  function empty(message) {
    return '<div class="carte"><div class="card">×&nbsp;/&nbsp;×</div><p>' +
      message + "</p></div>";
  }
  function discChip(d) {
    if (!d) return "";
    return '<span class="chip ' + esc(d) + '"><span class="dot"></span>' +
      (d === "assaut" ? "Assaut" : "Combat") + "</span>";
  }
  function eventChips(e) {
    var out = "";
    if (e.label) out += '<span class="chip">' + esc(e.label) + "</span>";
    out += discChip(e.disc);
    if (e.age) out += '<span class="chip">' + esc(ageFR(e.age) || e.age) + "</span>";
    return out;
  }

  /* ================================================================
     La feuille de poule
     ================================================================ */

  function feuille(qi, opts) {
    opts = opts || {};
    var q = POULES[qi];
    if (!q) return "";
    var lines = q[Q_LINES], ev = event[q[Q_EV]];
    var order = lines.map(function (l) { return l[0]; });
    var at = {};
    order.forEach(function (x, i) { at[x] = i; });

    /* Which corner each tireur occupied against each opponent, and who won. */
    var cell = {}, list = pouleBouts[pouleKey(q)] || [];
    list.forEach(function (bi) {
      var b = BOUTS[bi];
      cell[b[B_RED] + ":" + b[B_BLUE]] = { bout: bi, corner: "r", won: b[B_WIN] === 0, dec: DECS[b[B_DEC]] };
      cell[b[B_BLUE] + ":" + b[B_RED]] = { bout: bi, corner: "b", won: b[B_WIN] === 1, dec: DECS[b[B_DEC]] };
    });

    var tied = {};
    (q[Q_UNRESOLVED] || []).forEach(function (g) {
      g.forEach(function (x) { tied[x] = g.length; });
    });

    var thead = '<tr><th class="who">' + esc(t("poule.fighter")) + "</th>" +
      order.map(function (x, i) {
        var p = person[x];
        return '<th title="' + esc(p ? p.name : "") + '">' + (i + 1) + "</th>";
      }).join("") +
      '<th title="' + esc(t("col.record")) + '">' + esc(t("poule.wins")) + "</th>" +
      '<th title="' + esc(t("bul.points")) + '">' + esc(t("poule.points")) + "</th>" +
      '<th title="' + esc(t("d.warnings")) + '">' + esc(t("poule.warnings")) + "</th>" +
      '<th title="' + esc(t("col.place")) + '">' + esc(t("poule.rank")) + "</th></tr>";

    var body = lines.map(function (l, i) {
      var p = person[l[0]];
      var cls = [];
      if (titulaire && titulaire.i === l[0]) cls.push("moi");
      if (tied[l[0]]) cls.push("tied");
      var row = "<tr" + (cls.length ? ' class="' + cls.join(" ") + '"' : "") +
        ' data-i="' + i + '">';
      row += '<td class="who" data-j="' + i + '">' +
        (i + 1) + ". " + (p ? pLink(p) : croix("pays")) + "</td>";
      order.forEach(function (other, j) {
        if (i === j) { row += '<td class="cell self"></td>'; return; }
        var c = cell[l[0] + ":" + other];
        if (!c) { row += '<td class="cell" data-j="' + j + '"></td>'; return; }
        var mark = c.won ? '<span class="v">V</span>' : '<span class="d">D</span>';
        if (c.dec === "forfait") mark = c.won ? '<span class="v">W.O.</span>' : '<span class="d">F</span>';
        else if (c.dec === "disqualification") mark = c.won ? '<span class="v">V</span>' : '<span class="d">DQ</span>';
        row += '<td class="cell corner-' + c.corner + '" data-j="' + j +
          '" data-bout="' + c.bout + '">' + mark + "</td>";
      });
      row += '<td class="sum">' + l[3] + "</td>";
      row += '<td class="sum">' + l[1] + "</td>";
      row += '<td class="sum">' + avertHTML(l[2], true) + "</td>";
      row += '<td class="sum' + (l[5] === 1 && !tied[l[0]] ? " rg1" : "") + '">' +
        (tied[l[0]] ? "=" + l[5] : l[5]) + "</td>";
      return row + "</tr>";
    }).join("");

    /* The rungs that actually separated people in this poule. */
    var rungs = {};
    lines.forEach(function (l) { if (l[6] && l[6] !== "unresolved") rungs[l[6]] = 1; });
    var RUNG_KEY = { points: "rung.points", "head-to-head": "rung.h2h",
                     warnings: "rung.warnings", weight: "rung.weight" };
    var used = Object.keys(rungs).map(function (r) {
      return RUNG_KEY[r] ? t(RUNG_KEY[r]) : r;
    });

    var decided = list.filter(function (bi) { return BOUTS[bi][B_WIN] >= 0; }).length;
    var n = order.length, expected = (n * (n - 1)) / 2;

    var foot = '<div class="sheetfoot">';
    foot += "<div>" + t("poule.ladder") +
      (used.length ? t("poule.ladderHere", { how: used.join(", ") }) : "") + "</div>";
    foot += "<div>" + t("poule.scale") + "</div>";
    if (decided < expected) {
      foot += '<div class="bad">' +
        esc(t("poule.incomplete", { decided: decided, expected: expected })) + "</div>";
    }
    if (q[Q_UNRESOLVED] && q[Q_UNRESOLVED].length) {
      var groups = q[Q_UNRESOLVED].map(function (g) {
        return g.map(function (x) {
          return person[x] ? person[x].name : "?";
        }).join(", ");
      }).join(" ; ");
      foot += "<div>" + croix("departage") + " " +
        esc(t("poule.tied", { groups: groups })) + "</div>";
    }
    foot += '<div><button class="chip" data-copy>' + esc(t("poule.copy")) +
      "</button></div>";
    foot += "</div>";

    var title = opts.title !== false
      ? '<div class="sectionhead"><h2 class="micro">' +
        esc(t("poule.sheet", { letter: q[Q_LETTER] || t("poule.unique"),
                               cat: catFR(q[Q_CAT]) })) + "</h2>" +
        (ev ? '<span class="note">' + eLink(ev) + "</span>" : "") + "</div>"
      : "";

    return '<div class="poulewrap">' + title +
      '<div class="scroll"><table class="poule"><thead>' + thead +
      "</thead><tbody>" + body + "</tbody></table></div>" + foot + "</div>";
  }

  /* ================================================================
     Le bulletin de rencontre
     ================================================================ */

  function bulletin(bi) {
    var b = BOUTS[bi];
    if (!b) return "";
    var red = person[b[B_RED]], blue = person[b[B_BLUE]];
    var dec = DECS[b[B_DEC]], phase = PHASES[b[B_PHASE]];

    function side(p, natIdx, pts, warn, corner, isWin, isLoss) {
      var cls = "corner " + corner + (isWin ? " won" : isLoss ? " lost" : "");
      var out = '<div class="' + cls + '">';
      out += '<div class="lab">' + (corner === "n"
        ? '<span style="color:var(--ink-3)">' + esc(t("bul.cornerUnknown")) +
          "</span> " + croix("coin")
        : esc(corner === "r" ? t("bul.cornerRed") : t("bul.cornerBlue"))) + "</div>";
      out += "<h3>" + (p ? pLink(p) : croix("pays")) + "</h3>";
      out += '<div class="meta">';
      out += "<div>" + natHTML(natIdx) + "</div>";
      if (p) {
        out += "<div>" + (p.bouts.length
          ? recordHTML(p.w, p.l) + ' <span class="gapnote">' +
            esc(t("fiche.inThisArchive")) + "</span>"
          : '<span class="gapnote">' + esc(t("fiche.noBouts")) + "</span>") + "</div>";
      }
      out += '<div><span class="micro">' + esc(t("bul.warnShort")) + "</span> " +
        avertHTML(warn) + "</div>";
      return out + "</div></div>";
    }

    var out = '<div class="bulletin">';
    var champ = winnerOf(b);
    var known = cornersKnown(b);
    out += side(red, b[B_RNAT], b[B_RP], b[B_RW], known ? "r" : "n",
                champ === b[B_RED], champ >= 0 && champ !== b[B_RED]);
    out += '<div class="gutter">';
    out += '<div class="phase">' + esc(phaseFR(phase) || phase) +
      (phase === "poule" && b[B_POULE] ? " " + esc(b[B_POULE]) : "") + "</div>";
    if (champ < 0) {
      out += '<div class="dec">' + croix("vainqueur") + " " +
        esc(t("bul.notPublished")) + "</div>";
    } else if (dec) {
      out += '<div class="dec">' + esc(decFR(dec) || dec) +
        (b[B_DETAIL] ? '<div class="gapnote">' + esc(b[B_DETAIL]) + "</div>" : "") +
        "</div>";
    } else {
      out += '<div class="dec">' + croix("methode") + " " +
        esc(t("bul.method")) + "</div>";
    }
    if (b[B_RP] !== "" && b[B_BP] !== "") {
      out += '<div class="pts"><span>' + esc(b[B_RP]) + "</span><span>" +
        esc(b[B_BP]) + "</span></div>";
      out += '<div class="micro">' + esc(t("bul.points")) + "</div>";
    } else {
      out += '<div class="micro">' + croix("points") + " " +
        esc(t("poule.points")) + "</div>";
    }
    out += "</div>";
    out += side(blue, b[B_BNAT], b[B_BP], b[B_BW], known ? "b" : "n",
                champ === b[B_BLUE], champ >= 0 && champ !== b[B_BLUE]);
    out += "</div>";
    return out;
  }

  function boutRow(bi, meIdx) {
    var b = BOUTS[bi];
    var mine = b[B_RED] === meIdx;
    var opp = person[mine ? b[B_BLUE] : b[B_RED]];
    var oppNat = mine ? b[B_BNAT] : b[B_RNAT];
    var champ = winnerOf(b);
    var won = champ >= 0 && champ === meIdx;
    var lost = champ >= 0 && champ !== meIdx;
    var phase = PHASES[b[B_PHASE]];
    var e = event[b[B_EV]];
    var dec = DECS[b[B_DEC]];

    var outcome = champ < 0 ? croix("vainqueur")
      : won ? '<span class="w" style="color:var(--vert);font-weight:700">' +
              esc(t("res.win")) + "</span>"
            : '<span style="color:var(--ink-2)">' + esc(t("res.loss")) + "</span>";

    return "<tr>" +
      '<td class="n" style="color:var(--ink-3)">' + esc(e ? e.year : "") + "</td>" +
      '<td class="name">' + (opp ? pLink(opp) : croix("pays")) + "</td>" +
      "<td>" + natHTML(oppNat, { name: false }) + "</td>" +
      '<td class="tour">' + esc(phaseShort(phase) || phase || "") +
        (phase === "poule" && b[B_POULE] ? " " + esc(b[B_POULE]) : "") + "</td>" +
      '<td class="issue">' + outcome + "</td>" +
      '<td class="dec">' + (dec ? esc(decFR(dec) || dec) : croix("methode")) +
        (b[B_DETAIL] ? ' <span class="gapnote">' + esc(b[B_DETAIL]) + "</span>" : "") +
        "</td>" +
      "<td>" + avertHTML(mine ? b[B_RW] : b[B_BW]) + "</td>" +
      '<td><span class="chip" style="border-color:transparent;padding-inline:0">' +
        (cornersKnown(b)
          ? esc(mine ? t("corner.red") : t("corner.blue"))
          : croix("coin")) + "</span></td>" +
      "<td>" + link("#/rencontre/" + bi, esc(t("col.bulletin")), "linky") + "</td>" +
      "</tr>";
  }

  /* ================================================================
     Views
     ================================================================ */

  var views = {};

  /* The front page is one search across the whole archive.
     Somebody arriving here wants a competition, a name, a year or a weight
     class, and does not know which of those the site calls a "route". So the
     field searches all of them at once and groups what it finds; with an empty
     field it shows the ways in. */
  views.home = function (q) {
    var text = q.q || "";
    var box = '<div class="field big">' +
      '<svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
      '<circle cx="7" cy="7" r="4.6" stroke="currentColor" stroke-width="1.6"/>' +
      '<path d="M10.6 10.6 14 14" stroke="currentColor" stroke-width="1.6" ' +
      'stroke-linecap="round"/></svg>' +
      '<input id="filtre" type="search" value="' + esc(text) +
      '" placeholder="' + esc(t("home.search")) + '" ' +
      'autocomplete="off" aria-label="' + esc(t("home.searchAria")) + '"></div>';

    var out = head(esc(t("home.title")), esc(t("home.stats", {
      bouts: num(BOUTS.length), people: num(PEOPLE.length),
      places: num(PLACINGS.length), events: EVENTS.length, years: YEAR_SPAN
    }))) + box;

    if (text.trim()) return out + searchResults(text);

    /* The years, as the index they are. */
    var maxY = 0;
    yearList.forEach(function (y) {
      var n = 0;
      event.forEach(function (e) {
        if (e.year === y) n += e.bouts.length + e.places.length;
      });
      years[y] = n; if (n > maxY) maxY = n;
    });
    var cov = '<div class="cov">' + yearList.map(function (y) {
      var n = years[y] || 0;
      var h = maxY ? Math.max(2, Math.round((n / maxY) * 46)) : 2;
      return '<a href="#/annee/' + esc(y) + '" class="' + (n ? "has" : "") +
        '" title="' + esc(y) + " : " + n + ' lignes"><span class="bar" style="height:' +
        h + 'px"></span><span class="yr">' + esc(y).slice(2) + "</span></a>";
    }).join("") + "</div>";
    out += section(t("home.byYear"), '<div class="card pad">' + cov +
      '<p style="margin-top:12px;font-size:12.5px;color:var(--ink-3)">' +
      esc(t("home.yearNote")) + "</p></div>");

    var recent = event.slice().sort(function (a, b) {
      return (b.year || "").localeCompare(a.year || "") ||
        (b.bouts.length - a.bouts.length);
    }).slice(0, 6);
    out += section(t("home.latest"), '<div class="grid g2">' +
      recent.map(eventCard).join("") + "</div>",
      link("#/epreuves", esc(t("home.allEvents")), "linky"));

    var top = person.slice().sort(function (a, b) {
      return b.or - a.or || b.medals - a.medals || b.bouts.length - a.bouts.length;
    }).slice(0, 12);
    out += section(t("home.mostTitled"),
      '<div class="scroll"><table><thead><tr><th>' + esc(t("col.fighter")) +
      "</th><th>" + esc(t("col.nation")) + "</th>" +
      '<th class="n">' + esc(t("col.titles")) + "</th><th>" +
      esc(t("col.medals")) + "</th><th>" + esc(t("col.record")) + "</th>" +
      "</tr></thead><tbody>" + top.map(function (p) {
        return "<tr" + (titulaire && titulaire.i === p.i ? ' class="moi"' : "") + ">" +
          '<td class="name">' + pLink(p) + "</td>" +
          "<td>" + (p.nats.length ? natHTML(p.nats[0]) : natHTML(-1)) + "</td>" +
          '<td class="n" style="color:var(--or)">' + p.or + "</td>" +
          "<td>" + (medalsHTML(p.or, p.ar, p.br) || "") + "</td>" +
          "<td>" + (p.bouts.length ? recordHTML(p.w, p.l)
            : '<span class="gapnote">' + croix("podiums") + "</span>") + "</td></tr>";
      }).join("") + "</tbody></table></div>",
      link("#/tireurs", esc(t("home.allFighters", { n: num(PEOPLE.length) })), "linky"));

    return out;
  };

  /* One query, every kind of thing the archive holds. */
  function searchResults(text) {
    var f = fold(text);
    var groups = {};
    ORDER_KINDS.forEach(function (k) { groups[k] = []; });
    index.forEach(function (x) {
      if (x.key.indexOf(f) < 0) return;
      if (groups[x.kind] && groups[x.kind].length < 60) groups[x.kind].push(x);
    });

    var total = 0;
    ORDER_KINDS.forEach(function (k) { total += groups[k].length; });
    if (!total) {
      return empty(esc(t("search.none", { q: text })));
    }

    return ORDER_KINDS.filter(function (k) { return groups[k].length; })
      .map(function (k) {
        return section(kindFR(k) + " · " + groups[k].length,
          '<div class="scroll"><table><tbody>' +
          groups[k].map(function (x) {
            return '<tr><td class="name">' +
              link(x.href, esc(x.label), "linky") + "</td>" +
              '<td style="color:var(--ink-3);font-size:12.5px">' +
              esc(x.hint || "") + "</td></tr>";
          }).join("") + "</tbody></table></div>");
      }).join("");
  }

  function eventCard(e) {
    return '<a class="card pad" href="#/epreuve/' + esc(e.slug) + '">' +
      '<div class="chips" style="margin-bottom:10px">' + eventChips(e) + "</div>" +
      '<h3 style="font-size:16px">' + esc(e.name) + "</h3>" +
      '<div class="foot fig" style="font-size:12.5px;color:var(--ink-3)">' +
      esc(e.year) + " · " +
      esc(e.bouts.length ? t("ev.rencontres", { n: e.bouts.length })
                         : t("ev.placesN", { n: e.places.length })) +
      "</div></a>";
  }

  /* -- la fiche ----------------------------------------------------- */
  function fiche(p, opts) {
    opts = opts || {};
    var out = fil([{ text: t("nav.fighters"), href: "#/tireurs" },
                   { text: p.name }]);

    var natsHTML = p.nats.length
      ? p.nats.map(function (n) { return natHTML(n); }).join(" ")
      : natHTML(-1);

    out += '<div class="pagehead">';
    if (titulaire && titulaire.i === p.i) {
      out += '<div class="micro" style="margin-bottom:8px">' +
        esc(t("fiche.mine")) + "</div>";
    }
    out += "<h1>" + esc(p.name) + "</h1>";
    out += '<div class="sub">' + natsHTML +
      (p.club ? " · " + esc(p.club) : "") +
      (p.years.length ? ' · <span class="fig">' + p.years[0] +
        (p.years.length > 1 ? "–" + p.years[p.years.length - 1] : "") + "</span>" : "") +
      "</div>";
    if (p.aliases.length) {
      out += '<div class="sub" style="font-size:12.5px;color:var(--ink-3)">' +
        esc(t("fiche.alsoPrinted", { list: p.aliases.join(" · ") })) + "</div>";
    }
    out += '<div class="chips" style="margin-top:12px">';
    out += '<button class="chip" data-pin="' + esc(p.slug) + '" aria-pressed="' +
      (pinned[p.slug] ? "true" : "false") + '">' + esc(t("fiche.pin")) + "</button>";
    if (!titulaire || titulaire.i !== p.i) {
      out += '<button class="chip" data-adopt="' + esc(p.slug) + '">' +
        esc(t("fiche.itsMe")) + "</button>";
    } else {
      out += '<button class="chip" aria-pressed="true" data-adopt="aucun">' +
        esc(t("fiche.itsMeSet")) + "</button>";
    }
    out += "</div></div>";

    /* The archive holds 1009 medallists with no bouts on file. For them a
       record is not "0–0" — it is a question the sources never answered. */
    var stats = '<div class="grid g4">';
    if (p.bouts.length) {
      stats += '<div class="stat"><b>' + recordHTML(p.w, p.l) + "</b><span>" +
        esc(t("fiche.wl")) + "</span></div>";
      stats += '<div class="stat win"><b>' + pct(p.w, p.w + p.l) + "%</b><span>" +
        esc(t("fiche.ratio")) + "</span></div>";
    }
    if (p.medals) {
      stats += '<div class="stat"><b>' + p.or + "</b><span>" +
        esc(t("fiche.titles")) + "</span></div>";
      stats += '<div class="stat"><b>' + p.medals + "</b><span>" +
        esc(t("fiche.podiums")) + "</span></div>";
    }
    stats += '<div class="stat"><b>' + Object.keys(p.events).length +
      "</b><span>" + esc(t("fiche.events")) + "</span></div>";
    stats += "</div>";
    out += stats;

    out += section(t("fiche.dossier"), dossier(p), esc(t("fiche.dossierNote")));

    /* Palmarès */
    if (p.places.length) {
      var rows = p.places.slice().sort(function (a, b) {
        var ea = event[PLACINGS[a][L_EV]], eb = event[PLACINGS[b][L_EV]];
        return ((eb && eb.year) || "").localeCompare((ea && ea.year) || "");
      }).map(function (x) {
        var l = PLACINGS[x], e = event[l[L_EV]];
        return "<tr>" +
          '<td class="n" style="color:var(--ink-3)">' + esc(e ? e.year : "") + "</td>" +
          '<td class="name" style="color:' +
            (l[L_RANK] === 1 ? "var(--or)" : l[L_RANK] === 2 ? "var(--argent)" : "var(--bronze)") +
            '">' + esc(rankFR(l[L_RANK]) || "") + "</td>" +
          '<td class="name">' + (e ? eLink(e) : "") + "</td>" +
          "<td>" + esc(catFR(l[L_CAT])) + "</td>" +
          "<td>" + (e ? esc(e.label || "") : "") + "</td>" +
          "</tr>";
      }).join("");
      out += section(t("fiche.palmares"),
        '<div class="scroll"><table><thead><tr><th class="n">' + esc(t("col.year")) +
        "</th><th>" + esc(t("col.place")) + "</th><th>" + esc(t("col.event")) +
        "</th><th>" + esc(t("col.category")) + "</th><th>" + esc(t("col.level")) +
        "</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>");
    }

    /* Rencontres, grouped by event */
    if (p.bouts.length) {
      var byEvent = {};
      p.bouts.forEach(function (bi) {
        var k = BOUTS[bi][B_EV];
        (byEvent[k] = byEvent[k] || []).push(bi);
      });
      var order = { poule: 0, r32: 1, r16: 2, quarter: 3, semi: 4, bronze: 5, final: 6 };
      var blocks = Object.keys(byEvent).sort(function (a, b) {
        return ((event[b] && event[b].year) || "").localeCompare((event[a] && event[a].year) || "");
      }).map(function (k) {
        var e = event[k];
        var list = byEvent[k].slice().sort(function (a, b) {
          return (order[PHASES[BOUTS[a][B_PHASE]]] || 0) -
                 (order[PHASES[BOUTS[b][B_PHASE]]] || 0);
        });
        return '<div class="section" style="margin-top:20px">' +
          '<div class="sectionhead"><h2 class="micro">' +
          (e ? eLink(e) : "") + '</h2><span class="note">' +
          (e ? esc(e.year + " · " + (e.label || "")) : "") + "</span></div>" +
          '<div class="scroll"><table><thead><tr><th class="n">' + esc(t("col.year")) +
          "</th><th>" + esc(t("col.opponent")) + "</th><th>" + esc(t("col.nation")) +
          "</th><th>" + esc(t("col.round")) + "</th><th>" + esc(t("col.outcome")) +
          "</th><th>" + esc(t("col.decision")) + "</th><th>" + esc(t("col.warnings")) +
          "</th><th>" + esc(t("col.corner")) + "</th><th></th></tr></thead><tbody>" +
          list.map(function (bi) { return boutRow(bi, p.i); }).join("") +
          "</tbody></table></div></div>";
      }).join("");
      out += section(t("fiche.bouts"), blocks);

      /* The people who have stood opposite. */
      var opps = {};
      p.bouts.forEach(function (bi) {
        var b = BOUTS[bi];
        var o = b[B_RED] === p.i ? b[B_BLUE] : b[B_RED];
        var champion = winnerOf(b);
        if (!opps[o]) opps[o] = { w: 0, l: 0, n: 0 };
        opps[o].n++;
        if (champion >= 0) { if (champion === p.i) opps[o].w++; else opps[o].l++; }
      });
      var oppRows = Object.keys(opps).map(function (k) {
        var o = person[k], r = opps[k];
        if (!o) return "";
        return "<tr>" +
          '<td class="name">' + pLink(o) + "</td>" +
          "<td>" + (o.nats.length ? natHTML(o.nats[0], { name: false }) : croix("pays")) + "</td>" +
          '<td class="n">' + r.n + "</td>" +
          "<td>" + recordHTML(r.w, r.l) + "</td>" +
          "<td>" + (o.bouts.length ? recordHTML(o.w, o.l) : '<span class="gapnote">—</span>') + "</td>" +
          "<td>" + link("#/confrontation/" + p.slug + "..." + o.slug, esc(t("fiche.compare")), "linky") + "</td>" +
          "</tr>";
      }).join("");
      out += section(t("fiche.opponents"),
        '<div class="scroll"><table><thead><tr><th>' + esc(t("col.fighter")) +
        "</th><th>" + esc(t("col.nation")) + "</th>" +
        '<th class="n">' + esc(t("col.meetings")) + "</th><th>" + esc(t("col.h2h")) +
        "</th><th>" + esc(t("col.theirRecord")) + "</th><th></th>" +
        "</tr></thead><tbody>" + oppRows + "</tbody></table></div>",
        esc(t("fiche.opponentCount", { n: Object.keys(opps).length })));

      /* Poules this person appears in, drawn as the sheet they came from. */
      var mine = [];
      POULES.forEach(function (q, qi) {
        if (q[Q_LINES].some(function (l) { return l[0] === p.i; })) mine.push(qi);
      });
      if (mine.length) {
        out += section(t("fiche.sheets"),
          mine.map(function (qi) { return feuille(qi); }).join(
            '<div style="height:22px"></div>'));
      }
    } else if (p.places.length) {
      out += section(t("fiche.bouts"), empty(
        noteText("podiums") + " " +
        t("fiche.podiumOnly", { n: p.places.length })));
    }

    return out;
  }

  /* Every field the archive can hold for a competitor, including the ones it
     does not hold for this one. A profile that silently omits what is missing
     reads as complete; showing the empty rows is how the reader learns what
     the federations publish and what they never have. */
  function dossier(p) {
    var cats = {}, discs = {}, ages = {}, corners = { r: 0, b: 0 };
    var warnings = 0, warnKnown = 0, decs = {};
    p.bouts.forEach(function (bi) {
      var b = BOUTS[bi], red = b[B_RED] === p.i;
      cats[b[B_CAT]] = 1;
      corners[red ? "r" : "b"]++;
      var w = red ? b[B_RW] : b[B_BW];
      if (w >= 0) { warnings += w; warnKnown++; }
      var d = DECS[b[B_DEC]];
      if (d) decs[d] = (decs[d] || 0) + 1;
      var e = event[b[B_EV]];
      if (e) { if (e.disc) discs[e.disc] = 1; if (e.age) ages[e.age] = 1; }
    });
    p.places.forEach(function (x) {
      cats[PLACINGS[x][L_CAT]] = 1;
      var e = event[PLACINGS[x][L_EV]];
      if (e) { if (e.disc) discs[e.disc] = 1; if (e.age) ages[e.age] = 1; }
    });
    CATS.forEach(function (c, i) {
      if (cats[i] && c[C_AGE]) ages[c[C_AGE]] = 1;
    });

    var catList = Object.keys(cats).map(function (i) { return catShort(i) || catFR(i); });
    catList = Object.keys(catList.reduce(function (a, x) { a[x] = 1; return a; }, {}));

    function field(label, value) {
      return '<div><div class="micro">' + esc(label) + "</div>" +
        '<div style="margin-top:3px">' + value + "</div></div>";
    }
    function orGap(value, note) {
      return value || '<span class="gapnote">' + croix(note) + "</span>";
    }

    var rows = [];
    rows.push(field(t("d.name"), esc(p.name)));
    rows.push(field(t("d.spellings"), p.aliases.length
      ? esc(p.aliases.join(" · "))
      : '<span class="gapnote">' + esc(t("d.oneSpelling")) + "</span>"));
    rows.push(field(t("col.nation"), p.nats.length
      ? p.nats.map(function (n) { return natHTML(n); }).join(" ") : orGap("", "pays")));
    rows.push(field(t("d.club"), orGap(esc(p.club), "club")));
    rows.push(field(t("d.weighed"), p.weighed.length
      ? '<span class="fig">' + esc(p.weighed.join(" · ")) + "</span>"
      : orGap("", "pesee")));
    rows.push(field(t("d.categories"), catList.length
      ? esc(catList.join(" · ")) : orGap("", "categorie")));
    rows.push(field(t("d.disciplines"), Object.keys(discs).length
      ? Object.keys(discs).map(discChip).join(" ") : orGap("", "discipline")));
    rows.push(field(t("d.ages"), Object.keys(ages).length
      ? esc(Object.keys(ages).map(function (a) { return ageFR(a) || a; }).join(" · "))
      : orGap("", "age")));
    rows.push(field(t("d.period"), p.years.length
      ? '<span class="fig">' + p.years.join(" · ") + "</span>" : orGap("", "annee")));
    rows.push(field(t("d.events"), '<span class="fig">' +
      Object.keys(p.events).length + "</span>"));
    rows.push(field(t("d.bouts"), p.bouts.length
      ? '<span class="fig">' + p.bouts.length + "</span>"
      : '<span class="gapnote">' + croix("podiums") + "</span>"));
    if (p.bouts.length) {
      rows.push(field(t("d.corners"),
        '<span class="fig"><span style="color:var(--rouge)">' + esc(t("corner.red")) +
        " " + corners.r + '</span> · <span style="color:var(--bleu)">' +
        esc(t("corner.blue")) + " " + corners.b + "</span></span>"));
      rows.push(field(t("d.warnings"), warnKnown
        ? '<span class="fig">' + warnings + "</span> " +
          (warnKnown < p.bouts.length
            ? '<span class="gapnote">' +
              esc(t("d.overPublished", { n: warnKnown })) + " " +
              croix("avert") + "</span>" : "")
        : orGap("", "avert")));
      var decList = Object.keys(decs).map(function (d) {
        return (decFR(d) || d) + " " + decs[d];
      });
      rows.push(field(t("d.decisions"), decList.length
        ? esc(decList.join(" · ")) : orGap("", "methode")));
    }
    rows.push(field(t("d.podiums"), p.places.length
      ? '<span class="fig">' + p.places.length + "</span>"
      : '<span class="gapnote">' + esc(t("d.nonePublished")) + "</span>"));

    return '<div class="card pad"><div class="grid g3">' + rows.join("") + "</div></div>";
  }

  /* -- registre ----------------------------------------------------- */
  function registre(q, isHome) {
    var filter = fold(q.q || "");
    var rows = person.filter(function (p) {
      return !filter || p.key.indexOf(filter) >= 0;
    });
    rows.sort(sorters.tireurs[sortState.tireurs.key] || sorters.tireurs.medals);
    if (sortState.tireurs.dir < 0) rows.reverse();

    var body = rows.slice(0, 400).map(function (p) {
      return "<tr" + (titulaire && titulaire.i === p.i ? ' class="moi"' : "") + ">" +
        '<td class="name">' + pLink(p) + "</td>" +
        "<td>" + (p.nats.length ? natHTML(p.nats[0]) : natHTML(-1)) + "</td>" +
        '<td class="n">' + (p.bouts.length || "") + "</td>" +
        "<td>" + (p.bouts.length ? recordHTML(p.w, p.l) : '<span class="gapnote">' +
          croix("podiums") + "</span>") + "</td>" +
        "<td>" + (medalsHTML(p.or, p.ar, p.br) || '<span class="gapnote">—</span>') + "</td>" +
        '<td class="n" style="color:var(--ink-3)">' +
          (p.years.length ? p.years[0] + (p.years.length > 1 ? "–" + p.years[p.years.length - 1].slice(2) : "") : "") +
        "</td></tr>";
    }).join("");

    var box = '<div class="field' + (isHome ? " big" : "") + '">' +
      '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
      '<circle cx="7" cy="7" r="4.6" stroke="currentColor" stroke-width="1.6"/>' +
      '<path d="M10.6 10.6 14 14" stroke="currentColor" stroke-width="1.6" ' +
      'stroke-linecap="round"/></svg>' +
      '<input id="filtre" type="search" value="' + esc(q.q || "") +
      '" placeholder="' + esc(t("reg.filter")) + '" autocomplete="off" ' +
      'aria-label="' + esc(t("reg.filterAria")) + '"></div>';

    var title = t("reg.title");
    var sub = t("reg.count", { n: num(rows.length) });
    if (filter) {
      sub = t("reg.matching", { n: num(rows.length), q: q.q });
    } else if (rows.length > 400) {
      sub += t("reg.capped");
    }

    return head(esc(title), sub) + box +
      '<div class="chips" style="margin-bottom:14px">' +
      '<button class="chip" data-copy>' + esc(t("reg.copy")) + "</button></div>" +
      '<div class="scroll"><table data-sort="tireurs"><thead><tr>' +
      th("name", t("col.fighter"), "tireurs") +
      "<th>" + esc(t("col.nation")) + "</th>" +
      th("bouts", t("col.bouts"), "tireurs", true) +
      "<th>" + esc(t("col.record")) + "</th>" +
      th("medals", t("col.medals"), "tireurs") +
      "<th>" + esc(t("col.period")) + "</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  views.tireurs = function (q) { return registre(q, false); };

  /* -- épreuves ----------------------------------------------------- */
  views.epreuves = function (q) {
    var lvl = q.niveau || "", fmt = q.format || "", disc = q.discipline || "";
    // Scope order: world first, then european, asian, panamerican, african,
    // oceanian, national, regional, club — same ladder the export uses.
    var _SCOPE_ORDER = {};
    D.scopes.forEach(function (s, i) { _SCOPE_ORDER[s[0]] = i; });
    var rows = event.filter(function (e) {
      return (!lvl || e.level === lvl) && (!fmt || e.format === fmt) &&
        (!disc || e.disc === disc);
    }).sort(function (a, b) {
      var y = (b.year || "").localeCompare(a.year || "");
      if (y) return y;
      return (_SCOPE_ORDER[a.level] || Infinity) - (_SCOPE_ORDER[b.level] || Infinity) || a.name.localeCompare(b.name);
    });

    var chips = '<div class="chips" style="margin-bottom:16px">';
    chips += filterChip("niveau", "", t("ev.allLevels"), q);
    D.scopes.forEach(function (s) {
      if (event.some(function (e) { return e.level === s[0]; })) {
        chips += filterChip("niveau", s[0], t("scope." + s[0]), q);
      }
    });
    chips += '<span style="width:10px"></span>';
    D.formats.forEach(function (f) {
      if (event.some(function (e) { return e.format === f[0]; })) {
        chips += filterChip("format", f[0], t("format." + f[0]), q);
      }
    });
    chips += '<span style="width:10px"></span>';
    chips += filterChip("discipline", "assaut", "Assaut", q);
    chips += filterChip("discipline", "combat", "Combat", q);
    chips += "</div>";

    /* Group events by competition (multi-stage championships).
       Shared competition → championship heading, then stages sorted by date.
       Empty competition → each event is its own row, sorted year newest-first. */
    var grouped = {}, groupedArr = [];
    rows.forEach(function (e) {
      var key = e.competition || "__no_comp__";
      if (!(key in grouped)) { grouped[key] = []; groupedArr.push(key); }
      grouped[key].push(e);
    });

    function stageDate(e) {
      return e.start_date || e.end_date || "";
    }

    /* Sort each group's stages by date (earliest first),
       then sort the group array: competitions first (by year desc),
       then ungrouped events (by year desc, scope, name). */
    groupedArr.sort(function (a, b) {
      var ga = grouped[a], gb = grouped[b];
      var aHas = ga[0].competition, bHas = gb[0].competition;
      /* Competition groups before ungrouped */
      if (aHas && !bHas) return -1;
      if (!aHas && bHas) return 1;
      /* Both have competition: sort by year desc, then name */
      if (aHas && bHas) {
        var y = (gb[0].year || "").localeCompare(ga[0].year || "");
        if (y) return y;
        return a.localeCompare(b);
      }
      /* Neither has competition: same as original sort */
      var y = (gb[0].year || "").localeCompare(ga[0].year || "");
      if (y) return y;
      return (_SCOPE_ORDER[ga[0].level] || Infinity) - (_SCOPE_ORDER[gb[0].level] || Infinity) || ga[0].name.localeCompare(gb[0].name);
    });

    var body = "";
    groupedArr.forEach(function (key) {
      var stages = grouped[key].slice().sort(function (a, b) {
        return (stageDate(a) || "z").localeCompare(stageDate(b) || "z");
      });
      var hasComp = stages[0].competition;
      if (hasComp) {
        /* Show competition name as a heading, then stages underneath */
        body += '<tr class="comp-heading"><td colspan="7">' +
          '<span class="comp-title">' + esc(hasComp) + "</span>" + "</td></tr>";
        stages.forEach(function (e) {
          body += "<tr>" +
            '<td class="n" style="color:var(--ink-3)">' + esc(e.year) + "</td>" +
            '<td class="name" style="padding-left:12px">' + eLink(e) + "</td>" +
            '<td class="comp">' + esc(stageDate(e) || "—") + "</td>" +
            "<td>" + esc(e.label || "") + "</td>" +
            "<td>" + (e.disc ? discChip(e.disc) : '<span class="gapnote">—</span>') + "</td>" +
            '<td class="n">' + (e.bouts.length || "") + "</td>" +
            '<td class="n">' + (e.places.length || "") + "</td>" +
            "</tr>";
        });
      } else {
        /* No competition — just render each event as a row */
        stages.forEach(function (e) {
          body += "<tr>" +
            '<td class="n" style="color:var(--ink-3)">' + esc(e.year) + "</td>" +
            '<td class="name">' + eLink(e) + "</td>" +
            '<td class="comp">' + esc(stageDate(e) || "—") + "</td>" +
            "<td>" + esc(e.label || "") + "</td>" +
            "<td>" + (e.disc ? discChip(e.disc) : '<span class="gapnote">—</span>') + "</td>" +
            '<td class="n">' + (e.bouts.length || "") + "</td>" +
            '<td class="n">' + (e.places.length || "") + "</td>" +
            "</tr>";
        });
      }
    });

    return head(esc(t("ev.title")), esc(t("ev.count", {
      n: num(rows.length), first: YEAR_FIRST, last: YEAR_LAST }))) + chips +
      '<div class="scroll"><table><thead><tr><th class="n">' + esc(t("col.year")) +
      "</th><th>" + esc(t("col.event")) + "</th>" +
      "<th>" + esc(t("col.date")) + "</th>" +
      "<th>" + esc(t("col.level")) + "</th><th>" + esc(t("col.discipline")) + "</th>" +
      '<th class="n">' + esc(t("col.bouts")) + "</th>" +
      '<th class="n">' + esc(t("col.places")) + "</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";
  };

  function filterChip(field, value, label, q) {
    var on = (q[field] || "") === value;
    var next = Object.assign({}, q);
    if (on || !value) delete next[field]; else next[field] = value;
    return '<a class="chip" href="' + esc(hashOf("/epreuves", next)) +
      '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(label) + "</a>";
  }
  function hashOf(path, q) {
    var parts = Object.keys(q).filter(function (k) { return q[k]; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(q[k]); });
    return "#" + path + (parts.length ? "?" + parts.join("&") : "");
  }

  /* -- une épreuve ---------------------------------------------------
     A championship is browsed division by division, the way a competitor
     looks for their own weight class. Rendering all 61 poules of the 2026
     worlds at once produced a 200 KB page nobody reads top to bottom, so
     the categories are an index and one opens at a time. */
  views.epreuve = function (q, slugName) {
    var e = eventBySlug[slugName];
    if (!e) return notFound(t("nf.event"));

    var out = fil([{ text: t("nav.events"), href: "#/epreuves" }, { text: e.name }]);
    out += head(esc(e.name), '<span class="chips">' + eventChips(e) + "</span>");

    out += '<div class="grid g4">';
    out += '<div class="stat"><b>' + e.bouts.length + "</b><span>" +
      esc(t("ev.bouts")) + "</span></div>";
    out += '<div class="stat"><b>' + e.poules.length + "</b><span>" +
      esc(t("ev.poules")) + "</span></div>";
    out += '<div class="stat"><b>' + e.places.length + "</b><span>" +
      esc(t("ev.places")) + "</span></div>";
    out += '<div class="stat"><b>' + Object.keys(e.cats).length + "</b><span>" +
      esc(t("ev.categories")) + "</span></div>";
    out += "</div>";

    /* The document this event was read from. An archive that cannot point
       at its source for a line is a rumour, so every event carries it. */
    if (e.source) {
      var srcUrl = /^https?:\/\//i.test(e.source);
      out += section(t("ev.source"), srcUrl
        ? '<p class="micro" style="word-break:break-all;margin:0"><a ' +
          'href="' + esc(e.source) + '" target="_blank" ' +
          'rel="noopener noreferrer">' + esc(e.source) + "</a></p>"
        : '<p class="micro" style="word-break:break-all;margin:0">' +
          esc(e.source) + "</p>");
    }

    /* What exists per category in this event. */
    var info = {};
    function bucket(c) {
      return (info[c] = info[c] || { bouts: 0, poules: [], places: [], knock: [] });
    }
    e.bouts.forEach(function (bi) {
      var b = BOUTS[bi], k = bucket(b[B_CAT]);
      k.bouts++;
      if (PHASES[b[B_PHASE]] !== "poule") k.knock.push(bi);
    });
    e.poules.forEach(function (qi) { bucket(POULES[qi][Q_CAT]).poules.push(qi); });
    e.places.forEach(function (x) { bucket(PLACINGS[x][L_CAT]).places.push(x); });

    var cats = Object.keys(info).sort(function (a, b) {
      return catFR(a).localeCompare(catFR(b), "fr");
    });
    var openCat = null;
    cats.forEach(function (c) {
      if (slug(CATS[c][C_LABEL]) === q.cat) openCat = c;
    });

    if (cats.length) {
      var groups = {}, groupOrder = [];
      cats.forEach(function (c) {
        var meta = CATS[c];
        var head = [ageFR(meta[C_AGE]) || meta[C_AGE] || "",
                    genderFR(meta[C_GENDER]) || meta[C_GENDER] || ""]
                   .filter(Boolean).join(" ") || t("cat.unstated");
        if (!groups[head]) { groups[head] = []; groupOrder.push(head); }
        groups[head].push(c);
      });
      var index = groupOrder.map(function (head) {
        return '<div style="margin-bottom:12px">' +
          '<div class="micro" style="margin-bottom:6px">' + esc(head) + "</div>" +
          '<div class="chips">' + groups[head].map(function (c) {
            var k = info[c], on = openCat === c;
            var next = Object.assign({}, q);
            if (on) delete next.cat; else next.cat = slug(CATS[c][C_LABEL]);
            return '<a class="chip" href="' +
              esc(hashOf("/epreuve/" + e.slug, next)) + '" aria-pressed="' +
              (on ? "true" : "false") + '">' + esc(catShort(c) || catFR(c)) +
              ' <span class="fig" style="opacity:.6">' +
              (k.bouts || k.places.length) + "</span></a>";
          }).join("") + "</div></div>";
      }).join("");
      out += section(t("ev.categoryIndex"), index,
        openCat ? esc(t("ev.filteredOn", { cat: catFR(openCat) }))
                : esc(t("ev.categoryCount", { n: cats.length })));
    }

    var shown = openCat ? [openCat] : cats;

    /* Podiums read well for a whole championship at once, so they are not
       hidden behind the filter unless one is chosen. */
    function podiumCard(c, rows, derived) {
      return '<div class="card pad"><div class="micro">' + esc(catFR(c)) +
        (derived ? ' <span class="note" style="opacity:.6">' + esc(t("ev.fromBracket")) + "</span>" : "") +
        "</div>" +
        '<div style="margin-top:10px;display:grid;gap:8px">' +
        rows.map(function (l) {
          var p = person[l.who];
          var colour = l.rank === 1 ? "var(--or)" :
            l.rank === 2 ? "var(--argent)" : "var(--bronze)";
          return '<div style="display:flex;gap:9px;align-items:center">' +
            '<span class="fig" style="color:' + colour + ';font-weight:600;width:22px">' +
            esc(RANK_SHORT[l.rank]) + "</span>" +
            '<span style="font-weight:600">' + (p ? pLink(p) : croix("pays")) + "</span>" +
            natHTML(l.nat, { name: false }) + "</div>";
        }).join("") + "</div></div>";
    }

    var pod = shown.filter(function (c) { return info[c].places.length; })
      .map(function (c) {
        var list = info[c].places.slice().sort(function (a, b) {
          return PLACINGS[a][L_RANK] - PLACINGS[b][L_RANK];
        }).map(function (x) {
          var l = PLACINGS[x];
          return { rank: l[L_RANK], who: l[L_WHO], nat: l[L_NAT] };
        });
        return podiumCard(c, list, false);
      }).join("");
    if (pod) out += section(t("ev.podiums"), '<div class="grid g2">' + pod + "</div>");

    /* A bracket crowns someone too. Where the sheets print the finals but no
       podium, the final and the petite finales say who stood there: the
       winner of the single final is the champion, the man he beat is second,
       and the winners of the bronze bouts share third. Only a single final
       with a named winner is read - several finals or no winner stay in the
       bracket, which still shows them. */
    var finals = {}, bronzes = {};
    e.bouts.forEach(function (bi) {
      var b = BOUTS[bi], ph = PHASES[b[B_PHASE]];
      if (ph === "final") (finals[b[B_CAT]] = finals[b[B_CAT]] || []).push(b);
      else if (ph === "bronze") (bronzes[b[B_CAT]] = bronzes[b[B_CAT]] || []).push(b);
    });
    var derivedRows = {};
    Object.keys(finals).forEach(function (c) {
      if (info[c].places.length) return;   /* the printed podium already stands */
      var fs = finals[c];
      if (fs.length !== 1) return;
      var f = fs[0], w = winnerOf(f);
      if (w !== f[B_RED] && w !== f[B_BLUE]) return;
      var rows = [
        { rank: 1, who: w, nat: w === f[B_RED] ? f[B_RNAT] : f[B_BNAT] },
        { rank: 2, who: w === f[B_RED] ? f[B_BLUE] : f[B_RED],
          nat: w === f[B_RED] ? f[B_BNAT] : f[B_RNAT] }
      ];
      var bs = bronzes[c] || [];
      if (bs.length && bs.length <= 2 && bs.every(function (b) {
        var bw = winnerOf(b); return bw === b[B_RED] || bw === b[B_BLUE];
      })) {
        bs.forEach(function (b) {
          var bw = winnerOf(b);
          rows.push({ rank: 3, who: bw,
                      nat: bw === b[B_RED] ? b[B_RNAT] : b[B_BNAT] });
        });
      }
      derivedRows[c] = rows;
    });
    var recon = shown.filter(function (c) { return derivedRows[c]; })
      .map(function (c) { return podiumCard(c, derivedRows[c], true); }).join("");
    if (recon) out += section(t("ev.podiumsDerived"),
      '<div class="grid g2">' + recon + "</div>",
      esc(t("ev.podiumsDerivedNote")));

    if (!openCat && cats.length > 1) {
      var withSheets = cats.filter(function (c) {
        return info[c].poules.length || info[c].knock.length;
      }).length;
      if (withSheets) {
        out += section(t("fiche.sheets"),
          '<div class="card pad"><p style="font-size:13.5px;color:var(--ink-2)">' +
          esc(t("ev.pickCategory", { n: withSheets })) + "</p></div>");
      }
    } else {
      shown.forEach(function (c) {
        var k = info[c];
        if (k.knock.length) {
          out += section(t("ev.brackets", { cat: catFR(c) }), tableau(k.knock));
        }
        if (k.poules.length) {
          out += section(t("ev.sheets", { cat: catFR(c) }),
            k.poules.map(function (qi) { return feuille(qi); })
              .join('<div style="height:22px"></div>'));
        }
      });
    }

    if (!e.places.length && !e.bouts.length) {
      out += empty(esc(t("ev.nothing")));
    }
    return out;
  };

  function tableau(list) {
    var order = ["r32", "r16", "quarter", "semi", "bronze", "final"];
    var by = {};
    list.forEach(function (bi) {
      var ph = PHASES[BOUTS[bi][B_PHASE]];
      (by[ph] = by[ph] || []).push(bi);
    });
    var rounds = order.filter(function (o) { return by[o]; });
    if (!rounds.length) return "";
    return '<div class="tableau">' + rounds.map(function (ph) {
      return '<div class="round"><div class="micro">' +
        esc(phaseFR(ph) || ph) + "</div>" +
        by[ph].map(function (bi) { return tie(bi); }).join("") + "</div>";
    }).join("") + "</div>";
  }
  function tie(bi) {
    var b = BOUTS[bi];
    function side(p, natIdx, corner, won, lost, pts) {
      return '<div class="side ' + corner + (won ? " won" : lost ? " lost" : "") + '">' +
        (p ? pLink(p) : croix("pays")) +
        '<span style="margin-left:auto;display:flex;gap:7px;align-items:center">' +
        natHTML(natIdx, { name: false }) +
        (pts !== "" ? '<span class="sc">' + esc(pts) + "</span>" : "") +
        "</span></div>";
    }
    var champ = winnerOf(b), known = cornersKnown(b);
    return '<a class="tie" href="#/rencontre/' + bi + '">' +
      side(person[b[B_RED]], b[B_RNAT], known ? "r" : "n",
           champ === b[B_RED], champ >= 0 && champ !== b[B_RED], b[B_RP]) +
      side(person[b[B_BLUE]], b[B_BNAT], known ? "b" : "n",
           champ === b[B_BLUE], champ >= 0 && champ !== b[B_BLUE], b[B_BP]) +
      "</a>";
  }

  /* -- une rencontre -------------------------------------------------- */
  views.rencontre = function (q, idx) {
    var bi = parseInt(idx, 10);
    var b = BOUTS[bi];
    if (!b) return notFound(t("nf.bout"));
    var e = event[b[B_EV]];
    var out = fil([
      { text: t("nav.events"), href: "#/epreuves" },
      e ? { text: e.name, href: "#/epreuve/" + e.slug } : { text: "—" },
      { text: t("d.bouts") }
    ]);
    out += head(esc(t("bul.title")),
      esc(catFR(b[B_CAT])) + (e ? " · " + esc(e.name) : ""));
    out += bulletin(bi);

    var meta = '<div class="card pad" style="margin-top:16px"><div class="grid g3">';
    meta += '<div><div class="micro">' + esc(t("bul.when")) + "</div><div>" +
      (b[B_DATE] ? esc(dateFR(b[B_DATE], b[B_TIME])) : croix("horaire")) + "</div></div>";
    meta += '<div><div class="micro">' + esc(t("bul.ring")) + "</div><div>" +
      (b[B_RING] ? esc(b[B_RING]) : croix("horaire")) + "</div></div>";
    meta += '<div><div class="micro">' + esc(t("col.category")) + "</div><div>" +
      esc(catFR(b[B_CAT])) + "</div></div>";
    meta += "</div></div>";
    out += meta;

    if (person[b[B_RED]] && person[b[B_BLUE]]) {
      out += '<div class="chips" style="margin-top:16px">' +
        link("#/confrontation/" + person[b[B_RED]].slug + "..." + person[b[B_BLUE]].slug,
             esc(t("bul.compareBoth")), "chip") + "</div>";
    }
    return out;
  };

  /* -- nations ---------------------------------------------------------
     A national title and a world title are not the same achievement, so they
     are not added together by default. The scope is a control, and whatever it
     is set to, the table says what it counted. */
  var SCOPE_SETS = {
    // "not domestic", rather than "level positively known" - an event whose
    // scope the document never stated is still not a national championship,
    // and dropping it would hide 34 placings to no purpose.
    international: { key: "nat.scopeInternational",
      test: function (e) { return e.level !== "national" && e.level !== "regional"; } },
    world: { key: "nat.scopeWorld",
      test: function (e) { return e.level === "world"; } },
    all: { key: "nat.scopeAll", test: function () { return true; } }
  };

  function nationStats(test) {
    var by = {};
    function get(i) {
      if (i == null || i < 0) return null;
      var n = nation[i];
      if (!n || !n.known || !n.iso) return null;
      return by[i] || (by[i] = { n: n, or: 0, ar: 0, br: 0, bouts: 0, wins: 0,
                                 people: {}, years: {} });
    }
    PLACINGS.forEach(function (l) {
      var e = event[l[L_EV]];
      if (!e || !test(e)) return;
      var row = get(l[L_NAT]); if (!row) return;
      if (l[L_RANK] === 1) row.or++;
      else if (l[L_RANK] === 2) row.ar++;
      else if (l[L_RANK] === 3) row.br++;
      row.people[l[L_WHO]] = 1;
      if (e.year) row.years[e.year] = 1;
    });
    BOUTS.forEach(function (b) {
      var e = event[b[B_EV]];
      if (!e || !test(e)) return;
      [[b[B_RNAT], b[B_RED], 0], [b[B_BNAT], b[B_BLUE], 1]].forEach(function (x) {
        var row = get(x[0]); if (!row) return;
        row.bouts++; row.people[x[1]] = 1;
        if (b[B_WIN] === x[2]) row.wins++;
        if (e.year) row.years[e.year] = 1;
      });
    });
    return Object.keys(by).map(function (k) {
      var r = by[k];
      var ys = Object.keys(r.years).sort();
      r.medals = r.or + r.ar + r.br;
      r.tireurs = Object.keys(r.people).length;
      r.first = ys[0] || ""; r.last = ys[ys.length - 1] || "";
      return r;
    }).filter(function (r) { return r.medals || r.bouts; });
  }

  views.nations = function (q) {
    var key = SCOPE_SETS[q.portee] ? q.portee : "international";
    var rows = nationStats(SCOPE_SETS[key].test);
    rows.sort(function (a, b) {
      return b.or - a.or || b.ar - a.ar || b.br - a.br ||
        nationName(a.n).localeCompare(nationName(b.n));
    });
    var unresolved = nation.filter(function (n) { return !n.known; }).length;

    var chips = '<div class="chips" style="margin-bottom:16px">' +
      Object.keys(SCOPE_SETS).map(function (k) {
        var next = Object.assign({}, q);
        if (k === "international") delete next.portee; else next.portee = k;
        return '<a class="chip" href="' + esc(hashOf("/nations", next)) +
          '" aria-pressed="' + (k === key ? "true" : "false") + '">' +
          esc(t(SCOPE_SETS[k].key)) + "</a>";
      }).join("") + "</div>";

    var body = rows.map(function (r, i) {
      return "<tr>" +
        '<td class="n" style="color:var(--ink-3)">' + (i + 1) + "</td>" +
        '<td class="name">' + link("#/nation/" + r.n.slug, natHTML(r.n.i), "linky") + "</td>" +
        '<td class="n" style="color:var(--or)">' + (r.or || "·") + "</td>" +
        '<td class="n" style="color:var(--argent)">' + (r.ar || "·") + "</td>" +
        '<td class="n" style="color:var(--bronze)">' + (r.br || "·") + "</td>" +
        '<td class="n"><b>' + (r.medals || "·") + "</b></td>" +
        '<td class="n">' + (r.tireurs || "·") + "</td>" +
        '<td class="n">' + (r.bouts || "·") + "</td>" +
        '<td class="n" style="color:var(--ink-3)">' +
          (r.first ? r.first + "–" + r.last.slice(2) : "") + "</td>" +
        "</tr>";
    }).join("");

    return head(esc(t("nat.title")), esc(t("nat.count", {
      n: rows.length, scope: t(SCOPE_SETS[key].key).toLowerCase()
    }))) + chips +
      '<div class="chips" style="margin-bottom:14px">' +
      '<button class="chip" data-copy>' + esc(t("reg.copy")) + "</button></div>" +
      '<div class="scroll"><table><thead><tr><th class="n">#</th><th>' +
      esc(t("col.nation")) + "</th>" +
      '<th class="n">' + esc(t("col.gold")) + "</th>" +
      '<th class="n">' + esc(t("col.silver")) + "</th>" +
      '<th class="n">' + esc(t("col.bronze")) + "</th>" +
      '<th class="n">' + esc(t("col.total")) + "</th>" +
      '<th class="n">' + esc(t("col.fighters")) + "</th>" +
      '<th class="n">' + esc(t("col.bouts")) + "</th>" +
      "<th>" + esc(t("col.period")) + "</th></tr></thead><tbody>" +
      body + "</tbody></table></div>" +
      '<div class="notes" style="border-top-width:1px"><p style="font-size:12.5px;' +
      'color:var(--ink-2);line-height:1.6;max-width:70ch">' +
      t("nat.caveat") +
      (unresolved ? " " + croix("graphie") + " " +
        esc(t("nat.unresolved", { n: unresolved })) : "") +
      "</p></div>";
  };

  views.nation = function (q, slugName) {
    var n = nationBySlug[slugName];
    if (!n) return notFound(t("nf.nation"));
    var out = fil([{ text: t("nav.nations"), href: "#/nations" },
                   { text: nationName(n) }]);
    out += head((n.iso ? flagOf(n.iso) + " " : "") + esc(nationName(n)),
      '<span class="fig">' + esc(n.code || "") + "</span>" +
      (n.first ? " · " + n.first + "–" + n.last : ""));

    out += '<div class="grid g4">';
    out += '<div class="stat"><b style="color:var(--or)">' + n.or + "</b><span>" +
      esc(t("col.titles")) + "</span></div>";
    out += '<div class="stat"><b>' + n.medals + "</b><span>" +
      esc(t("col.medals")) + "</span></div>";
    out += '<div class="stat"><b>' + n.tireurs + "</b><span>" +
      esc(t("col.fighters")) + "</span></div>";
    out += '<div class="stat"><b>' + n.bouts + "</b><span>" +
      esc(t("d.bouts")) + "</span></div>";
    out += "</div>";

    var people = Object.keys(n.people).map(function (k) { return person[k]; })
      .filter(Boolean)
      .sort(function (a, b) { return b.or - a.or || b.medals - a.medals || b.bouts.length - a.bouts.length; });
    out += section(t("nav.fighters"),
      '<div class="scroll"><table><thead><tr><th>' + esc(t("col.fighter")) + "</th>" +
      '<th class="n">' + esc(t("col.bouts")) + "</th><th>" + esc(t("col.record")) +
      "</th><th>" + esc(t("col.medals")) + "</th><th>" + esc(t("col.period")) + "</th>" +
      "</tr></thead><tbody>" + people.slice(0, 200).map(function (p) {
        return "<tr" + (titulaire && titulaire.i === p.i ? ' class="moi"' : "") + ">" +
          '<td class="name">' + pLink(p) + "</td>" +
          '<td class="n">' + (p.bouts.length || "") + "</td>" +
          "<td>" + (p.bouts.length ? recordHTML(p.w, p.l) : '<span class="gapnote">—</span>') + "</td>" +
          "<td>" + (medalsHTML(p.or, p.ar, p.br) || "") + "</td>" +
          '<td class="n" style="color:var(--ink-3)">' + (p.years[0] || "") + "</td></tr>";
      }).join("") + "</tbody></table></div>",
      esc(t("fiche.opponentCount", { n: people.length })));
    return out;
  };

  /* -- catégories ----------------------------------------------------- */
  views.classes = function () {
    var body = klasses.map(function (k) {
      return "<tr>" +
        '<td class="name">' + link("#/classe/" + k.key, esc(klassLabel(k)), "linky") + "</td>" +
        "<td>" + esc(genderFR(k.gender) || "") + "</td>" +
        "<td>" + esc(ageFR(k.age) || "") + "</td>" +
        '<td class="n">' + (k.champs.length || "·") + "</td>" +
        '<td class="n">' + (k.bouts || "·") + "</td>" +
        "</tr>";
    }).join("");
    return head(esc(t("cls.title")), esc(t("cls.count", { n: klasses.length }))) +
      '<div class="chips" style="margin-bottom:14px">' +
      '<button class="chip" data-copy>' + esc(t("reg.copy")) + "</button></div>" +
      '<div class="scroll"><table><thead><tr><th>' + esc(t("col.category")) +
      "</th><th>" + esc(t("col.gender")) + "</th>" +
      "<th>" + esc(t("col.ageClass")) + "</th>" +
      '<th class="n">' + esc(t("col.titles")) + "</th>" +
      '<th class="n">' + esc(t("col.bouts")) + "</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";
  };

  views.classe = function (q, key) {
    var k = klass[key];
    if (!k) return notFound(t("nf.class"));
    var out = fil([{ text: t("nav.classes"), href: "#/classes" }, { text: klassLabel(k) }]);
    out += head(esc(klassLabel(k)), esc(t("cls.lineage")));

    var rows = k.champs.slice().sort(function (a, b) {
      var ea = event[PLACINGS[a][L_EV]], eb = event[PLACINGS[b][L_EV]];
      return ((eb && eb.year) || "").localeCompare((ea && ea.year) || "");
    }).map(function (x) {
      var l = PLACINGS[x], e = event[l[L_EV]], p = person[l[L_WHO]];
      return "<tr" + (titulaire && titulaire.i === l[L_WHO] ? ' class="moi"' : "") + ">" +
        '<td class="n" style="color:var(--ink-3)">' + esc(e ? e.year : "") + "</td>" +
        '<td class="name">' + (p ? pLink(p) : croix("pays")) + "</td>" +
        "<td>" + natHTML(l[L_NAT]) + "</td>" +
        '<td class="name">' + (e ? eLink(e) : "") + "</td>" +
        "<td>" + (e ? esc(e.label || "") : "") + "</td></tr>";
    }).join("");

    out += section(t("cls.champions"), rows
      ? '<div class="scroll"><table><thead><tr><th class="n">' + esc(t("col.year")) +
        "</th><th>" + esc(t("col.fighter")) + "</th>" +
        "<th>" + esc(t("col.nation")) + "</th><th>" + esc(t("col.event")) +
        "</th><th>" + esc(t("col.level")) + "</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>"
      : empty(esc(t("cls.noTitles"))));
    return out;
  };

  /* -- une année ------------------------------------------------------ */
  views.annee = function (q, y) {
    var list = event.filter(function (e) { return e.year === y; })
      .sort(function (a, b) {
        return (_SCOPE_ORDER[a.level] || Infinity) - (_SCOPE_ORDER[b.level] || Infinity) ||
          a.name.localeCompare(b.name);
      });
    if (!list.length) return notFound(t("yr.none", { year: y }));
    var out = fil([{ text: t("nav.events"), href: "#/epreuves" }, { text: y }]);
    var nb = 0, np = 0;
    list.forEach(function (e) { nb += e.bouts.length; np += e.places.length; });
    out += head(esc(y), esc(t("yr.count", {
      events: list.length, bouts: nb, places: np })));
    out += '<div class="grid g2">' + list.map(eventCard).join("") + "</div>";
    return out;
  };

  /* -- confrontation -------------------------------------------------- */
  views.confrontation = function (q, pair) {
    var two = String(pair || "").split("...");
    var a = personBySlug[two[0]], b = personBySlug[two[1]];
    if (!a || !b) return notFound(t("nf.pair"));

    var met = [];
    a.bouts.forEach(function (bi) {
      var x = BOUTS[bi];
      if (x[B_RED] === b.i || x[B_BLUE] === b.i) met.push(bi);
    });
    var aw = 0, bw = 0;
    met.forEach(function (bi) {
      var w = winnerOf(BOUTS[bi]);
      if (w < 0) return;
      if (w === a.i) aw++; else if (w === b.i) bw++;
    });

    var out = fil([{ text: t("nav.fighters"), href: "#/tireurs" },
                   { text: t("cmp.title") }]);
    out += head(esc(a.name) + " · " + esc(b.name),
      esc(met.length ? t("cmp.met", { n: met.length }) : t("cmp.never")));

    function col(p, wins) {
      return '<div class="card pad"><h3 style="font-size:17px">' + pLink(p) + "</h3>" +
        '<div style="margin-top:8px">' +
        (p.nats.length ? natHTML(p.nats[0]) : natHTML(-1)) + "</div>" +
        '<div class="grid g2" style="margin-top:14px">' +
        '<div class="stat"><b>' + (p.bouts.length ? recordHTML(p.w, p.l) : "—") +
          "</b><span>" + esc(t("cmp.record")) + "</span></div>" +
        '<div class="stat"><b>' + p.medals + "</b><span>" +
          esc(t("cmp.podiums")) + "</span></div>" +
        (met.length ? '<div class="stat"><b>' + wins + "</b><span>" +
          esc(t("cmp.h2h")) + "</span></div>" : "") +
        "</div></div>";
    }
    out += '<div class="grid g2">' + col(a, aw) + col(b, bw) + "</div>";

    if (met.length) {
      out += section(t("cmp.theirBouts"),
        '<div class="scroll"><table><thead><tr><th class="n">' + esc(t("col.year")) +
        "</th><th>" + esc(t("col.event")) + "</th><th>" + esc(t("col.round")) +
        "</th><th>" + esc(t("col.winner")) + "</th><th>" + esc(t("col.decision")) +
        "</th><th></th></tr></thead><tbody>" + met.map(function (bi) {
          var x = BOUTS[bi], e = event[x[B_EV]];
          var w = winnerOf(x);
          var winner = w < 0 ? null : person[w];
          var dec = DECS[x[B_DEC]];
          return "<tr>" +
            '<td class="n" style="color:var(--ink-3)">' + esc(e ? e.year : "") + "</td>" +
            '<td class="name">' + (e ? eLink(e) : "") + "</td>" +
            "<td>" + esc(phaseShort(PHASES[x[B_PHASE]]) || "") + "</td>" +
            '<td class="name">' + (winner ? pLink(winner) : croix("vainqueur")) + "</td>" +
            "<td>" + (dec ? esc(decFR(dec) || dec) : croix("methode")) + "</td>" +
            "<td>" + link("#/rencontre/" + bi, esc(t("col.bulletin")), "linky") + "</td></tr>";
        }).join("") + "</tbody></table></div>");
    } else {
      out += section(t("cmp.theirBouts"), empty(esc(t("cmp.noneNote"))));
    }
    return out;
  };

  /* -- épinglés -------------------------------------------------------- */
  views.epingles = function () {
    var list = Object.keys(pinned).map(function (s) { return personBySlug[s]; })
      .filter(Boolean);
    var out = head(esc(t("pin.title")), esc(t("pin.count", { n: list.length })));
    if (!list.length) return out + empty(esc(t("pin.empty")));
    out += '<div class="scroll"><table><thead><tr><th>' + esc(t("col.fighter")) +
      "</th><th>" + esc(t("col.nation")) + "</th>" +
      '<th class="n">' + esc(t("col.bouts")) + "</th><th>" + esc(t("col.record")) +
      "</th><th>" + esc(t("col.medals")) + "</th></tr></thead><tbody>" +
      list.map(function (p) {
        return "<tr><td class=\"name\">" + pLink(p) + "</td>" +
          "<td>" + (p.nats.length ? natHTML(p.nats[0]) : natHTML(-1)) + "</td>" +
          '<td class="n">' + (p.bouts.length || "") + "</td>" +
          "<td>" + (p.bouts.length ? recordHTML(p.w, p.l) : '<span class="gapnote">—</span>') + "</td>" +
          "<td>" + (medalsHTML(p.or, p.ar, p.br) || "") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    return out;
  };

  /* -- choisir le titulaire -------------------------------------------- */
  views.moi = function () {
    var out = head(esc(t("me.title")), esc(t("me.lede")));
    if (titulaire) {
      out += '<div class="card pad"><div class="micro">' + esc(t("me.marked")) +
        '</div><h3 style="font-size:19px;margin-top:8px">' + pLink(titulaire) + "</h3>" +
        '<div class="chips" style="margin-top:12px">' +
        link("#/tireur/" + titulaire.slug, esc(t("me.open")), "chip") +
        '<button class="chip" data-adopt="aucun">' + esc(t("me.clear")) +
        "</button></div></div>";
    } else {
      out += '<div class="card pad"><p style="font-size:14px;color:var(--ink-2)">' +
        esc(t("me.search", { n: num(PEOPLE.length) })) + "</p>" +
        '<div class="chips" style="margin-top:12px">' +
        link("#/", esc(t("me.browse")), "chip");
      if (person[D.owner]) {
        out += '<button class="chip" data-adopt="' + esc(person[D.owner].slug) +
          '">' + esc(person[D.owner].name) + "</button>";
      }
      out += "</div></div>";
    }
    return out;
  };

  /* -- la notice -------------------------------------------------------- */
  views.notice = function () {
    var out = head(esc(t("notice.title")), esc(t("notice.lede")));
    var blocks = ["corners", "scale", "ladder", "cross", "podium", "refuse"];
    /* The notice bodies quote archive-wide figures from the export's report,
       never from the text (guarded by tests/test_notice_figures.py). */
    var nf = {
      redWin: REPORT.red_win_pct == null ? "" : pctOne(REPORT.red_win_pct),
      poules: REPORT.poules_unresolved == null ? "" : num(REPORT.poules_unresolved),
      noWarn: REPORT.bouts_no_warnings == null ? "" : num(REPORT.bouts_no_warnings),
      nations: REPORT.nations_unmatched == null ? "" : num(REPORT.nations_unmatched)
    };
    out += '<div class="grid g2">' + blocks.map(function (b) {
      return '<div class="card pad"><h3 style="font-size:15px">' +
        esc(t("notice." + b + "H")) + "</h3>" +
        '<p style="margin-top:9px;font-size:13.5px;color:var(--ink-2);line-height:1.65">' +
        esc(t("notice." + b + "B", nf)) + "</p></div>";
    }).join("") + "</div>";

    /* The privacy block stands apart because it carries a live contact
       route: the way a data subject consults, corrects or erases their
       data, and the only one there is. */
    out += '<div class="card pad" style="margin-top:14px">' +
      '<h3 style="font-size:15px">' + esc(t("notice.privacyH")) + "</h3>" +
      '<p style="margin-top:9px;font-size:13.5px;color:var(--ink-2);line-height:1.65">' +
      esc(t("notice.privacyB")) + "</p>" +
      '<p style="margin-top:12px">' + link(
        "mailto:" + CONTACT_EMAIL,
        esc(t("notice.contact")) + " — " + esc(CONTACT_EMAIL), "chip") +
      "</p></div>";

    out += section(t("notice.figuresH"), '<div class="card pad">' +
      '<div class="grid g4">' +
      '<div class="stat"><b>' + num(BOUTS.length) + "</b><span>" +
        esc(t("d.bouts")) + "</span></div>" +
      '<div class="stat"><b>' + num(PEOPLE.length) + "</b><span>" +
        esc(t("col.fighters")) + "</span></div>" +
      '<div class="stat"><b>' + num(PLACINGS.length) + "</b><span>" +
        esc(t("col.places")) + "</span></div>" +
      '<div class="stat"><b>' + EVENTS.length + "</b><span>" +
        esc(t("nav.events")) + "</span></div>" +
      "</div></div>");
    return out;
  };

  function notFound(msg) {
    return head(esc(t("nf.title")), "") + empty(esc(msg) + " " +
      link("#/", esc(t("nf.home")), "linky"));
  }

  /* ================================================================
     Sorting
     ================================================================ */

  var filtreTimer = null;
  var sortState = { tireurs: { key: "medals", dir: 1 } };
  var sorters = {
    tireurs: {
      name: function (a, b) { return a.name.localeCompare(b.name); },
      bouts: function (a, b) { return b.bouts.length - a.bouts.length || a.name.localeCompare(b.name); },
      medals: function (a, b) {
        return b.or - a.or || b.ar - a.ar || b.br - a.br ||
          b.bouts.length - a.bouts.length || a.name.localeCompare(b.name);
      }
    }
  };
  function th(key, label, table, n) {
    var st = sortState[table];
    var dir = st.key === key ? (st.dir > 0 ? "descending" : "ascending") : "none";
    return "<th" + (n ? ' class="n"' : "") + ' aria-sort="' + dir +
      '" data-key="' + key + '" data-table="' + table + '">' + esc(label) + "</th>";
  }

  /* ================================================================
     Router
     ================================================================ */

  var ROUTES = [
    [/^\/?$/, "home"],
    [/^\/tireurs$/, "tireurs"],
    [/^\/tireur\/(.+)$/, "tireurPage"],
    [/^\/epreuves$/, "epreuves"],
    [/^\/epreuve\/(.+)$/, "epreuve"],
    [/^\/rencontre\/(\d+)$/, "rencontre"],
    [/^\/nations$/, "nations"],
    [/^\/nation\/(.+)$/, "nation"],
    [/^\/classes$/, "classes"],
    [/^\/classe\/(.+)$/, "classe"],
    [/^\/annee\/(\d{4})$/, "annee"],
    [/^\/confrontation\/(.+)$/, "confrontation"],
    [/^\/epingles$/, "epingles"],
    [/^\/moi$/, "moi"],
    [/^\/notice$/, "notice"],
    [/^\/hasard$/, "hasard"]
  ];

  views.tireurPage = function (q, s) {
    var p = personBySlug[s];
    if (!p) return notFound(t("nf.fighter"));
    return fiche(p);
  };
  views.hasard = function () {
    var i = Math.floor(Math.random() * person.length);
    location.hash = "#/tireur/" + person[i].slug;
    return "";
  };

  var NAV = [
    ["#/", "nav.home"], ["#/tireurs", "nav.fighters"], ["#/epreuves", "nav.events"],
    ["#/nations", "nav.nations"], ["#/classes", "nav.classes"], ["#/notice", "nav.notice"]
  ];

  /* Which nav item a route belongs under. A prefix test cannot do this once
     the register lives at "#/", because every route starts with it. */
  function navFor(path) {
    if (path === "/" || path === "") return "#/";
    if (/^\/(tireurs?|confrontation|epingles|moi)(\/|$)/.test(path)) return "#/tireurs";
    if (/^\/(epreuves?|rencontre|annee)(\/|$)/.test(path)) return "#/epreuves";
    if (/^\/nations?(\/|$)/.test(path)) return "#/nations";
    if (/^\/classes?(\/|$)/.test(path)) return "#/classes";
    if (/^\/notice$/.test(path)) return "#/notice";
    return "";
  }

  function parseHash() {
    var raw = location.hash.replace(/^#/, "") || "/";
    var at = raw.indexOf("?");
    var path = at < 0 ? raw : raw.slice(0, at);
    var q = {};
    if (at >= 0) {
      raw.slice(at + 1).split("&").forEach(function (kv) {
        var p = kv.split("=");
        if (p[0]) q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || "");
      });
    }
    return { path: decodeURIComponent(path), q: q };
  }

  var viewEl = document.getElementById("view");

  var keepScroll = false;

  function render() {
    var r = parseHash();
    usedNotes = [];
    var html = "", matched = false;
    for (var i = 0; i < ROUTES.length; i++) {
      var m = r.path.match(ROUTES[i][0]);
      if (m) {
        matched = true;
        html = views[ROUTES[i][1]](r.q, m[1], m[2]);
        break;
      }
    }
    if (!matched) html = notFound(t("nf.page"));
    viewEl.innerHTML = html + notesHTML();

    var current = navFor(r.path);
    Array.prototype.forEach.call(document.querySelectorAll("#nav a"), function (a) {
      if (a.getAttribute("href") === current) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    drawMine();
    if (!keepScroll) window.scrollTo(0, 0);
    keepScroll = false;
    wire();
  }

  function tableToTSV(table) {
    return Array.prototype.map.call(table.querySelectorAll("tr"), function (tr) {
      return Array.prototype.map.call(tr.querySelectorAll("th,td"), function (c) {
        return (c.innerText || "").replace(/\s+/g, " ").trim();
      }).join("\t");
    }).join("\n");
  }

  /* -- post-render interactivity -------------------------------------- */
  function wire() {
    /* Copy any table as TSV. A published artifact's sandbox blocks downloads
       the page starts itself, so no CSV file is offered - the clipboard is the
       one route out of here that actually works. */
    Array.prototype.forEach.call(viewEl.querySelectorAll("[data-copy]"), function (b) {
      b.addEventListener("click", function () {
        var wrap = b.closest(".section") || viewEl;
        var table = wrap.querySelector("table");
        if (!table || !navigator.clipboard) return;
        navigator.clipboard.writeText(tableToTSV(table)).then(function () {
          var was = b.textContent;
          b.textContent = t("reg.copied");
          setTimeout(function () { b.textContent = was; }, 1400);
        }, function () {
          b.textContent = t("reg.copyRefused");
        });
      });
    });

    /* Poule cross-tables teach their own symmetry: lighting a row lights
       the mirrored column, because the matrix is symmetric by construction. */
    Array.prototype.forEach.call(viewEl.querySelectorAll("table.poule"), function (t) {
      t.addEventListener("mouseover", function (ev) {
        var td = ev.target.closest("td[data-j]");
        clearHi(t);
        if (!td) return;
        var j = td.getAttribute("data-j");
        var tr = td.parentNode;
        tr.classList.add("hi");
        Array.prototype.forEach.call(t.querySelectorAll('td[data-j="' + j + '"]'),
          function (c) { c.classList.add("hi"); });
      });
      t.addEventListener("mouseleave", function () { clearHi(t); });
      t.addEventListener("click", function (ev) {
        var td = ev.target.closest("td[data-bout]");
        if (td && !ev.target.closest("a")) {
          location.hash = "#/rencontre/" + td.getAttribute("data-bout");
        }
      });
    });
    function clearHi(t) {
      Array.prototype.forEach.call(t.querySelectorAll(".hi"), function (x) {
        x.classList.remove("hi");
      });
    }

    /* Sorting */
    Array.prototype.forEach.call(viewEl.querySelectorAll("th[data-key]"), function (h) {
      h.addEventListener("click", function () {
        var table = h.getAttribute("data-table"), key = h.getAttribute("data-key");
        var st = sortState[table];
        if (st.key === key) st.dir = -st.dir; else { st.key = key; st.dir = 1; }
        render();
      });
    });

    /* Pin and adopt */
    Array.prototype.forEach.call(viewEl.querySelectorAll("[data-pin]"), function (b) {
      b.addEventListener("click", function () {
        togglePin(b.getAttribute("data-pin"));
        b.setAttribute("aria-pressed", pinned[b.getAttribute("data-pin")] ? "true" : "false");
      });
    });
    Array.prototype.forEach.call(viewEl.querySelectorAll("[data-adopt]"), function (b) {
      b.addEventListener("click", function () {
        var s = b.getAttribute("data-adopt");
        setTitulaire(s === "aucun" ? null : personBySlug[s] || null);
        render();
      });
    });

    /* Live filtering. The field is re-created by each render, so the caret
       is put back deliberately rather than left wherever the browser drops it. */
    var filtre = viewEl.querySelector("#filtre");
    if (filtre) {
      filtre.addEventListener("input", function () {
        clearTimeout(filtreTimer);
        filtreTimer = setTimeout(function () {
          var value = filtre.value;
          var r = parseHash();
          var q = Object.assign({}, r.q);
          if (value) q.q = value; else delete q.q;
          keepScroll = true;
          try { history.replaceState(null, "", hashOf(r.path, q)); }
          catch (e) { location.hash = hashOf(r.path, q).slice(1); }
          render();
          var again = viewEl.querySelector("#filtre");
          if (again) {
            again.focus();
            try { again.setSelectionRange(value.length, value.length); } catch (e) {}
          }
        }, 130);
      });
    }

    /* Notes */
    Array.prototype.forEach.call(viewEl.querySelectorAll(".croix[data-note]"), function (b) {
      b.addEventListener("click", function () {
        var el = document.getElementById("note-" + b.getAttribute("data-note"));
        if (!el) return;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.remove("flash");
        void el.offsetWidth;
        el.classList.add("flash");
      });
    });
  }

  /* ================================================================
     Command palette
     ================================================================ */

  var index = [];
  person.forEach(function (p) {
    var hint = [];
    if (p.nats.length && nation[p.nats[0]]) hint.push(nation[p.nats[0]].name);
    if (p.bouts.length) hint.push(p.w + "–" + p.l);
    if (p.or) hint.push(t("search.titles", { n: p.or }));
    if (p.years.length) hint.push(p.years[0] + (p.years.length > 1 ? "–" + p.years[p.years.length - 1] : ""));
    index.push({ key: p.key, label: p.name, kind: "tireur",
                 hint: hint.join(" · "), href: "#/tireur/" + p.slug });
  });
  event.forEach(function (e) {
    index.push({
      key: fold(e.name + " " + e.year + " " + (e.label || "") + " " + (e.disc || "")),
      label: e.name, kind: "epreuve",
      hint: [e.year, e.label, e.disc].filter(Boolean).join(" · "),
      href: "#/epreuve/" + e.slug });
  });
  yearList.forEach(function (y) {
    var n = 0, count = 0;
    event.forEach(function (e) {
      if (e.year === y) { n++; count += e.bouts.length + e.places.length; }
    });
    index.push({ key: fold(y), label: y, kind: "annee",
                 hint: t("search.yearHint", { events: n, lines: count }),
                 href: "#/annee/" + y });
  });
  nation.forEach(function (n) {
    if (!n.known || !n.iso) return;
    // n.search carries every attested spelling - Croatie, Kroatien, Croacia,
    // CRO - so a reader finds a nation under the name they know it by.
    index.push({ key: n.search, label: nationName(n), kind: "nation",
                 hint: [n.or ? t("search.titles", { n: n.or }) : "",
                        t("search.nationHint", { n: n.tireurs })]
                   .filter(Boolean).join(" · "),
                 href: "#/nation/" + n.slug });
  });
  klasses.forEach(function (k) {
    index.push({ key: fold(klassLabel(k)), label: klassLabel(k), kind: "categorie",
                 hint: (k.champs.length ? t("search.titles", { n: k.champs.length }) : "") +
                   (k.bouts ? " · " + t("search.bouts", { n: k.bouts }) : ""),
                 href: "#/classe/" + k.key });
  });

  var scrim = null, palInput = null, palList = null, palSel = 0, palHits = [];

  function openPalette() {
    if (scrim) return;
    scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.innerHTML =
      '<div class="palette" role="dialog" aria-modal="true" aria-label="' +
      esc(t("bar.search")) + '">' +
      '<input id="pal-input" type="search" autocomplete="off" spellcheck="false" ' +
      'placeholder="' + esc(t("home.search")) + '" ' +
      'role="combobox" aria-expanded="true" aria-controls="pal-list" aria-autocomplete="list">' +
      '<ul id="pal-list" role="listbox"></ul></div>';
    document.body.appendChild(scrim);
    document.body.style.overflow = "hidden";
    palInput = scrim.querySelector("input");
    palList = scrim.querySelector("ul");
    palInput.addEventListener("input", function () { runPalette(palInput.value); });
    scrim.addEventListener("click", function (e) {
      if (e.target === scrim) closePalette();
    });
    runPalette("");
    palInput.focus();
  }
  function closePalette() {
    if (!scrim) return;
    scrim.remove(); scrim = null; palInput = null; palList = null;
    document.body.style.overflow = "";
  }
  function runPalette(text) {
    var f = fold(text);
    palHits = [];
    if (!f) {
      palHits = index.filter(function (x) { return x.kind === "epreuve"; }).slice(0, 8);
    } else {
      for (var i = 0; i < index.length && palHits.length < 40; i++) {
        if (index[i].key.indexOf(f) >= 0) palHits.push(index[i]);
      }
      palHits.sort(function (a, b) {
        return a.key.indexOf(f) - b.key.indexOf(f) || a.label.length - b.label.length;
      });
    }
    palSel = 0;
    drawPalette();
  }
  function drawPalette() {
    if (!palList) return;
    if (!palHits.length) {
      palList.innerHTML = '<li class="empty">' +
        esc(t("search.none", { q: palInput ? palInput.value : "" })) + "</li>";
      return;
    }
    palList.innerHTML = palHits.map(function (x, i) {
      return '<li role="option" aria-selected="' + (i === palSel) + '">' +
        '<a href="' + esc(x.href) + '">' +
        '<span style="min-width:0;overflow:hidden;text-overflow:ellipsis;' +
        'white-space:nowrap">' + esc(x.label) +
        (x.hint ? ' <span style="color:var(--ink-3);font-size:12px">' +
          esc(x.hint) + "</span>" : "") + "</span>" +
        '<span class="kind">' + esc(kindFR(x.kind) || x.kind) + "</span></a></li>";
    }).join("");
    var sel = palList.children[palSel];
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
  }

  /* ================================================================
     Theme
     ================================================================ */

  var SUN = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<circle cx="8" cy="8" r="3.2" stroke="currentColor" stroke-width="1.5"/>' +
    '<path d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1' +
    'M12.9 12.9l-1.1-1.1M4.2 4.2 3.1 3.1" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round"/></svg>';
  var MOON = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<path d="M13.5 9.6A6 6 0 0 1 6.4 2.5a6 6 0 1 0 7.1 7.1Z" stroke="currentColor" ' +
    'stroke-width="1.5" stroke-linejoin="round"/></svg>';

  var PERSON_ICON = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" ' +
    'aria-hidden="true"><circle cx="8" cy="5.2" r="2.8" stroke="currentColor" ' +
    'stroke-width="1.5"/><path d="M2.6 14c.6-3 2.8-4.4 5.4-4.4S12.8 11 13.4 14" ' +
    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

  var themeBtn = document.getElementById("theme");
  function applyTheme(mode) {
    if (mode === "dark" || mode === "light") {
      document.documentElement.setAttribute("data-theme", mode);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    var dark = mode === "dark" || (mode !== "light" &&
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    themeBtn.innerHTML = dark ? SUN : MOON;
    themeBtn.setAttribute("title", mode === "auto" ? t("bar.themeAuto")
      : dark ? t("bar.themeDark") : t("bar.themeLight"));
    themeBtn.setAttribute("aria-label", t("bar.theme"));
  }
  var themeMode = read("savate.theme", "auto");
  applyTheme(themeMode);
  themeBtn.addEventListener("click", function () {
    themeMode = themeMode === "auto" ? "light" : themeMode === "light" ? "dark" : "auto";
    write("savate.theme", themeMode);
    applyTheme(themeMode);
  });

  /* ================================================================
     Boot
     ================================================================ */

  /* Everything the chrome says is redrawn when the language changes. */
  function boot() {
    document.getElementById("nav").innerHTML = NAV.map(function (n) {
      return '<a href="' + n[0] + '">' + esc(t(n[1])) + "</a>";
    }).join("");

    document.getElementById("foot-count").textContent = t("foot.stats", {
      bouts: num(BOUTS.length), people: num(PEOPLE.length),
      places: num(PLACINGS.length), events: EVENTS.length, years: YEAR_SPAN
    });
    document.getElementById("foot-note").innerHTML = esc(t("foot.note")) + " " +
      link("#/notice", esc(t("foot.notice")));
    document.getElementById("foot-keys").innerHTML = [
      ["/", t("key.search")], ["j</kbd><kbd>k", t("key.walk")],
      ["↵", t("key.open")], ["Esc", t("key.close")]
    ].map(function (k) {
      return "<span><kbd>" + k[0] + "</kbd> " + esc(k[1]) + "</span>";
    }).join("");

    var skip = document.querySelector(".skip");
    if (skip) skip.textContent = t("bar.skip");
    var searchBtn = document.getElementById("search");
    searchBtn.setAttribute("aria-label", t("bar.search"));
    var label = searchBtn.querySelector(".label");
    if (label) label.textContent = t("bar.search");

    document.getElementById("lang").innerHTML = LANGS.map(function (l) {
      return '<option value="' + l + '"' + (l === LANG ? " selected" : "") +
        ">" + esc((STR[l] || {})["lang.name"] || l) + "</option>";
    }).join("");
    document.getElementById("lang").setAttribute("aria-label", t("bar.language"));
    applyTheme(themeMode);
  }

  document.getElementById("search").addEventListener("click", openPalette);
  document.getElementById("lang").addEventListener("change", function (e) {
    setLang(e.target.value);
  });

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault(); openPalette(); return;
    }
    if (scrim) {
      if (e.key === "Escape") { e.preventDefault(); closePalette(); return; }
      if (e.key === "ArrowDown") {
        e.preventDefault(); palSel = Math.min(palSel + 1, palHits.length - 1); drawPalette();
      } else if (e.key === "ArrowUp") {
        e.preventDefault(); palSel = Math.max(palSel - 1, 0); drawPalette();
      } else if (e.key === "Enter" && palHits[palSel]) {
        e.preventDefault(); location.hash = palHits[palSel].href; closePalette();
      }
      return;
    }
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || ""));
    if (typing) return;
    if (e.key === "/") { e.preventDefault(); openPalette(); return; }
    if (e.key === "j" || e.key === "k") {
      e.preventDefault();
      step(e.key === "j" ? 1 : -1);
    }
  });

  /* Walking the page with j/k moves real focus rather than a painted
     highlight, so Enter opens the row the browser already agrees is current,
     and a screen reader is told where it went. */
  function step(by) {
    var rows = Array.prototype.slice.call(
      viewEl.querySelectorAll("tbody td.name a, a.card, a.tie, .chips a.chip"));
    if (!rows.length) return;
    var at = rows.indexOf(document.activeElement);
    var next = at < 0 ? (by > 0 ? 0 : rows.length - 1)
                      : Math.min(rows.length - 1, Math.max(0, at + by));
    rows[next].focus();
    if (rows[next].scrollIntoView) {
      rows[next].scrollIntoView({ block: "nearest" });
    }
  }

  /* Being in the register is a shortcut, not the front page. */
  function drawMine() {
    var el = document.getElementById("mine");
    if (!el) return;
    if (titulaire) {
      el.setAttribute("href", "#/tireur/" + titulaire.slug);
      el.innerHTML = PERSON_ICON + '<span class="label">' + esc(t("bar.mine")) + "</span>";
      el.setAttribute("title", t("bar.mineTitle", { name: titulaire.name }));
    } else {
      el.setAttribute("href", "#/moi");
      el.innerHTML = PERSON_ICON + '<span class="label">' + esc(t("bar.findme")) + "</span>";
      el.setAttribute("title", t("bar.findmeTitle"));
    }
  }

  document.documentElement.setAttribute("lang", LANG);
  boot();
  window.addEventListener("hashchange", render);
  render();
})();
