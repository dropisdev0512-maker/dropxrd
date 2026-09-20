export const API_KEY = "dropx_api";

export function getApiBase(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_KEY);
}

export function setApiBase(url: string) {
  window.localStorage.setItem(API_KEY, url.replace(/\/+$/, ""));
}

export type ApiResult = { ok: boolean; data?: unknown; error?: string };

async function request(path: string, init?: RequestInit): Promise<ApiResult> {
  const base = getApiBase();
  if (!base) return { ok: false, error: "No PC API URL saved" };
  try {
    const headers: Record<string, string> = init?.body
      ? { "Content-Type": "application/json" }
      : {};
    const res = await fetch(`${base}${path}`, { ...init, headers });
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      data = await res.text().catch(() => null);
    }
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}`, data };
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Network error" };
  }
}

export const api = {
  status: () => request("/status"),
  wake: () => request("/wake", { method: "POST", body: JSON.stringify({}) }),
  shutdown: (delay = 30) =>
    request("/shutdown", { method: "POST", body: JSON.stringify({ delay }) }),
  cancelShutdown: () => request("/shutdown/cancel", { method: "POST", body: JSON.stringify({}) }),
  scaffold: (kind: string, target: string) =>
    request("/scaffold", { method: "POST", body: JSON.stringify({ kind, target }) }),
  qa: (path: string) => request("/qa", { method: "POST", body: JSON.stringify({ path }) }),
  open: (target: string, window_: string) =>
    request("/open", { method: "POST", body: JSON.stringify({ target, window: window_ }) }),
  call: (message: string) =>
    request("/call", { method: "POST", body: JSON.stringify({ message }) }),
  dropx: () => request("/dropx", { method: "POST", body: JSON.stringify({}) }),
};

export function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = "en-IN";
  utter.rate = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

export function stamp() {
  return new Date().toLocaleTimeString("en-IN", { hour12: false });
}
