// Shared UI helpers. No external dependencies.

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function attr(value) {
  return esc(value).replace(/`/g, "&#96;");
}

export function icon(name, cls = "") {
  return `<span class="ms ${cls}" aria-hidden="true">${esc(name)}</span>`;
}

export function fmtBytes(bytes, compact = false) {
  const value = Number(bytes) || 0;
  if (!value) return "0 Б";
  const units = compact ? ["Б", "К", "М", "Г", "Т"] : ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let index = 0;
  let number = value;
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024;
    index += 1;
  }
  if (index === 0) return `${Math.round(number)} ${units[index]}`;
  return `${number >= 100 ? number.toFixed(0) : number.toFixed(1)} ${units[index]}`;
}

export function plural(number, one, few, many) {
  const n = Math.abs(Number(number) || 0) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return many;
  if (n1 === 1) return one;
  if (n1 >= 2 && n1 <= 4) return few;
  return many;
}

export function fmtNumber(value) {
  const number = Number(value) || 0;
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1).replace(".0", "")} млн`;
  if (number >= 10_000) return `${(number / 1000).toFixed(1).replace(".0", "")} тыс.`;
  return String(number);
}

export function fmtDate(value) {
  if (!value) return "—";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff >= 0 && diff < 60) return "только что";
  if (diff >= 0 && diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff >= 0 && diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff >= 0 && diff < 86400 * 7) return `${Math.floor(diff / 86400)} дн назад`;
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDuration(seconds) {
  const value = Number(seconds) || 0;
  if (value < 60) return `${value.toFixed(0)} с`;
  if (value < 3600) return `${Math.floor(value / 60)} мин`;
  return `${Math.floor(value / 3600)} ч ${Math.floor((value % 3600) / 60)} мин`;
}

export function debounce(fn, delay = 400) {
  let timer = null;
  return function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

export function kindMeta(kind) {
  const map = {
    llm: { icon: "forum", label: "LLM", tone: "violet" },
    vlm: { icon: "visibility", label: "VLM", tone: "pink" },
    image: { icon: "image", label: "Классификация", tone: "blue" },
    detection: { icon: "center_focus_strong", label: "Детекция", tone: "red" },
    audio: { icon: "graphic_eq", label: "Аудио", tone: "teal" },
    embedding: { icon: "scatter_plot", label: "Эмбеддинги", tone: "green" },
    unknown: { icon: "draft", label: "Другое", tone: "blue" },
  };
  return map[kind] || map.unknown;
}

export function toneFor(text) {
  const tones = ["violet", "blue", "green", "orange", "pink", "teal"];
  let hash = 0;
  for (const char of String(text || "")) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return tones[hash % tones.length];
}

export function repoTitle(repo) {
  const name = String(repo || "").split("/").pop() || "model";
  return name.replace(/[-_]/g, " ").replace(/\bint[48]\b/gi, (m) => m.toUpperCase());
}

export function modelInitials(repo) {
  const name = String(repo || "").split("/").pop() || "OV";
  return name.replace(/[-_].*$/, "").slice(0, 2).toUpperCase() || "OV";
}

// ------------------------------------------------------------------ markdown
export function md(source) {
  if (!source) return "";
  let text = String(source).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const codeBlocks = [];
  text = text.replace(/```([\w+#.-]*)[ \t]*\n([\s\S]*?)```/g, (_match, language, code) => {
    const index = codeBlocks.push(`<pre><code data-lang="${attr(language)}">${esc(code.replace(/\n$/, ""))}</code></pre>`) - 1;
    return `\n\n\u0000CODE${index}\u0000\n\n`;
  });
  text = esc(text);
  const inlineCode = [];
  text = text.replace(/`([^`\n]+)`/g, (_match, code) => {
    const index = inlineCode.push(`<code>${code}</code>`) - 1;
    return `\u0000IC${index}\u0000`;
  });
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, "");
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  text = text.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  text = text.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>");

  const lines = text.split("\n");
  const output = [];
  let paragraph = [];
  let quote = [];
  let listType = null;
  let listItems = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      output.push(`<p>${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };
  const closeList = () => {
    if (listType && listItems.length) {
      output.push(`<${listType}>${listItems.join("")}</${listType}>`);
    }
    listType = null;
    listItems = [];
  };
  const flushQuote = () => {
    if (quote.length) {
      output.push(`<blockquote>${quote.join("<br>")}</blockquote>`);
      quote = [];
    }
  };
  const flushAll = () => {
    flushParagraph();
    closeList();
    flushQuote();
  };

  for (const line of lines) {
    const codeMatch = line.match(/^\u0000CODE(\d+)\u0000$/);
    if (codeMatch) {
      flushAll();
      output.push(codeBlocks[Number(codeMatch[1])] || "");
      continue;
    }
    if (!line.trim()) {
      flushAll();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushAll();
      const level = Math.min(4, heading[1].length);
      output.push(`<h${level}>${heading[2]}</h${level}>`);
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      flushAll();
      output.push("<hr>");
      continue;
    }
    const blockquote = line.match(/^&gt;\s?(.*)$/);
    if (blockquote) {
      flushParagraph();
      closeList();
      quote.push(blockquote[1]);
      continue;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (unordered || ordered) {
      flushParagraph();
      flushQuote();
      const type = unordered ? "ul" : "ol";
      if (listType && listType !== type) closeList();
      listType = type;
      listItems.push(`<li>${(unordered || ordered)[1]}</li>`);
      continue;
    }
    if (listType) closeList();
    if (quote.length) flushQuote();
    paragraph.push(line.trim());
  }
  flushAll();
  let html = output.join("\n");
  html = html.replace(/\u0000IC(\d+)\u0000/g, (_m, index) => inlineCode[Number(index)] || "");
  return html;
}

// -------------------------------------------------------------------- toasts
let toastCounter = 0;

export function toast(message, type = "info", timeout = 4500) {
  const host = $("#toasts");
  if (!host) return;
  const id = `toast-${++toastCounter}`;
  const icons = { info: "info", success: "check_circle", error: "error", warn: "warning" };
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.id = id;
  element.innerHTML = `${icon(icons[type] || "info")}<span>${esc(message)}</span>`;
  host.appendChild(element);
  const remove = () => {
    element.style.opacity = "0";
    element.style.transform = "translateY(6px)";
    element.style.transition = "opacity 160ms ease, transform 160ms ease";
    setTimeout(() => element.remove(), 180);
  };
  const timer = setTimeout(remove, timeout);
  element.addEventListener("click", () => {
    clearTimeout(timer);
    remove();
  });
}

// ------------------------------------------------------------------- dialogs
export function confirmDialog({
  title = "Подтвердите действие",
  text = "",
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    const dialog = $("#modal");
    dialog.innerHTML = `
      <div class="modal-inner">
        <div class="modal-head">
          <h3>${esc(title)}</h3>
          <button class="icon-btn small" type="button" data-confirm="0" aria-label="Закрыть">${icon("close")}</button>
        </div>
        <div class="modal-body">${text}</div>
        <div class="modal-actions">
          <button class="btn text" type="button" data-confirm="0">${esc(cancelLabel)}</button>
          <button class="btn ${danger ? "danger" : "filled"}" type="button" data-confirm="1">${esc(confirmLabel)}</button>
        </div>
      </div>`;
    const finish = (value) => {
      dialog.onclick = null;
      dialog.oncancel = null;
      if (dialog.open) dialog.close();
      resolve(value);
    };
    dialog.querySelectorAll("[data-confirm]").forEach((button) => {
      button.addEventListener("click", () => finish(button.dataset.confirm === "1"), { once: true });
    });
    dialog.oncancel = (event) => {
      event.preventDefault();
      finish(false);
    };
    dialog.onclick = (event) => {
      if (event.target === dialog) finish(false);
    };
    dialog.showModal();
  });
}

export function openSheet(html) {
  const sheet = $("#sheet");
  sheet.innerHTML = `<div class="sheet-inner">${html}</div>`;
  sheet.onclick = (event) => {
    if (event.target === sheet) sheet.close();
  };
  if (!sheet.open) sheet.showModal();
}

export function closeSheet() {
  const sheet = $("#sheet");
  if (sheet?.open) sheet.close();
}

export function openModal(html) {
  const modal = $("#modal");
  modal.innerHTML = `<div class="modal-inner">${html}</div>`;
  if (!modal.open) modal.showModal();
}

export function closeModal() {
  const modal = $("#modal");
  if (modal?.open) modal.close();
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Скопировано в буфер обмена", "success", 2200);
  } catch {
    toast("Не удалось скопировать", "error");
  }
}

export function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Не удалось прочитать файл."));
    reader.readAsDataURL(file);
  });
}

export function spinnerHTML(label = "") {
  return `<div class="flex gap-8" style="justify-content:center;padding:28px 0;color:var(--on-surface-variant)"><span class="spinner"></span><span>${esc(label)}</span></div>`;
}

export function emptyState({ iconName = "inbox", title, text, action = "" }) {
  return `<div class="empty">
    <div class="empty-icon">${icon(iconName)}</div>
    <h3>${esc(title)}</h3>
    <p>${text}</p>
    ${action}
  </div>`;
}

export function statusDot(kind) {
  const cls = kind === "ok" ? "ok" : kind === "warn" ? "warn" : kind === "error" ? "error" : "";
  return `<span class="status-dot ${cls}"></span>`;
}
