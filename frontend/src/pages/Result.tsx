import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, ChevronLeft, ChevronRight, Download, Link2, Plus } from "lucide-react";
import { Compare } from "../components/Compare";
import { ShareDialog } from "../components/ShareDialog";
import { Button, Logo, Spinner } from "../components/ui";
import { ApiError, api, formatBytes, relativeFromNow, saveBlob } from "../lib/api";
import type { Analysis, RedactResult } from "../lib/types";

interface Props {
  analysis: Analysis;
  result: RedactResult;
  before: Record<number, string>;
  onNew: () => void;
  onEdit: () => void;
}

export function Result({ analysis: a, result: r, before, onNew, onEdit }: Props) {
  const [page, setPage] = useState(0);
  const [after, setAfter] = useState<Record<number, string>>({});
  const [sharing, setSharing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pageCount = a.pages.length;

  useEffect(() => {
    if (after[page]) return;
    let cancelled = false;
    api
      .artifactPreview(r.artifact_id, a.session_token, page)
      .then((b) => !cancelled && setAfter((m) => ({ ...m, [page]: URL.createObjectURL(b) })))
      .catch((e: ApiError) => setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [page, after, r.artifact_id, a.session_token]);

  useEffect(() => () => Object.values(after).forEach(URL.revokeObjectURL), []); // eslint-disable-line react-hooks/exhaustive-deps

  const download = async () => {
    setDownloading(true);
    try {
      saveBlob(await api.artifactDownload(r.artifact_id, a.session_token), r.filename);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Download failed.");
    } finally {
      setDownloading(false);
    }
  };

  const v = r.verification;
  const checks = [
    `${r.regions} area${r.regions === 1 ? "" : "s"} permanently removed`,
    a.kind === "pdf" ? "No text remains extractable in redacted areas" : "Redacted pixels overwritten and verified",
    r.metadata_removed.length ? `Metadata removed: ${r.metadata_removed.join(", ")}` : "No identifying metadata in export",
    ...(a.kind === "pdf" ? ["Comments, links, form data and attachments removed"] : []),
    ...(v.rasterized ? ["Pages flattened to images"] : []),
  ];

  return (
    <div className="flex h-screen flex-col animate-fade">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-zinc-100 px-4">
        <Logo compact onClick={onNew} />
        <div className="h-5 w-px bg-zinc-200" />
        <p className="min-w-0 truncate text-[13px] font-medium">{r.filename}</p>
        <span className="hidden text-[12px] text-zinc-400 sm:inline">{formatBytes(r.size)}</span>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={onEdit}>
            <ArrowLeft className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Edit again</span>
          </Button>
          <Button variant="ghost" size="sm" onClick={onNew}>
            <Plus className="h-3.5 w-3.5" /> <span className="hidden sm:inline">New file</span>
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="min-h-[50vh] flex-1 overflow-auto bg-zinc-50/70 p-6 sm:p-10">
          <Compare before={before[page] ?? null} after={after[page] ?? null} width={a.pages[page].width} height={a.pages[page].height} />
          {pageCount > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2 text-[13px] text-zinc-500">
              <Button variant="ghost" size="sm" aria-label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="tabular-nums">
                {page + 1} / {pageCount}
              </span>
              <Button variant="ghost" size="sm" aria-label="Next page" disabled={page === pageCount - 1} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </main>

        <aside className="flex flex-col border-t border-zinc-100 lg:w-[340px] lg:shrink-0 lg:border-t-0 lg:border-l">
          <div className="flex-1 overflow-y-auto px-5 py-6">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
              <Check className="h-4 w-4" strokeWidth={2.5} />
            </div>
            <h2 className="mt-4 text-[17px] font-semibold tracking-[-0.01em]">Redaction complete</h2>
            <p className="mt-1 text-[13px] text-zinc-500">A new file was written from scratch. The original was deleted from the server.</p>

            <ul className="mt-6 space-y-2.5">
              {checks.map((c) => (
                <li key={c} className="flex gap-2.5 text-[13px] leading-snug text-zinc-700">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" strokeWidth={2.5} />
                  {c}
                </li>
              ))}
            </ul>

            {(v.residual_matches ?? 0) > 0 && (
              <div className="mt-6 flex gap-2.5 rounded-lg bg-amber-50 px-3 py-2.5 text-[12.5px] leading-snug text-amber-800">
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
                {v.residual_matches} redacted value{v.residual_matches === 1 ? " also appears" : "s also appear"} elsewhere in
                the document. Edit again to review.
              </div>
            )}

            {error && (
              <p role="alert" className="mt-6 text-[13px] text-red-600">
                {error}
              </p>
            )}
          </div>

          <div className="space-y-2 border-t border-zinc-100 px-5 py-5">
            <Button variant="primary" size="lg" className="w-full" onClick={download} disabled={downloading}>
              {downloading ? <Spinner className="h-3.5 w-3.5" /> : <Download className="h-4 w-4" />}
              Download sanitized file
            </Button>
            <Button size="lg" className="w-full" onClick={() => setSharing(true)}>
              <Link2 className="h-4 w-4" /> Create secure link
            </Button>
            <p className="pt-1 text-center text-[12px] text-zinc-400">Deleted from the server {relativeFromNow(r.expires_at)} unless shared.</p>
          </div>
        </aside>
      </div>

      {sharing && <ShareDialog artifactId={r.artifact_id} token={a.session_token} onClose={() => setSharing(false)} />}
    </div>
  );
}
