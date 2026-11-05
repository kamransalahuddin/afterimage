import { useEffect, useRef, useState } from "react";
import { Check, Copy, Link2, X } from "lucide-react";
import { ApiError, api, formatDate } from "../lib/api";
import type { ShareCreated } from "../lib/types";
import { Button, Segmented, Spinner } from "./ui";

type Expiry = "1h" | "24h" | "7d";
type Limit = 1 | 5 | null;

export function ShareDialog({ artifactId, token, onClose }: { artifactId: string; token: string; onClose: () => void }) {
  const [expiry, setExpiry] = useState<Expiry>("24h");
  const [limit, setLimit] = useState<Limit>(1);
  const [share, setShare] = useState<ShareCreated | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocus.current = document.activeElement as HTMLElement;
    dialog.current?.querySelector<HTMLElement>("button, input")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && dialog.current) {
        const items = [...dialog.current.querySelectorAll<HTMLElement>("button:not([disabled]), input")];
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousFocus.current?.focus();
    };
  }, [onClose]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      setShare(await api.createShare(artifactId, token, expiry, limit));
      setRevoked(false);
      setConfirmRevoke(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create a link.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!share) return;
    try {
      await navigator.clipboard.writeText(share.url);
    } catch {
      const input = dialog.current?.querySelector<HTMLInputElement>("input");
      input?.select();
      document.execCommand("copy");
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const revoke = async () => {
    if (!share) return;
    setBusy(true);
    try {
      await api.revokeShare(share.id, share.manage_token);
      setRevoked(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not revoke the link.");
    } finally {
      setBusy(false);
      setConfirmRevoke(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade">
      <div className="absolute inset-0 bg-zinc-900/20" onClick={onClose} aria-hidden />
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-title"
        className="relative w-full max-w-[420px] rounded-2xl border border-zinc-200 bg-white p-6 shadow-[0_24px_48px_-16px_rgba(0,0,0,0.18)] animate-rise"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 id="share-title" className="text-[17px] font-semibold tracking-[-0.01em]">
              Share securely
            </h2>
            <p className="mt-1 text-[13px] text-zinc-500">An encrypted link to the redacted file only.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="-mt-1 -mr-1 rounded-md p-1.5 text-zinc-400 hover:text-ink">
            <X className="h-4 w-4" />
          </button>
        </div>

        {!share || revoked ? (
          <div className="mt-6 space-y-5">
            <div>
              <p className="mb-2 text-[12px] font-medium text-zinc-500">Expires after</p>
              <Segmented<Expiry>
                label="Expiration"
                value={expiry}
                onChange={setExpiry}
                options={[
                  { value: "1h", label: "1 hour" },
                  { value: "24h", label: "24 hours" },
                  { value: "7d", label: "7 days" },
                ]}
              />
            </div>
            <div>
              <p className="mb-2 text-[12px] font-medium text-zinc-500">Maximum downloads</p>
              <Segmented<Limit>
                label="Maximum downloads"
                value={limit}
                onChange={setLimit}
                options={[
                  { value: 1, label: "1" },
                  { value: 5, label: "5" },
                  { value: null, label: "Unlimited" },
                ]}
              />
            </div>
            {revoked && <p className="text-[13px] text-zinc-500">The previous link was revoked and no longer works.</p>}
            <Button variant="primary" size="lg" className="w-full" onClick={generate} disabled={busy}>
              {busy ? <Spinner className="h-3.5 w-3.5" /> : <Link2 className="h-4 w-4" />}
              {revoked ? "Generate a new link" : "Generate secure link"}
            </Button>
          </div>
        ) : (
          <div className="mt-6 space-y-4 animate-fade">
            <div className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50/60 p-1 pl-3">
              <input
                readOnly
                value={share.url}
                aria-label="Secure link"
                onFocus={(e) => e.target.select()}
                className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-zinc-700 outline-none"
              />
              <Button variant={copied ? "secondary" : "primary"} size="sm" onClick={copy} aria-live="polite">
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy link"}
              </Button>
            </div>
            <dl className="grid grid-cols-2 gap-3 text-[13px]">
              <div className="rounded-lg border border-zinc-100 px-3 py-2.5">
                <dt className="text-[11px] text-zinc-400">Expires</dt>
                <dd className="mt-0.5 font-medium">{formatDate(share.expires_at)}</dd>
              </div>
              <div className="rounded-lg border border-zinc-100 px-3 py-2.5">
                <dt className="text-[11px] text-zinc-400">Downloads</dt>
                <dd className="mt-0.5 font-medium">
                  {share.max_downloads === null ? "Unlimited" : `${share.max_downloads} allowed`}
                </dd>
              </div>
            </dl>
            <p className="text-[12px] leading-relaxed text-zinc-500">
              Anyone with this link can download the file until it expires. This is the only time the link is shown.
              Recipients can keep a copy of anything they download.
            </p>
            <div className="flex items-center justify-between border-t border-zinc-100 pt-4">
              {confirmRevoke ? (
                <div className="flex items-center gap-2">
                  <span className="text-[13px] text-zinc-600">Revoke now?</span>
                  <Button variant="danger" size="sm" onClick={revoke} disabled={busy}>
                    Revoke
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmRevoke(false)}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button variant="danger" size="sm" onClick={() => setConfirmRevoke(true)}>
                  Revoke link
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        )}
        {error && (
          <p role="alert" className="mt-4 text-[13px] text-red-600">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
