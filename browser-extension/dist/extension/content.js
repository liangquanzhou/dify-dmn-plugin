"use strict";
(() => {
  // src/binding.ts
  var SNAPSHOT_EVENT = "dmn-preview:snapshot:v1";
  var STOP_EVENT = "dmn-preview:stop:v1";
  var REFRESH_EVENT = "dmn-preview:refresh:v1";
  var MAX_TABLE_CHARS = 512 * 1024;

  // src/model.ts
  var isRecord = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  var own = (v, k) => Object.prototype.hasOwnProperty.call(v, k);
  var literal = (v) => JSON.stringify(v);
  var binary = ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "all_values", "is_minimum"];
  var tolerance = ["within", "below", "above"];
  var symbols = { eq: "=", ne: "\u2260", gt: ">", gte: "\u2265", lt: "<", lte: "\u2264", contains: "\u5305\u542B", not_contains: "\u4E0D\u5305\u542B", all_values: "\u5168\u90E8\u503C\u7B49\u4E8E", is_minimum: "\u4E3A\u6700\u5C0F\u503C\u4E8E", within: "\u63A5\u8FD1", below: "\u4F4E\u4E8E", above: "\u9AD8\u4E8E" };
  function fail(message) {
    throw new Error(message);
  }
  function validString(s) {
    if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(s))
      fail("JSON \u542B\u65E0\u6548 Unicode");
  }
  function uniqueKeys(raw) {
    let p = 0;
    const ws = () => {
      while (/\s/.test(raw[p] || "") && p < raw.length)
        p++;
    };
    const str = () => {
      const start = p++;
      while (p < raw.length) {
        if (raw[p] === "\\")
          p += 2;
        else if (raw[p++] === '"')
          break;
      }
      return JSON.parse(raw.slice(start, p));
    };
    function visit(depth) {
      if (depth > 32)
        fail("JSON \u5D4C\u5957\u6DF1\u5EA6\u8D85\u8FC7 32");
      ws();
      if (raw[p] === "{") {
        p++;
        ws();
        const keys = /* @__PURE__ */ new Set();
        while (raw[p] !== "}") {
          const key = str();
          if (keys.has(key))
            fail("JSON \u542B\u91CD\u590D\u5B57\u6BB5");
          keys.add(key);
          ws();
          p++;
          visit(depth + 1);
          ws();
          if (raw[p] === ",") {
            p++;
            ws();
          } else {
            break;
          }
        }
        p++;
      } else if (raw[p] === "[") {
        p++;
        ws();
        while (raw[p] !== "]") {
          visit(depth + 1);
          ws();
          if (raw[p] === ",") {
            p++;
            ws();
          } else {
            break;
          }
        }
        p++;
      } else if (raw[p] === '"') {
        str();
      } else {
        while (p < raw.length && !/[\s,}\]]/.test(raw[p]))
          p++;
      }
    }
    visit(0);
  }
  function validateExpression(v, depth = 0) {
    if (depth > 32)
      fail("\u6761\u4EF6\u5D4C\u5957\u8FC7\u6DF1");
    if (typeof v === "boolean")
      return;
    if (!isRecord(v) || Object.keys(v).length !== 1)
      fail("\u6761\u4EF6\u5FC5\u987B\u4E3A\u5E03\u5C14\u503C\u6216\u5355\u4E00\u7B97\u5B50");
    const [op, arg] = Object.entries(v)[0];
    if (op === "all" || op === "any") {
      if (!Array.isArray(arg))
        fail("all / any \u5FC5\u987B\u4E3A\u6570\u7EC4");
      arg.forEach((x) => validateExpression(x, depth + 1));
      return;
    }
    if (op === "is_unknown" || op === "is_empty") {
      if (typeof arg !== "string")
        fail("\u6761\u4EF6\u5B57\u6BB5\u5FC5\u987B\u4E3A\u5B57\u7B26\u4E32");
      return;
    }
    if (op === "constraint_set") {
      if (!isRecord(arg) || Object.keys(arg).sort().join(",") !== "mode,record" || typeof arg.record !== "string" || arg.mode !== "satisfied" && arg.mode !== "violated")
        fail("constraint_set \u9700\u8981 record \u4E0E\u5408\u6CD5 mode");
      return;
    }
    if (![...binary, ...tolerance].includes(op))
      fail(`\u4E0D\u652F\u6301\u7684\u6761\u4EF6\u7B97\u5B50\uFF1A${op}`);
    if (!Array.isArray(arg) || arg.length !== (tolerance.includes(op) ? 3 : 2) || typeof arg[0] !== "string")
      fail("\u6761\u4EF6\u7B97\u5B50\u53C2\u6570\u7ED3\u6784\u9519\u8BEF");
    if (isRecord(arg[1]) && own(arg[1], "ref")) {
      if (Object.keys(arg[1]).length !== 1 || typeof arg[1].ref !== "string" || op === "all_values")
        fail("\u53D8\u91CF\u5F15\u7528\u7ED3\u6784\u9519\u8BEF");
    }
  }
  function parseTable(value) {
    if (value === void 0 || value === null || value === "")
      return { kind: "empty", message: "\u5C1A\u672A\u914D\u7F6E\u51B3\u7B56\u8868\u3002\u5728\u4E0B\u65B9\u539F\u751F\u914D\u7F6E\u4E2D\u586B\u5199 table_json \u540E\uFF0C\u8FD9\u91CC\u4F1A\u81EA\u52A8\u663E\u793A\u77E9\u9635\u3002" };
    try {
      let walk2 = function(v) {
        if (++count > 2e4)
          fail("JSON \u503C\u8282\u70B9\u8D85\u8FC7 20,000");
        if (typeof v === "number" && (!Number.isFinite(v) || Number.isInteger(v) && !Number.isSafeInteger(v)))
          fail("\u6570\u503C\u8D85\u51FA\u5B89\u5168\u8303\u56F4");
        if (typeof v === "string")
          validString(v);
        if (v && typeof v === "object") {
          if (!Array.isArray(v))
            Object.keys(v).forEach(validString);
          Object.values(v).forEach(walk2);
        }
      };
      var walk = walk2;
      if (typeof value !== "string")
        fail("table_json \u5FC5\u987B\u662F JSON \u5B57\u7B26\u4E32");
      if (!value.trim())
        return { kind: "empty", message: "\u5C1A\u672A\u914D\u7F6E\u51B3\u7B56\u8868" };
      if (new TextEncoder().encode(value).length > 512 * 1024)
        fail("\u8868\u683C JSON \u8D85\u8FC7 512 KiB");
      const t = JSON.parse(value);
      uniqueKeys(value);
      let count = 0;
      walk2(t);
      if (!isRecord(t) || typeof t.id !== "string" || !t.id.trim() || !Array.isArray(t.rules))
        fail("\u9700\u8981 id\u3001hit_policy \u548C rules \u6570\u7EC4");
      if (t.hit_policy !== "FIRST" && t.hit_policy !== "COLLECT" && t.hit_policy !== "UNIQUE")
        fail("\u4EC5\u652F\u6301 FIRST / COLLECT / UNIQUE \u547D\u4E2D\u7B56\u7565");
      if (own(t, "unknown_policy") && t.unknown_policy !== "strict" && t.unknown_policy !== "compatible")
        fail("\u672A\u77E5\u503C\u7B56\u7565\u5FC5\u987B\u4E3A strict / compatible");
      if (t.rules.length > 1e3)
        fail("\u89C4\u5219\u6570\u8D85\u8FC7 1,000");
      const ids = /* @__PURE__ */ new Set();
      t.rules.forEach((r) => {
        if (!isRecord(r) || typeof r.id !== "string" || !r.id.trim() || !own(r, "when"))
          fail("\u6BCF\u6761\u89C4\u5219\u9700\u8981\u552F\u4E00 id \u548C when");
        if (ids.has(r.id))
          fail("\u89C4\u5219 id \u91CD\u590D");
        ids.add(r.id);
        validateExpression(r.when);
      });
      return { kind: "ready", matrix: buildMatrix(t) };
    } catch (e) {
      if (e instanceof SyntaxError)
        return { kind: "error", message: "JSON \u683C\u5F0F\u9519\u8BEF\uFF0C\u8BF7\u68C0\u67E5\u539F\u751F\u914D\u7F6E" };
      return { kind: "error", message: e instanceof Error ? e.message : "\u65E0\u6CD5\u8BFB\u53D6\u51B3\u7B56\u8868" };
    }
  }
  function operand(v) {
    return isRecord(v) && own(v, "ref") ? `\u5F15\u7528(${literal(v.ref)})` : literal(v);
  }
  function describe(op, arg) {
    if (op === "constraint_set") {
      const a2 = arg;
      return { field: a2.record, label: `\u7EA6\u675F\u96C6 ${a2.mode === "satisfied" ? "\u6EE1\u8DB3" : "\u8FDD\u53CD"}` };
    }
    if (op === "is_unknown" || op === "is_empty")
      return { field: arg, label: op === "is_unknown" ? "\u672A\u77E5 / null" : "\u4E3A\u7A7A" };
    const a = arg;
    const toleranceLabel = tolerance.includes(op) ? `\uFF08\u5BB9\u5DEE ${literal(a[2])}\uFF09` : "";
    return { field: a[0], label: `${symbols[op]} ${operand(a[1])}${toleranceLabel}` };
  }
  function buildMatrix(table) {
    const fields = [];
    const outputs = [];
    const outputKeys = /* @__PURE__ */ new Set();
    const addOutput = (parent, child) => {
      const key = JSON.stringify([parent, child ?? null]);
      if (!outputKeys.has(key)) {
        outputKeys.add(key);
        outputs.push({ key, parent, child, label: child !== void 0 ? `$[${JSON.stringify(parent)}][${JSON.stringify(child)}]` : `$[${JSON.stringify(parent)}]` });
      }
    };
    const rows = table.rules.map((rule) => {
      const atoms = [];
      const visit = (v, full) => {
        if (typeof v === "boolean")
          return v ? "\u59CB\u7EC8\u6210\u7ACB" : "\u59CB\u7EC8\u4E0D\u6210\u7ACB";
        const [op, arg] = Object.entries(v)[0];
        if (op === "all" || op === "any") {
          const a = arg;
          if (!a.length)
            return op === "all" ? "\u59CB\u7EC8\u6210\u7ACB" : "\u59CB\u7EC8\u4E0D\u6210\u7ACB";
          return `(${a.map((x) => visit(x, full)).join(op === "all" ? " \u4E14 " : " \u6216 ")})`;
        }
        const d = describe(op, arg);
        if (full)
          return `${literal(d.field)} ${d.label}`;
        const id = String.fromCharCode(65 + atoms.length % 26) + (atoms.length >= 26 ? String(Math.floor(atoms.length / 26)) : "");
        atoms.push({ id, ...d });
        if (!fields.includes(d.field))
          fields.push(d.field);
        return id;
      };
      const logic = visit(rule.when, false);
      const fullLogic = visit(rule.when, true);
      Object.entries(rule).forEach(([parent, value]) => {
        if (parent === "id" || parent === "when")
          return;
        if (isRecord(value) && Object.keys(value).length)
          Object.keys(value).forEach((child) => addOutput(parent, child));
        else
          addOutput(parent);
      });
      return { rule, atoms, logic, fullLogic };
    });
    return { table, fields, outputs, rows };
  }
  function outputValue(rule, column) {
    if (!own(rule, column.parent))
      return { present: false };
    const v = rule[column.parent];
    if (column.child === void 0) {
      if (isRecord(v) && Object.keys(v).length)
        return { present: true, expanded: true };
      return { present: true, value: v };
    }
    return isRecord(v) && own(v, column.child) ? { present: true, value: v[column.child] } : { present: false };
  }

  // src/view.ts
  function element(document2, tag, text, className) {
    const result = document2.createElement(tag);
    if (text !== void 0) result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function renderSnapshot(container, snapshot, page = 0) {
    const document2 = container.ownerDocument;
    container.replaceChildren();
    container.dataset.status = snapshot.status;
    if (snapshot.nodeId) container.dataset.nodeId = snapshot.nodeId;
    else delete container.dataset.nodeId;
    const source = element(document2, "div", snapshot.nodeId ? `${snapshot.title} \xB7 \u8282\u70B9 ${snapshot.nodeId}` : "\u5F53\u524D\u5DE5\u4F5C\u6D41\u8282\u70B9", "dmnp-source");
    container.append(source);
    if (snapshot.status !== "ready") {
      const message = element(document2, "div", snapshot.message || "\u65E0\u6CD5\u8BFB\u53D6\u5F53\u524D\u8282\u70B9\u3002", "dmnp-status");
      message.setAttribute("role", snapshot.status === "error" ? "alert" : "status");
      container.append(message);
      return;
    }
    const parsed = parseTable(snapshot.raw);
    if (parsed.kind !== "ready") {
      container.dataset.status = parsed.kind;
      const message = element(document2, "div", parsed.message, "dmnp-status");
      message.setAttribute("role", parsed.kind === "error" ? "alert" : "status");
      container.append(message);
      return;
    }
    const { matrix } = parsed;
    const columns = matrix.fields.length + matrix.outputs.length + 2;
    if (columns > 128) {
      container.dataset.status = "error";
      container.append(element(document2, "div", `\u6B64\u8868\u542B ${columns} \u5217\uFF0C\u8D85\u8FC7\u53EF\u8BFB\u9884\u89C8\u4E0A\u9650 128 \u5217\uFF1B\u672A\u663E\u793A\u4E0D\u5B8C\u6574\u8868\u683C\u3002`, "dmnp-status"));
      return;
    }
    const pageSize = 50;
    const pages = Math.max(1, Math.ceil(matrix.rows.length / pageSize));
    page = Math.max(0, Math.min(page, pages - 1));
    container.append(element(document2, "div", `${matrix.table.id} \xB7 ${matrix.table.hit_policy} \xB7 ${matrix.rows.length} \u6761\u89C4\u5219 \xB7 \u672A\u6267\u884C`, "dmnp-meta"));
    const scroll = element(document2, "div", void 0, "dmnp-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("aria-label", "\u51B3\u7B56\u8868\uFF0C\u53EF\u6A2A\u5411\u6EDA\u52A8");
    const table = document2.createElement("table");
    table.setAttribute("aria-label", `\u51B3\u7B56\u8868 ${matrix.table.id}`);
    const head = table.createTHead();
    const header = head.insertRow();
    for (const label of ["\u89C4\u5219", ...matrix.fields.map((field) => `\u6761\u4EF6 \xB7 ${literal(field)}`), "\u903B\u8F91", ...matrix.outputs.map((output) => `\u8F93\u51FA \xB7 ${output.label}`)]) {
      const th = document2.createElement("th");
      th.textContent = label;
      th.scope = "col";
      header.append(th);
    }
    const body = table.createTBody();
    for (const row of matrix.rows.slice(page * pageSize, (page + 1) * pageSize)) {
      const tr = body.insertRow();
      const id = document2.createElement("th");
      id.scope = "row";
      id.textContent = row.rule.id;
      tr.append(id);
      for (const field of matrix.fields) {
        const cell = tr.insertCell();
        const atoms = row.atoms.filter((atom) => atom.field === field);
        cell.textContent = atoms.length ? atoms.map((atom) => `${atom.id}: ${atom.label}`).join("\n") : "\u2014";
      }
      const logic = tr.insertCell();
      const details = document2.createElement("details");
      details.append(element(document2, "summary", row.logic), element(document2, "div", row.fullLogic, "dmnp-full-logic"));
      logic.append(details);
      for (const output of matrix.outputs) {
        const cell = tr.insertCell();
        const value = outputValue(row.rule, output);
        cell.textContent = !value.present ? "\u672A\u5B9A\u4E49" : value.expanded ? "\u89C1\u5C55\u5F00\u5217" : literal(value.value);
      }
    }
    scroll.append(table);
    container.append(scroll);
    if (!matrix.rows.length) container.append(element(document2, "div", "\u6B64\u8868\u6CA1\u6709\u89C4\u5219\u3002", "dmnp-status"));
    if (pages > 1) {
      const paging = element(document2, "nav", void 0, "dmnp-paging");
      paging.setAttribute("aria-label", "\u89C4\u5219\u5206\u9875");
      const previous = element(document2, "button", "\u4E0A\u4E00\u9875");
      previous.disabled = page === 0;
      previous.addEventListener("click", () => renderSnapshot(container, snapshot, page - 1));
      const next = element(document2, "button", "\u4E0B\u4E00\u9875");
      next.disabled = page === pages - 1;
      next.addEventListener("click", () => renderSnapshot(container, snapshot, page + 1));
      paging.append(previous, element(document2, "span", `\u7B2C ${page + 1}/${pages} \u9875 \xB7 \u6BCF\u9875\u6700\u591A ${pageSize} \u6761`), next);
      container.append(paging);
    }
    container.append(element(document2, "div", "\u53EA\u8BFB\u7ED3\u6784\u9884\u89C8 \xB7 \u70B9\u51FB\u903B\u8F91\u67E5\u770B\u5B8C\u6574\u6761\u4EF6 \xB7 \u4E0D\u5224\u65AD\u547D\u4E2D\u3001\u4E0D\u8FD0\u884C\u5DE5\u4F5C\u6D41", "dmnp-footnote"));
  }

  // src/content.ts
  var existing = document.getElementById("dmn-preview-extension-root");
  if (existing) {
    existing.hidden = false;
    document.dispatchEvent(new CustomEvent(REFRESH_EVENT));
  } else {
    let notify = function(type) {
      try {
        if (typeof chrome !== "undefined" && typeof chrome.runtime?.sendMessage === "function")
          chrome.runtime.sendMessage({ type }).catch(() => {
          });
      } catch {
      }
    }, receive = function(event) {
      const detail = event.detail;
      if (typeof detail !== "string" || detail.length > MAX_TABLE_CHARS * 2 + 8192) return;
      let snapshot;
      try {
        snapshot = JSON.parse(detail);
      } catch {
        return;
      }
      if (!snapshot || !["ready", "empty", "dynamic", "unsupported", "idle", "error"].includes(snapshot.status)) return;
      if (snapshot.raw !== void 0 && (typeof snapshot.raw !== "string" || snapshot.raw.length > MAX_TABLE_CHARS)) return;
      if (snapshot.nodeId !== void 0 && typeof snapshot.nodeId !== "string") return;
      if (snapshot.title !== void 0 && typeof snapshot.title !== "string") return;
      if (snapshot.message !== void 0 && typeof snapshot.message !== "string") return;
      lastReceived = Date.now();
      if (!announced) {
        announced = true;
        notify("dmn-preview-active");
      }
      if (detail === lastSnapshot && !stale) return;
      stale = false;
      lastSnapshot = detail;
      renderSnapshot(body, snapshot);
    }, cleanup = function() {
      clearInterval(watchdog);
      document.removeEventListener(SNAPSHOT_EVENT, receive);
      document.dispatchEvent(new CustomEvent(STOP_EVENT));
      root.remove();
      notify("dmn-preview-closed");
    };
    notify2 = notify, receive2 = receive, cleanup2 = cleanup;
    const root = element(document, "section");
    root.id = "dmn-preview-extension-root";
    root.setAttribute("aria-label", "DMN \u6269\u5C55\u53EA\u8BFB\u9884\u89C8");
    const header = element(document, "header");
    const title = element(document, "strong", "DMN \u51B3\u7B56\u8868");
    const readonly = element(document, "span", "\u6D4F\u89C8\u5668\u6269\u5C55 \xB7 \u53EA\u8BFB", "dmnp-badge");
    const grow = element(document, "button", "\u5C55\u5F00");
    grow.setAttribute("aria-label", "\u5C55\u5F00\u6216\u8FD8\u539F\u51B3\u7B56\u8868");
    grow.addEventListener("click", () => {
      const expanded = root.classList.toggle("dmnp-expanded");
      grow.textContent = expanded ? "\u8FD8\u539F" : "\u5C55\u5F00";
    });
    const close = element(document, "button", "\u5173\u95ED");
    const body = element(document, "div", void 0, "dmnp-body");
    let lastSnapshot = "";
    let lastReceived = Date.now();
    let stale = false;
    let announced = false;
    const watchdog = setInterval(() => {
      if (Date.now() - lastReceived > 5e3 && !stale) {
        stale = true;
        renderSnapshot(body, { status: "error", message: "\u5F53\u524D\u8282\u70B9\u8BFB\u53D6\u5DF2\u4E2D\u65AD\uFF0C\u65E7\u9884\u89C8\u5DF2\u6E05\u9664\u3002\u8BF7\u518D\u6B21\u70B9\u51FB\u6269\u5C55\u542F\u7528\u3002" });
      }
    }, 1e3);
    close.addEventListener("click", cleanup);
    header.append(title, readonly, grow, close);
    root.append(header, body);
    document.documentElement.append(root);
    document.addEventListener(SNAPSHOT_EVENT, receive);
    renderSnapshot(body, { status: "idle", message: "\u6B63\u5728\u8BFB\u53D6\u5F53\u524D\u9009\u4E2D\u7684 DMN \u8282\u70B9\u2026" });
  }
  var notify2;
  var receive2;
  var cleanup2;
})();
