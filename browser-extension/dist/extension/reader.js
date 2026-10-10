"use strict";
(() => {
  // src/binding.ts
  var PROVIDER = "liangquanzhou/dmn_decision/dmn";
  var SNAPSHOT_EVENT = "dmn-preview:snapshot:v1";
  var STOP_EVENT = "dmn-preview:stop:v1";
  var REFRESH_EVENT = "dmn-preview:refresh:v1";
  var MAX_TABLE_CHARS = 512 * 1024;
  function ownValue(object, name) {
    if (!object || typeof object !== "object") return void 0;
    return Object.getOwnPropertyDescriptor(object, name)?.value;
  }
  function extractTable(data, nodeId) {
    if (ownValue(data, "type") !== "tool" || ownValue(data, "provider_type") !== "builtin" || ownValue(data, "provider_id") !== PROVIDER || ownValue(data, "tool_name") !== "evaluate")
      return { status: "unsupported", message: "\u5F53\u524D\u8282\u70B9\u4E0D\u5728\u652F\u6301\u8303\u56F4\u3002\u4EC5\u652F\u6301\u6307\u5B9A DMN \u63D2\u4EF6\u7684 evaluate \u5DE5\u5177\u3002" };
    const titleValue = ownValue(data, "title");
    const base = { nodeId, title: typeof titleValue === "string" ? titleValue.slice(0, 300) : "DMN evaluate" };
    const config = ownValue(data, "tool_configurations");
    const setting = ownValue(config, "table_json");
    let raw = setting;
    if (setting && typeof setting === "object") {
      const type = ownValue(setting, "type");
      if (type !== "constant" && type !== "mixed") return { ...base, status: "dynamic", message: "table_json \u662F\u53D8\u91CF\u6216\u672A\u652F\u6301\u7684\u7ED1\u5B9A\uFF1B\u8FD0\u884C\u524D\u6CA1\u6709\u53EF\u786E\u8BA4\u7684\u5B8C\u6574\u8868\u683C\u3002" };
      raw = ownValue(setting, "value");
      if (type === "mixed" && typeof raw === "string" && /\{\{#.*?#\}\}/s.test(raw))
        return { ...base, status: "dynamic", message: "table_json \u542B\u672A\u89E3\u6790\u7684\u53D8\u91CF\uFF1B\u4E0D\u663E\u793A\u63A8\u6D4B\u8868\u683C\u3002" };
    }
    if (raw === void 0 || raw === null || raw === "") return { ...base, status: "empty", message: "\u6B64\u8282\u70B9\u5C1A\u672A\u914D\u7F6E table_json\u3002" };
    if (typeof raw !== "string") return { ...base, status: "error", message: "table_json \u5FC5\u987B\u662F JSON \u5B57\u7B26\u4E32\u3002" };
    if (raw.length > MAX_TABLE_CHARS) return { ...base, status: "error", message: "table_json \u8D85\u8FC7\u9884\u89C8\u5927\u5C0F\u9650\u5236\u3002" };
    return { ...base, status: "ready", raw };
  }
  function readRenderedNode(element) {
    const id = element.getAttribute("data-id");
    if (!id) return null;
    const key = Object.getOwnPropertyNames(element).find((name) => name.startsWith("__reactProps$"));
    if (!key) return null;
    const props = ownValue(element, key);
    const queue = [{ value: ownValue(props, "children"), depth: 0 }];
    let examined = 0;
    while (queue.length && examined++ < 96) {
      const { value, depth } = queue.shift();
      if (depth > 6 || !value || typeof value !== "object") continue;
      if (Array.isArray(value)) {
        for (const child of value.slice(0, 48)) queue.push({ value: child, depth: depth + 1 });
        continue;
      }
      const childProps = ownValue(value, "props");
      const data = ownValue(childProps, "data");
      if (ownValue(childProps, "id") === id && data && typeof ownValue(data, "type") === "string") return { id, data };
      queue.push({ value: ownValue(childProps, "children"), depth: depth + 1 });
    }
    return null;
  }
  function isWorkflowEditorLocation(location) {
    if (/^\/app\/[^/]+\/workflow\/?$/.test(location.pathname)) return true;
    return /^\/v2\/app\/[^/]+\/?$/.test(location.pathname) && new URLSearchParams(location.search).get("mode") === "workflow";
  }
  function snapshotDocument(document2) {
    if (!isWorkflowEditorLocation(document2.location))
      return { status: "unsupported", message: "\u8BF7\u6253\u5F00 Dify 1.11.1 \u7684 Workflow \u7F16\u8F91\u9875\u9762\u3002" };
    const rendered = document2.querySelectorAll(".react-flow__node[data-id]");
    if (rendered.length > 1500) return { status: "error", message: "\u5DE5\u4F5C\u6D41\u8282\u70B9\u8D85\u8FC7 1,500\uFF0C\u65E0\u6CD5\u53EF\u9760\u8BC6\u522B\u5F53\u524D\u9009\u62E9\uFF1B\u672A\u663E\u793A\u90E8\u5206\u626B\u63CF\u7ED3\u679C\u3002" };
    if (!rendered.length) return { status: "idle", message: "\u7B49\u5F85\u5DE5\u4F5C\u6D41\u8282\u70B9\uFF1B\u6253\u5F00\u5DE5\u4F5C\u6D41\u5E76\u70B9\u51FB DMN evaluate \u8282\u70B9\u3002" };
    let readable = 0;
    const selected = [];
    for (const element of Array.from(rendered).slice(0, 1500)) {
      const node = readRenderedNode(element);
      if (!node) continue;
      readable++;
      if (ownValue(node.data, "selected") === true) selected.push(node);
    }
    if (readable !== rendered.length) return { status: "error", message: "\u65E0\u6CD5\u5B8C\u6574\u8BFB\u53D6\u6B64 Dify \u9875\u9762\u7ED3\u6784\u3002\u9884\u89C8\u4EC5\u9002\u914D\u7ECF\u9A8C\u8BC1\u7684 1.11.1\uFF1B\u4E0D\u4F1A\u663E\u793A\u7F13\u5B58\u6216\u731C\u6D4B\u6570\u636E\u3002" };
    if (selected.length !== 1) return { status: "idle", message: selected.length ? "\u8BF7\u53EA\u9009\u62E9\u4E00\u4E2A DMN evaluate \u8282\u70B9\u3002" : "\u70B9\u51FB DMN evaluate \u8282\u70B9\u5373\u53EF\u9884\u89C8\u5F53\u524D table_json\u3002" };
    return extractTable(selected[0].data, selected[0].id);
  }
  function createPageReader(document2) {
    const activationPath = document2.location.pathname;
    let navigated = false;
    return () => {
      if (document2.location.pathname !== activationPath) navigated = true;
      if (navigated) return { status: "unsupported", message: "\u5DE5\u4F5C\u6D41\u9875\u9762\u5DF2\u5207\u6362\uFF0C\u65E7\u9884\u89C8\u5DF2\u6E05\u9664\u3002\u8BF7\u518D\u6B21\u70B9\u51FB\u6269\u5C55\u542F\u7528\u5F53\u524D\u9875\u9762\u3002" };
      return snapshotDocument(document2);
    };
  }

  // src/reader.ts
  function startReader() {
    const root = document.getElementById("dmn-preview-extension-root");
    if (!root) return;
    document.dispatchEvent(new CustomEvent(STOP_EVENT));
    const readCurrentPage = createPageReader(document);
    let previous = "";
    let lastSent = 0;
    let timer;
    let stopped = false;
    let scheduled = false;
    function emit() {
      if (stopped) return;
      if (!root?.isConnected) {
        stop();
        return;
      }
      let snapshot;
      try {
        snapshot = readCurrentPage();
      } catch {
        snapshot = { status: "error", message: "\u8BFB\u53D6\u5F53\u524D\u8282\u70B9\u5931\u8D25\uFF0C\u65E7\u9884\u89C8\u5DF2\u6E05\u9664\u3002\u8BF7\u91CD\u65B0\u6253\u5F00\u5DE5\u4F5C\u6D41\u540E\u542F\u7528\u6269\u5C55\u3002" };
      }
      const detail = JSON.stringify(snapshot);
      if (detail !== previous || Date.now() - lastSent >= 1e3) {
        previous = detail;
        lastSent = Date.now();
        document.dispatchEvent(new CustomEvent(SNAPSHOT_EVENT, { detail }));
      }
    }
    function schedule() {
      if (scheduled || stopped) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        emit();
      });
    }
    function refresh() {
      previous = "";
      emit();
    }
    function stop() {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("click", schedule, true);
      document.removeEventListener("input", schedule, true);
      document.removeEventListener("change", schedule, true);
      document.removeEventListener(STOP_EVENT, stop);
      document.removeEventListener(REFRESH_EVENT, refresh);
      window.removeEventListener("pagehide", stop);
    }
    document.addEventListener("click", schedule, true);
    document.addEventListener("input", schedule, true);
    document.addEventListener("change", schedule, true);
    document.addEventListener(STOP_EVENT, stop);
    document.addEventListener(REFRESH_EVENT, refresh);
    window.addEventListener("pagehide", stop);
    timer = setInterval(emit, 250);
    emit();
  }
  startReader();
})();
