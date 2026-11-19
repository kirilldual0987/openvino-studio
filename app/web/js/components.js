// Reusable HTML fragments.

import { esc, icon, fmtBytes, fmtNumber, fmtDate, kindMeta, toneFor, repoTitle } from "./util.js";

export function modelIcon(pipelineTag) {
  const tag = String(pipelineTag || "").toLowerCase();
  if (tag.includes("text-generation") || tag.includes("text2text")) return "forum";
  if (tag.includes("image-text")) return "visibility";
  if (tag.includes("speech")) return "graphic_eq";
  if (tag.includes("image-classification")) return "image";
  if (tag.includes("object-detection")) return "center_focus_strong";
  if (tag.includes("feature-extraction")) return "scatter_plot";
  return "deployed_code";
}

function curatedIcon(item) {
  const kind = String(item.kind || "").toLowerCase();
  if (kind.includes("детек")) return "center_focus_strong";
  if (kind.includes("класс") || kind.includes("vision")) return "image";
  if (kind.includes("эмбед")) return "scatter_plot";
  if (kind.includes("аудио")) return "graphic_eq";
  if (kind.includes("vlm") || kind.includes("мультимод")) return "visibility";
  return "forum";
}

export function curatedCard(item, installed = false) {
  return `<article class="model-card" data-action="open-model" data-repo="${esc(item.repo)}" tabindex="0">
    <div class="model-top">
      <div class="model-avatar tone-${esc(item.tone || toneFor(item.repo))}">${icon(curatedIcon(item))}</div>
      <div class="model-top-actions">
        ${installed ? `<span class="model-installed" title="Уже в библиотеке">${icon("check_circle")}</span>` : ""}
        <button class="icon-btn small" type="button" title="Скачать" data-action="download" data-repo="${esc(item.repo)}" data-size="${item.size || 0}">${icon("download")}</button>
      </div>
    </div>
    <div>
      <div class="model-title">${esc(item.title || repoTitle(item.repo))}</div>
      <div class="model-repo">${esc(item.repo)}</div>
    </div>
    <p class="model-desc">${esc(item.desc || "")}</p>
    <div class="model-meta">
      <span>${icon("category", "xs")} ${esc(item.kind || "Модель")}</span>
      <span>${icon("hard_drive", "xs")} ${esc(fmtBytes(item.size))}</span>
    </div>
    <div class="model-foot">
      <div class="model-badges">
        ${(item.badges || []).slice(0, 3).map((badge) => `<span class="model-badge">${esc(badge)}</span>`).join("")}
      </div>
      ${installed ? `<span class="model-installed">${icon("check_circle", "xs")} в библиотеке</span>` : `<button class="btn text small" type="button" data-action="download" data-repo="${esc(item.repo)}" data-size="${item.size || 0}">Скачать ${icon("arrow_downward", "xs")}</button>`}
    </div>
  </article>`;
}

export function searchCard(item, installed = false) {
  const tag = item.pipeline_tag || "";
  const labels = (item.tags || []).filter((t) => !t.includes(":")).slice(0, 3);
  return `<article class="model-card" data-action="open-model" data-repo="${esc(item.repo)}" tabindex="0">
    <div class="model-top">
      <div class="model-avatar tone-${toneFor(item.repo)}">${icon(modelIcon(tag))}</div>
      <div class="model-top-actions">
        ${installed ? `<span class="model-installed" title="Уже в библиотеке">${icon("check_circle")}</span>` : ""}
        <button class="icon-btn small" type="button" title="Скачать" data-action="download" data-repo="${esc(item.repo)}">${icon("download")}</button>
      </div>
    </div>
    <div>
      <div class="model-title">${esc(item.name || repoTitle(item.repo))}</div>
      <div class="model-repo">${esc(item.repo)}</div>
    </div>
    <p class="model-desc">${esc(labels.length ? labels.join(" · ") : (tag || "OpenVINO-совместимая модель"))}</p>
    <div class="model-meta">
      <span>${icon("download", "xs")} ${fmtNumber(item.downloads)}</span>
      <span>${icon("favorite", "xs")} ${fmtNumber(item.likes)}</span>
      ${tag ? `<span>${esc(tag)}</span>` : ""}
    </div>
    <div class="model-foot">
      <div class="model-badges">
        <span class="model-badge primary">OpenVINO</span>
        ${item.gated ? `<span class="model-badge">нужен токен</span>` : ""}
      </div>
      <span class="small muted">${esc(fmtDate(item.last_modified))}</span>
    </div>
  </article>`;
}

export function libraryRow(model) {
  const meta = kindMeta(model.kind);
  const isVision = model.kind === "image" || model.kind === "detection";
  const isVlm = model.kind === "vlm";
  const isChat = model.chat_ready;
  return `<div class="library-row" data-model-id="${esc(model.id)}">
    <div class="library-avatar tone-${meta.tone}">${icon(meta.icon)}</div>
    <div class="library-main">
      <div class="library-name">${esc(model.name)}</div>
      <div class="library-sub">
        <span class="row-badge kind">${esc(meta.label)}</span>
        <span>${esc(model.size_label)}</span>
        <span class="dot"></span>
        <span>${esc(model.files)} файлов</span>
        ${model.repo ? `<span class="dot"></span><span class="mono" style="font-size:10.5px">${esc(model.repo)}</span>` : ""}
        ${model.incomplete ? `<span class="row-badge warn">неполная</span>` : ""}
        ${model.weight_format ? `<span class="row-badge">${esc(model.weight_format.toUpperCase())}</span>` : ""}
      </div>
    </div>
    <div class="library-actions">
      ${
        isChat
          ? `<button class="btn tonal small" type="button" data-action="library-chat" data-id="${esc(model.id)}">${icon("forum", "xs")} Чат</button>`
          : isVlm
          ? `<button class="btn tonal small" type="button" data-action="library-vlm" data-id="${esc(model.id)}">${icon("visibility", "xs")} VLM</button>`
          : isVision
          ? `<button class="btn tonal small" type="button" data-action="library-image" data-id="${esc(model.id)}">${icon("image", "xs")} Изображения</button>`
          : ""
      }
      <button class="icon-btn small" type="button" title="Бенчмарк" data-action="library-bench" data-id="${esc(model.id)}">${icon("speed")}</button>
      <button class="icon-btn small" type="button" title="Открыть папку" data-action="reveal-model" data-id="${esc(model.id)}">${icon("folder_open")}</button>
      <button class="icon-btn small" type="button" title="Удалить" data-action="delete-model" data-id="${esc(model.id)}" data-name="${esc(model.name)}">${icon("delete")}</button>
    </div>
  </div>`;
}

export function statCard({ iconName, value, label, hint = "", tone = "" }) {
  return `<div class="stat-card">
    <div class="stat-top">
      <div class="stat-icon ${tone}">${icon(iconName)}</div>
      ${hint ? `<span class="stat-hint">${esc(hint)}</span>` : ""}
    </div>
    <div>
      <div class="stat-value">${value}</div>
      <div class="stat-label">${esc(label)}</div>
    </div>
  </div>`;
}

export function deviceLine(device, available = true) {
  const details = device.details || {};
  const type = (device.type || "").toUpperCase();
  const name = device.name || device.id || "Устройство";
  const iconName = type.includes("GPU") ? "memory" : type.includes("NPU") ? "neurology" : "developer_board";
  return `<div class="device-line">
    <div class="device-icon ${available ? "primary" : ""}">${icon(iconName)}</div>
    <div class="grow">
      <div class="device-name">${esc(name)}</div>
      <div class="device-sub">${esc(device.id)}${details.DEVICE_ARCHITECTURE ? ` · ${esc(details.DEVICE_ARCHITECTURE)}` : ""}</div>
    </div>
    <span class="status-pill ${available ? "ok" : ""}">${available ? "доступно" : "нет"}</span>
  </div>`;
}

export function jobIcon(status) {
  if (status === "running") return "progress_activity";
  if (status === "queued") return "schedule";
  if (status === "done") return "check";
  if (status === "cancelled") return "cancel";
  return "error";
}

export function jobItem(job) {
  const progress = Math.round((job.progress || 0) * 100);
  const active = job.status === "running" || job.status === "queued";
  return `<div class="job-item" data-job-id="${esc(job.id)}">
    <div class="job-top">
      <div class="job-status-icon ${job.status}">${icon(jobIcon(job.status))}</div>
      <div class="job-main">
        <div class="job-title">${esc(job.title)}</div>
        <div class="job-detail">${esc(job.detail || "")}</div>
        <div class="job-progress progress ${active && !job.progress ? "indeterminate" : ""}">
          <div class="progress-bar" style="width:${active ? Math.max(2, progress) : 100}%"></div>
        </div>
        ${job.error ? `<div class="job-error">${esc(job.error.split("\n").slice(0, 2).join(" · "))}</div>` : ""}
      </div>
      <div class="job-actions">
        <button class="job-log-btn" type="button" title="Журнал" data-action="job-log" data-id="${esc(job.id)}">${icon("subject", "sm")}</button>
        ${active ? `<button class="job-log-btn" type="button" title="Отменить" data-action="job-cancel" data-id="${esc(job.id)}">${icon("close", "sm")}</button>` : ""}
      </div>
    </div>
  </div>`;
}

export function jobDockBody(jobs) {
  if (!jobs.length) return `<div class="empty" style="border:0;background:transparent;padding:24px 12px"><p>Активных задач нет.</p></div>`;
  return jobs.map(jobItem).join("");
}

export function componentRow(component) {
  const version = component.versions?.openvino || component.versions?.["openvino-genai"] || component.versions?.["optimum-intel"] || "";
  return `<div class="component-row">
    <div class="component-icon ${component.installed ? "installed" : ""}">${icon(component.installed ? "check_circle" : "extension")}</div>
    <div class="component-main">
      <div class="component-name">${esc(component.name)}
        <span class="status-pill ${component.installed ? "ok" : "warn"}">${component.installed ? "установлен" : "не установлен"}</span>
      </div>
      <div class="component-desc">${esc(component.description)}</div>
      <div class="component-version">${version ? `v${esc(version)} · ` : ""}${esc(component.size_hint || "")}</div>
    </div>
    <div>
      ${
        component.installed
          ? `<button class="btn text small" type="button" data-action="install-component" data-component="${esc(component.id)}">Переустановить</button>`
          : `<button class="btn filled small" type="button" data-action="install-component" data-component="${esc(component.id)}">Установить</button>`
      }
    </div>
  </div>`;
}

export function metricCard(value, unit, label) {
  return `<div class="metric">
    <div class="metric-value">${esc(value)}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div>
    <div class="metric-label">${esc(label)}</div>
  </div>`;
}

export function skeletonCards(count = 6) {
  return `<div class="model-grid">${Array.from({ length: count }, () => `<div class="card sk-card" style="padding:18px"><div class="skeleton" style="width:46px;height:46px;border-radius:13px"></div><div class="skeleton sk-title" style="margin-top:16px"></div><div class="skeleton sk-line short"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line tiny"></div></div>`).join("")}</div>`;
}

export function benchmarkTable(history) {
  if (!history.length) {
    return `<div class="empty" style="padding:26px"><p>Пока нет запусков. Выполните первый бенчмарк.</p></div>`;
  }
  return `<div class="table-wrap"><table class="data-table">
    <thead><tr><th>Когда</th><th>Модель</th><th>Устройство</th><th>Метрика</th><th>Значение</th></tr></thead>
    <tbody>${history
      .slice(0, 12)
      .map((row) => {
        const isLlm = row.mode === "llm";
        return `<tr>
          <td>${esc(fmtDate(row.timestamp))}</td>
          <td>${esc(row.model || "—")}</td>
          <td>${esc(row.device || "—")}</td>
          <td>${isLlm ? "Токены/с" : "Кадры/с"}</td>
          <td>${isLlm ? esc(row.throughput_tps ?? row.throughput_fps ?? 0) : esc(row.throughput_fps ?? 0)}</td>
        </tr>`;
      })
      .join("")}</tbody></table></div>`;
}

export function chartRows(history) {
  const rows = history
    .filter((row) => row.throughput_fps || row.throughput_tps)
    .slice(0, 6);
  if (!rows.length) return `<p class="muted small">Недостаточно данных для графика.</p>`;
  const max = Math.max(...rows.map((row) => Number(row.throughput_tps || row.throughput_fps) || 1));
  return `<div class="chart">${rows
    .map((row) => {
      const value = Number(row.throughput_tps || row.throughput_fps) || 0;
      return `<div class="chart-row">
        <span class="chart-label" title="${esc(row.model)}">${esc(row.model)} · ${esc(row.device)}</span>
        <span class="chart-track"><span class="chart-bar" style="width:${Math.max(4, (value / max) * 100)}%"></span></span>
        <span class="chart-value">${esc(value)}</span>
      </div>`;
    })
    .join("")}</div>`;
}

export function emptyBox(iconName, title, text, action = "") {
  return `<div class="empty">
    <div class="empty-icon">${icon(iconName)}</div>
    <h3>${esc(title)}</h3>
    <p>${text}</p>
    ${action}
  </div>`;
}
