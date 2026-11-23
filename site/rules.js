/* Recon's deciding code, for the page. A line-for-line copy of recon_core.py: the same rules.json, the same order of
   checks, whole cents only. tests/parity.py runs both on the same month (and after logged deliveries) and fails on
   any difference. Works in the browser (window.ReconRules) and in Node (require). */
(function (root) {
  "use strict";

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function commas(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function money(c) {
    var sign = c < 0 ? "-" : "";
    c = Math.abs(Math.trunc(c));
    var cents = c % 100;
    return sign + "$" + commas(Math.floor(c / 100)) + "." + (cents < 10 ? "0" : "") + cents;
  }
  function dollars(c) {
    var sign = c < 0 ? "-" : "";
    return sign + "$" + commas(Math.floor((Math.abs(Math.trunc(c)) + 50) / 100));
  }
  function halfUp(x) {
    return Math.floor(x + 0.5);
  }
  function normNumber(s) {
    s = (s || "").toUpperCase().replace(/[\s\-_/]/g, "");
    return s.replace(/(\D)0+(?=\d)/g, "$1");
  }
  function day(iso) {
    var p = iso.split("-");
    return MONTHS[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10);
  }
  function show(v) {
    if (typeof v === "number" && Number.isInteger(v)) return commas(v);
    return v === null ? "None" : String(v);
  }
  function fill(template, values) {
    return template.replace(/\[(\w+)\]/g, function (m, k) {
      if (!Object.prototype.hasOwnProperty.call(values, k)) return "[" + k + "]";
      return show(values[k]);
    });
  }
  function sum(xs, f) {
    var t = 0;
    for (var i = 0; i < xs.length; i++) t += f(xs[i]);
    return t;
  }
  function find(xs, f) {
    for (var i = 0; i < xs.length; i++) if (f(xs[i])) return xs[i];
    return null;
  }
  function copy(o) {
    var r = {};
    for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) r[k] = o[k];
    return r;
  }

  function Books(books, extraReceipts, monthStart) {
    this.b = books;
    this.applied = books.bank_lines.filter(function (x) {
      return x.applied_to && (monthStart == null || x.date < monthStart);
    });
    this.entered = books.bills_entered.filter(function (e) { return monthStart == null || e.date < monthStart; });
    this.po = {};
    var self = this;
    books.purchase_orders.forEach(function (p) { self.po[p.id] = p; });
    this.items = books.items;
    this.suppliers = books.suppliers;
    this.customers = books.customers;
    this.receipts = books.receipts.concat(extraReceipts || []);
    this.invoices = {};
    books.invoices_out.forEach(function (i) { self.invoices[i.id] = i; });
  }
  Books.prototype.poLine = function (pid, n) { return this.po[pid].lines[n - 1]; };
  Books.prototype.received = function (pid, n, by) {
    return sum(this.receipts.filter(function (r) { return r.po === pid && r.line === n && (by == null || r.date <= by); }), function (r) { return r.qty; });
  };

  var BOX_UNITS = ["BX", "BOX", "PK", "CS"];
  var SAME_UNIT = { PC: "EA", PCS: "EA", EACH: "EA" };
  function unitOf(u) {
    u = (u || "").toUpperCase();
    return Object.prototype.hasOwnProperty.call(SAME_UNIT, u) ? SAME_UNIT[u] : u;
  }
  function whole(x) { return typeof x === "number" && Number.isInteger(x); }
  // Python's sense of "true": empty lists, empty strings, 0 and nothing are false
  function truthy(v) {
    if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  }

  function decideSupplierDoc(B, read, state, rules, wording) {
    var steps = [];
    var sup = read.from;
    function R(outcome, reason, values, note, at) {
      return { outcome: outcome, reason: reason, values: values || {}, steps: steps, note_key: note === undefined ? null : note, at: at === undefined ? null : at };
    }
    var supplier = Object.prototype.hasOwnProperty.call(B.suppliers, sup) ? B.suppliers[sup] : null;
    var kind = read.kind || "bill";
    if (truthy(read.unsure)) return R("held", "ai_unsure", { what: read.unsure });
    if (kind === "bank_change" || truthy(read.asks_bank_change)) return R("flagged", "bank_details_change", { supplier: supplier ? supplier.name : "the sender" }, "bank_details_change");
    if (!supplier) return R("held", "unknown_supplier");
    if (kind === "statement") return R("set_aside", "statement");
    if (kind === "pro_forma") return R("set_aside", "pro_forma");
    if (kind === "packing_slip") return R("set_aside", "packing_slip", { for_doc: read.for_doc || "a bill" });
    var lines = read.lines || [];
    var number = read.number || "";
    var i, e, l, at;
    for (i = 0; i < state.bills.length; i++) {
      var earlier = state.bills[i];
      if (earlier.from === sup && number && normNumber(earlier.number) === normNumber(number)) {
        if ((earlier.total === undefined ? null : earlier.total) !== (read.total === undefined ? null : read.total)) {
          return R("held", "corrected_bill", { original: earlier.number, received: day(earlier.date) }, "corrected_bill");
        }
        return R("held", "duplicate_same_number", { original: earlier.number, received: day(earlier.date) }, "duplicate_same_number");
      }
    }
    for (i = 0; i < B.entered.length; i++) {
      e = B.entered[i];
      if (e.supplier === sup && number && normNumber(e.number) === normNumber(number)) {
        return R("held", "duplicate_entered", { original: e.number, received: day(e.date) }, "duplicate_same_number");
      }
    }
    if (supplier.billing === "no_po") return R("set_aside", "no_po_supplier");
    if (!lines.length) return R("held", "no_lines");
    var tk = ["total", "freight", "tax"];
    for (i = 0; i < tk.length; i++) {
      if (read[tk[i]] !== undefined && read[tk[i]] !== null && !whole(read[tk[i]])) return R("held", "ai_unsure", { what: "the totals" });
    }
    for (at = 0; at < lines.length; at++) {
      l = lines[at];
      if (!(whole(l.qty) && whole(l.price) && whole(l.amount))) return R("held", "ai_unsure", { what: "the numbers on line " + (at + 1) }, null, at);
      if (l.qty * l.price !== l.amount) {
        return R("held", "line_amount", { n: at + 1, qty: l.qty, price: money(l.price), should: money(l.qty * l.price), amount: money(l.amount) }, "line_amount", at);
      }
    }
    if (kind === "bill" && (lines.some(function (x) { return x.qty <= 0 || x.price < 0; }) || (read.total !== undefined && read.total !== null && read.total <= 0))) {
      return R("held", "negative_amounts");
    }
    var freight = read.freight || 0, tax = read.tax || 0, total = read.total || 0;
    var sums = sum(lines, function (x) { return x.amount; }) + freight + tax;
    if (kind === "credit_note" && sums !== total) return R("held", "arithmetic", { sum: money(sums), total: money(total) }, "arithmetic");
    if (kind === "credit_note") {
      var l0 = lines[0];
      var ret = find(B.b.returns, function (r) { return r.supplier === sup && r.item === l0.item && r.qty === Math.abs(l0.qty); });
      steps.push({ who: "code", text: "Looked for the return behind this credit: " + (ret ? ret.id : "none") });
      if (!ret) return R("held", "credit_no_return", null, "credit_no_return");
      var credit = Math.abs(read.total || 0);
      if (state.returns_used.has(ret.id)) return R("held", "credit_used", { return: ret.id }, "credit_used");
      if (credit !== ret.amount) return R("held", "credit_mismatch", { credit: money(credit), return: ret.id, return_amount: money(ret.amount) }, "credit_mismatch");
      state.returns_used.add(ret.id);
      return R("set_aside", "credit_available", { credit: money(credit), return: ret.id });
    }
    for (i = 0; i < B.entered.length; i++) {
      e = B.entered[i];
      if (e.supplier !== sup || !e.po) continue;
      var ee = e;
      var sameLine = lines.some(function (x) { return x.po === ee.po && x.po_line === ee.po_line; });
      if (sameLine && read.total === e.amount) {
        if (!B.receipts.some(function (r) { return r.po === ee.po && r.line === ee.po_line && r.date > ee.date; })) {
          return R("held", "duplicate_new_number", { original_number: e.number }, "duplicate_new_number");
        }
      }
    }

    var amb = read.order_ambiguous || [];
    if (amb.length >= 2) return R("held", "ambiguous_order", { a: amb[0], b: amb[1] }, "ambiguous_order");
    for (at = 0; at < lines.length; at++) {
      l = lines[at];
      if (!l.po) {
        steps.push({ who: "code", text: "Searched every supplier's open orders: none fits" });
        return R("held", "no_order", null, "no_order");
      }
      var p = Object.prototype.hasOwnProperty.call(B.po, l.po) ? B.po[l.po] : null;
      if (!p || !whole(l.po_line) || !(l.po_line >= 1 && l.po_line <= p.lines.length)) return R("held", "unknown_order", { po: l.po }, null, at);
      if (p.supplier !== sup) {
        var maker = B.suppliers[p.supplier].name;
        steps.push({ who: "code", text: "Searched every supplier's open orders: " + p.id + " with " + maker });
        return R("held", "different_payee", { supplier: supplier.name, po: p.id, maker: maker }, "different_payee");
      }
    }

    var notes = [];
    var thisBill = {};
    for (at = 0; at < lines.length; at++) {
      l = lines[at];
      var ol = B.poLine(l.po, l.po_line);
      var item = B.items[ol.item];
      if (l.item !== ol.item) {
        return R("held", "substituted_part", { billed_part: l.item || "a part with no number", ordered_part: ol.item, po: l.po }, "substituted_part", at);
      }
      var qty = l.qty, conv = 1;
      var billedUnit = unitOf(l.unit), orderUnit = unitOf(ol.unit);
      if (billedUnit !== orderUnit) {
        var pack = item.pack;
        if (BOX_UNITS.indexOf(billedUnit) < 0 || !pack) {
          return R("held", "unit_unknown", { boxes: qty, unit: billedUnit === "BX" || billedUnit === "BOX" ? "boxes" : (l.unit || "no unit"), order_qty: ol.qty, po: l.po }, "unit_unknown", at);
        }
        steps.push({ who: "code", text: commas(qty) + " " + l.unit + " at " + commas(pack) + " per box is " + commas(qty * pack) + " pieces" });
        qty = qty * pack;
        conv = pack;
      }
      var ll = l;
      var billedBefore = sum(state.billed_lines.filter(function (x) { return x.po === ll.po && x.po_line === ll.po_line; }), function (x) { return x.qty; });
      billedBefore += sum(B.entered.filter(function (x) { return x.po === ll.po && x.po_line === ll.po_line; }), function (x) { return x.qty || 0; });
      var lineKey = l.po + "#" + l.po_line;
      billedBefore += thisBill[lineKey] || 0;
      if (billedBefore + qty > ol.qty) {
        return R("held", "billed_beyond_ordered", { billed: billedBefore + qty, ordered: ol.qty, po: l.po, item: item.short || item.name }, "billed_beyond_ordered", at);
      }
      var received = B.received(l.po, l.po_line);
      if (billedBefore + qty > received) {
        var slip = read.packing_slip;
        if (slip == null) slip = find(state.slips, function (s) { return s.po === ll.po && s.po_line === ll.po_line; });
        steps.push({ who: slip ? "ai" : "code", text: "Looked for a packing slip: " + (slip ? "found, " + commas(slip.qty) + " shipped " + day(slip.date) : "none") });
        var v = { billed: billedBefore + qty, received: received, po: l.po, item: item.short || item.name };
        if (slip && slip.qty >= billedBefore + qty) {
          v.slip_shipped = slip.qty;
          v.slip_date = day(slip.date);
          return R("held", "receipt_not_logged", v, "receipt_not_logged", at);
        }
        if (billedBefore) return R("held", "billed_beyond_received", v, "billed_beyond_received", at);
        return R("held", "qty_over_received", v, "qty_over_received", at);
      }
      var orderPrice = ol.price * conv;
      var over = l.price - orderPrice;
      if (over > 0) {
        var overLine = over * l.qty;
        if (over * 100 > rules.price.hold_if_over_percent * orderPrice || overLine > rules.price.hold_if_over_dollars_per_line * 100) {
          var change = find(B.b.price_changes, function (c) {
            return c.supplier === sup && c.item === ol.item && c.new * conv === ll.price && c.logged <= read.date && (c.from || "") <= read.date && (c.po == null || c.po === ll.po);
          });
          var shown = money(halfUp(l.price / conv));
          steps.push({ who: "code", text: "Looked for a price change someone logged: " + (change ? "found, by " + change.logged_by + ", " + day(change.logged) : "none") });
          if (change) {
            notes.push(["price_change_logged", { logged_by: change.logged_by, logged: day(change.logged) }]);
          } else {
            return R("held", "price_over", { price: shown, order_price: money(ol.price), po: l.po, item: item.short || item.name }, "price_over", at);
          }
        } else {
          var tenths = halfUp(over * 1000 / orderPrice);
          notes.push(["price_within_rule", { pct: Math.floor(tenths / 10) + "." + (tenths % 10) + "%" }]);
        }
      } else if (over < 0) {
        notes.push(["price_under", {}]);
      }
      thisBill[lineKey] = (thisBill[lineKey] || 0) + qty;
    }

    var p0 = B.po[lines[0].po];
    if (freight) {
      if (p0.freight === "not on the order") {
        if (freight > rules.freight.not_on_the_order_hold_over_dollars * 100) return R("held", "freight_not_ordered", { freight: money(freight), po: p0.id }, "freight_not_ordered");
        notes.push(["freight_small", { freight: money(freight) }]);
      } else {
        var estimate = p0.freight_estimate || 0;
        var extraF = freight - estimate;
        if (extraF > 0 && (extraF * 100 > rules.price.hold_if_over_percent * estimate || extraF > rules.price.hold_if_over_dollars_per_line * 100)) {
          return R("held", "freight_over_estimate", { freight: money(freight), estimate: money(estimate), po: p0.id }, "freight_over_estimate");
        }
      }
    }
    if (tax && p0.tax === "none") return R("held", "tax_not_expected", { tax: money(tax), po: p0.id }, "tax_not_expected");
    if (sums !== total) return R("held", "arithmetic", { sum: money(sums), total: money(total) }, "arithmetic");
    var r = R("cleared", null);
    r.cleared_notes = notes.map(function (n) { return fill(wording.cleared_notes[n[0]], n[1]); });
    return r;
  }

  function decideOwnInvoice(B, invId) {
    var inv = B.invoices[invId];
    var dels = B.b.deliveries.filter(function (d) { return d.so === inv.so; });
    for (var at = 0; at < inv.lines.length; at++) {
      var l = inv.lines[at];
      var onLine = dels.filter(function (d) { return d.line === l.so_line; });
      var byInvoice = sum(onLine.filter(function (d) { return d.date <= inv.date; }), function (d) { return d.qty; });
      if (byInvoice === 0 && onLine.length) {
        var first = onLine.map(function (d) { return d.date; }).sort()[0];
        return { outcome: "held", reason: "invoiced_before_delivery", values: { invoiced: day(inv.date), delivered: day(first), invoice: invId }, steps: [], note_key: "invoiced_before_delivery", at: at };
      }
      if (l.qty > byInvoice) {
        var prod = B.b.products[l.product];
        return { outcome: "held", reason: "invoiced_more_than_delivered", values: { invoiced: l.qty, delivered: byInvoice, invoice: invId,
          item: prod.plural || prod.name }, steps: [], note_key: "invoiced_more_than_delivered", at: at };
      }
      var so = find(B.b.sales_orders, function (s) { return s.id === inv.so; });
      var sol = find((so || {}).lines || [], function (x) { return x.line === l.so_line; });
      var differs = null;
      if (!sol) differs = ["sales order line", "line " + l.so_line, "no such line"];
      else if (l.price !== sol.price) differs = ["price", money(l.price), money(sol.price)];
      else if (l.qty > sol.qty) differs = ["quantity", commas(l.qty), commas(sol.qty)];
      else if (l.qty * l.price !== l.amount) differs = ["line amount", money(l.amount), money(l.qty * l.price)];
      if (differs) {
        return { outcome: "held", reason: "invoice_differs", values: { what: differs[0], invoiced: differs[1], ordered: differs[2], invoice: invId },
          steps: [], note_key: "invoice_differs", at: at };
      }
    }
    var lineSum = sum(inv.lines, function (x) { return x.amount; });
    if (lineSum !== inv.total) {
      return { outcome: "held", reason: "invoice_differs", values: { what: "total", invoiced: money(inv.total), ordered: money(lineSum), invoice: invId },
        steps: [], note_key: "invoice_differs", at: null };
    }
    return { outcome: "cleared", reason: null, values: {}, steps: [], note_key: null, at: null };
  }

  function decidePayment(B, read, state) {
    var cust = read.from;
    var steps = [];
    function R(outcome, reason, values, note) {
      return { outcome: outcome, reason: reason, values: values || {}, steps: steps, note_key: note === undefined ? null : note, at: null };
    }
    if (!Object.prototype.hasOwnProperty.call(B.customers, cust)) return R("held", "unknown_customer");
    if (truthy(read.unsure)) return R("held", "ai_unsure", { what: read.unsure });
    var amount = read.amount;
    if (!whole(amount)) return R("held", "ai_unsure", { what: "the amount" });
    var openInv = B.b.invoices_out.filter(function (i) {
      return i.customer === cust && !B.applied.some(function (b) { return b.applied_to === i.id; }) && !state.paid.has(i.id);
    });
    var match = openInv.filter(function (i) { return i.total === amount; }).map(function (i) { return i.id; });
    var named = read.invoices_named || [];
    var looked = "Open invoices to " + B.customers[cust].name + " for " + money(amount) + ": " + (match.join(", ") || "none");
    if (!named.length) {
      steps.push({ who: "code", text: looked });
      if (!match.length) return R("held", "names_no_invoice_unmatched", { amount: money(amount) }, "names_no_invoice_unmatched");
      return R("held", "names_no_invoice", { suggested: match.join(", "), amount: money(amount) }, "names_no_invoice");
    }
    var i, n;
    for (i = 0; i < named.length; i++) {
      n = named[i];
      var inv = Object.prototype.hasOwnProperty.call(B.invoices, n) ? B.invoices[n] : null;
      if (!inv) return R("held", "unknown_invoice", { named: n, amount: money(amount) }, "unknown_invoice");
      if (inv.customer !== cust) return R("held", "other_customer_invoice", { named: n, billed_to: B.customers[inv.customer].name, amount: money(amount) }, "other_customer_invoice");
    }
    for (i = 0; i < named.length; i++) {
      n = named[i];
      var nn = n;
      var paidBefore = find(B.applied, function (b) { return b.applied_to === nn; });
      if (paidBefore || state.paid.has(n)) {
        steps.push({ who: "code", text: looked });
        if (match.length) return R("held", "names_paid_invoice", { named: n, suggested: match.join(", "), amount: money(amount) }, "names_paid_invoice");
        return R("held", "paid_twice", { invoice: n, paid_on: paidBefore ? "on " + day(paidBefore.date) : "earlier this month" }, "paid_twice");
      }
    }
    var due = sum(named, function (x) { return B.invoices[x].total; });
    if (amount < due) return R("held", "paid_short", { short_by: money(due - amount), short_by_dollars: dollars(due - amount), invoice: named.join(", "), line: read.explanation_line || "" },
      read.explanation_line ? "paid_short" : "paid_short_no_note");
    if (amount > due) return R("held", "paid_over", { over_by: money(amount - due), over_by_dollars: dollars(amount - due), invoice: named.join(", ") }, "paid_over");
    named.forEach(function (x) { state.paid.add(x); });
    return R("cleared", null);
  }

  function runMonth(books, docs, reads, rules, wording, extraReceipts, month) {
    month = month || docs.map(function (d) { return d.received; }).sort()[0].slice(0, 7);
    var B = new Books(books, extraReceipts, month + "-01");
    var state = { bills: [], billed_lines: [], slips: [], paid: new Set(), returns_used: new Set() };
    var paidBy = {};
    docs.forEach(function (d) {
      var r = reads[d.doc];
      if (r && r.kind === "packing_slip") {
        (r.lines || []).forEach(function (l) {
          if (l && l.po && whole(l.po_line) && whole(l.qty)) state.slips.push({ po: l.po, po_line: l.po_line, qty: l.qty, date: r.date || d.received, doc: d.doc });
        });
      }
    });
    var sorted = docs.slice().sort(function (x, y) {
      if (x.received !== y.received) return x.received < y.received ? -1 : 1;
      return x.doc < y.doc ? -1 : x.doc > y.doc ? 1 : 0;
    });
    var results = [];
    var unsure = function () { return { outcome: "held", reason: "could_not_decide", values: {}, steps: [], note_key: null, at: null }; };
    sorted.forEach(function (d) {
      var res, r;
      if (d.kind !== "own_invoice") {
        r = copy(reads[d.doc]);
        if (!r.date) r.date = d.received;
      }
      if (d.kind === "own_invoice") {
        res = decideOwnInvoice(B, d.invoice);
      } else if (d.kind === "payment") {
        try { res = decidePayment(B, r, state); } catch (err) { res = unsure(); }
        if (res.outcome === "cleared") {
          (r.invoices_named || []).forEach(function (n) { paidBy[n] = { doc: d.doc, date: d.received }; });
        }
      } else {
        if (r.kind === "packing_slip") {
          var first = ((r.lines || [])[0] || {}).po;
          var covered = first ? find(docs, function (x) {
            var rx = reads[x.doc] || {};
            return x.doc !== d.doc && rx.kind === "bill" && (rx.lines || []).some(function (l) { return l.po === first; });
          }) : null;
          r = copy(r);
          r.for_doc = covered ? covered.doc : "a bill";
        }
        try { res = decideSupplierDoc(B, r, state, rules, wording); } catch (err) { res = unsure(); }
        if (((r.kind || "bill") === "bill" || r.kind === "credit_note") && r.number) {
          state.bills.push({ doc: d.doc, from: r.from, number: r.number, total: r.total, date: r.date });
        }
        if (res.outcome === "cleared") {
          (r.lines || []).forEach(function (l) {
            var olUnit = B.poLine(l.po, l.po_line).unit;
            var q = unitOf(l.unit) !== unitOf(olUnit) ? l.qty * (B.items[l.item].pack || 1) : l.qty;
            state.billed_lines.push({ po: l.po, po_line: l.po_line, qty: q });
          });
        }
      }
      res.doc = d.doc;
      res.case = d.case === undefined ? null : d.case;
      res.kind = d.kind;
      res.from = d.from;
      res.from_name = d.from_name;
      res.received = d.received;
      res.format = d.format;
      res.reason_row = res.reason ? fill(wording.reasons[res.reason].row, res.values) : null;
      res.reason_full = res.reason ? fill(wording.reasons[res.reason].full, res.values) : null;
      results.push(res);
    });
    results.forEach(function (res) {
      if (res.kind === "own_invoice") res.paid_by = Object.prototype.hasOwnProperty.call(paidBy, res.doc.slice(2)) ? paidBy[res.doc.slice(2)] : null;
    });
    return results;
  }

  function draftNote(res, read, books, wording) {
    var key = res.note_key;
    if (!key) return null;
    var v = copy(res.values);
    function setdefault(k, val) { if (!Object.prototype.hasOwnProperty.call(v, k)) v[k] = val; }
    if (res.kind === "payment") {
      setdefault("customer", res.from_name);
      setdefault("amount", read ? money(read.amount) : "");
    } else {
      setdefault("supplier", res.from_name);
      setdefault("number", read ? read.number || "" : "");
      if (read && read.lines && read.lines.length) {
        var l0 = read.lines[0];
        setdefault("po", l0.po || "");
        if (l0.item) {
          var it = books.items[l0.item];
          setdefault("item", it.short || it.name);
        }
      }
    }
    return fill(wording.notes[key], v);
  }

  var UNIT_SHOWN = { EA: "", MO: "month" };
  var KIND_WORD = { bill: "bill", credit_note: "credit note", statement: "statement", pro_forma: "pro forma", packing_slip: "packing slip",
    bank_change: "email", payment: "payment", own_invoice: "invoice" };
  var SAYS = { printed: "The bill says", email: "The email says", sheet: "The sheet says" };
  var KIND_SAYS = { credit_note: "The credit note says", packing_slip: "The slip says", pro_forma: "The pro forma says", statement: "The statement says" };
  var KIND_COL = { bill: "on the bill", credit_note: "on the credit", packing_slip: "on the slip", pro_forma: "on the pro forma",
    statement: "on the statement", bank_change: "on the email" };
  var CLEARED = { payment: "Matches its invoice to the cent.", own_invoice: "Matches the sales order and the delivery." };
  var MARK = { qty_over_received: 2, receipt_not_logged: 2, billed_beyond_received: 2, price_over: 0, unit_unknown: 0, substituted_part: 0, line_amount: 0,
    invoiced_before_delivery: 1, invoiced_more_than_delivered: 1 };
  var has = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); };

  function addDays(iso, n) {
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function q(n, unit) {
    var u = has(UNIT_SHOWN, unit) ? UNIT_SHOWN[unit] : unit;
    if (u === "month" && Math.abs(n) !== 1) u = "months";
    return u ? commas(n) + " " + u : commas(n);
  }
  function lineOnFile(B, l) {
    var p = l.po && Object.prototype.hasOwnProperty.call(B.po, l.po) ? B.po[l.po] : null;
    var n = l.po_line;
    return p && whole(n) && n >= 1 && n <= p.lines.length ? p.lines[n - 1] : null;
  }
  function num(v) { return typeof v === "number" && isFinite(v); }
  function lowerFirst(s) {
    s = s.replace(/\.+$/, "");
    return s.slice(0, 1).toLowerCase() + s.slice(1);
  }

  function detail(books, res, read, wording) {
    var B = new Books(books);
    if (read && !read.date) { read = copy(read); read.date = res.received; }
    var kind = res.kind;
    var rkind = read ? (read.kind || (kind === "supplier" ? "bill" : kind)) : kind;
    var side = kind === "payment" || kind === "own_invoice" ? "customer" : "supplier";
    var rows = [];
    var notes = (res.cleared_notes || []).slice();
    var headline, row;
    if (res.outcome === "cleared") {
      headline = notes.length ? notes.shift() : (has(CLEARED, kind) ? CLEARED[kind] : "Matches the order and what arrived.");
      row = lowerFirst(headline);
    } else {
      headline = res.reason_full;
      row = res.reason_row;
    }
    var out = {
      doc: res.doc, kind: has(KIND_WORD, rkind) ? KIND_WORD[rkind] : rkind, from_name: res.from_name, outcome: res.outcome,
      reason: headline, row: row, number: null, amount: null, due: null,
      columns: side === "supplier" ? [has(KIND_COL, rkind) ? KIND_COL[rkind] : "on the bill", "ordered", "arrived"] : ["invoiced", "delivered", "paid"],
      rows: rows, quote: null, quote_label: null, steps: res.steps || [], cleared_notes: notes,
      note: draftNote(res, read, books, wording), next: null, reason_code: res.reason
    };
    var mark = has(MARK, res.reason) ? MARK[res.reason] : null;
    if (kind === "own_invoice") {
      var inv = B.invoices[res.doc.replace("O-", "")];
      out.number = inv.id;
      out.amount = money(inv.total);
      out.due = day(addDays(inv.date, inv.due_days));
      var paid = find(books.bank_lines, function (b) { return b.applied_to === inv.id; });
      var by = res.paid_by;
      inv.lines.forEach(function (l, at) {
        var dels = books.deliveries.filter(function (d) { return d.so === inv.so && d.line === l.so_line; });
        var got = sum(dels, function (d) { return d.qty; });
        var last = dels.map(function (d) { return d.date; }).sort().pop();
        var paidCell = by ? by.doc + ", " + day(by.date) : paid ? money(paid.amount) + ", " + day(paid.date) : "not yet";
        rows.push({ label: books.products[l.product].name, sub: inv.so,
          cells: [commas(l.qty) + ", " + day(inv.date), dels.length ? commas(got) + ", " + day(last) : "none yet", paidCell],
          mark: res.at === at ? mark : null });
      });
      return out;
    }
    if (kind === "payment") {
      var paidAmount = num(read.amount) ? money(read.amount) : "?";
      out.amount = paidAmount;
      var named = read.invoices_named || [];
      var suggested = (res.values.suggested || "").split(",").map(function (x) { return x.trim(); }).filter(function (x) { return x && x !== "none"; });
      named.concat(suggested.filter(function (x) { return named.indexOf(x) < 0; })).forEach(function (n) {
        var inv2 = B.invoices[n];
        if (!inv2) return;
        var got2 = sum(books.deliveries.filter(function (d) { return d.so === inv2.so; }), function (d) { return d.qty; });
        var want = sum(inv2.lines, function (l) { return l.qty; });
        var before = find(B.applied, function (b) { return b.applied_to === n; });
        var namedOrInvoice = has(res.values, "named") ? res.values.named : res.values.invoice;
        var earlier = (res.reason === "names_paid_invoice" || res.reason === "paid_twice") && namedOrInvoice === n;
        rows.push({ label: n, sub: named.indexOf(n) >= 0 ? "named on the payment" : "suggested",
          cells: [money(inv2.total), want && got2 === want ? "all" : commas(got2) + " of " + commas(want), before ? "paid " + day(before.date) : earlier ? "paid earlier" : "not yet"],
          mark: earlier ? 2 : null });
      });
      rows.push({ label: "This payment", sub: day(read.date), cells: ["", "", paidAmount],
        mark: ["paid_short", "paid_over", "names_no_invoice"].indexOf(res.reason) >= 0 ? 2 : null });
      if (read.explanation_line) { out.quote = read.explanation_line; out.quote_label = "Their note says"; }
      return out;
    }
    out.number = read.number || null;
    out.amount = num(read.total) && read.total ? money(Math.abs(read.total)) : null;
    if (read.terms_days && read.date && rkind === "bill" && res.reason !== "duplicate_same_number" && res.reason !== "duplicate_new_number") {
      out.due = day(addDays(read.date, read.terms_days));
    }
    var amb = res.reason === "ambiguous_order" ? res.values : null;
    (read.lines || []).forEach(function (l, at) {
      var ol = lineOnFile(B, l);
      var it = B.items[l.item || ""] || {};
      var label = l.item || (l.unit === "MO" ? "monthly charge" : "no part number");
      var bill = (num(l.qty) ? q(Math.abs(l.qty), l.unit) : "?") + (num(l.price) && l.price ? " × " + money(l.price) : "");
      var la = null, lb = null;
      if (amb && B.po[amb.a] && B.po[amb.b]) {
        la = find(B.po[amb.a].lines, function (x) { return x.item === l.item; });
        lb = find(B.po[amb.b].lines, function (x) { return x.item === l.item; });
      }
      if (la && lb) {
        var ra = B.received(amb.a, la.line), rb = B.received(amb.b, lb.line);
        var ordered = la.qty === lb.qty && la.price === lb.price ? q(la.qty, la.unit) + " × " + money(la.price) + " on each"
          : amb.a + ": " + q(la.qty, la.unit) + ", " + amb.b + ": " + q(lb.qty, lb.unit);
        var arrived = ra === rb ? q(ra, la.unit) + " on each" : amb.a + ": " + commas(ra) + ", " + amb.b + ": " + commas(rb);
        var subA = [it.short, amb.a + " or " + amb.b].filter(function (x) { return x; }).join(" · ");
        rows.push({ label: label, sub: subA, cells: [bill, ordered, arrived], mark: null });
        return;
      }
      var sub = [it.short, ol ? l.po + " line " + l.po_line : null].filter(function (x) { return x; }).join(" · ");
      rows.push({ label: label, sub: sub,
        cells: [bill, ol ? q(ol.qty, ol.unit) + " × " + money(ol.price) : "no order", ol ? q(B.received(l.po, l.po_line), ol.unit) : ""],
        mark: res.at === at ? mark : null });
    });
    var lines0 = read.lines && read.lines.length ? read.lines : [{}];
    var p0 = B.po[lines0[0].po || ""];
    if (num(read.freight) && read.freight) {
      var onOrder = p0 ? (p0.freight_estimate ? money(p0.freight_estimate) : p0.freight) : "";
      rows.push({ label: "Freight", sub: "", cells: [money(read.freight), onOrder, ""], mark: res.reason === "freight_not_ordered" ? 0 : null });
    }
    if (num(read.tax) && read.tax) {
      rows.push({ label: "Tax", sub: "", cells: [money(read.tax), p0 ? (p0.tax === "none" ? "none expected" : "expected") : "", ""],
        mark: res.reason === "tax_not_expected" ? 0 : null });
    }
    if (res.reason === "arithmetic") {
      rows.push({ label: "Total", sub: "", cells: [res.values.total, "lines add up to " + res.values.sum, ""], mark: 0 });
    }
    if (read.explanation_line) {
      out.quote = read.explanation_line;
      out.quote_label = has(KIND_SAYS, rkind) ? KIND_SAYS[rkind] : (SAYS[res.format] || "The bill says");
    }
    if (res.reason === "bank_details_change") out.next = { text: "The email", command: "recon doc " + res.doc, do: "doc", doc: res.doc };
    if (res.reason === "ai_unsure") out.next = { text: "To read it yourself", command: "recon doc " + res.doc, do: "doc", doc: res.doc };
    if ((res.reason === "qty_over_received" || res.reason === "receipt_not_logged" || res.reason === "billed_beyond_received") && res.at !== null && res.at !== undefined) {
      var ln = read.lines[res.at];
      var oln = B.poLine(ln.po, ln.po_line);
      var gotn = B.received(ln.po, ln.po_line);
      var shipped = has(res.values, "slip_shipped") ? res.values.slip_shipped : res.values.billed;
      var nn = Math.min(shipped - gotn, oln.qty - gotn);
      var linePart = B.po[ln.po].lines.length > 1 ? " --line " + ln.po_line : "";
      if (nn > 0) out.next = { text: "If they've arrived", command: "recon receive " + ln.po + " " + nn + linePart, do: "receive", po: ln.po, line: ln.po_line, qty: nn };
    }
    return out;
  }

  var api = { money: money, dollars: dollars, day: day, fill: fill, normNumber: normNumber, Books: Books, runMonth: runMonth,
    draftNote: draftNote, detail: detail };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ReconRules = api;
})(typeof window !== "undefined" ? window : this);
