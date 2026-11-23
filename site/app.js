/* Recon's page: a terminal that knows a few recon commands. The month was decided by the recon command
   (site/data/run.json); a delivery a visitor logs is decided again here by rules.js, the same rules. */
(function () {
  "use strict";
  var R = window.ReconRules;
  var FILM = new URLSearchParams(location.search).has("film") && /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
  var PHONE = window.matchMedia("(max-width: 900px)");
  var D = null;           // run.json
  var extra = [];         // deliveries logged by this visitor
  var res = [], det = {}, counts = {};
  var selected = null, expanded = false, lastOrder = [];
  var history = [], hpos = 0;
  var busy = false;

  var $ = function (id) { return document.getElementById(id); };
  var log = $("log"), input = $("cmd"), list = $("held-list");

  // ---------------------------------------------------------------- storage (this browser only, dropped when the data changes)
  function storeKey() { return "recon-deliveries-" + (D.version || "v1"); }
  function readStore() {
    if (FILM) return [];
    try { var v = JSON.parse(localStorage.getItem(storeKey()) || "[]"); return Array.isArray(v) ? v.filter(validDelivery) : []; } catch (e) { return []; }
  }
  function writeStore() {
    if (FILM) return;
    try { localStorage.setItem(storeKey(), JSON.stringify(extra)); } catch (e) { /* storage blocked: the page still works */ }
  }
  function validDelivery(x) {
    if (!x || typeof x.po !== "string" || !Number.isInteger(x.line) || !Number.isInteger(x.qty) || x.qty <= 0) return false;
    var p = D.inputs.books.purchase_orders.filter(function (o) { return o.id === x.po; })[0];
    return !!p && x.line >= 1 && x.line <= p.lines.length;
  }

  // ---------------------------------------------------------------- deciding
  function books() {
    var b = Object.assign({}, D.inputs.books);
    b.receipts = D.inputs.books.receipts.concat(extra);
    return b;
  }
  function decide() {
    var i = D.inputs, b = books();
    res = R.runMonth(b, i.docs, i.reads, i.rules, i.wording, [], D.month);
    det = {};
    res.forEach(function (r) { det[r.doc] = R.detail(b, r, i.reads[r.doc] || null, i.wording); });
    counts = { documents: res.length, cleared: 0, held: 0, flagged: 0, set_aside: 0 };
    res.forEach(function (r) { counts[r.outcome] += 1; });
  }
  function amountOf(r) {
    if (r.kind === "own_invoice") return D.inputs.books.invoices_out.filter(function (x) { return x.id === r.doc.slice(2); })[0].total;
    var rd = D.inputs.reads[r.doc] || {};
    var v = r.kind === "payment" ? rd.amount : rd.total;
    return typeof v === "number" ? Math.abs(v) : 0;
  }
  function order(a, b) {
    var fa = a.outcome !== "flagged", fb = b.outcome !== "flagged";
    if (fa !== fb) return fa ? 1 : -1;
    // documents held only because the AI wasn't sure go after the concrete problems
    var ua = a.reason === "ai_unsure", ub = b.reason === "ai_unsure";
    if (ua !== ub) return ua ? 1 : -1;
    if (a.received !== b.received) return a.received < b.received ? -1 : 1;
    return a.doc < b.doc ? -1 : 1;
  }
  function pick(which) {
    var want = { held: ["held", "flagged"], cleared: ["cleared"], "set-aside": ["set_aside"] }[which];
    return res.filter(function (r) { return want.indexOf(r.outcome) >= 0; }).sort(order);
  }
  var isCustomer = function (r) { return r.kind === "payment" || r.kind === "own_invoice"; };
  function heldN() { return counts.held + counts.flagged; }
  function countLine() { return counts.cleared + " cleared · " + heldN() + " held · " + counts.set_aside + " set aside"; }

  // ---------------------------------------------------------------- drawing the page
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function renderCounts() {
    $("h-cleared").textContent = counts.cleared;
    $("h-total").textContent = counts.documents;
    $("h-held").textContent = heldN();
    $("h-aside").textContent = counts.set_aside;
    $("held-count").textContent = heldN();
    $("foot-cleared").textContent = counts.cleared + " cleared";
    $("foot-aside").textContent = counts.set_aside + " set aside";
  }
  function heldRow(r, gone) {
    var b = el("button", "row" + (gone ? " gone" : ""));
    b.type = "button";
    b.dataset.doc = r.doc;
    var a = amountOf(r);
    b.appendChild(el("span", "who", r.from_name));
    b.appendChild(el("span", "amt", a ? R.dollars(a) : ""));
    b.appendChild(el("span", "why", gone ? "cleared" : det[r.doc].row));
    if (gone) { b.disabled = true; return b; }
    b.setAttribute("aria-label", r.from_name + (a ? ", " + R.dollars(a) : "") + ", " + det[r.doc].row + ". Show why.");
    if (r.doc === selected) b.setAttribute("aria-current", "true");
    b.addEventListener("click", function () { openDoc(r.doc); });
    return b;
  }
  // gone: documents that just left the held list; they fade in their own place, then the list is drawn again
  function renderHeld(gone) {
    list.textContent = "";
    var now = pick("held");
    var byDoc = {};
    res.forEach(function (r) { byDoc[r.doc] = r; });
    var rows = now;
    if (gone && gone.length) {
      var keep = {};
      now.forEach(function (r) { keep[r.doc] = true; });
      gone.forEach(function (d) { keep[d] = true; });
      rows = lastOrder.filter(function (d) { return keep[d]; }).map(function (d) { return byDoc[d]; });
    }
    var goneSet = {};
    (gone || []).forEach(function (d) { goneSet[d] = true; });
    var limit = PHONE.matches && !expanded ? 6 : Infinity, shown = 0, first = null;
    [["Bills", function (r) { return !isCustomer(r); }], ["Customers", isCustomer]].forEach(function (g) {
      var part = rows.filter(g[1]);
      if (!part.length || shown >= limit) return;
      list.appendChild(el("div", "group", g[0]));
      part.forEach(function (r) {
        if (shown >= limit) return;
        var row = heldRow(r, goneSet[r.doc]);
        if (goneSet[r.doc] && !first) first = row;
        list.appendChild(row);
        shown += 1;
      });
    });
    if (rows.length > shown) {
      var more = el("button", "cmd-link more", "Show " + (rows.length - shown) + " more");
      more.type = "button";
      more.addEventListener("click", function () { expanded = true; renderHeld(); });
      list.appendChild(more);
    }
    if (!rows.length) list.appendChild(el("div", "group", "Nothing held"));
    if (!gone || !gone.length) lastOrder = now.map(function (r) { return r.doc; });
    if (first) {
      list.scrollTop = Math.max(0, first.offsetTop - list.offsetTop - 60);
      setTimeout(function () { renderHeld(); list.scrollTop = 0; fadeHint(); }, FILM ? 0 : 1700);
    }
    fadeHint();
  }
  function fadeHint() {
    list.classList.toggle("has-more", list.scrollHeight - list.clientHeight - list.scrollTop > 8);
  }
  list.addEventListener("scroll", fadeHint);
  window.addEventListener("resize", fadeHint);
  function markSelected(doc) {
    selected = doc;
    Array.prototype.forEach.call(document.querySelectorAll(".row"), function (b) {
      if (b.dataset.doc === doc) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
  }

  // ---------------------------------------------------------------- the log
  // a line is a list of [text, class] pieces (or nodes)
  function line(pieces, cls, parent) {
    var d = el("div", "ln" + (cls ? " " + cls : ""));
    (typeof pieces === "string" ? [[pieces]] : pieces).forEach(function (p) {
      if (p instanceof Node) { d.appendChild(p); return; }
      d.appendChild(p[1] ? el("span", p[1], p[0]) : document.createTextNode(p[0]));
    });
    (parent || log).appendChild(d);
    return d;
  }
  function blank() { line(""); }
  function cmdLine(text) { return line(text, "cmd"); }
  function roomBelow(node) {
    Array.prototype.forEach.call(log.querySelectorAll(".tail"), function (t) { t.parentNode.removeChild(t); });
    if (!node) return;
    var below = log.scrollHeight - (node.offsetTop - log.offsetTop);
    var need = log.clientHeight - below - 4;
    if (need > 0) { var t = el("div", "tail"); t.style.height = need + "px"; log.appendChild(t); }
  }
  function logFade() { log.classList.toggle("has-more", log.scrollHeight - log.clientHeight - log.scrollTop > 8); }
  log.addEventListener("scroll", logFade);
  function scrollTo(node, instant) {
    roomBelow(node);
    var top = node ? node.offsetTop - log.offsetTop - 2 : log.scrollHeight;
    if (instant || FILM) {
      var b = log.style.scrollBehavior;
      log.style.scrollBehavior = "auto";
      log.scrollTop = top;
      log.style.scrollBehavior = b;
    } else {
      log.scrollTop = top;
    }
    setTimeout(logFade, 400);
  }
  function runButton(command, label) {
    var b = el("button", "run", label || command);
    b.type = "button";
    b.addEventListener("click", function () { typeAndRun(command); });
    return b;
  }
  function pad(s, n) { s = String(s); while (s.length < n) s += " "; return s; }
  var cwCache = 0;
  function charWidth() {
    if (cwCache) return cwCache;
    var probe = el("span", "", "0000000000");
    probe.style.visibility = "hidden";
    log.appendChild(probe);
    cwCache = probe.getBoundingClientRect().width / 10 || 9;
    log.removeChild(probe);
    return cwCache;
  }
  window.addEventListener("resize", function () { cwCache = 0; });

  // ---------------------------------------------------------------- commands
  var MONTHS = { "2026-10": "October 2026", "2026-09": "September 2026" };
  var KEY = function () { return D.source === "key"; };

  function doRun() {
    line([[res.length + " documents · " + countLine(), "bright"]]);
    if (KEY()) line([["The answer key stands in for the AI until the scored run.", "dim"]]);
    else {
      var ai = res.filter(function (r) { return r.kind !== "own_invoice"; }).length;
      line([[ai + " read by the AI, " + (res.length - ai) + " of the company's own invoices checked by code", "dim"]]);
    }
  }

  function findDoc(ref) {
    ref = (ref || "").trim().toUpperCase();
    if (!ref) return null;
    var hit = res.filter(function (r) { return r.doc === ref || r.doc === "O-" + ref; })[0];
    if (hit) return hit;
    var hits = res.filter(function (r) { var rd = D.inputs.reads[r.doc]; return rd && (rd.number || "").toUpperCase() === ref; });
    if (hits.length > 1) return { many: hits.map(function (r) { return r.doc; }) };
    return hits[0] || null;
  }
  function found(ref, cmd) {
    var r = findDoc(ref);
    if (!ref) { line("Which document? For example: " + cmd + " D-1002"); return null; }
    if (!r) { line("No document " + ref + " in this run. Try: held"); return null; }
    if (r.many) {
      var pieces = [[ref.toUpperCase() + " is the number on more than one document: "]];
      r.many.forEach(function (doc, k) {
        if (k) pieces.push([" or "]);
        pieces.push(runButton("recon " + cmd + " " + doc, cmd + " " + doc));
      });
      line(pieces);
      return null;
    }
    return r;
  }
  function tag(who) { return who === "ai" ? (KEY() ? "answer key" : "AI") : "code"; }

  function doShow(ref) {
    var r = found(ref, "show");
    if (!r) return;
    var d = det[r.doc];
    markSelected(r.outcome === "held" || r.outcome === "flagged" ? r.doc : null);
    var word = { held: "HELD", flagged: "HELD", cleared: "CLEARED", set_aside: "SET ASIDE" }[d.outcome];
    line([[word + "  ", "bright"], [d.reason, "bright"]]);
    var label = d.doc.replace(/^O-/, "");
    line(label + " · " + d.kind + (d.number && label.indexOf(d.number) < 0 ? " " + d.number : "") + " " + (d.kind === "invoice" ? "to" : "from") + " " + d.from_name);
    var money = [d.amount, d.due ? "due " + d.due : null].filter(function (x) { return x; }).join(" · ");
    if (money) line(money);
    if (d.rows.length) {
      var w0 = Math.max(12, Math.max.apply(null, d.rows.map(function (x) { return x.label.length; })) + 2);
      var cw = [0, 1, 2].map(function (i) { return Math.max(d.columns[i].length, Math.max.apply(null, d.rows.map(function (x) { return x.cells[i].length; }))) + 3; });
      var fits = (w0 + cw.reduce(function (t, x) { return t + x; }, 0) - 3) * charWidth() <= log.clientWidth - 24;
      if (fits) {
        blank();
        var tbl = el("div", "tbl");
        log.appendChild(tbl);
        line([[(pad("", w0) + d.columns.map(function (c, i) { return pad(c, cw[i]); }).join("")).replace(/\s+$/, ""), "dim"]], "pre", tbl);
        d.rows.forEach(function (x) {
          var pieces = [[pad(x.label, w0)]];
          for (var i = 0; i < 3; i++) pieces.push([i === 2 ? x.cells[i] : pad(x.cells[i], cw[i]), x.mark === i ? "mark" : ""]);
          line(pieces, "pre", tbl);
          if (x.sub) line([["  " + x.sub, "dim"]], "pre", tbl);
        });
      } else {
        d.rows.forEach(function (x) {
          blank();
          line([[x.label, "bright"], [x.sub ? "  " + x.sub : "", "dim"]]);
          for (var i = 0; i < 3; i++) if (x.cells[i]) line([[pad(d.columns[i], 12), "dim"], [x.cells[i], x.mark === i ? "mark" : ""]], "hang h14");
        });
      }
    }
    if (d.quote) { blank(); line([[d.quote_label + ": "], ["“" + d.quote + "”", "bright"]]); }
    if (d.next) { blank(); line([[d.next.text + ": "], runButton(d.next.command)]); }
    if (d.steps.length) {
      blank();
      line([["Steps", "dim"]]);
      var tw = KEY() && d.steps.some(function (s) { return s.who === "ai"; }) ? 12 : 7;
      d.steps.forEach(function (s) { line([[pad(tag(s.who), tw), "lav"], [s.text]], tw === 12 ? "hang h14" : "hang h9"); });
    }
    if (d.cleared_notes.length) { blank(); d.cleared_notes.forEach(function (n) { line(n); }); }
    if (d.note) { blank(); noteBlock(d.note); }
  }

  function noteBlock(note) {
    var head = line([["Draft note", "dim"]]);
    var c = el("button", "copy", "Copy");
    c.type = "button";
    head.appendChild(c);
    var n = el("div", "note");
    note.split("\n").forEach(function (t) { line(t, "indent", n); });
    log.appendChild(n);
    c.addEventListener("click", function () {
      var done = function () { c.textContent = "Copied"; setTimeout(function () { c.textContent = "Copy"; }, 1500); };
      var fallback = function () {
        var range = document.createRange();
        range.selectNodeContents(n);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        c.textContent = "Selected";
      };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(note).then(done, fallback);
        else fallback();
      } catch (e) { fallback(); }
    });
  }

  function doNote(ref) {
    var r = found(ref, "note");
    if (!r) return;
    var d = det[r.doc];
    if (!d.note) { line("No note for " + r.doc + ": it was " + (r.outcome === "set_aside" ? "set aside" : r.outcome === "flagged" ? "held" : r.outcome) + "."); return; }
    noteBlock(d.note);
  }

  function doDoc(ref) {
    var r = found(ref, "doc");
    if (!r) return;
    if (r.kind === "own_invoice") {
      line([[r.doc.slice(2) + " is one of " + D.company + "' own invoices, so there is no document to show. Try: "], runButton("recon show " + r.doc, "show " + r.doc)]);
      return;
    }
    markSelected(r.outcome === "held" || r.outcome === "flagged" ? r.doc : null);
    var t = (D.texts[r.doc] || "The text of " + r.doc + " isn't here.").replace(/\s+$/, "");
    var box = el("div", "doc");
    log.appendChild(box);
    // numbered, so "line 15" in a reason can be found; the line the AI doubted is marked
    var doubted = (/line (\d+)/.exec(det[r.doc].reason || "") || [])[1], marked = null;
    t.split("\n").forEach(function (s, i) {
      var n = String(i + 1);
      // long runs of spaces (column padding) are shortened so a line wraps next to its number; the words are unchanged
      var shown = s.replace(/^ {7,}/, "      ").replace(/(\S) {4,}/g, "$1   ");
      var node = line([[pad(n, 4), "dim"], [shown, n === doubted ? "mark" : ""]], "docline", box);
      if (n === doubted) marked = node;
    });
    return marked;
  }

  function doList(which) {
    var rows = pick(which);
    var title = { held: "Held", cleared: "Cleared", "set-aside": "Set aside" }[which];
    line([[title + ": " + rows.length + " of " + counts.documents, "bright"]]);
    var groups = [["Bills", function (r) { return !isCustomer(r); }], ["Customers", isCustomer]];
    var generic = { "matches the order and what arrived": 1, "matches its invoice to the cent": 1, "matches the sales order and the delivery": 1 };
    var what = function (r) {
      var row = det[r.doc].row;
      if (!generic[row]) return row;
      if (r.kind === "own_invoice") return "our invoice " + r.doc.slice(2) + ", matches the delivery";
      if (r.kind === "payment") return "payment for " + (det[r.doc].rows[0] ? det[r.doc].rows[0].label : "an invoice") + ", matches it";
      return "bill " + (det[r.doc].number || r.doc) + ", matches the order";
    };
    groups.forEach(function (g) {
      var part = rows.filter(g[1]);
      if (!part.length) return;
      if (g[0]) line([[g[0].toUpperCase(), "dim"]], "group-ln");
      part.forEach(function (r) {
        var a = amountOf(r);
        var b = el("button", "entry");
        b.type = "button";
        b.appendChild(el("span", "who", r.from_name));
        b.appendChild(el("span", "amt", a ? R.dollars(a) : ""));
        b.appendChild(el("span", "why", what(r)));
        b.addEventListener("click", function () { openDoc(r.doc); });
        log.appendChild(b);
      });
    });
    if (!rows.length) line("  none");
  }

  function doRules() {
    var r = D.inputs.rules;
    [["Quantity", "Billed can't be more than has arrived on that order line."],
      ["Price", "Held if over " + r.price.hold_if_over_percent + "% or $" + r.price.hold_if_over_dollars_per_line + " a line above the order, unless a new price was logged."],
      ["Freight", "Held over $" + r.freight.not_on_the_order_hold_over_dollars + " if not on the order; if on the order, checked against the estimate."],
      ["Tax", "Held if the order expected none."], ["Total", "Lines, freight and tax must add up to the total, to the cent."],
      ["Payments", "Must name an invoice and match it to the cent."], ["Duplicates", "Same supplier and number, or same order line and amount with no new delivery."],
      ["Payee", "A bill from a company other than the one on the order is never cleared."],
      ["AI", "Each document is read twice. An answer counts only if both reads agree and are sure."],
      ["No order", "Suppliers that always bill without an order, like rent, are set aside."], ["Cleared", "A bill is ready for a person to pay; a payment or our own invoice matches."]].forEach(function (x) {
      if (PHONE.matches) { line([[x[0], "lav"]]); line(x[1], "indent"); }
      else line([[pad(x[0], 11), "lav"], [x[1]]], "hang h11");
    });
  }

  function doReceive(args) {
    var lineArg = null, i = args.indexOf("--line");
    if (i >= 0) {
      if (!/^\d+$/.test(args[i + 1] || "")) { line("--line must be a line number, for example: --line 1"); return; }
      lineArg = parseInt(args[i + 1], 10);
      args.splice(i, 2);
    }
    if (args.length < 2) { line("Say the order and how many arrived, for example: receive PO-1188 4"); return; }
    var po = args[0].toUpperCase();
    if (!/^\d+$/.test(args[1])) { line("The quantity must be a whole number, for example: receive PO-1188 4"); return; }
    var qty = parseInt(args[1], 10);
    if (qty <= 0) { line("The quantity must be more than zero."); return; }
    var orderRow = D.inputs.books.purchase_orders.filter(function (p) { return p.id === po; })[0];
    if (!orderRow) { line("No order " + po + "."); return; }
    var b = books();
    var got = function (n) { return b.receipts.filter(function (x) { return x.po === po && x.line === n; }).reduce(function (t, x) { return t + x.qty; }, 0); };
    var pickLine;
    if (lineArg === null) {
      var open = orderRow.lines.filter(function (l) { return l.qty > got(l.line); });
      if (!open.length) { line("Everything on " + po + " has arrived; nothing is still open."); return; }
      if (orderRow.lines.length === 1) pickLine = orderRow.lines[0];
      else if (open.length === 1) pickLine = open[0];
      else { line(po + " has " + orderRow.lines.length + " lines. Say which: receive " + po + " " + qty + " --line N"); return; }
    } else {
      pickLine = orderRow.lines.filter(function (l) { return l.line === lineArg; })[0];
      if (!pickLine) { line(po + " has no line " + lineArg + "."); return; }
    }
    var have = got(pickLine.line), openQty = pickLine.qty - have;
    if (qty > openQty) {
      line(po + " line " + pickLine.line + " has " + openQty + " still open (" + have + " of " + pickLine.qty + " arrived). Recon won't log more than was ordered.");
      return;
    }
    var before = {};
    res.forEach(function (r) { before[r.doc] = r; });
    extra.push({ id: "RC-Y" + ("00" + (extra.length + 1)).slice(-3), po: po, line: pickLine.line, qty: qty, date: D.run_date });
    writeStore();
    decide();
    var changed = res.filter(function (r) { var w = before[r.doc]; return w && (w.outcome !== r.outcome || w.reason !== r.reason); });
    var item = D.inputs.books.items[pickLine.item];
    line("Logged " + qty + " as arrived on " + po + " line " + pickLine.line + " (" + (item.short || item.name) + "). "
      + (have + qty === pickLine.qty ? "All " + pickLine.qty + " have arrived." : (have + qty) + " of " + pickLine.qty + " have arrived."));
    line("Checked the month again.");
    changed.forEach(function (c) {
      var was = before[c.doc].outcome === "flagged" ? "held" : before[c.doc].outcome.replace("_", " ");
      line([["  " + c.doc + " " + c.from_name + ": " + was + " → " + c.outcome.replace("_", " "), "mark"]]);
    });
    if (!changed.length) line("  No document changed.");
    line(countLine());
    var gone = changed.filter(function (c) { return c.outcome === "cleared"; }).map(function (c) { return c.doc; });
    if (gone.indexOf(selected) >= 0) selected = null;
    renderCounts();
    renderHeld(gone);
  }

  function doReset() {
    var n = extra.length;
    extra = [];
    writeStore();
    decide();
    renderCounts();
    renderHeld();
    line("Removed " + n + " logged deliver" + (n === 1 ? "y" : "ies") + ". " + countLine());
  }

  function doHelp() {
    [["show D-1002", "why it was held or cleared"], ["note D-1002", "the drafted note"], ["doc D-1002", "the document as it came in"],
      ["receive PO-1188 4", "log a late delivery and check the month again"], ["held", "list the held documents"], ["cleared", "list the cleared documents"],
      ["set-aside", "list what was set aside for a person"], ["rules", "the rules it decides with"], ["reset", "undo deliveries logged here"], ["clear", "empty this pane"]]
      .forEach(function (x) {
        if (PHONE.matches) { line([runButton(x[0])]); line([[x[1], "dim"]], "indent"); }
        else line([runButton(x[0]), [pad("", Math.max(1, 19 - x[0].length))], [x[1]]], "hang h19");
      });
  }

  function execute(raw) {
    var text = raw.trim().replace(/\s+/g, " ");
    if (!text) return;
    roomBelow(null);
    var start = cmdLine(text.indexOf("recon ") === 0 || text === "clear" || text === "help" ? text : "recon " + text);
    var args = text.split(" ");
    if (args[0] === "recon") args.shift();
    var c = (args.shift() || "").toLowerCase();
    if (c === "clear") { log.textContent = ""; return; }
    if (c === "show") doShow(args[0]);
    else if (c === "note") doNote(args[0]);
    else if (c === "doc") { var marked = doDoc(args[0]); if (marked) { roomBelow(start); log.scrollTop = Math.max(0, marked.offsetTop - log.offsetTop - log.clientHeight / 3); return; } }
    else if (c === "receive") doReceive(args);
    else if (c === "held" || c === "cleared" || c === "set-aside") doList(c);
    else if (c === "rules") doRules();
    else if (c === "reset") doReset();
    else if (c === "run") doRun();
    else if (c === "help" || c === "") doHelp();
    else line("Unknown command " + c + ". Try: help");
    scrollTo(["show", "doc", "rules", "help", "held", "cleared", "set-aside", "receive", "reset"].indexOf(c) >= 0 ? start : null);
  }

  // opening a document from a list starts a fresh pane, so its answer is the only thing in it
  function openDoc(doc) {
    if (busy) return;
    log.textContent = "";
    typeAndRun("recon show " + doc);
    if (PHONE.matches) document.querySelector(".out").scrollIntoView({ behavior: FILM ? "auto" : "smooth", block: "start" });
  }

  // typing a command into the prompt, then running it, the way a person would
  function typeAndRun(command) {
    if (busy) return;
    if (FILM) { execute(command); return; }
    busy = true;
    input.value = "";
    var k = 0;
    var tick = setInterval(function () {
      k += 1;
      input.value = command.slice(0, k);
      if (k >= command.length) {
        clearInterval(tick);
        setTimeout(function () { input.value = ""; busy = false; remember(command); execute(command); }, 90);
      }
    }, 14);
  }
  function remember(command) { history.push(command); hpos = history.length; }

  $("prompt").addEventListener("submit", function (e) {
    e.preventDefault();
    if (busy) return;
    var v = input.value;
    input.value = "";
    if (v.trim()) remember(v.trim());
    execute(v);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowUp" && history.length) { hpos = Math.max(0, hpos - 1); input.value = history[hpos]; e.preventDefault(); }
    if (e.key === "ArrowDown" && history.length) { hpos = Math.min(history.length, hpos + 1); input.value = history[hpos] || ""; e.preventDefault(); }
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-cmd]"), function (b) {
    b.addEventListener("click", function () { if (!busy) { log.textContent = ""; typeAndRun(b.dataset.cmd); } });
  });
  if (PHONE.addEventListener) PHONE.addEventListener("change", function () { if (D) renderHeld(); });

  // ---------------------------------------------------------------- scores
  function scoreTable(S) {
    var a = S.ai.documents, b = S.no_ai ? S.no_ai.documents : null;
    var stopped = S.no_ai && S.no_ai.stopped_on ? Object.keys(S.no_ai.stopped_on).length : 0;
    var t = el("table");
    var head = el("tr");
    ["", "AI", "No-AI reader"].forEach(function (h) { head.appendChild(el("th", "", h)); });
    t.appendChild(head);
    var of = function (n, d) { return n + " of " + d; };
    [["Wrongly cleared", of(a.wrongly_cleared.length, a.problems), b ? of(b.wrongly_cleared.length, b.problems) : ""],
      ["Clean documents cleared", of(a.clean_cleared, a.clean), b ? of(b.clean_cleared, b.clean) : ""],
      ["Held or set aside for the right reason", of(a.right_reason, a.problems), b ? of(b.right_reason, b.problems) : ""],
      ["Held because it wasn't sure", String(a.unsure.length), b ? String(b.unsure.length) + (stopped ? " (it stopped with an error)" : "") : ""],
      ["Sender's reason quoted", of(S.ai.quotes.quoted, S.ai.quotes.had_one), S.no_ai ? "not tried" : ""]]
      .forEach(function (row) {
        var tr = el("tr");
        row.forEach(function (c, i) { tr.appendChild(el(i ? "td" : "th", "", c)); });
        t.appendChild(tr);
      });
    return t;
  }
  function renderScores() {
    var body = $("scores-body");
    body.textContent = "";
    var p = function (t, cls) { body.appendChild(el("p", cls, t)); };
    var S = D.scores && D.scores.readers;
    if (!S || !S.ai) {
      if (KEY()) p("The scored AI run comes next. For now the answer key stands in for the AI, so all " + D.counts.documents + " documents come out as keyed. That tests the rules, not the AI.");
      p("The AI reads the supplier documents and customer payment notes and picks from fixed options. Code checks every number and writes every reason and note.");
      return;
    }
    var F = D.fair_test && D.fair_test.readers;
    var run = S.ai.run || {}, frun = F && F.ai && F.ai.run;
    p("October, scored against an answer key written by AI.");
    body.appendChild(scoreTable(S));
    p("The no-AI reader matched or beat the AI on every decision. Only the AI quoted the sender's reason.", "line");
    if (F && F.ai && F.no_ai) {
      body.appendChild(el("h3", "", "Fair test"));
      p("Freshly written documents neither reader had seen, with the same planted cases.");
      body.appendChild(scoreTable(F));
      p("The no-AI reader was again slightly ahead.", "line");
    }
    if (run.cost_dollars !== undefined) {
      var c1 = "$" + run.cost_dollars.toFixed(3), c2 = frun ? "$" + frun.cost_dollars.toFixed(3) : null;
      p(c2 === null ? "The AI cost " + c1 + "." : c1 === c2 ? "The AI cost " + c1 + " for each of the two tests." : "The AI cost " + c1 + " for October and " + c2 + " for the fair test.", "line");
    }
  }
  $("scores-link").addEventListener("click", function (e) {
    e.preventDefault();
    var s = $("scores");
    s.hidden = false;
    s.scrollIntoView({ behavior: FILM ? "auto" : "smooth", block: "start" });
  });

  // ---------------------------------------------------------------- start
  function firstHeldBill() {
    var d1002 = findDoc("D-1002");
    if (d1002 && d1002.outcome === "held") return "D-1002";
    var b = pick("held").filter(function (r) { return r.outcome === "held" && !isCustomer(r); })[0];
    return b ? b.doc : null;
  }
  function start(data) {
    D = data;
    $("month-name").textContent = MONTHS[D.month] || D.month;
    $("ai-state").hidden = !KEY();
    input.placeholder = PHONE.matches ? "type help, or tap a line" : "click a held line, or type help";
    extra = readStore();
    decide();
    renderCounts();
    renderHeld();
    renderScores();
    if (location.hash === "#scores") { $("scores").hidden = false; setTimeout(function () { $("scores").scrollIntoView(); }, 50); }
    cmdLine("recon run --month " + D.month);
    doRun();
    if (extra.length) line([["You logged " + extra.length + " deliver" + (extra.length === 1 ? "y" : "ies") + " here before. Type reset to put the month back.", "dim"]]);
    var first = firstHeldBill();
    if (first) {
      var s = cmdLine("recon show " + first);
      doShow(first);
      scrollTo(s, true);
    }
    if (FILM) {
      window.__app = {
        apply: function (st) {
          if (st.reset) { extra = []; decide(); renderCounts(); renderHeld(); log.textContent = ""; cmdLine("recon run --month " + D.month); doRun(); }
          if (st.open) { log.textContent = ""; execute("recon show " + st.open); }
          if (st.run) execute(st.run);
          if (st.clear) log.textContent = "";
          if (st.scroll !== undefined) log.scrollTop = st.scroll;
        },
        rows: function () { return pick("held").map(function (r) { return r.doc; }); }
      };
      var sc = document.createElement("script");
      fetch("film.js", { method: "HEAD" }).then(function (r) { if (r.ok) { sc.src = "film.js"; document.body.appendChild(sc); } }).catch(function () {});
    }
  }

  fetch("data/run.json").then(function (r) { return r.json(); }).then(start).catch(function () {
    line("The sample month didn't load. Reload the page to try again.");
  });
})();
