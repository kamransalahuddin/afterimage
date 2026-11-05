import { useEffect, useState } from "react";
import { Download, FileText, Image as ImageIcon } from "lucide-react";
import { Button, Logo, Spinner } from "../components/ui";
import { GONE, Voxels } from "../components/Voxels";
import { ApiError, api, formatBytes, formatDate, relativeFromNow, saveBlob } from "../lib/api";
import type { SharePublic } from "../lib/types";

const MESSAGES: Record<string, { title: string; body: string }> = {
  share_expired: { title: "This link has expired", body: "Ask the sender for a new link." },
  share_revoked: { title: "This link was revoked", body: "The sender turned this link off." },
  share_download_limit: { title: "No downloads left", body: "This link reached its download limit." },
  share_not_found: { title: "Link not found", body: "Check that you copied the whole link." },
  invalid_request: { title: "Link not found", body: "Check that you copied the whole link." },
};

export function Recipient() {
  // The token lives in the URL fragment so it is never sent to any server in a request line or Referer.
  const [token] = useState(() => window.location.hash.slice(1));
  const [info, setInfo] = useState<SharePublic | null>(null);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setError(MESSAGES.share_not_found);
      return;
    }
    api
      .shareInfo(token)
      .then(setInfo)
      .catch((e: ApiError) => setError(MESSAGES[e.code] ?? { title: "Something went wrong", body: e.message }));
  }, [token]);

  const download = async () => {
    if (!info) return;
    setBusy(true);
    try {
      saveBlob(await api.shareDownload(token), info.filename);
      setDone(true);
      setInfo({ ...info, downloads_remaining: info.downloads_remaining === null ? null : info.downloads_remaining - 1 });
    } catch (e) {
      const err = e as ApiError;
      setError(MESSAGES[err.code] ?? { title: "Download failed", body: err.message });
    } finally {
      setBusy(false);
    }
  };

  const Icon = info?.mime === "application/pdf" ? FileText : ImageIcon;
  const exhausted = info?.downloads_remaining === 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
        <Logo />
      </header>
      <main className="flex flex-1 items-center justify-center px-6 pb-24">
        <div className="w-full max-w-sm animate-rise">
          {error ? (
            <div className="text-center">
              <Voxels voxels={GONE} size={10} className="mx-auto mb-8 h-20 w-auto" />
              <h1 className="text-xl font-semibold tracking-[-0.02em]">{error.title}</h1>
              <p className="mt-2 text-[14px] text-zinc-500">{error.body}</p>
            </div>
          ) : !info ? (
            <div className="flex justify-center text-zinc-400">
              <Spinner className="h-5 w-5" />
            </div>
          ) : (
            <div className="rounded-2xl border border-zinc-200 p-6">
              <p className="text-[12px] font-medium text-zinc-400">Someone shared a file with you</p>
              <div className="mt-4 flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-500">
                  <Icon className="h-4.5 w-4.5" strokeWidth={1.75} />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium">{info.filename}</p>
                  <p className="text-[12px] text-zinc-500">{formatBytes(info.size)}</p>
                </div>
              </div>
              <dl className="mt-5 space-y-1.5 text-[13px]">
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Expires</dt>
                  <dd title={formatDate(info.expires_at)}>{relativeFromNow(info.expires_at)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Downloads left</dt>
                  <dd>{info.downloads_remaining === null ? "Unlimited" : info.downloads_remaining}</dd>
                </div>
              </dl>
              <Button variant="primary" size="lg" className="mt-6 w-full" onClick={download} disabled={busy || exhausted}>
                {busy ? <Spinner className="h-3.5 w-3.5" /> : <Download className="h-4 w-4" />}
                {done ? (exhausted ? "Downloaded" : "Download again") : "Download"}
              </Button>
              <p className="mt-4 text-center text-[12px] leading-relaxed text-zinc-400">
                Sanitized with AFTERIMAGE. Automated redaction can miss things.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
