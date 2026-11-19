// OpenVINO Studio — application shell, routing and interactions.

import { api, streamChat, streamVLM } from "./api.js";
import {
  $,
  $$,
  esc,
  icon,
  toast,
  confirmDialog,
  openSheet,
  closeSheet,
  openModal,
  closeModal,
  copyText,
  debounce,
  fileToDataURL,
  fmtBytes,
  fmtDate,
  fmtNumber,
  md,
  kindMeta,
  repoTitle,
  plural,
} from "./util.js";
import {
  pages,
  catalogResults,
  libraryList,
  chatMessageHTML,
  routeTitle,
} from "./pages.js";
import { jobDockBody, emptyBox, modelIcon } from "./components.js";

const ROUTES = ["overview", "models", "library", "chat", "vlm", "images", "benchmark", "tools", "settings"];
const THEMES = ["system", "light", "dark"];

const storedTheme = localStorage.getItem("ovs-theme") || "system";
const state = {
  route: "overview",
  system: null,
  systemError: "",
  settings: null,
  models: null,
  loadingSystem: true,
  loadingModels: true,
  theme: THEMES.includes(storedTheme) ? storedTheme : "system",
  catalog: {
    q: "",
    task: "",
    sort: "downloads",
    official: false,
    results: [],
    curated: [],
    loading: true,
    loaded: false,
    error: "",
  },
  library: { q: "", filter: "all" },
  chat: {
    modelId: null,
    device: "CPU",
    messages: [],
    system: "",
    params: {
      temperature: 0.7,
      max_new_tokens: 512,
      top_p: 0.95,
      top_k: 40,
      repetition_penalty: 1.05,
    },
    streaming: false,
    controller: null,
    aborted: false,
    metrics: "",
  },
  vlm: {
    modelId: null,
    device: "CPU",
    dataUrl: null,
    fileName: "",
    prompt: "",
    answer: "",
    streaming: false,
    controller: null,
    aborted: false,
    metrics: "",
    error: "",
    params: { temperature: 0.4, max_new_tokens: 512 },
  },
  image: {
    modelId: null,
    task: "auto",
    dataUrl: null,
    fileName: "",
    result: null,
    running: false,
    threshold: 0.3,
    device: "CPU",
  },
  bench: {
    modelId: null,
    device: "CPU",
    iterations: 10,
    warmup: 2,
    mode: "auto",
    prompt: "The capital of France is",
    max_tokens: 64,
    history: [],
    loaded: false,
    running: false,
  },
  tools: { logs: "", logsLoading: false, logsLoaded: false, convertFormat: "int4" },
  jobs: [],
  jobStatuses: {},
  jobsActive: 0,
  dockOpen: localStorage.getItem("ovs-dock") === "1",
  jobsTimer: null,
  booted: false,
};

let catalogToken = 0;
let jobsBusy = false;

// ------------------------------------------------------------------- theme
function resolveTheme(theme) {
  if (theme === "light" || theme === "dark") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  state.theme = THEMES.includes(theme) ? theme : "system";
  const resolved = resolveTheme(state.theme);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", resolved === "dark" ? "#121318" : "#FBF8FF");
}

function persistTheme(theme, syncServer = true) {
  localStorage.setItem("ovs-theme", theme);
  applyTheme(theme);
  if (state.settings) state.settings.theme = theme;
  if (syncServer) {
    api.saveSettings({ theme }).catch(() => {});
  }
}

function cycleTheme() {
  const index = THEMES.indexOf(state.theme);
  const next = THEMES[(index + 1) % THEMES.length];
  persistTheme(next);
  toast(`Тема: ${next === "system" ? "системная" : next === "light" ? "светлая" : "тёмная"}`, "info", 1800);
  if (state.route === "settings") render();
}

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (state.theme === "system") applyTheme("system");
});

// ------------------------------------------------------------------ chrome
function engineStatus() {
  const openvino = state.system?.openvino;
  if (!state.system) return { label: "Проверка окружения…", dot: "" };
  if (!openvino?.installed) return { label: "OpenVINO не установлен", dot: "warn" };
  const short = String(openvino.ov_version || "").split("-")[0];
  return { label: `OpenVINO ${short}`.trim(), dot: "ok" };
}

function updateChrome() {
  const title = routeTitle(state.route);
  document.title = `${title} — OpenVINO Studio`;
  const pageTitle = $("#page-title");
  if (pageTitle) pageTitle.textContent = title;
  $$(".rail-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.route === state.route);
  });
  const more = document.querySelector(".rail-more");
  if (more) more.classList.toggle("active", ["vlm", "images", "benchmark", "tools", "settings"].includes(state.route));
  const status = engineStatus();
  const chip = $("#engine-chip");
  if (chip) {
    const dot = chip.querySelector(".status-dot");
    if (dot) dot.className = `status-dot ${status.dot}`;
  }
  const label = $("#engine-label");
  if (label) label.textContent = status.label;
  const railStatus = $("#rail-status");
  if (railStatus) {
    railStatus.innerHTML = `<span class="status-dot ${status.dot}"></span><span>v${esc(state.system?.app_version || "1.0")}</span>`;
    railStatus.title = status.label;
  }
  updateJobsUI();
}

// ------------------------------------------------------------------ selections
function ensureSelections() {
  const all = state.models?.models || [];
  const chatModels = all.filter((model) => model.chat_ready);
  if (!chatModels.some((model) => model.id === state.chat.modelId)) {
    state.chat.modelId = chatModels[0]?.id || null;
  }
  const visionModels = all.filter((model) => model.kind === "image" || model.kind === "detection");
  if (!visionModels.some((model) => model.id === state.image.modelId)) {
    state.image.modelId = (visionModels.find((model) => model.kind === "detection") || visionModels[0])?.id || null;
  }
  if (!all.some((model) => model.id === state.bench.modelId)) {
    state.bench.modelId = all[0]?.id || null;
  }
  const vlmModels = all.filter((model) => model.kind === "vlm");
  if (!vlmModels.some((model) => model.id === state.vlm.modelId)) {
    state.vlm.modelId = vlmModels[0]?.id || null;
  }
  const available = (state.system?.openvino?.devices || []).map((device) => String(device.id).toUpperCase());
  const usable = (device) => {
    const value = String(device || "CPU").toUpperCase();
    if (value === "CPU" || value === "AUTO") return true;
    return available.some((id) => id === value || id.startsWith(`${value}.`));
  };
  const defaultDevice = state.system?.settings?.default_device || "CPU";
  if (!state.chat.device) state.chat.device = defaultDevice;
  if (!state.image.device) state.image.device = defaultDevice;
  if (!state.bench.device) state.bench.device = defaultDevice;
  if (!state.vlm.device) state.vlm.device = defaultDevice;
  if (!usable(state.chat.device)) state.chat.device = "CPU";
  if (!usable(state.image.device)) state.image.device = "CPU";
  if (!usable(state.bench.device)) state.bench.device = "CPU";
  if (!usable(state.vlm.device)) state.vlm.device = "CPU";
}

// ------------------------------------------------------------------- render
function scrollChat(force = true) {
  const host = $("#chat-messages");
  if (!host) return;
  if (force || host.scrollHeight - host.scrollTop - host.clientHeight < 220) {
    host.scrollTop = host.scrollHeight;
  }
}

function render() {
  ensureSelections();
  const view = $("#view");
  const pageFn = pages[state.route] || pages.overview;
  try {
    view.innerHTML = pageFn(state);
  } catch (error) {
    console.error(error);
    view.innerHTML = `<div class="fatal">${emptyBox(
      "error",
      "Не удалось отрисовать страницу",
      esc(error.message || String(error)),
      `<button class="btn filled" type="button" data-action="reload-page">Перезагрузить</button>`,
    )}</div>`;
  }
  updateChrome();
  bindPage();
}

function bindPage() {
  if (state.route === "images") bindImagePage();
  if (state.route === "vlm") bindVlmPage();
  if (state.route === "models" && !state.catalog.loaded && !state.catalog.loading) {
    loadCatalog();
  }
  if (state.route === "benchmark" && !state.bench.loaded) {
    loadBenchmarks();
  }
  if (state.route === "tools" && !state.tools.logsLoaded && !state.tools.logsLoading) {
    loadLogs();
  }
  if (state.route === "chat") {
    requestAnimationFrame(() => scrollChat(true));
  }
}

function goto(route) {
  if (!ROUTES.includes(route)) route = "overview";
  if (state.route === route) {
    render();
    return;
  }
  location.hash = `#/${route}`;
}

function parseRoute() {
  const raw = (location.hash || "").replace(/^#\/?/, "").split("?")[0];
  state.route = ROUTES.includes(raw) ? raw : "overview";
}

// -------------------------------------------------------------------- boot
async function boot() {
  applyTheme(state.theme);
  parseRoute();
  updateChrome();
  wireEvents();
  loadCurated();
  loadCatalog();
  try {
    await loadSystem(false);
    state.booted = true;
    render();
    await loadModels();
    render();
    scheduleJobs(900);
  } catch (error) {
    state.systemError = error.message || String(error);
    render();
  }
}

async function loadSystem(force = false) {
  state.loadingSystem = true;
  try {
    const data = await api.system(force);
    state.system = data;
    state.settings = data.settings || state.settings;
    state.systemError = "";
    if (!localStorage.getItem("ovs-theme") && state.settings?.theme) {
      state.theme = state.settings.theme;
      applyTheme(state.theme);
    }
    const device = state.settings?.default_device;
    if (device && !state.chat.device) state.chat.device = device;
    updateChrome();
  } catch (error) {
    state.systemError = error.message || String(error);
    throw error;
  } finally {
    state.loadingSystem = false;
    updateChrome();
  }
}

async function loadModels() {
  state.loadingModels = true;
  try {
    state.models = await api.models();
  } catch (error) {
    toast(`Библиотека недоступна: ${error.message}`, "error");
  } finally {
    state.loadingModels = false;
  }
}

async function loadCurated() {
  try {
    const data = await api.curated();
    state.catalog.curated = data.models || [];
    if (state.route === "overview") render();
  } catch {
    // offline: curated is optional
  }
}

async function loadCatalog() {
  const token = ++catalogToken;
  state.catalog.loading = true;
  state.catalog.error = "";
  updateCatalogResults();
  try {
    const data = await api.searchModels({
      q: state.catalog.q,
      task: state.catalog.task,
      sort: state.catalog.sort,
      official: state.catalog.official,
      limit: 36,
    });
    if (token !== catalogToken) return;
    state.catalog.results = data.models || [];
    state.catalog.loaded = true;
  } catch (error) {
    if (token !== catalogToken) return;
    state.catalog.error = error.message;
    state.catalog.results = [];
    state.catalog.loaded = true;
  } finally {
    if (token === catalogToken) {
      state.catalog.loading = false;
      updateCatalogResults();
      if (state.route === "models") {
        const count = $("#catalog-count");
        if (count) count.textContent = `${state.catalog.results.length} ${plural(state.catalog.results.length, "модель", "модели", "моделей")}`;
      }
    }
  }
}

function updateCatalogResults() {
  const host = $("#catalog-results");
  if (!host) return;
  host.innerHTML = catalogResults(state);
  const count = $("#catalog-count");
  if (count) count.textContent = state.catalog.loading ? "поиск…" : `${state.catalog.results.length} ${plural(state.catalog.results.length, "модель", "модели", "моделей")}`;
}

async function loadBenchmarks() {
  try {
    const data = await api.benchmarks();
    state.bench.history = data.history || [];
    state.bench.loaded = true;
    if (state.route === "benchmark") render();
  } catch {
    // ignore
  }
}

async function loadLogs() {
  state.tools.logsLoading = true;
  try {
    const data = await api.logs(500);
    state.tools.logs = data.log || "";
    const box = $("#log-box");
    if (box) box.textContent = state.tools.logs;
  } catch (error) {
    toast(`Журнал недоступен: ${error.message}`, "error");
  } finally {
    state.tools.logsLoading = false;
    state.tools.logsLoaded = true;
  }
}

// -------------------------------------------------------------------- jobs
function scheduleJobs(delay) {
  clearTimeout(state.jobsTimer);
  state.jobsTimer = setTimeout(pollJobs, delay);
}

async function pollJobs() {
  if (jobsBusy) {
    scheduleJobs(1200);
    return;
  }
  jobsBusy = true;
  try {
    const data = await api.jobs();
    const previous = state.jobStatuses;
    const next = {};
    const finished = [];
    for (const job of data.jobs || []) {
      next[job.id] = job.status;
      const old = previous[job.id];
      if (old && old !== job.status && ["done", "error", "cancelled"].includes(job.status)) {
        finished.push(job);
      }
      if (!old && (job.status === "running" || job.status === "queued")) {
        state.dockOpen = true;
        localStorage.setItem("ovs-dock", "1");
      }
    }
    state.jobStatuses = next;
    state.jobs = data.jobs || [];
    state.jobsActive = data.active || 0;
    updateJobsUI();
    for (const job of finished) {
      await onJobFinished(job);
    }
  } catch {
    // server restarting; keep polling
  } finally {
    jobsBusy = false;
    scheduleJobs(state.jobsActive ? 1200 : 5000);
  }
}

async function refreshJobs() {
  clearTimeout(state.jobsTimer);
  await pollJobs();
}

async function onJobFinished(job) {
  if (job.status === "done") {
    toast(`${job.title}: готово`, "success");
  } else if (job.status === "error") {
    const line = (job.error || "неизвестная ошибка").split("\n")[0];
    toast(`${job.title}: ${line}`, "error", 7000);
  }
  if (job.kind === "download" || job.kind === "convert") {
    await loadModels();
    if (["library", "models", "overview"].includes(state.route) && !state.chat.streaming) render();
  } else if (job.kind === "install") {
    try {
      await loadSystem(true);
    } catch {
      // ignore
    }
    if (["tools", "settings", "overview", "chat"].includes(state.route) && !state.chat.streaming) render();
  } else if (job.kind === "benchmark") {
    state.bench.running = false;
    await loadBenchmarks();
    if (state.route === "benchmark" && !state.chat.streaming) render();
  }
}

function updateJobsUI() {
  const active = state.jobs.filter((job) => ["running", "queued"].includes(job.status));
  const recent = state.jobs.filter((job) => !["running", "queued"].includes(job.status)).slice(0, 2);
  const visible = [...active, ...recent].slice(0, 6);
  const badge = $("#jobs-badge");
  if (badge) {
    badge.hidden = active.length === 0;
    badge.textContent = String(active.length);
  }
  const dock = $("#job-dock");
  if (!dock) return;
  if (!state.jobs.length || !state.dockOpen) {
    dock.hidden = true;
    return;
  }
  dock.hidden = false;
  dock.classList.toggle("collapsed", !state.dockOpen);
  const body = $("#job-dock-body");
  if (body) body.innerHTML = jobDockBody(visible);
  const count = $("#job-dock-count");
  if (count) count.textContent = active.length ? `${active.length} активных` : "завершены";
  const chevron = $("#dock-chevron");
  if (chevron) chevron.textContent = state.dockOpen ? "expand_more" : "expand_less";
}

function toggleDock() {
  state.dockOpen = !state.dockOpen;
  localStorage.setItem("ovs-dock", state.dockOpen ? "1" : "0");
  updateJobsUI();
}

// ------------------------------------------------------------------ actions
async function handleDownload(repo, sizeHint = 0) {
  if (!repo) return;
  const existing = state.models?.models?.find((model) => model.repo === repo && !model.incomplete);
  if (existing) {
    toast("Эта модель уже есть в библиотеке.", "info");
    return;
  }
  const size = Number(sizeHint) || 0;
  if (size > 1_500_000_000) {
    const free = state.system?.disk?.free || 0;
    const enough = !free || free > size * 1.1;
    const confirmed = await confirmDialog({
      title: "Скачать модель?",
      text: `<p><strong>${esc(repo)}</strong></p><p>Объём: ${fmtBytes(size)}. ${enough ? `Свободно на диске: ${fmtBytes(free)}.` : `<span style="color:var(--error)">Внимание: свободно только ${fmtBytes(free)}.</span>`}</p><p>Загрузка продолжится в фоне, её можно отменить в панели задач.</p>`,
      confirmLabel: "Скачать",
      danger: !enough,
    });
    if (!confirmed) return;
  }
  try {
    await api.download({ repo });
    toast("Загрузка началась", "success");
    state.dockOpen = true;
    localStorage.setItem("ovs-dock", "1");
    closeSheet();
    await refreshJobs();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function openModelDetail(repo) {
  openSheet(`<div class="sheet-head"><div class="sheet-title-block"><div class="sheet-title">${esc(repo)}</div><div class="sheet-sub">Загрузка сведений…</div></div><button class="icon-btn" type="button" data-action="close-sheet" aria-label="Закрыть">${icon("close")}</button></div><div class="sheet-body"><div class="flex gap-8" style="padding:24px 0;justify-content:center"><span class="spinner"></span><span class="muted">Запрашиваем Hugging Face…</span></div></div>`);
  try {
    const detail = await api.modelDetail(repo);
    const local = state.models?.models?.find((model) => model.repo === repo);
    const files = detail.files || [];
    const weightFiles = files.filter((file) => !/\.(md|png|jpg|jpeg|gif|webp|svg|mp4|pdf)$/i.test(file.name));
    const readme = (detail.readme || "").replace(/^---[\s\S]*?---\s*\n/, "");
    const tags = (detail.tags || []).slice(0, 8);
    const sheet = `<div class="sheet-head">
      <div class="sheet-title-block">
        <div class="sheet-title">${esc(repoTitle(detail.name || repo))}</div>
        <div class="sheet-sub">${esc(repo)}</div>
      </div>
      <button class="icon-btn" type="button" data-action="close-sheet" aria-label="Закрыть">${icon("close")}</button>
    </div>
    <div class="sheet-body">
      <div class="flex gap-8" style="flex-wrap:wrap;margin-bottom:16px">
        <span class="tag primary">${esc(detail.pipeline_tag || "OpenVINO")}</span>
        <span class="tag">${fmtBytes(detail.total_size)}</span>
        <span class="tag">${files.length} файлов</span>
        ${detail.has_ir ? `<span class="tag success">готовый IR</span>` : `<span class="tag warn">нужна конвертация</span>`}
        ${local ? `<span class="tag success">в библиотеке</span>` : ""}
      </div>
      <div class="flex gap-8" style="flex-wrap:wrap;margin-bottom:16px">
        ${tags.map((tag) => `<span class="chip tone">${esc(tag)}</span>`).join("")}
      </div>
      ${detail.gated ? `<div class="banner warning" style="margin-bottom:16px">${icon("lock")}<div>Модель с ограниченным доступом. Укажите HF-токен в настройках и примите условия на странице модели.</div></div>` : ""}
      ${!detail.has_ir ? `<div class="banner warning" style="margin-bottom:16px">${icon("transform")}<div>В репозитории нет готового OpenVINO IR. После загрузки сконвертируйте модель в разделе «Инструменты».</div></div>` : ""}
      <div class="card card-pad card-flat" style="margin-bottom:18px">
        <div class="flex-between" style="flex-wrap:wrap;gap:10px">
          <div><div class="small muted">Размер загрузки</div><div style="font-size:18px;font-weight:500">${fmtBytes(detail.downloadable_size || detail.total_size)}</div></div>
          <div><div class="small muted">Лицензия</div><div class="small">${esc(detail.license || "не указана")}</div></div>
          <div><div class="small muted">Обновлено</div><div class="small">${esc(fmtDate(detail.last_modified))}</div></div>
        </div>
      </div>
      <div class="section" style="margin-top:0">
        <div class="section-head"><div class="section-title"><h3 style="font-size:15px">Файлы</h3><span>${weightFiles.length}</span></div></div>
        <div class="card card-flat" style="padding:6px 14px;max-height:180px;overflow:auto">
          ${weightFiles.slice(0, 40).map((file) => `<div class="flex-between" style="padding:6px 0;border-bottom:1px solid var(--border)"><span class="mono" style="font-size:11px;overflow:hidden;text-overflow:ellipsis">${esc(file.name)}</span><span class="small muted nowrap">${fmtBytes(file.size)}</span></div>`).join("")}
          ${weightFiles.length > 40 ? `<div class="small muted" style="padding:8px 0">и ещё ${weightFiles.length - 40}…</div>` : ""}
        </div>
      </div>
      <div class="section">
        <div class="section-head"><div class="section-title"><h3 style="font-size:15px">Описание</h3></div></div>
        <div class="markdown">${readme ? md(readme.slice(0, 50000)) : '<p class="muted">Описание отсутствует.</p>'}</div>
      </div>
    </div>
    <div class="sheet-actions">
      ${local ? `<span class="tag success">${icon("check_circle", "xs")} уже скачано</span><button class="btn tonal" type="button" data-action="goto-library">Библиотека</button>` : `<button class="btn filled" type="button" data-action="download" data-repo="${esc(repo)}" data-size="${detail.total_size || 0}">${icon("download")} Скачать ${fmtBytes(detail.total_size)}</button>`}
      <button class="btn outlined" type="button" data-action="copy-repo" data-repo="${esc(repo)}">${icon("content_copy")} Копировать ID</button>
      <a class="btn text" href="https://huggingface.co/${esc(repo)}" target="_blank" rel="noopener">${icon("open_in_new")} Hugging Face</a>
    </div>`;
    openSheet(sheet);
  } catch (error) {
    openSheet(`<div class="sheet-head"><div class="sheet-title-block"><div class="sheet-title">Ошибка</div></div><button class="icon-btn" type="button" data-action="close-sheet">${icon("close")}</button></div><div class="sheet-body"><div class="banner error">${icon("error")}<div>${esc(error.message)}</div></div></div>`);
  }
}

async function startBenchmark() {
  const modelId = $("#bench-model")?.value;
  if (!modelId) {
    toast("Выберите модель.", "warn");
    return;
  }
  const payload = {
    model_id: modelId,
    device: $("#bench-device")?.value || "CPU",
    iterations: Number($("#bench-iterations")?.value || 10),
    warmup: Number($("#bench-warmup")?.value || 2),
    mode: $("#bench-mode")?.value || "auto",
    prompt: $("#bench-prompt")?.value || "The capital of France is",
    max_new_tokens: Number($("#bench-tokens")?.value || 64),
  };
  Object.assign(state.bench, {
    modelId: payload.model_id,
    device: payload.device,
    iterations: payload.iterations,
    warmup: payload.warmup,
    mode: payload.mode,
    prompt: payload.prompt,
    max_tokens: payload.max_new_tokens,
    running: true,
  });
  try {
    await api.benchmark(payload);
    toast("Бенчмарк запущен", "success");
    state.dockOpen = true;
    await refreshJobs();
    render();
  } catch (error) {
    state.bench.running = false;
    toast(error.message, "error");
  }
}

async function startConvert() {
  let repo = ($("#convert-repo")?.value || "").trim();
  if (!repo) {
    toast("Укажите модель Hugging Face.", "warn");
    return;
  }
  const match = repo.match(/huggingface\.co\/([^/]+\/[^/?#]+)/i);
  if (match) repo = match[1];
  repo = repo.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (repo.split("/").length !== 2) {
    toast("Формат: organization/model", "warn");
    return;
  }
  const payload = {
    repo,
    task: $("#convert-task")?.value || "auto",
    weight_format: state.tools.convertFormat,
    output_name: ($("#convert-name")?.value || "").trim(),
    trust_remote_code: Boolean($("#convert-trust")?.checked),
  };
  try {
    await api.convert(payload);
    toast("Конвертация запущена", "success");
    state.dockOpen = true;
    await refreshJobs();
    render();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function installComponents(ids) {
  const list = Array.isArray(ids) ? ids : [ids];
  if (!list.length) {
    toast("Все компоненты уже установлены.", "info");
    return;
  }
  if (state.jobs.some((job) => job.kind === "install" && ["running", "queued"].includes(job.status))) {
    toast("Установка уже выполняется.", "info");
    return;
  }
  try {
    await api.install(list);
    toast("Установка запущена. Это может занять несколько минут.", "success", 6000);
    state.dockOpen = true;
    await refreshJobs();
    if (state.route === "tools" || state.route === "overview") render();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function saveSettings() {
  const payload = {
    theme: state.theme,
    proxy: $("#settings-proxy")?.value || "",
    default_device: $("#settings-device")?.value || "CPU",
    num_threads: Number($("#settings-threads")?.value || 0),
    confirm_delete: Boolean($("#settings-confirm")?.checked),
  };
  const token = $("#settings-token")?.value.trim();
  if (token) payload.hf_token = token;
  if ($("#settings-clear-token")?.checked) payload.clear_hf_token = true;
  try {
    const data = await api.saveSettings(payload);
    state.settings = data.settings;
    if (state.system) state.system.settings = data.settings;
    if (state.settings.default_device) {
      state.chat.device = state.settings.default_device;
      state.image.device = state.settings.default_device;
      state.bench.device = state.settings.default_device;
    }
    localStorage.setItem("ovs-theme", state.theme);
    toast("Настройки сохранены", "success");
    render();
  } catch (error) {
    toast(error.message, "error");
  }
}

// -------------------------------------------------------------------- chat
function chatPayload(text) {
  const messages = state.chat.messages
    .filter((message) => !message.streaming && message.content)
    .map((message) => ({ role: message.role, content: message.content }));
  return {
    model_id: state.chat.modelId,
    device: state.chat.device,
    system: state.chat.system,
    messages,
    params: state.chat.params,
  };
}

async function sendChat(text) {
  if (state.chat.streaming) return;
  const value = String(text || "").trim();
  if (!value) return;
  if (!state.chat.modelId) {
    toast("Сначала выберите модель.", "warn");
    return;
  }
  state.chat.messages.push({ role: "user", content: value });
  const assistant = { role: "assistant", content: "", streaming: true, metrics: null };
  state.chat.messages.push(assistant);
  const assistantIndex = state.chat.messages.length - 1;
  state.chat.streaming = true;
  state.chat.aborted = false;
  state.chat.metrics = "";
  state.chat.controller = new AbortController();
  render();
  scrollChat(true);

  const node = document.querySelector(`[data-message-index="${assistantIndex}"] .md-content`);
  try {
    await streamChat(chatPayload(), {
      signal: state.chat.controller.signal,
      onEvent: (event) => {
        if (event.event === "token") {
          assistant.content += event.text || "";
          if (node) node.textContent = assistant.content;
          scrollChat(false);
        } else if (event.event === "status") {
          const sub = $(".chat-head-sub");
          if (sub && event.detail) sub.textContent = event.detail;
        } else if (event.event === "done") {
          assistant.metrics = event.metrics || null;
          if (assistant.metrics?.throughput) {
            state.chat.metrics = `${assistant.metrics.tokens || ""} ток · ${assistant.metrics.throughput} ток/с`;
          }
        } else if (event.event === "error") {
          assistant.error = true;
          assistant.content += `${assistant.content ? "\n\n" : ""}${event.message || "Ошибка генерации."}`;
        }
      },
    });
    if (!assistant.content) {
      assistant.content = "Модель не вернула текст. Проверьте журнал в разделе «Инструменты».";
      assistant.error = true;
    }
  } catch (error) {
    if (error.name === "AbortError" || state.chat.aborted) {
      assistant.stopped = true;
    } else {
      assistant.error = true;
      assistant.content += `${assistant.content ? "\n\n" : ""}${error.message}`;
      toast(error.message, "error");
    }
  } finally {
    assistant.streaming = false;
    state.chat.streaming = false;
    state.chat.controller = null;
    render();
    scrollChat(true);
  }
}

function stopChat() {
  if (!state.chat.streaming) return;
  state.chat.aborted = true;
  state.chat.controller?.abort();
}

// -------------------------------------------------------------------- images
function bindImagePage() {
  const dropzone = $("#dropzone");
  if (dropzone) {
    dropzone.addEventListener("click", () => $("#image-file")?.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        $("#image-file")?.click();
      }
    });
    ["dragenter", "dragover"].forEach((name) => {
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.remove("drag");
      });
    });
    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (file) handleImageFile(file);
    });
  }
}

async function handleImageFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast("Нужен файл изображения (JPG, PNG, WebP).", "error");
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    toast("Файл больше 20 МБ.", "error");
    return;
  }
  try {
    const dataUrl = await fileToDataURL(file);
    state.image.dataUrl = dataUrl;
    state.image.fileName = file.name;
    state.image.result = null;
    render();
  } catch (error) {
    toast(error.message, "error");
  }
}

function bindVlmPage() {
  const dropzone = $("#vlm-dropzone");
  if (dropzone) {
    dropzone.addEventListener("click", () => $("#vlm-file")?.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        $("#vlm-file")?.click();
      }
    });
    ["dragenter", "dragover"].forEach((name) => {
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.remove("drag");
      });
    });
    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (file) handleVlmFile(file);
    });
  }
}

async function handleVlmFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast("Нужен файл изображения (JPG, PNG, WebP).", "error");
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    toast("Файл больше 20 МБ.", "error");
    return;
  }
  try {
    const dataUrl = await fileToDataURL(file);
    state.vlm.dataUrl = dataUrl;
    state.vlm.fileName = file.name;
    state.vlm.answer = "";
    state.vlm.error = "";
    state.vlm.metrics = "";
    render();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function startVlm() {
  if (state.vlm.streaming) return;
  if (!state.vlm.dataUrl) {
    toast("Сначала загрузите изображение.", "warn");
    return;
  }
  if (!state.vlm.prompt.trim()) {
    toast("Напишите вопрос к изображению.", "warn");
    return;
  }
  if (!state.vlm.modelId) {
    toast("Сначала скачайте VLM-модель.", "warn");
    return;
  }
  state.vlm.streaming = true;
  state.vlm.aborted = false;
  state.vlm.answer = "";
  state.vlm.error = "";
  state.vlm.metrics = "";
  state.vlm.controller = new AbortController();
  render();
  const answerCard = $(".vlm-answer-card");
  answerCard?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const body = $("#vlm-answer-body");
  try {
    await streamVLM(
      {
        model_id: state.vlm.modelId,
        image: state.vlm.dataUrl,
        prompt: state.vlm.prompt.trim(),
        device: state.vlm.device,
        params: state.vlm.params,
      },
      {
        signal: state.vlm.controller.signal,
        onEvent: (event) => {
          if (event.event === "token") {
            state.vlm.answer += event.text || "";
            if (body) body.textContent = state.vlm.answer;
          } else if (event.event === "done") {
            const metrics = event.metrics || {};
            if (metrics.throughput) {
              state.vlm.metrics = `${metrics.tokens || ""} ток · ${metrics.throughput} ток/с${metrics.ttft_ms ? ` · TTFT ${Math.round(metrics.ttft_ms)} мс` : ""}`;
            }
          } else if (event.event === "error") {
            state.vlm.error = event.message || "Ошибка VLM.";
          } else if (event.event === "status") {
            const sub = $(".vlm-answer-card .card-sub");
            if (sub && event.detail) sub.textContent = event.detail;
          }
        },
      },
    );
    if (!state.vlm.answer && !state.vlm.error) {
      state.vlm.error = "Модель не вернула ответ. Проверьте журнал.";
    }
  } catch (error) {
    if (error.name === "AbortError" || state.vlm.aborted) {
      if (!state.vlm.answer) state.vlm.error = "Генерация остановлена.";
    } else {
      state.vlm.error = error.message;
      toast(error.message, "error");
    }
  } finally {
    state.vlm.streaming = false;
    state.vlm.controller = null;
    render();
  }
}

function stopVlm() {
  if (!state.vlm.streaming) return;
  state.vlm.aborted = true;
  state.vlm.controller?.abort();
}

function clearVlm() {
  if (state.vlm.streaming) stopVlm();
  state.vlm.dataUrl = null;
  state.vlm.fileName = "";
  state.vlm.prompt = "";
  state.vlm.answer = "";
  state.vlm.error = "";
  state.vlm.metrics = "";
  render();
}

async function runImage() {
  if (state.image.running || !state.image.dataUrl) return;
  if (!state.image.modelId) {
    toast("Сначала выберите модель.", "warn");
    return;
  }
  state.image.running = true;
  render();
  state.image.running = true;
  const button = $("#image-run");
  if (button) button.disabled = true;
  try {
    const data = await api.image({
      model_id: state.image.modelId,
      image: state.image.dataUrl,
      task: state.image.task,
      threshold: state.image.threshold,
      top_k: 5,
      device: state.image.device,
    });
    state.image.result = data;
    toast(data.task === "detect" ? `Найдено объектов: ${data.detections?.length || 0}` : "Готово", "success", 2600);
  } catch (error) {
    toast(error.message, "error", 7000);
  } finally {
    state.image.running = false;
    render();
  }
}

// ------------------------------------------------------------------ catalog
const debouncedCatalog = debounce(() => loadCatalog(), 450);

function buildJobLogModal(job) {
  if (!job) {
    openModal(`<div class="modal-head"><h3>Журнал недоступен</h3><button class="icon-btn small" type="button" data-action="close-modal">${icon("close")}</button></div>`);
    return;
  }
  openModal(`<div class="modal-head"><div><h3>${esc(job.title)}</h3><div class="small muted">${esc(job.status)} · ${esc(job.detail || "")}</div></div><button class="icon-btn small" type="button" data-action="close-modal">${icon("close")}</button></div>
    <pre class="log-box" style="max-height:52vh">${esc((job.logs || []).join("\n") || "Журнал пуст.")}</pre>
    <div class="modal-actions split">
      <button class="btn text small" type="button" data-action="copy-job-log" data-id="${esc(job.id)}">${icon("content_copy")} Копировать</button>
      <div class="flex gap-8">
        ${["running", "queued"].includes(job.status) ? `<button class="btn danger small" type="button" data-action="job-cancel" data-id="${esc(job.id)}">${icon("stop")} Отменить</button>` : ""}
        <button class="btn tonal small" type="button" data-action="close-modal">Закрыть</button>
      </div>
    </div>`);
}

async function openJobLog(jobId) {
  let job = state.jobs.find((item) => item.id === jobId);
  try {
    const data = await api.jobs();
    state.jobs = data.jobs || state.jobs;
    job = state.jobs.find((item) => item.id === jobId) || job;
  } catch {
    // use cached
  }
  buildJobLogModal(job);
}

// ------------------------------------------------------------------ routing
function renderAfterAction() {
  if (!state.chat.streaming) render();
}

function wireEvents() {
  window.addEventListener("hashchange", () => {
    parseRoute();
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
    updateChrome();
  });

  document.addEventListener("click", async (event) => {
    const routeLink = event.target.closest("[data-route]");
    if (routeLink) {
      event.preventDefault();
      goto(routeLink.dataset.route);
      return;
    }
    const target = event.target.closest("[data-action]");
    if (!target) {
      const card = event.target.closest('[data-action="open-model"]');
      if (card) {
        openModelDetail(card.dataset.repo);
      }
      return;
    }
    const action = target.dataset.action;
    if (target.closest("#chat-form") && action === "chat-send") return;
    event.preventDefault();
    event.stopPropagation();
    try {
      switch (action) {
        case "goto-catalog":
          goto("models");
          break;
        case "goto-chat":
          goto("chat");
          break;
        case "goto-library":
          goto("library");
          break;
        case "goto-tools":
          goto("tools");
          break;
        case "goto-images":
          goto("images");
          break;
        case "goto-benchmark":
          goto("benchmark");
          break;
        case "cycle-theme":
          cycleTheme();
          break;
        case "set-theme":
          persistTheme(target.dataset.theme);
          if (state.route === "settings") render();
          break;
        case "toggle-dock":
          toggleDock();
          break;
        case "mobile-more":
          openMobileMenu();
          break;
        case "mobile-goto":
          closeModal();
          goto(target.dataset.routeX);
          break;
        case "refresh-page":
          await refreshCurrentPage();
          break;
        case "refresh-system": {
          toast("Проверяем устройства…", "info", 1600);
          await loadSystem(true);
          renderAfterAction();
          break;
        }
        case "download":
          await handleDownload(target.dataset.repo, Number(target.dataset.size || 0));
          break;
        case "open-model":
          await openModelDetail(target.dataset.repo);
          break;
        case "close-sheet":
          closeSheet();
          break;
        case "close-modal":
          closeModal();
          break;
        case "copy-repo":
          await copyText(target.dataset.repo || "");
          break;
        case "clear-catalog-search":
          state.catalog.q = "";
          renderAfterAction();
          loadCatalog();
          break;
        case "catalog-task":
          state.catalog.task = target.dataset.task || "";
          render();
          loadCatalog();
          break;
        case "library-filter":
          state.library.filter = target.dataset.filter || "all";
          render();
          break;
        case "library-chat":
          state.chat.modelId = target.dataset.id;
          goto("chat");
          break;
        case "library-image":
          state.image.modelId = target.dataset.id;
          state.image.result = null;
          goto("images");
          break;
        case "library-vlm":
          state.vlm.modelId = target.dataset.id;
          state.vlm.answer = "";
          state.vlm.error = "";
          goto("vlm");
          break;
        case "library-bench":
          state.bench.modelId = target.dataset.id;
          goto("benchmark");
          break;
        case "reveal-model":
          await api.revealModel(target.dataset.id);
          break;
        case "delete-model": {
          const id = target.dataset.id;
          const name = target.dataset.name || id;
          const confirmed = await confirmDialog({
            title: "Удалить модель?",
            text: `<p><strong>${esc(name)}</strong></p><p>Файлы будут удалены с диска без возможности восстановления.</p>`,
            confirmLabel: "Удалить",
            danger: true,
          });
          if (!confirmed) return;
          await api.deleteModel(id);
          toast("Модель удалена", "success");
          await loadModels();
          render();
          break;
        }
        case "job-cancel": {
          const id = target.dataset.id;
          await api.cancelJob(id);
          toast("Отмена задачи…", "info", 2000);
          await refreshJobs();
          break;
        }
        case "job-log":
          await openJobLog(target.dataset.id);
          break;
        case "copy-job-log": {
          const job = state.jobs.find((item) => item.id === target.dataset.id);
          await copyText((job?.logs || []).join("\n"));
          break;
        }
        case "install-component":
          await installComponents([target.dataset.component]);
          break;
        case "install-missing": {
          const missing = (state.system?.components || []).filter((component) => !component.installed).map((component) => component.id);
          await installComponents(missing);
          break;
        }
        case "refresh-logs":
          await loadLogs();
          break;
        case "copy-logs":
          await copyText(state.tools.logs || "");
          break;
        case "open-logs":
          await api.openFolder("logs");
          break;
        case "open-models":
          await api.openFolder("models");
          break;
        case "open-base":
          await api.openFolder("base");
          break;
        case "save-settings":
          await saveSettings();
          break;
        case "shutdown": {
          const confirmed = await confirmDialog({
            title: "Завершить работу?",
            text: "Сервер будет остановлен, активные задачи отменены. Окно приложения можно закрыть.",
            confirmLabel: "Выйти",
            danger: true,
          });
          if (!confirmed) return;
          try {
            await api.shutdown();
          } catch {
            // server may close connection
          }
          document.body.innerHTML = `<div class="boot-screen" style="min-height:100vh"><img src="assets/logo.svg" width="56" height="56" alt=""><h2 style="font-size:20px">OpenVINO Studio остановлен</h2><p>Это окно можно закрыть.</p><button class="btn filled" onclick="location.reload()">Запустить снова</button></div>`;
          break;
        }
        case "chat-suggestion": {
          const text = target.dataset.text || "";
          await sendChat(text);
          break;
        }
        case "chat-new":
          if (state.chat.streaming) stopChat();
          state.chat.messages = [];
          state.chat.metrics = "";
          render();
          break;
        case "chat-device":
          if (state.chat.streaming) {
            toast("Дождитесь окончания генерации.", "info");
            return;
          }
          state.chat.device = target.dataset.device || "CPU";
          render();
          break;
        case "chat-stop":
          stopChat();
          break;
        case "vlm-stop":
          stopVlm();
          break;
        case "vlm-clear":
          clearVlm();
          break;
        case "vlm-clear-image":
          state.vlm.dataUrl = null;
          state.vlm.fileName = "";
          state.vlm.answer = "";
          state.vlm.error = "";
          state.vlm.metrics = "";
          render();
          break;
        case "vlm-suggestion": {
          const text = target.dataset.text || "";
          state.vlm.prompt = text;
          const box = $("#vlm-prompt");
          if (box) {
            box.value = text;
            box.focus();
          }
          break;
        }
        case "image-run":
          await runImage();
          break;
        case "image-clear":
          state.image.dataUrl = null;
          state.image.fileName = "";
          state.image.result = null;
          render();
          break;
        case "image-task":
          state.image.task = target.dataset.task || "auto";
          render();
          break;
        case "open-image":
          if (state.image.result?.image || state.image.dataUrl) {
            openModal(`<div class="modal-head"><div><h3>Изображение</h3></div><button class="icon-btn small" type="button" data-action="close-modal">${icon("close")}</button></div><div style="border-radius:16px;overflow:hidden;background:var(--surface-low)"><img src="${state.image.result?.image || state.image.dataUrl}" style="display:block;width:100%;height:auto;max-height:70vh;object-fit:contain" alt=""></div><div class="modal-actions"><button class="btn tonal" type="button" data-action="close-modal">Закрыть</button></div>`);
          }
          break;
        case "reload-page":
          location.reload();
          break;
        case "reload-benchmarks":
          await loadBenchmarks();
          toast("История обновлена", "info", 1600);
          break;
        default:
          break;
      }
    } catch (error) {
      toast(error.message || String(error), "error", 6500);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches('[data-action="open-model"]')) {
      event.preventDefault();
      openModelDetail(event.target.dataset.repo);
    }
    if (event.key === "Enter" && !event.shiftKey && event.target.id === "chat-input") {
      event.preventDefault();
      $("#chat-form")?.requestSubmit();
    }
  });

  document.addEventListener("submit", async (event) => {
    if (event.target.id === "chat-form") {
      event.preventDefault();
      const input = $("#chat-input");
      const text = input?.value || "";
      if (input) input.value = "";
      await sendChat(text);
      return;
    }
    if (event.target.id === "bench-form") {
      event.preventDefault();
      await startBenchmark();
      return;
    }
    if (event.target.id === "convert-form") {
      event.preventDefault();
      await startConvert();
    }
    if (event.target.id === "vlm-form") {
      event.preventDefault();
      await startVlm();
    }
  });

  document.addEventListener("input", (event) => {
    const id = event.target.id;
    if (id === "catalog-search") {
      state.catalog.q = event.target.value;
      state.catalog.loading = true;
      updateCatalogResults();
      debouncedCatalog();
    } else if (id === "library-search") {
      state.library.q = event.target.value;
      const host = $("#library-list");
      if (host) host.innerHTML = libraryList(state);
    } else if (id === "chat-temperature") {
      state.chat.params.temperature = Number(event.target.value);
      const label = $("#chat-temperature-value");
      if (label) label.textContent = Number(event.target.value).toFixed(2);
    } else if (id === "chat-maxtokens") {
      state.chat.params.max_new_tokens = Number(event.target.value);
      const label = $("#chat-maxtokens-value");
      if (label) label.textContent = event.target.value;
    } else if (id === "chat-system") {
      state.chat.system = event.target.value;
    } else if (id === "image-threshold") {
      state.image.threshold = Number(event.target.value);
      const label = $("#image-threshold-value");
      if (label) label.textContent = Number(event.target.value).toFixed(2);
    } else if (id === "vlm-prompt") {
      state.vlm.prompt = event.target.value;
    } else if (id === "vlm-temperature") {
      state.vlm.params.temperature = Number(event.target.value);
      const label = $("#vlm-temperature-value");
      if (label) label.textContent = Number(event.target.value).toFixed(2);
    } else if (id === "vlm-maxtokens") {
      state.vlm.params.max_new_tokens = Number(event.target.value) || 512;
    }
  });

  document.addEventListener("change", async (event) => {
    const id = event.target.id;
    if (id === "catalog-sort") {
      state.catalog.sort = event.target.value;
      loadCatalog();
    } else if (id === "catalog-official") {
      state.catalog.official = event.target.checked;
      loadCatalog();
    } else if (id === "image-model") {
      state.image.modelId = event.target.value;
      state.image.result = null;
      render();
    } else if (id === "image-device") {
      state.image.device = event.target.value;
    } else if (id === "chat-model") {
      if (state.chat.streaming) {
        toast("Сначала остановите генерацию.", "info");
        return;
      }
      state.chat.modelId = event.target.value;
      state.chat.metrics = "";
      render();
    } else if (id === "image-file") {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (file) await handleImageFile(file);
    } else if (id === "vlm-file") {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (file) await handleVlmFile(file);
    } else if (id === "vlm-model") {
      if (state.vlm.streaming) {
        toast("Сначала остановите генерацию.", "info");
        return;
      }
      state.vlm.modelId = event.target.value;
      state.vlm.answer = "";
      state.vlm.error = "";
      state.vlm.metrics = "";
      render();
    } else if (id === "vlm-device") {
      state.vlm.device = event.target.value;
    }
  });

  document.addEventListener("click", (event) => {
    const format = event.target.closest("[data-format]");
    if (format) {
      state.tools.convertFormat = format.dataset.format;
      $$("[data-format]").forEach((button) => button.classList.toggle("active", button === format));
    }
  });
}

function openMobileMenu() {
  openModal(`<div class="modal-head"><div><h3>Ещё</h3><div class="small muted">Разделы приложения</div></div><button class="icon-btn small" type="button" data-action="close-modal">${icon("close")}</button></div>
    <div class="mobile-menu">
      <button type="button" data-action="mobile-goto" data-route-x="vlm"><span class="ms">visibility</span><span>VLM · изображения + текст</span><span class="ms mobile-chevron">chevron_right</span></button>
      <button type="button" data-action="mobile-goto" data-route-x="images"><span class="ms">image</span><span>Изображения</span><span class="ms mobile-chevron">chevron_right</span></button>
      <button type="button" data-action="mobile-goto" data-route-x="benchmark"><span class="ms">speed</span><span>Бенчмарк</span><span class="ms mobile-chevron">chevron_right</span></button>
      <button type="button" data-action="mobile-goto" data-route-x="tools"><span class="ms">build</span><span>Инструменты</span><span class="ms mobile-chevron">chevron_right</span></button>
      <button type="button" data-action="mobile-goto" data-route-x="settings"><span class="ms">settings</span><span>Настройки</span><span class="ms mobile-chevron">chevron_right</span></button>
    </div>
    <div class="modal-actions"><button class="btn tonal" type="button" data-action="close-modal">Закрыть</button></div>`);
}

async function refreshCurrentPage() {
  try {
    if (state.route === "overview" || state.route === "settings") {
      await loadSystem(true);
      await loadModels();
    } else if (state.route === "models") {
      await loadCatalog();
    } else if (state.route === "library") {
      await loadModels();
    } else if (state.route === "benchmark") {
      await loadBenchmarks();
      await loadModels();
    } else if (state.route === "tools") {
      await loadSystem(true);
      await loadLogs();
    } else if (state.route === "chat" || state.route === "images") {
      await loadModels();
    }
    await refreshJobs();
    renderAfterAction();
    toast("Обновлено", "info", 1500);
  } catch (error) {
    toast(error.message, "error");
  }
}

// ------------------------------------------------------------------- start
boot().catch((error) => {
  const view = $("#view");
  if (view) {
    view.innerHTML = `<div class="fatal">${emptyBox(
      "error",
      "Не удалось запустить интерфейс",
      esc(error.message || String(error)),
      `<button class="btn filled" type="button" onclick="location.reload()">Повторить</button>`,
    )}</div>`;
  }
});
