// Thin API client for the local OpenVINO Studio server.

async function request(path, { method = "GET", body = null, signal = null } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new Error("Сервер OpenVINO Studio не отвечает.");
  }
  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const message = data?.error || `Ошибка сервера (${response.status}).`;
    throw new Error(message);
  }
  return data;
}

export const api = {
  ping: () => request("/api/ping"),
  system: (force = false) => request(`/api/system${force ? "?refresh=1" : ""}`),
  settings: () => request("/api/settings"),
  saveSettings: (payload) => request("/api/settings", { method: "POST", body: payload }),
  models: () => request("/api/models"),
  deleteModel: (id) => request("/api/models/delete", { method: "POST", body: { id } }),
  revealModel: (id) => request("/api/models/reveal", { method: "POST", body: { id } }),
  jobs: () => request("/api/jobs"),
  cancelJob: (id) => request("/api/jobs/cancel", { method: "POST", body: { id } }),
  searchModels: (params) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.task) search.set("task", params.task);
    if (params.sort) search.set("sort", params.sort);
    if (params.official) search.set("author", "OpenVINO");
    if (params.limit) search.set("limit", params.limit);
    return request(`/api/hf/search?${search.toString()}`);
  },
  modelDetail: (repo) => request(`/api/hf/model?repo=${encodeURIComponent(repo)}`),
  curated: () => request("/api/hf/curated"),
  download: (payload) => request("/api/models/download", { method: "POST", body: payload }),
  benchmark: (payload) => request("/api/benchmark", { method: "POST", body: payload }),
  benchmarks: () => request("/api/benchmarks"),
  convert: (payload) => request("/api/convert", { method: "POST", body: payload }),
  install: (components) => request("/api/install", { method: "POST", body: { components } }),
  logs: (limit = 400) => request(`/api/logs?limit=${limit}`),
  image: (payload) => request("/api/image", { method: "POST", body: payload }),
  openFolder: (target) => request("/api/open-folder", { method: "POST", body: { target } }),
  shutdown: () => request("/api/shutdown", { method: "POST", body: {} }),
};

async function streamEndpoint(path, payload, { signal = null, onEvent = () => {} } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new Error("Не удалось подключиться к серверу.");
  }
  if (!response.ok) {
    let message = `Ошибка генерации (${response.status}).`;
    try {
      const data = await response.json();
      if (data?.error) message = data.error;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  if (!response.body) throw new Error("Браузер не поддерживает потоковый ответ.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw));
        } catch {
          // ignore malformed event
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export function streamChat(payload, options = {}) {
  return streamEndpoint("/api/chat", payload, options);
}

export function streamVLM(payload, options = {}) {
  return streamEndpoint("/api/vlm", payload, options);
}
