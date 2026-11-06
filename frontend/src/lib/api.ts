import type { Analysis, ManualRegion, RedactResult, ShareCreated, SharePublic } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error) return new ApiError(res.status, body.error.code, body.error.message);
  } catch {
    /* fall through */
  }
  return new ApiError(res.status, "http_error", "Something went wrong. Please try again.");
}

/** Empty in dev (Vite proxies /api). In production, the API origin, e.g. https://afterimage-api-xe4u.onrender.com */
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...init, credentials: "omit", referrerPolicy: "no-referrer" });
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Check your connection.");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function blob(path: string, init: RequestInit = {}): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...init, credentials: "omit", referrerPolicy: "no-referrer" });
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Check your connection.");
  }
  if (!res.ok) throw await parseError(res);
  return res.blob();
}

const json = (body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(body),
});

/** Upload with real progress events (fetch has no upload progress). */
export function analyzeFile(file: File, onProgress: (fraction: number) => void): Promise<Analysis> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API_BASE + "/api/files/analyze");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.upload.onload = () => onProgress(1);
    xhr.onerror = () => reject(new ApiError(0, "network", "Can't reach the server. Check your connection."));
    xhr.onload = () => {
      const body = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Analysis);
      else
        reject(
          new ApiError(
            xhr.status,
            body?.error?.code ?? "http_error",
            body?.error?.message ?? "The file could not be processed.",
          ),
        );
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  pagePreview: (sessionId: string, token: string, page: number) =>
    blob(`/api/files/${sessionId}/pages/${page}/preview`, { headers: { "X-Session-Token": token } }),

  redact: (a: Analysis, detectionIds: string[], manual: ManualRegion[], rasterize: boolean) =>
    request<RedactResult>(
      "/api/files/redact",
      json(
        {
          session_id: a.session_id,
          detection_ids: detectionIds,
          manual_regions: manual.map(({ page, x, y, w, h }) => ({ page, x, y, w, h })),
          rasterize,
        },
        { "X-Session-Token": a.session_token },
      ),
    ),

  artifactPreview: (artifactId: string, token: string, page: number) =>
    blob(`/api/artifacts/${artifactId}/pages/${page}/preview`, { headers: { "X-Session-Token": token } }),

  artifactDownload: (artifactId: string, token: string) =>
    blob(`/api/artifacts/${artifactId}/download`, { headers: { "X-Session-Token": token } }),

  createShare: (artifactId: string, token: string, expiresIn: "1h" | "24h" | "7d", maxDownloads: 1 | 5 | null) =>
    request<ShareCreated>(
      "/api/shares",
      json({ artifact_id: artifactId, expires_in: expiresIn, max_downloads: maxDownloads }, { "X-Session-Token": token }),
    ),

  revokeShare: (shareId: string, manageToken: string) =>
    request<void>(`/api/shares/${shareId}`, { method: "DELETE", headers: { Authorization: `Bearer ${manageToken}` } }),

  shareInfo: (token: string) => request<SharePublic>(`/api/shares/${encodeURIComponent(token)}`),

  shareDownload: (token: string) => blob(`/api/shares/${encodeURIComponent(token)}/download`, { method: "POST" }),
};

export function saveBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function relativeFromNow(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const mins = Math.round(ms / 60_000);
  if (mins < 60) return `in ${mins} minute${mins === 1 ? "" : "s"}`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `in ${hours} hour${hours === 1 ? "" : "s"}`;
  const days = Math.round(hours / 24);
  return `in ${days} days`;
}
