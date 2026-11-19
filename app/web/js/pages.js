// Page templates. Each function returns an HTML string from the app state.

import { esc, icon, fmtBytes, fmtNumber, fmtDate, fmtDuration, md, kindMeta, repoTitle, plural } from "./util.js";
import {
  curatedCard,
  searchCard,
  libraryRow,
  statCard,
  deviceLine,
  jobItem,
  componentRow,
  metricCard,
  skeletonCards,
  benchmarkTable,
  chartRows,
  emptyBox,
  modelIcon,
} from "./components.js";

const ROUTE_TITLES = {
  overview: "Обзор",
  models: "Модели",
  library: "Библиотека",
  chat: "Чат",
  vlm: "VLM",
  images: "Изображения",
  benchmark: "Бенчмарк",
  tools: "Инструменты",
  settings: "Настройки",
};

export function routeTitle(route) {
  return ROUTE_TITLES[route] || "Обзор";
}

function isLocal(state, repo) {
  return Boolean(state.models?.models?.some((model) => model.repo === repo));
}

function componentInstalled(state, id) {
  return Boolean(state.system?.components?.find((component) => component.id === id)?.installed);
}

function devices(state) {
  return state.system?.openvino?.devices || [];
}

function hasDevice(state, prefix) {
  return devices(state).some((device) => String(device.id).toUpperCase().startsWith(prefix));
}

function pageHead(title, text, actions = "") {
  return `<div class="page-head">
    <div class="page-head-text"><p class="page-intro">${text}</p></div>
    ${actions ? `<div class="page-actions">${actions}</div>` : ""}
  </div>`;
}

// ------------------------------------------------------------------ overview
export function overview(state) {
  const system = state.system;
  const models = state.models;
  const openvino = system?.openvino || {};
  const runtimeReady = Boolean(openvino.installed);
  const genaiReady = componentInstalled(state, "genai");
  const devicesList = devices(state);
  const llmCount = models?.models?.filter((model) => model.chat_ready).length || 0;
  const installedModels = models?.count || 0;
  const jobs = state.jobs || [];

  const hero = `<section class="hero">
    <div class="hero-copy">
      <span class="hero-badge">${icon("bolt", "xs")} Локальный AI · OpenVINO</span>
      <h2>Модели работают на вашем ПК.<br>Без облака и терминала.</h2>
      <p>Скачивайте модели с Hugging Face, общайтесь с LLM и запускайте инференс на Intel CPU, GPU или NPU. Всё хранится на внешнем диске.</p>
      <div class="hero-actions">
        <button class="btn filled large" type="button" data-action="goto-catalog">${icon("travel_explore")} Каталог моделей</button>
        <button class="btn tonal large" type="button" data-action="goto-chat">${icon("forum")} Открыть чат</button>
      </div>
    </div>
    <div class="hero-side">
      <div class="hero-side-title"><span>Окружение</span><span class="status-pill ${runtimeReady ? "ok" : "warn"}">${runtimeReady ? "готово" : "нужна настройка"}</span></div>
      <div class="hero-device-list">
        ${
          devicesList.length
            ? devicesList.slice(0, 4).map((device) => deviceLine(device, true)).join("")
            : `<div class="device-line"><div class="device-icon">${icon("developer_board")}</div><div class="grow"><div class="device-name">${runtimeReady ? "Устройства не найдены" : "OpenVINO Runtime"}</div><div class="device-sub">${runtimeReady ? "Проверьте драйверы" : "Установите компонент Runtime"}</div></div></div>`
        }
      </div>
      <div class="hero-note">${runtimeReady ? `OpenVINO ${esc(String(openvino.ov_version || "").split("-")[0])} · Python ${esc(system?.python || "")}` : "Откройте «Инструменты», чтобы установить OpenVINO одной кнопкой."}</div>
    </div>
  </section>`;

  const stats = `<div class="stats">
    ${statCard({
      iconName: "memory",
      value: runtimeReady ? esc(String(openvino.ov_version || "—").split("-")[0]) : "—",
      label: "OpenVINO Runtime",
      hint: runtimeReady ? "установлен" : "не установлен",
      tone: runtimeReady ? "green" : "orange",
    })}
    ${statCard({
      iconName: "devices",
      value: String(devicesList.length || 0),
      label: "Доступных устройств",
      hint: devicesList.map((device) => device.id).join(" · ") || "—",
      tone: "primary",
    })}
    ${statCard({
      iconName: "inventory_2",
      value: String(installedModels),
      label: "Моделей в библиотеке",
      hint: models?.total_size_label || "0 Б",
      tone: "",
    })}
    ${statCard({
      iconName: "hard_drive",
      value: system?.disk?.free_label || "—",
      label: "Свободно на диске",
      hint: system?.disk ? `${system.disk.percent}% занято` : "",
      tone: "",
    })}
  </div>`;

  const checklist = `<div class="section">
    <div class="section-head"><div class="section-title"><h3>Быстрый старт</h3><span>три шага до первого ответа</span></div></div>
    <div class="card card-pad">
      <div class="checklist">
        <div class="check-item">
          <div class="check-icon ${runtimeReady ? "done" : ""}">${icon(runtimeReady ? "check" : "download")}</div>
          <div class="check-body"><strong>Установите OpenVINO Runtime</strong><span>Ядро инференса и поддержка CPU, GPU, NPU.</span></div>
          <div class="check-action">${runtimeReady ? `<span class="tag success">готово</span>` : `<button class="btn tonal small" type="button" data-action="install-component" data-component="runtime">Установить</button>`}</div>
        </div>
        <div class="check-item">
          <div class="check-icon ${genaiReady ? "done" : ""}">${icon(genaiReady ? "check" : "chat")}</div>
          <div class="check-body"><strong>Добавьте OpenVINO GenAI</strong><span>Нужен для потокового чата с языковыми моделями.</span></div>
          <div class="check-action">${genaiReady ? `<span class="tag success">готово</span>` : `<button class="btn tonal small" type="button" data-action="install-component" data-component="genai">Установить</button>`}</div>
        </div>
        <div class="check-item">
          <div class="check-icon ${installedModels ? "done" : ""}">${icon(installedModels ? "check" : "cloud_download")}</div>
          <div class="check-body"><strong>Скачайте модель</strong><span>${installedModels ? `В библиотеке уже ${installedModels} ${plural(installedModels, "модель", "модели", "моделей")}, из них ${llmCount} для чата.` : "Начните с лёгкой TinyLlama или Qwen 1.5B."}</span></div>
          <div class="check-action">${installedModels ? `<button class="btn text small" type="button" data-action="goto-library">Библиотека ${icon("arrow_forward", "xs")}</button>` : `<button class="btn filled small" type="button" data-action="goto-catalog">Выбрать модель</button>`}</div>
        </div>
      </div>
    </div>
  </div>`;

  const curated = state.catalog?.curated || [];
  const recommended = `<div class="section">
    <div class="section-head">
      <div class="section-title"><h3>Рекомендуемые модели</h3><span>проверены для OpenVINO</span></div>
      <button class="section-link" type="button" data-action="goto-catalog">Все модели ${icon("arrow_forward")}</button>
    </div>
    ${curated.length ? `<div class="model-grid">${curated.slice(0, 3).map((item) => curatedCard(item, isLocal(state, item.repo))).join("")}</div>` : skeletonCards(3)}
  </div>`;

  const recent = `<div class="section">
    <div class="section-head"><div class="section-title"><h3>Недавние задачи</h3></div>${jobs.length ? `<button class="section-link" type="button" data-action="toggle-dock">Все задачи ${icon("arrow_forward")}</button>` : ""}</div>
    <div class="card card-pad">
      ${
        jobs.length
          ? `<div style="display:flex;flex-direction:column">${jobs
              .slice(0, 4)
              .map(
                (job) => `<div class="check-item">
                  <div class="check-icon ${job.status === "done" ? "done" : ""}">${icon(job.status === "done" ? "check" : job.status === "error" ? "error" : "progress_activity")}</div>
                  <div class="check-body"><strong>${esc(job.title)}</strong><span>${esc(job.detail || "")}</span></div>
                  <span class="small muted nowrap">${esc(fmtDate(job.created_at))}</span>
                </div>`,
              )
              .join("")}</div>`
          : `<div class="flex-between" style="padding:6px 0">
              <div class="flex gap-12"><div class="check-icon">${icon("science")}</div><div><strong class="small">Здесь появятся загрузки, конвертации и бенчмарки</strong><div class="small muted">Запустите первую задачу из каталога моделей.</div></div></div>
              <button class="btn text small" type="button" data-action="goto-catalog">В каталог ${icon("arrow_forward", "xs")}</button>
            </div>`
      }
    </div>
  </div>`;

  const devicesSection = `<div class="section">
    <div class="section-head"><div class="section-title"><h3>Устройства</h3><span>инференс на доступном железе</span></div><button class="section-link" type="button" data-action="refresh-system">${icon("refresh")} Проверить</button></div>
    <div class="card card-pad">
      ${
        devicesList.length
          ? `<div class="hero-device-list">${devicesList.map((device) => deviceLine(device, true)).join("")}</div>`
          : `<div class="flex gap-12" style="padding:4px 0"><div class="device-icon">${icon("info")}</div><div class="grow"><strong class="small">${runtimeReady ? "Устройства не обнаружены" : "OpenVINO ещё не установлен"}</strong><div class="small muted">${runtimeReady ? "Обновите драйверы Intel GPU/NPU и нажмите «Проверить»." : "Установите Runtime в разделе «Инструменты»."}</div></div><button class="btn tonal small" type="button" data-action="goto-tools">Инструменты</button></div>`
      }
      <div class="banner info mt-16">${icon("lightbulb")}<div>Совет: CPU работает всегда. Intel GPU ускоряет LLM и изображения, NPU — экономит батарею на ноутбуках.</div></div>
    </div>
  </div>`;

  return `<div class="page">
    ${pageHead("Обзор", "Локальный AI-стек с загрузкой моделей, чатом и бенчмарком.", `<button class="btn outlined" type="button" data-action="refresh-system">${icon("refresh")} Обновить окружение</button>`)}
    ${!runtimeReady && system ? `<div class="banner warning" style="margin-bottom:18px">${icon("warning")}<div><strong>OpenVINO Runtime не установлен.</strong> Установите компоненты, чтобы запускать модели. Это делается здесь, без терминала: <button class="btn text small" type="button" data-action="goto-tools" style="padding:0;height:auto">перейти к установке →</button></div></div>` : ""}
    ${hero}
    <div class="section">${stats}</div>
    ${checklist}
    ${recommended}
    <div class="overview-bottom">
      ${recent}
      <div class="section" style="margin-top:30px">
        <div class="section-head"><div class="section-title"><h3>Хранилище</h3></div></div>
        <div class="card card-pad">
          <div class="disk-meter">
            <div class="flex-between"><span class="small">Внешний диск</span><span class="small muted">${esc(system?.disk?.free_label || "—")} свободно</span></div>
            <div class="progress"><div class="progress-bar" style="width:${Math.min(100, system?.disk?.percent || 0)}%"></div></div>
            <div class="disk-meter-labels"><span>${esc(system?.disk?.used_label || "—")} занято</span><span>${esc(system?.disk?.total_label || "—")} всего</span></div>
          </div>
          <hr class="divider">
          <div class="setting-row"><label>Папка моделей</label><div class="path-box"><input class="input" readonly value="${esc(system?.models_path || "")}"><button class="icon-btn small" type="button" data-action="open-models">${icon("folder_open")}</button></div></div>
          <div class="small muted mt-8">Модели, кэш и окружение хранятся на этом диске. Ничего не пишется в системный диск, кроме временных файлов Windows.</div>
        </div>
      </div>
    </div>
    ${devicesSection}
  </div>`;
}

// ------------------------------------------------------------------- catalog
export function catalog(state) {
  const catalog = state.catalog;
  const tasks = [
    ["", "Все"],
    ["text-generation", "Чат"],
    ["image-classification", "Изображения"],
    ["object-detection", "Детекция"],
    ["image-text-to-text", "Мультимодальные"],
  ];
  const showCurated = !catalog.q && !catalog.task;
  return `<div class="page">
    ${pageHead("Модели", "Каталог Hugging Face с фильтром OpenVINO. Скачивание идёт напрямую на внешний диск.", `<button class="btn outlined" type="button" data-action="refresh-system">${icon("refresh")} Обновить окружение</button>`)}
    <div class="card card-pad" style="margin-bottom:20px">
      <div class="search-bar" style="margin-bottom:14px">
        ${icon("search")}
        <input id="catalog-search" type="search" placeholder="Поиск: qwen, llama, whisper, yolo…" value="${esc(catalog.q)}" autocomplete="off">
        ${catalog.q ? `<button class="clear-search" type="button" data-action="clear-catalog-search" aria-label="Очистить">${icon("close")}</button>` : ""}
      </div>
      <div class="flex-between" style="align-items:flex-start;flex-wrap:wrap;gap:12px">
        <div class="chips">
          ${tasks.map(([value, label]) => `<button class="chip ${catalog.task === value ? "active" : ""}" type="button" data-action="catalog-task" data-task="${value}">${label}</button>`).join("")}
        </div>
        <div class="flex gap-12" style="flex-wrap:wrap">
          <label class="switch-row" style="padding:0;gap:9px">
            <span class="switch-copy"><strong style="font-size:12px">Только OpenVINO</strong></span>
            <span class="switch"><input type="checkbox" id="catalog-official" ${catalog.official ? "checked" : ""}><span class="track"></span><span class="thumb"></span></span>
          </label>
          <select class="select" id="catalog-sort" style="height:36px;width:auto;min-width:150px;padding-left:12px;font-size:12px">
            <option value="downloads" ${catalog.sort === "downloads" ? "selected" : ""}>По загрузкам</option>
            <option value="likes" ${catalog.sort === "likes" ? "selected" : ""}>По лайкам</option>
            <option value="lastModified" ${catalog.sort === "lastModified" ? "selected" : ""}>Новые</option>
          </select>
        </div>
      </div>
    </div>
    ${showCurated ? `<div class="section" style="margin-top:0">
      <div class="section-head"><div class="section-title"><h3>Подборка OpenVINO Studio</h3><span>готовые IR-модели</span></div></div>
      ${catalog.curated.length ? `<div class="model-grid">${catalog.curated.map((item) => curatedCard(item, isLocal(state, item.repo))).join("")}</div>` : skeletonCards(6)}
    </div>` : ""}
    <div class="section" style="${showCurated ? "" : "margin-top:0"}">
      <div class="section-head">
        <div class="section-title"><h3>${catalog.q ? `Результаты: «${esc(catalog.q)}»` : "Модели Hugging Face"}</h3><span id="catalog-count">${catalog.loading ? "поиск…" : `${catalog.results.length} ${plural(catalog.results.length, "модель", "модели", "моделей")}`}</span></div>
      </div>
      <div id="catalog-results">${catalogResults(state)}</div>
    </div>
  </div>`;
}

export function catalogResults(state) {
  const catalog = state.catalog;
  if (catalog.loading) return skeletonCards(6);
  if (catalog.error) {
    return `<div class="banner error">${icon("error")}<div><strong>Не удалось загрузить каталог.</strong><br>${esc(catalog.error)}</div></div>`;
  }
  if (!catalog.results.length) {
    return emptyBox("search_off", "Ничего не найдено", "Попробуйте другой запрос или снимите фильтр задачи. Для конвертации подойдёт любая модель Hugging Face.", `<button class="btn tonal" type="button" data-action="goto-tools">Конвертировать модель</button>`);
  }
  return `<div class="model-grid">${catalog.results.map((item) => searchCard(item, isLocal(state, item.repo))).join("")}</div>`;
}

// ------------------------------------------------------------------- library
export function library(state) {
  const data = state.models;
  const filter = state.library.filter;
  const filters = [
    ["all", "Все"],
    ["llm", "LLM"],
    ["image", "Изображения"],
    ["detection", "Детекция"],
    ["other", "Другое"],
  ];
  return `<div class="page">
    ${pageHead("Библиотека", "Скачанные и сконвертированные модели на внешнем диске.", `<button class="btn outlined" type="button" data-action="open-models">${icon("folder_open")} Открыть папку</button><button class="btn filled" type="button" data-action="goto-catalog">${icon("add")} Добавить модель</button>`)}
    ${
      data && data.count
        ? `<div class="card card-pad" style="margin-bottom:18px">
            <div class="flex-between" style="flex-wrap:wrap;gap:14px">
              <div class="flex gap-12">
                <div class="stat-icon primary">${icon("inventory_2")}</div>
                <div><div style="font-size:15px;font-weight:500">${data.count} ${plural(data.count, "модель", "модели", "моделей")} · ${esc(data.total_size_label)}</div><div class="small muted" style="word-break:break-all">${esc(data.path)}</div></div>
              </div>
              <div class="small muted">Модели можно удалять и перекачивать в любой момент</div>
            </div>
          </div>`
        : ""
    }
    <div class="library-toolbar">
      <div class="search-bar">
        ${icon("search")}
        <input id="library-search" type="search" placeholder="Фильтр по названию…" value="${esc(state.library.q)}" autocomplete="off">
      </div>
      <div class="chips">
        ${filters.map(([value, label]) => `<button class="chip ${filter === value ? "active" : ""}" type="button" data-action="library-filter" data-filter="${value}">${label}</button>`).join("")}
      </div>
    </div>
    <div id="library-list">${libraryList(state)}</div>
  </div>`;
}

export function libraryList(state) {
  const data = state.models;
  if (!data) return skeletonCards(4);
  const query = state.library.q.trim().toLowerCase();
  const filter = state.library.filter;
  let items = data.models || [];
  if (query) {
    items = items.filter((model) => `${model.name} ${model.repo} ${model.id}`.toLowerCase().includes(query));
  }
  if (filter !== "all") {
    items = items.filter((model) => {
      if (filter === "llm") return model.kind === "llm" || model.kind === "vlm";
      if (filter === "image") return model.kind === "image";
      if (filter === "detection") return model.kind === "detection";
      return !["llm", "vlm", "image", "detection"].includes(model.kind);
    });
  }
  if (!items.length) {
    return emptyBox(
      "inventory_2",
      data.count ? "Ничего не найдено" : "Библиотека пуста",
      data.count ? "Измените фильтр или поисковый запрос." : "Скачайте готовую OpenVINO-модель или сконвертируйте любую модель Hugging Face.",
      `<button class="btn filled" type="button" data-action="goto-catalog">${icon("travel_explore")} Открыть каталог</button>`,
    );
  }
  return `<div class="library-list">${items.map(libraryRow).join("")}</div>`;
}

// ----------------------------------------------------------------------- chat
export function chat(state) {
  const models = (state.models?.models || []).filter((model) => model.chat_ready);
  const genaiReady = componentInstalled(state, "genai");
  const runtimeReady = Boolean(state.system?.openvino?.installed);
  const chatState = state.chat;
  const model = models.find((item) => item.id === chatState.modelId) || models[0];
  const modelName = model?.name || "Модель не выбрана";

  if (!models.length) {
    return `<div class="page">
      ${pageHead("Чат", "Локальный чат с языковыми моделями через OpenVINO GenAI.")}
      ${emptyBox(
        "forum",
        "Нет модели для чата",
        runtimeReady
          ? "Скачайте LLM из каталога — например, TinyLlama 1.1B или Qwen 2.5 1.5B. После загрузки модель появится здесь автоматически."
          : "Сначала установите OpenVINO Runtime и GenAI в разделе «Инструменты», затем скачайте языковую модель.",
        `<div class="flex gap-8" style="flex-wrap:wrap;justify-content:center"><button class="btn filled" type="button" data-action="goto-catalog">${icon("travel_explore")} В каталог</button><button class="btn tonal" type="button" data-action="goto-tools">${icon("build")} Установить компоненты</button></div>`,
      )}
    </div>`;
  }

  const messages = chatState.messages || [];
  const deviceOptions = [
    ["CPU", "CPU"],
    ["GPU", "GPU"],
    ["NPU", "NPU"],
    ["AUTO", "AUTO"],
  ];
  const devicesAvailable = devices(state).map((device) => String(device.id).toUpperCase());
  const chatMessages = messages.length
    ? messages.map((message, index) => chatMessageHTML(message, index, state)).join("")
    : `<div class="chat-welcome">
        <div class="welcome-icon">${icon("neurology")}</div>
        <h3>Спросите что-нибудь</h3>
        <p>Модель работает полностью на этом компьютере. История диалога не покидает устройство.</p>
        <div class="suggestions">
          <button class="suggestion" type="button" data-action="chat-suggestion" data-text="Объясни простыми словами, что такое OpenVINO.">Что такое OpenVINO?</button>
          <button class="suggestion" type="button" data-action="chat-suggestion" data-text="Напиши на Python функцию, которая считает факториал.">Функция факториала</button>
          <button class="suggestion" type="button" data-action="chat-suggestion" data-text="Придумай план поездки в Санкт-Петербург на 3 дня.">План поездки</button>
        </div>
      </div>`;

  return `<div class="page">
    ${pageHead("Чат", "Локальный чат без облака. Потоковая генерация на CPU, GPU или NPU.", `<button class="btn outlined" type="button" data-action="chat-new">${icon("add")} Новый диалог</button>`)}
    ${!genaiReady ? `<div class="banner warning" style="margin-bottom:14px">${icon("warning")}<div>OpenVINO GenAI не установлен — чат не сможет загрузить модель. <button class="btn text small" style="padding:0;height:auto" type="button" data-action="install-component" data-component="genai">Установить сейчас</button></div></div>` : ""}
    <div class="chat-layout">
      <section class="chat-card ${chatState.streaming ? "streaming" : ""}" id="chat-card">
        <div class="chat-head">
          <div class="chat-head-main">
            <div class="chat-head-icon">${icon("neurology")}</div>
            <div>
              <div class="chat-head-name">${esc(modelName)}</div>
              <div class="chat-head-sub">${esc(chatState.device)} · OpenVINO GenAI</div>
            </div>
          </div>
          <div class="flex gap-4">
            ${chatState.metrics ? `<span class="tag">${esc(chatState.metrics)}</span>` : ""}
            <button class="icon-btn small" type="button" title="Очистить" data-action="chat-new">${icon("delete_sweep")}</button>
          </div>
        </div>
        <div class="chat-messages" id="chat-messages">${chatMessages}</div>
        <form class="composer" id="chat-form">
          <textarea id="chat-input" rows="1" placeholder="Сообщение…  Enter — отправить, Shift+Enter — новая строка" ${chatState.streaming ? "disabled" : ""}></textarea>
          <div class="composer-actions">
            <button class="icon-btn stop-btn" type="button" title="Остановить" data-action="chat-stop" style="width:44px;height:44px">${icon("stop_circle", "fill")}</button>
            <button class="send-btn" type="submit" title="Отправить" ${chatState.streaming ? "disabled" : ""}>${icon("arrow_upward")}</button>
          </div>
        </form>
      </section>
      <aside class="chat-settings">
        <div class="card card-pad">
          <div class="card-header" style="margin-bottom:12px"><div><div class="card-title">Параметры</div><div class="card-sub">Настройки генерации</div></div>${icon("tune")}</div>
          <div class="settings-block">
            <label for="chat-model">Модель</label>
            <div class="select-wrap"><select class="select" id="chat-model">${models.map((item) => `<option value="${esc(item.id)}" ${model?.id === item.id ? "selected" : ""}>${esc(item.name)}</option>`).join("")}</select>${icon("expand_more")}</div>
          </div>
          <div class="settings-block mt-16">
            <label>Устройство</label>
            <div class="segmented" style="width:100%">
              ${deviceOptions
                .map(([value, label]) => {
                  const available = value === "CPU" || value === "AUTO" || devicesAvailable.some((id) => id.startsWith(value));
                  return `<button type="button" class="${chatState.device === value ? "active" : ""}" data-action="chat-device" data-device="${value}" ${available ? "" : `disabled title="Устройство не найдено" style="opacity:.4"`}>${label}</button>`;
                })
                .join("")}
            </div>
          </div>
          <div class="settings-block mt-16">
            <div class="flex-between"><label for="chat-temperature">Температура</label><span class="small mono" id="chat-temperature-value">${Number(chatState.params.temperature).toFixed(2)}</span></div>
            <div class="range-row"><input type="range" id="chat-temperature" min="0" max="1.5" step="0.05" value="${chatState.params.temperature}"><span class="range-value">${Number(chatState.params.temperature) <= 0.05 ? "точно" : "креатив"}</span></div>
          </div>
          <div class="settings-block mt-16">
            <div class="flex-between"><label for="chat-maxtokens">Максимум токенов</label><span class="small mono" id="chat-maxtokens-value">${chatState.params.max_new_tokens}</span></div>
            <div class="range-row"><input type="range" id="chat-maxtokens" min="64" max="2048" step="64" value="${chatState.params.max_new_tokens}"></div>
          </div>
          <div class="settings-block mt-16">
            <label for="chat-system">Системная инструкция</label>
            <textarea class="textarea" id="chat-system" rows="3" placeholder="Например: отвечай кратко и по-русски.">${esc(chatState.system)}</textarea>
          </div>
          <div class="chat-metrics mt-16">
            <span>${icon("memory", "xs")} ${esc(model?.size_label || "")}</span>
            <span>${icon("tag", "xs")} ${esc(model?.weight_format ? model.weight_format.toUpperCase() : "IR")}</span>
            <span>${icon("shield", "xs")} офлайн</span>
          </div>
        </div>
        <div class="card card-pad">
          <div class="small muted" style="line-height:18px">${icon("info", "xs")} Первый ответ может занять 10–60 секунд: модель загружается в память. Следующие сообщения быстрее.</div>
        </div>
      </aside>
    </div>
  </div>`;
}

export function chatMessageHTML(message, index, state) {
  const isUser = message.role === "user";
  const content = message.content || "";
  const streaming = Boolean(message.streaming);
  const body = streaming
    ? `<div class="md-content raw">${esc(content)}</div>`
    : `<div class="md-content markdown">${isUser ? esc(content).replace(/\n/g, "<br>") : md(content)}</div>`;
  const meta = [];
  if (!isUser && message.metrics) {
    const m = message.metrics;
    if (m.tokens) meta.push(`${m.tokens} токенов`);
    if (m.throughput) meta.push(`${m.throughput} ток/с`);
    if (m.ttft_ms) meta.push(`TTFT ${Math.round(m.ttft_ms)} мс`);
  }
  if (message.stopped) meta.push("остановлено");
  return `<div class="msg ${isUser ? "user" : "assistant"}" data-message-index="${index}">
    <div class="msg-avatar">${icon(isUser ? "person" : "neurology")}</div>
    <div style="min-width:0">
      <div class="msg-role">OpenVINO</div>
      <div class="msg-bubble">
        ${body}
        ${meta.length ? `<div class="msg-meta">${meta.map((item) => `<span>${esc(item)}</span>`).join("<span>·</span>")}</div>` : ""}
      </div>
    </div>
  </div>`;
}

// ------------------------------------------------------------------------ vlm
export function vlm(state) {
  const models = (state.models?.models || []).filter((model) => model.kind === "vlm");
  const current = state.vlm;
  const genaiReady = componentInstalled(state, "genai");
  const runtimeReady = Boolean(state.system?.openvino?.installed);
  if (!models.length) {
    return `<div class="page">
      ${pageHead("VLM", "Мультимодальный чат: изображение + вопрос. Локально, без облака.")}
      ${emptyBox(
        "visibility",
        "Нет мультимодальной модели",
        runtimeReady
          ? "Скачайте Gemma 4, Qwen3-VL или InternVL из каталога. Например, Gemma 4 E2B INT4 — около 4.4 ГБ."
          : "Сначала установите OpenVINO Runtime и GenAI в «Инструментах», затем скачайте VLM-модель.",
        `<div class="flex gap-8" style="flex-wrap:wrap;justify-content:center"><button class="btn filled" type="button" data-action="goto-catalog">${icon("travel_explore")} В каталог</button><button class="btn tonal" type="button" data-action="goto-tools">${icon("build")} Компоненты</button></div>`,
      )}
    </div>`;
  }
  const model = models.find((item) => item.id === current.modelId) || models[0];
  const dropzone = `<div class="dropzone ${current.dataUrl ? "has-image" : ""}" id="vlm-dropzone" tabindex="0" role="button" aria-label="Загрузить изображение">
    ${current.dataUrl ? `<img class="preview-image" src="${current.dataUrl}" alt="Изображение для анализа">` : ""}
    <div class="dz-empty">
      <div class="dz-icon">${icon("add_photo_alternate")}</div>
      <h4>Изображение для анализа</h4>
      <p>Перетащите файл или нажмите. JPG, PNG, WebP · до 20 МБ.</p>
      <span class="btn tonal small">${icon("upload")} Выбрать файл</span>
    </div>
  </div>
  <div class="flex-between mt-8">
    <span class="small muted">${esc(current.fileName || "файл не выбран")}</span>
    ${current.dataUrl ? `<button class="btn text small" type="button" data-action="vlm-clear-image">${icon("delete")} Убрать</button>` : ""}
  </div>`;

  const answer = current.error
    ? `<div class="banner error">${icon("error")}<div>${esc(current.error)}</div></div>`
    : current.streaming || current.answer
    ? `<div class="md-content ${current.streaming ? "raw" : "markdown"}" id="vlm-answer-body">${current.streaming ? esc(current.answer) : md(current.answer)}</div>`
    : `<div class="vlm-placeholder">${icon("forum")}<p>Ответ появится здесь. Загрузите изображение, задайте вопрос и нажмите «Анализировать».</p></div>`;
  const metrics = current.metrics
    ? `<div class="chat-metrics"><span>${icon("bolt", "xs")} ${esc(current.metrics)}</span></div>`
    : "";

  return `<div class="page">
    ${pageHead("VLM", "Мультимодальный чат: модель смотрит на изображение и отвечает на вопрос. Всё локально.", `<button class="btn outlined" type="button" data-action="vlm-clear">${icon("delete_sweep")} Очистить</button>`)}
    ${!genaiReady ? `<div class="banner warning" style="margin-bottom:14px">${icon("warning")}<div>Для VLM нужен OpenVINO GenAI. <button class="btn text small" style="padding:0;height:auto" type="button" data-action="install-component" data-component="genai">Установить</button></div></div>` : ""}
    <div class="vlm-layout">
      <div class="card card-pad">
        <div class="card-header"><div><div class="card-title">Изображение</div><div class="card-sub">Что показать модели</div></div>${icon("image")}</div>
        ${dropzone}
      </div>
      <form class="card card-pad vlm-form" id="vlm-form">
        <div class="card-header"><div><div class="card-title">Вопрос</div><div class="card-sub">Модель и параметры</div></div>${icon("tune")}</div>
        <div class="settings-block">
          <label for="vlm-model">Модель</label>
          <div class="select-wrap"><select class="select" id="vlm-model">${models.map((item) => `<option value="${esc(item.id)}" ${model.id === item.id ? "selected" : ""}>${esc(item.name)}</option>`).join("")}</select>${icon("expand_more")}</div>
        </div>
        <div class="form-grid-2">
          <div class="settings-block"><label for="vlm-device">Устройство</label><div class="select-wrap"><select class="select" id="vlm-device">${["CPU", "GPU", "NPU", "AUTO"].map((device) => `<option value="${device}" ${current.device === device ? "selected" : ""}>${device}</option>`).join("")}</select>${icon("expand_more")}</div></div>
          <div class="settings-block"><label for="vlm-maxtokens">Макс. токенов</label><input class="input" id="vlm-maxtokens" type="number" min="32" max="2048" step="32" value="${current.params.max_new_tokens}"></div>
        </div>
        <div class="settings-block">
          <label for="vlm-prompt">Вопрос к изображению</label>
          <textarea class="textarea" id="vlm-prompt" rows="4" placeholder="Например: что изображено? Опиши детали и найди текст.">${esc(current.prompt)}</textarea>
        </div>
        <div class="chips">
          ${["Что изображено на картинке?", "Опиши изображение подробно.", "Найди и прочитай текст на изображении."].map((text) => `<button class="chip" type="button" data-action="vlm-suggestion" data-text="${esc(text)}">${esc(text)}</button>`).join("")}
        </div>
        <div class="settings-block">
          <div class="flex-between"><label for="vlm-temperature">Температура</label><span class="small mono" id="vlm-temperature-value">${Number(current.params.temperature).toFixed(2)}</span></div>
          <div class="range-row"><input type="range" id="vlm-temperature" min="0" max="1.2" step="0.05" value="${current.params.temperature}"></div>
        </div>
        <div class="flex gap-8">
          <button class="btn filled grow" type="submit" ${current.streaming ? "disabled" : ""}>${current.streaming ? `<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> Анализируем…` : `${icon("play_arrow")} Анализировать`}</button>
          ${current.streaming ? `<button class="btn danger" type="button" data-action="vlm-stop">${icon("stop")} Стоп</button>` : ""}
        </div>
        <div class="small muted">${icon("info", "xs")} VLM — тяжёлая модель. На CPU первый ответ может занять 30–120 секунд, дальше быстрее.</div>
      </form>
    </div>
    <div class="card card-pad vlm-answer-card mt-16 ${current.streaming ? "streaming" : ""}">
      <div class="flex-between" style="margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <div><div class="card-title">Ответ</div><div class="card-sub">${esc(model.name)} · ${esc(current.device)}</div></div>
        ${metrics}
      </div>
      ${answer}
    </div>
  </div>`;
}

// --------------------------------------------------------------------- images
export function images(state) {
  const visionModels = (state.models?.models || []).filter((model) => model.kind === "image" || model.kind === "detection");
  const runtimeReady = Boolean(state.system?.openvino?.installed);
  const imageState = state.image;
  if (!visionModels.length) {
    return `<div class="page">
      ${pageHead("Изображения", "Классификация и детекция объектов на OpenVINO.")}
      ${emptyBox(
        "image",
        "Нет модели для изображений",
        runtimeReady
          ? "Скачайте YOLO11n для детекции или ResNet-50 для классификации — они занимают всего несколько мегабайт."
          : "Установите OpenVINO Runtime, затем скачайте модель изображений из каталога.",
        `<div class="flex gap-8" style="flex-wrap:wrap;justify-content:center"><button class="btn filled" type="button" data-action="goto-catalog">${icon("travel_explore")} В каталог</button><button class="btn tonal" type="button" data-action="goto-tools">${icon("build")} Компоненты</button></div>`,
      )}
    </div>`;
  }
  const result = imageState.result;
  const isDetection = result?.task === "detect";
  const dropzone = `<div class="dropzone ${imageState.dataUrl ? "has-image" : ""}" id="dropzone" tabindex="0" role="button" aria-label="Загрузить изображение">
    ${imageState.dataUrl ? `<img class="preview-image" id="image-preview" src="${imageState.dataUrl}" alt="Загруженное изображение">` : ""}
    <div class="dz-empty">
      <div class="dz-icon">${icon("add_photo_alternate")}</div>
      <h4>Перетащите изображение или нажмите</h4>
      <p>JPG, PNG, WebP · до 20 МБ. Файл обрабатывается локально.</p>
      <span class="btn tonal small">${icon("upload")} Выбрать файл</span>
    </div>
  </div>
  ${imageState.dataUrl ? `<div class="flex-between mt-8"><span class="small muted">${esc(imageState.fileName || "изображение")}</span><button class="btn text small" type="button" data-action="image-clear">${icon("delete")} Убрать</button></div>` : ""}`;

  const predictions = result
    ? `<div class="card card-pad result-card">
        <div class="flex-between" style="margin-bottom:12px"><div><div class="card-title">${isDetection ? "Найденные объекты" : "Результат классификации"}</div><div class="card-sub">${esc(result.model || "")} · ${esc(result.device || "")} · ${esc(result.elapsed_ms || 0)} мс</div></div><span class="tag">${isDetection ? `${result.detections?.length || 0} объектов` : "топ-5"}</span></div>
        ${
          isDetection
            ? (result.detections || []).length
              ? `<div>${result.detections.map((detection) => `<div class="prediction"><div class="prediction-head"><span class="prediction-name">${esc(detection.label)}</span><span class="prediction-score">${(detection.score * 100).toFixed(1)}%</span></div><div class="prediction-bar"><span style="width:${(detection.score * 100).toFixed(1)}%"></span></div></div>`).join("")}</div>`
              : `<p class="muted small">Объекты не найдены. Попробуйте снизить порог уверенности.</p>`
            : `<div>${(result.predictions || []).map((prediction) => `<div class="prediction"><div class="prediction-head"><span class="prediction-name">${esc(prediction.label)}</span><span class="prediction-score">${(prediction.score * 100).toFixed(1)}%</span></div><div class="prediction-bar"><span style="width:${(prediction.score * 100).toFixed(1)}%"></span></div></div>`).join("")}</div>`
        }
      </div>`
    : "";

  const resultImage = result
    ? `<div class="card result-card" style="padding:12px"><div class="flex-between" style="margin-bottom:8px"><span class="small muted">${isDetection ? "Детекция" : "Изображение"}</span><button class="icon-btn small" type="button" data-action="open-image" title="Открыть">${icon("open_in_full")}</button></div><div class="result-image"><img src="${result.image || imageState.dataUrl}" alt="Результат"></div></div>`
    : "";

  return `<div class="page">
    ${pageHead("Изображения", "Классификация и детекция объектов. Всё выполняется локально на выбранном устройстве.")}
    <div class="image-layout">
      <div>
        ${dropzone}
        ${resultImage}
      </div>
      <div>
        <div class="card card-pad image-settings">
          <div class="card-header" style="margin-bottom:0"><div><div class="card-title">Параметры</div><div class="card-sub">Модель и режим</div></div>${icon("image")}</div>
          <div class="settings-block">
            <label for="image-model">Модель</label>
            <div class="select-wrap"><select class="select" id="image-model">${visionModels.map((model) => `<option value="${esc(model.id)}" ${imageState.modelId === model.id ? "selected" : ""}>${esc(model.name)} · ${esc(model.kind_label)}</option>`).join("")}</select>${icon("expand_more")}</div>
          </div>
          <div class="settings-block">
            <label>Режим</label>
            <div class="segmented" style="width:100%">
              ${[
                ["auto", "Авто"],
                ["classify", "Классификация"],
                ["detect", "Детекция"],
              ]
                .map(([value, label]) => `<button type="button" class="${imageState.task === value ? "active" : ""}" data-action="image-task" data-task="${value}">${label}</button>`)
                .join("")}
            </div>
          </div>
          <div class="settings-block">
            <label>Устройство</label>
            <div class="select-wrap"><select class="select" id="image-device">${["CPU", "GPU", "NPU", "AUTO"].map((device) => `<option value="${device}" ${imageState.device === device ? "selected" : ""}>${device}</option>`).join("")}</select>${icon("expand_more")}</div>
          </div>
          <div class="settings-block" id="threshold-block" ${imageState.task === "classify" ? "hidden" : ""}>
            <div class="flex-between"><label for="image-threshold">Порог уверенности</label><span class="small mono" id="image-threshold-value">${Number(imageState.threshold).toFixed(2)}</span></div>
            <div class="range-row"><input type="range" id="image-threshold" min="0.05" max="0.9" step="0.05" value="${imageState.threshold}"></div>
          </div>
          <button class="btn filled block" type="button" id="image-run" data-action="image-run" ${imageState.running || !imageState.dataUrl ? "disabled" : ""}>${imageState.running ? `<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> Обработка…` : `${icon("play_arrow")} Распознать`}</button>
          <div class="small muted">${icon("info", "xs")} Для классификации модель ResNet, для детекции — YOLO. Режим «Авто» определит тип сам.</div>
        </div>
      </div>
    </div>
    ${result ? `<div class="result-grid" style="margin-top:16px"><div class="card card-pad"><div class="card-title" style="margin-bottom:10px">Сводка</div><div class="metric-grid">${metricCard(result.elapsed_ms || 0, "мс", "Время инференса")}${metricCard(result.width || 0, "px", "Ширина")}${metricCard(result.height || 0, "px", "Высота")}${metricCard(result.device || "CPU", "", "Устройство")}</div></div>${predictions}</div>` : ""}
  </div>`;
}

// ------------------------------------------------------------------ benchmark
export function benchmark(state) {
  const allModels = state.models?.models || [];
  const bench = state.bench;
  const activeJob = (state.jobs || []).find((job) => job.kind === "benchmark" && (job.status === "running" || job.status === "queued"));
  const latest = bench.history?.[0];
  return `<div class="page">
    ${pageHead("Бенчмарк", "Замер задержки и пропускной способности на выбранном устройстве.", `<button class="btn outlined" type="button" data-action="reload-benchmarks">${icon("refresh")} Обновить историю</button>`)}
    ${!allModels.length ? emptyBox("speed", "Нет моделей для замера", "Скачайте модель из каталога, чтобы измерить скорость инференса.", `<button class="btn filled" type="button" data-action="goto-catalog">В каталог</button>`) : `<div class="bench-layout">
      <form class="card card-pad bench-form" id="bench-form">
        <div class="card-header" style="margin-bottom:0"><div><div class="card-title">Параметры запуска</div><div class="card-sub">Измерение на реальном железе</div></div>${icon("speed")}</div>
        <div class="settings-block">
          <label for="bench-model">Модель</label>
          <div class="select-wrap"><select class="select" id="bench-model">${allModels.map((model) => `<option value="${esc(model.id)}" ${bench.modelId === model.id ? "selected" : ""}>${esc(model.name)} · ${esc(model.kind_label)}</option>`).join("")}</select>${icon("expand_more")}</div>
        </div>
        <div class="form-grid-2">
          <div class="settings-block">
            <label for="bench-device">Устройство</label>
            <div class="select-wrap"><select class="select" id="bench-device">${["CPU", "GPU", "NPU", "AUTO"].map((device) => `<option value="${device}" ${bench.device === device ? "selected" : ""}>${device}</option>`).join("")}</select>${icon("expand_more")}</div>
          </div>
          <div class="settings-block">
            <label for="bench-mode">Режим</label>
            <div class="select-wrap"><select class="select" id="bench-mode"><option value="auto" ${bench.mode === "auto" ? "selected" : ""}>Авто</option><option value="llm" ${bench.mode === "llm" ? "selected" : ""}>LLM</option><option value="classic" ${bench.mode === "classic" ? "selected" : ""}>Классический IR</option></select>${icon("expand_more")}</div>
          </div>
        </div>
        <div class="form-grid-2">
          <div class="settings-block"><label for="bench-iterations">Итерации</label><input class="input" id="bench-iterations" type="number" min="1" max="100" value="${bench.iterations}"></div>
          <div class="settings-block"><label for="bench-warmup">Прогрев</label><input class="input" id="bench-warmup" type="number" min="0" max="20" value="${bench.warmup}"></div>
        </div>
        <div class="settings-block"><label for="bench-prompt">Промпт (для LLM)</label><input class="input" id="bench-prompt" type="text" value="${esc(bench.prompt)}"></div>
        <div class="settings-block"><label for="bench-tokens">Новых токенов (для LLM)</label><input class="input" id="bench-tokens" type="number" min="8" max="512" value="${bench.max_tokens}"></div>
        <button class="btn filled block" type="submit" ${activeJob ? "disabled" : ""}>${activeJob ? `<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> Выполняется…` : `${icon("play_arrow")} Запустить бенчмарк`}</button>
        ${activeJob ? `<div class="job-progress progress ${!activeJob.progress ? "indeterminate" : ""}"><div class="progress-bar" style="width:${Math.max(3, Math.round((activeJob.progress || 0) * 100))}%"></div></div><div class="progress-label"><span>${esc(activeJob.detail || "")}</span><span>${Math.round((activeJob.progress || 0) * 100)}%</span></div>` : ""}
        <div class="small muted">${icon("info", "xs")} Для LLM измеряется токены/с и TTFT. Для обычных IR — задержка и кадры/с.</div>
      </form>
      <div>
        ${latest ? `<div class="card card-pad" style="margin-bottom:16px">
          <div class="card-header"><div><div class="card-title">Последний результат</div><div class="card-sub">${esc(latest.model || "")} · ${esc(latest.device || "")} · ${esc(fmtDate(latest.timestamp))}</div></div><span class="tag primary">${latest.mode === "llm" ? "LLM" : "IR"}</span></div>
          <div class="metric-grid">
            ${metricCard(latest.throughput_tps ?? latest.throughput_fps ?? 0, latest.mode === "llm" ? "ток/с" : "кадр/с", "Пропускная способность")}
            ${metricCard(latest.latency_mean_ms ?? 0, "мс", "Средняя задержка")}
            ${metricCard(latest.latency_p90_ms ?? latest.ttft_ms ?? 0, "мс", latest.mode === "llm" ? "TTFT" : "p90")}
            ${metricCard(latest.compile_ms ?? latest.load_ms ?? 0, "мс", latest.mode === "llm" ? "Загрузка" : "Компиляция")}
          </div>
        </div>` : `<div class="card card-pad" style="margin-bottom:16px"><div class="card-header"><div><div class="card-title">Результат</div><div class="card-sub">Здесь появятся метрики после запуска</div></div>${icon("insights")}</div><div class="metric-grid">${metricCard("—", "", "Пропускная способность")}${metricCard("—", "мс", "Задержка")}${metricCard("—", "мс", "p90")}${metricCard("—", "мс", "Компиляция")}</div></div>`}
        <div class="card card-pad" style="margin-bottom:16px"><div class="card-title" style="margin-bottom:14px">Сравнение скорости</div>${chartRows(bench.history || [])}</div>
        <div class="card card-pad"><div class="card-title" style="margin-bottom:12px">История</div>${benchmarkTable(bench.history || [])}</div>
      </div>
    </div>`}
  </div>`;
}

// ---------------------------------------------------------------------- tools
export function tools(state) {
  const system = state.system;
  const components = system?.components || [];
  const installJob = (state.jobs || []).find((job) => job.kind === "install" && (job.status === "running" || job.status === "queued"));
  const convertJob = (state.jobs || []).find((job) => job.kind === "convert" && (job.status === "running" || job.status === "queued"));
  const allInstalled = components.length && components.every((component) => component.installed);
  return `<div class="page">
    ${pageHead("Инструменты", "Установка компонентов, конвертация моделей и журналы. Без командной строки.")}
    <div class="tools-grid">
      <div>
        <div class="card card-pad">
          <div class="card-header">
            <div><div class="card-title">Компоненты</div><div class="card-sub">Ставятся в изолированное окружение на внешнем диске</div></div>
            ${allInstalled ? `<span class="tag success">${icon("check_circle", "xs")} всё готово</span>` : `<button class="btn filled small" type="button" data-action="install-missing" ${installJob ? "disabled" : ""}>Установить недостающее</button>`}
          </div>
          <div class="component-list">
            ${components.length ? components.map(componentRow).join("") : `<div class="skeleton" style="height:90px"></div>`}
          </div>
          ${installJob ? `<div class="mt-16"><div class="progress-label"><span>${esc(installJob.detail || "Установка…")}</span><span>${Math.round((installJob.progress || 0) * 100)}%</span></div><div class="progress ${!installJob.progress ? "indeterminate" : ""}"><div class="progress-bar" style="width:${Math.max(2, Math.round((installJob.progress || 0) * 100))}%"></div></div></div>` : ""}
          <div class="banner info mt-16">${icon("storage")}<div>Компоненты устанавливаются с PyPI. Нужен интернет. «Конвертация» весит около 2–3 ГБ — это PyTorch и Optimum.</div></div>
        </div>

        <div class="card card-pad mt-16">
          <div class="card-header"><div><div class="card-title">Конвертация в OpenVINO IR</div><div class="card-sub">Любая модель Hugging Face → оптимизированный IR</div></div><span class="tag">Optimum Intel</span></div>
          <form class="convert-form" id="convert-form">
            <div class="settings-block"><label for="convert-repo">Модель Hugging Face</label><input class="input" id="convert-repo" type="text" placeholder="Qwen/Qwen2.5-1.5B-Instruct" autocomplete="off"><div class="hint">Формат organization/model. Можно вставить ссылку на страницу модели.</div></div>
            <div class="form-grid-2">
              <div class="settings-block"><label for="convert-task">Задача</label><div class="select-wrap"><select class="select" id="convert-task">${[
                ["auto", "Авто"],
                ["text-generation-with-past", "LLM (с KV-кэшем)"],
                ["text-generation", "Текстовая генерация"],
                ["image-classification", "Классификация изображений"],
                ["object-detection", "Детекция объектов"],
                ["feature-extraction", "Эмбеддинги"],
                ["automatic-speech-recognition", "Распознавание речи"],
                ["text2text-generation", "Seq2seq"],
              ].map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select>${icon("expand_more")}</div></div>
              <div class="settings-block"><label for="convert-name">Имя папки (необязательно)</label><input class="input" id="convert-name" type="text" placeholder="auto"></div>
            </div>
            <div class="settings-block"><label>Формат весов</label>
              <div class="segmented" id="convert-format">
                <button type="button" data-format="fp16" class="${state.tools.convertFormat === "fp16" ? "active" : ""}">FP16</button>
                <button type="button" data-format="int8" class="${state.tools.convertFormat === "int8" ? "active" : ""}">INT8</button>
                <button type="button" data-format="int4" class="${state.tools.convertFormat === "int4" ? "active" : ""}">INT4</button>
                <button type="button" data-format="fp32" class="${state.tools.convertFormat === "fp32" ? "active" : ""}">FP32</button>
              </div>
            </div>
            <label class="switch-row" style="padding:6px 0"><span class="switch-copy"><strong>Доверять коду модели</strong><span>Нужно для некоторых новых архитектур</span></span><span class="switch"><input type="checkbox" id="convert-trust"><span class="track"></span><span class="thumb"></span></span></label>
            <button class="btn filled block" type="submit" ${convertJob ? "disabled" : ""}>${convertJob ? `<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> Конвертация…` : `${icon("transform")} Конвертировать`}</button>
            ${convertJob ? `<div><div class="progress-label"><span>${esc(convertJob.detail || "")}</span><span>${Math.round((convertJob.progress || 0) * 100)}%</span></div><div class="progress ${!convertJob.progress ? "indeterminate" : ""}"><div class="progress-bar" style="width:${Math.max(2, Math.round((convertJob.progress || 0) * 100))}%"></div></div></div>` : ""}
            <div class="small muted">${icon("info", "xs")} Конвертация LLM может занимать от 5 до 40 минут и требует свободного места для исходных весов.</div>
          </form>
        </div>
      </div>

      <div>
        <div class="card card-pad">
          <div class="card-header"><div><div class="card-title">Журнал</div><div class="card-sub">Последние события приложения</div></div><div class="flex gap-4"><button class="icon-btn small" type="button" title="Обновить" data-action="refresh-logs">${icon("refresh")}</button><button class="icon-btn small" type="button" title="Копировать" data-action="copy-logs">${icon("content_copy")}</button></div></div>
          <pre class="log-box" id="log-box">${esc(state.tools.logs || "Нажмите «Обновить», чтобы загрузить журнал.")}</pre>
          <div class="flex gap-8 mt-16"><button class="btn text small" type="button" data-action="open-logs">${icon("folder_open")} Папка журналов</button><button class="btn text small" type="button" data-action="refresh-logs">${icon("refresh")} Обновить</button></div>
        </div>
        <div class="card card-pad mt-16">
          <div class="card-title" style="margin-bottom:10px">Полезно знать</div>
          <div class="small muted" style="line-height:20px">
            <p style="margin-bottom:8px"><strong style="color:var(--on-surface)">Где хранятся данные?</strong><br>Модели, кэш OpenVINO, pip-кэш и журналы — в папках <span class="mono">models</span> и <span class="mono">runtime</span> рядом с приложением.</p>
            <p style="margin-bottom:8px"><strong style="color:var(--on-surface)">Нужен ли интернет?</strong><br>Только для скачивания моделей и установки компонентов. Инференс полностью офлайн.</p>
            <p><strong style="color:var(--on-surface)">Поддерживаемые устройства</strong><br>CPU, Intel GPU, Intel NPU. Список доступных устройств — в «Обзоре».</p>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

// ------------------------------------------------------------------- settings
export function settings(state) {
  const current = state.settings || {};
  const system = state.system;
  const theme = state.theme || "system";
  return `<div class="page">
    ${pageHead("Настройки", "Интерфейс, сеть, производительность и пути хранения.", `<button class="btn filled" type="button" data-action="save-settings">${icon("save")} Сохранить</button>`)}
    <div class="settings-grid">
      <div class="card card-pad settings-card">
        <div class="card-title">Интерфейс</div>
        <div class="settings-block">
          <label>Тема</label>
          <div class="segmented" style="width:100%">
            ${[
              ["system", "Системная"],
              ["light", "Светлая"],
              ["dark", "Тёмная"],
            ]
              .map(([value, label]) => `<button type="button" class="${theme === value ? "active" : ""}" data-action="set-theme" data-theme="${value}">${label}</button>`)
              .join("")}
          </div>
        </div>
        <div class="setting-row"><label class="field-label" for="settings-token">HF-токен</label>
          <input class="input" id="settings-token" type="password" autocomplete="off" placeholder="${current.hf_token_set ? "Токен сохранён — введите новый, чтобы заменить" : "hf_… (для приватных моделей)"}">
          <div class="hint">Токен нужен только для закрытых моделей и хранится локально в runtime/settings.json.</div>
          ${current.hf_token_set ? `<label class="flex gap-8 small" style="margin-top:4px"><input type="checkbox" id="settings-clear-token"> Удалить сохранённый токен</label>` : ""}
        </div>
        <div class="setting-row"><label class="field-label" for="settings-proxy">Прокси</label>
          <input class="input" id="settings-proxy" type="text" value="${esc(current.proxy || "")}" placeholder="http://127.0.0.1:8080">
          <div class="hint">Применяется к скачиванию моделей и установке компонентов.</div>
        </div>
      </div>

      <div class="card card-pad settings-card">
        <div class="card-title">Производительность</div>
        <div class="setting-row"><label class="field-label" for="settings-device">Устройство по умолчанию</label>
          <div class="select-wrap"><select class="select" id="settings-device">${["CPU", "GPU", "NPU", "AUTO"].map((device) => `<option value="${device}" ${current.default_device === device ? "selected" : ""}>${device}</option>`).join("")}</select>${icon("expand_more")}</div>
        </div>
        <div class="setting-row"><label class="field-label" for="settings-threads">Потоки CPU (0 — авто)</label><input class="input" id="settings-threads" type="number" min="0" max="256" value="${current.num_threads || 0}">
          <div class="hint">Ограничение числа потоков инференса. Оставьте 0 для автоматического выбора.</div>
        </div>
        <div class="setting-row inline"><div class="setting-copy"><strong>Подтверждать удаление</strong><span>Спрашивать перед удалением модели</span></div><span class="switch"><input type="checkbox" id="settings-confirm" ${current.confirm_delete !== false ? "checked" : ""}><span class="track"></span><span class="thumb"></span></span></div>
        <div class="setting-row"><label class="field-label">Устройства сейчас</label><div class="small muted">${devices(state).map((device) => esc(device.id)).join(" · ") || "OpenVINO не установлен"}</div></div>
      </div>

      <div class="card card-pad settings-card" style="grid-column:1/-1">
        <div class="card-title">Хранилище</div>
        <div class="form-grid-2">
          <div class="setting-row"><label class="field-label">Папка приложения</label><div class="path-box"><input class="input" readonly value="${esc(system?.base_path || "")}"><button class="icon-btn small" type="button" data-action="open-base">${icon("folder_open")}</button></div></div>
          <div class="setting-row"><label class="field-label">Папка моделей</label><div class="path-box"><input class="input" readonly value="${esc(system?.models_path || "")}"><button class="icon-btn small" type="button" data-action="open-models">${icon("folder_open")}</button></div></div>
        </div>
        <div class="disk-meter">
          <div class="flex-between"><span class="small">Занято на диске</span><span class="small muted">${esc(system?.disk?.used_label || "—")} из ${esc(system?.disk?.total_label || "—")}</span></div>
          <div class="progress"><div class="progress-bar" style="width:${Math.min(100, system?.disk?.percent || 0)}%"></div></div>
          <div class="disk-meter-labels"><span>Свободно ${esc(system?.disk?.free_label || "—")}</span><span>${system?.disk?.percent ?? 0}%</span></div>
        </div>
        <div class="flex gap-8" style="flex-wrap:wrap"><button class="btn outlined small" type="button" data-action="open-models">${icon("folder_open")} Открыть модели</button><button class="btn text small" type="button" data-action="open-logs">${icon("description")} Журналы</button><button class="btn text small" type="button" data-action="open-base">${icon("home")} Папка приложения</button></div>
      </div>

      <div class="card card-pad settings-card">
        <div class="card-title">О программе</div>
        <div class="setting-row"><span class="small muted">Версия</span><strong>OpenVINO Studio ${esc(system?.app_version || "1.0.0")}</strong></div>
        <div class="setting-row"><span class="small muted">Python</span><span class="mono">${esc(system?.python || "—")}</span></div>
        <div class="setting-row"><span class="small muted">Платформа</span><span class="small">${esc(system?.platform || "—")} · ${esc(system?.arch || "")}</span></div>
        <div class="setting-row"><span class="small muted">OpenVINO</span><span class="mono">${esc(system?.openvino?.ov_version || "не установлен")}</span></div>
        <div class="setting-row"><span class="small muted">Автор</span><strong>ByKirilldual0987</strong></div>
        <div class="setting-row"><span class="small muted">Лицензия</span><span class="small">MIT</span></div>
        <div class="flex gap-8" style="flex-wrap:wrap"><a class="btn text small" href="https://docs.openvino.ai" target="_blank" rel="noopener">Документация ${icon("open_in_new", "xs")}</a><a class="btn text small" href="https://huggingface.co/OpenVINO" target="_blank" rel="noopener">Модели OpenVINO ${icon("open_in_new", "xs")}</a><a class="btn text small" href="https://github.com/kirilldual0987/openvino-studio" target="_blank" rel="noopener">GitHub ${icon("open_in_new", "xs")}</a></div>
        <p class="small muted" style="margin-top:12px">© 2026 ByKirilldual0987. OpenVINO и Intel — товарные знаки Intel Corporation. Проект не связан с Intel.</p>
      </div>

      <div class="card card-pad settings-card">
        <div class="card-title">Завершение работы</div>
        <p class="small muted" style="line-height:19px">Сервер работает в фоне, пока открыто окно приложения. Кнопка ниже останавливает его. Все незавершённые задачи будут отменены.</p>
        <button class="btn danger" type="button" data-action="shutdown">${icon("power_settings_new")} Выйти из OpenVINO Studio</button>
      </div>
    </div>
  </div>`;
}

export const pages = {
  overview,
  models: catalog,
  library,
  chat,
  vlm,
  images,
  benchmark,
  tools,
  settings,
};
