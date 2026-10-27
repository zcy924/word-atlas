import { useSyncExternalStore } from "react";
import { sanitizeProgress, sanitizeSettings, store, type Progress, type Settings } from "./store";
import { stableJSON, syncAction } from "./sync-policy";

type Snapshot = { app: "word-atlas"; version: 2; progress: Progress; settings: Settings };
type Remote = { revision: number; data: Snapshot | null; updated: number | null };
type Status = {
  code: string | null;
  busy: boolean;
  message: string;
  lastSync: number | null;
  conflict: Remote | null;
};
let status: Status = { code: null, busy: false, message: "未开启同步", lastSync: null, conflict: null };
const listeners = new Set<() => void>();
const update = (patch: Partial<Status>) => {
  status = { ...status, ...patch };
  listeners.forEach((fn) => fn());
};
export const useSyncStatus = () => useSyncExternalStore(
  (fn) => { listeners.add(fn); return () => listeners.delete(fn); },
  () => status,
);

class APIError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(`/api/sync/${path}`, {
      method, credentials: "same-origin", cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new APIError(response.status, result.error || "同步失败，请稍后重试。");
    return result as T;
  } finally { window.clearTimeout(timeout); }
}
const snapshot = (): Snapshot => {
  const { progress, settings } = store.get();
  return { app: "word-atlas", version: 2, progress: { ...progress, session: null }, settings };
};
async function hash(text: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}
const baseKey = (code: string) => `word-atlas:sync:${code}`;
function baseHash(code: string): string | null {
  try { return localStorage.getItem(baseKey(code)); } catch { return null; }
}
function remember(code: string, value: string) {
  // A missing baseline must stop automatic overwrites on the next device refresh.
  localStorage.setItem(baseKey(code), value);
  update({ lastSync: Date.now(), conflict: null, message: "已同步" });
}
function normalize(data: Snapshot): Snapshot {
  if (data.app !== "word-atlas" || data.version !== 2 || data.progress?.datasetId !== "word-atlas-open") {
    throw new Error("云端数据格式不兼容，已保留本机记录。");
  }
  return { app: "word-atlas", version: 2, progress: { ...sanitizeProgress(data.progress, "word-atlas-open"), session: null }, settings: sanitizeSettings(data.settings) };
}

let timer: number | undefined;
let running = false;
let changedDuringRequest = false;
let generation = 0;
const schedule = () => {
  changedDuringRequest = true;
  window.clearTimeout(timer);
  timer = window.setTimeout(() => void syncNow(), 2000);
};

export async function syncNow(choice?: "push" | "pull") {
  const code = status.code;
  if (!code || running || store.get().progress.datasetId !== "word-atlas-open") return;
  running = true;
  changedDuringRequest = false;
  const requestGeneration = generation;
  const selectedRevision = status.conflict?.revision;
  update({ busy: true, message: "正在同步…" });
  try {
    const local = snapshot();
    const text = stableJSON(local);
    const localHash = await hash(text);
    const remote = await api<Remote>("state/word-atlas-open");
    if (requestGeneration !== generation) return;
    const cloud = remote.data ? normalize(remote.data) : null;
    const cloudHash = cloud ? await hash(stableJSON(cloud)) : null;
    // Never apply a response to a local snapshot that changed during the request.
    if (stableJSON(snapshot()) !== text) { schedule(); return; }
    const p = local.progress;
    const localEmpty = !Object.keys(p.cards).length && !p.bookmarks.length && !Object.keys(p.days).length && !p.typing.length && !p.mistakes.length;
    let action = syncAction(localHash, cloudHash, baseHash(code), localEmpty);
    if (choice && selectedRevision === remote.revision) action = choice;
    else if (choice) action = "conflict";
    if (action === "conflict") {
      update({ conflict: remote, message: "本机和云端都有修改，请选择要保留的版本。" });
      return;
    }
    if (action === "pull" && cloud) {
      const session = store.get().progress.session;
      if (session && !session.finished && !choice) {
        update({ conflict: remote, message: "云端有更新，结束当前练习后同步；也可手动选择版本。" });
        return;
      }
      store.applySynced(cloud.progress, cloud.settings);
      remember(code, await hash(stableJSON(snapshot())));
    } else if (action === "push") {
      await api("state/word-atlas-open", "PUT", { revision: remote.revision, data: local });
      if (requestGeneration !== generation) return;
      remember(code, localHash);
    } else {
      remember(code, localHash);
    }
  } catch (error) {
    if (requestGeneration !== generation) return;
    if (error instanceof APIError && error.status === 401) {
      update({ code: null, conflict: null, message: "连接已过期，请重新输入同步码和密码。" });
    } else if (error instanceof APIError && error.status === 409) {
      update({ message: "另一台设备刚刚更新，正在重新检查…" });
      schedule();
    } else {
      update({ message: error instanceof APIError ? error.message : "暂时无法同步，学习数据已保留在本机。请检查网络或浏览器存储空间。" });
    }
  } finally {
    running = false;
    update({ busy: false });
    if (changedDuringRequest) schedule();
  }
}

export async function connectSync(password: string, code?: string) {
  if (running || status.busy) return;
  generation++;
  update({ busy: true, conflict: null });
  try {
    const result = await api<{ code: string }>(code ? "login" : "create", "POST", { password, code: code?.replace(/[\s-]/g, "").toUpperCase() });
    update({ code: result.code, lastSync: null, message: "已连接，正在检查学习数据…" });
  } catch (error) {
    update({ message: error instanceof APIError ? error.message : "连接失败，请检查网络。" });
  } finally {
    update({ busy: false });
  }
  await syncNow();
}

export async function disconnectSync() {
  if (status.busy) return;
  generation++;
  update({ busy: true });
  try {
    await api("logout", "POST", {});
    update({ code: null, conflict: null, lastSync: null, message: "已断开同步，本机记录保留。" });
  } catch {
    update({ message: "断开失败，请检查网络后重试。" });
  } finally { update({ busy: false }); }
}

export function startSync() {
  const initial = ++generation;
  let stopped = false;
  let sessionChecked = false;
  const restore = () => void api<{ code: string }>("session").then((session) => {
    if (stopped || initial !== generation) return;
    sessionChecked = true;
    update({ code: session.code });
    void syncNow();
  }).catch((error: unknown) => {
    if (error instanceof APIError && error.status === 401) sessionChecked = true;
  });
  restore();
  const unsubscribe = store.subscribe(schedule);
  const resume = () => {
    if (document.visibilityState !== "visible") return;
    if (status.code) void syncNow();
    else if (!sessionChecked) restore();
  };
  const interval = window.setInterval(resume, 30000);
  window.addEventListener("online", resume);
  document.addEventListener("visibilitychange", resume);
  return () => {
    stopped = true;
    generation++;
    unsubscribe();
    window.clearTimeout(timer);
    window.clearInterval(interval);
    window.removeEventListener("online", resume);
    document.removeEventListener("visibilitychange", resume);
  };
}
