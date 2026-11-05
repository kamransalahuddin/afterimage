import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff, MousePointer2, RotateCcw, SquareDashed } from "lucide-react";
import { DetectionPanel } from "../components/DetectionPanel";
import { PageCanvas, type Mode } from "../components/PageCanvas";
import { Button, Kbd, Logo, Spinner } from "../components/ui";
import { ApiError, api } from "../lib/api";
import type { Analysis, Detection, ManualRegion, RedactResult } from "../lib/types";

export interface WorkspaceSeed {
  excludedKeys?: Set<string>;
  manual?: ManualRegion[];
  rasterize?: boolean;
}

export const detectionKey = (d: Detection) =>
  `${d.category}:${d.page}:${d.boxes.map((b) => `${b.x.toFixed(3)},${b.y.toFixed(3)}`).join("|")}`;

interface Props {
  analysis: Analysis;
  previews: Record<number, string>;
  setPreview: (page: number, url: string) => void;
  seed?: WorkspaceSeed;
  onExit: () => void;
  onRedacted: (r: RedactResult, state: WorkspaceSeed) => void;
}

const initialSelection = (a: Analysis, seed?: WorkspaceSeed) =>
  new Set(
    a.detections
      .filter((d) => (seed?.excludedKeys ? !seed.excludedKeys.has(detectionKey(d)) && d.suggested : d.suggested))
      .map((d) => d.id),
  );

export function Workspace({ analysis: a, previews, setPreview, seed, onExit, onRedacted }: Props) {
  const [selected, setSelected] = useState(() => initialSelection(a, seed));
  const [manual, setManual] = useState<ManualRegion[]>(seed?.manual ?? []);
  const [mode, setMode] = useState<Mode>("select");
  const [preview, setPreviewMode] = useState(false);
  const [page, setPage] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);
  const [activeManual, setActiveManual] = useState<string | null>(null);
  const [rasterize, setRasterize] = useState(seed?.rasterize ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pageCount = a.pages.length;
  const dims = a.pages[page];

  const loadPage = useCallback(
    async (n: number) => {
      if (previews[n]) return previews[n];
      const blob = await api.pagePreview(a.session_id, a.session_token, n);
      const url = URL.createObjectURL(blob);
      setPreview(n, url);
      return url;
    },
    [a.session_id, a.session_token, previews, setPreview],
  );

  useEffect(() => {
    loadPage(page).catch((e: ApiError) => setError(e.message));
    if (page + 1 < pageCount) loadPage(page + 1).catch(() => {});
  }, [page, pageCount, loadPage]);

  const toggle = (id: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });

  const reset = () => {
    setSelected(initialSelection(a));
    setManual([]);
    setActiveManual(null);
    setPreviewMode(false);
    setMode("select");
  };

  const dirty = useMemo(() => {
    const init = initialSelection(a);
    return manual.length > 0 || init.size !== selected.size || [...init].some((id) => !selected.has(id));
  }, [a, manual, selected]);

  const total = selected.size + manual.length;

  const redact = async () => {
    setBusy(true);
    setError(null);
    try {
      // The server deletes the original after redaction; cache every page first for before/after.
      await Promise.all(a.pages.map((_, i) => loadPage(i)));
      const result = await api.redact(a, [...selected], manual, rasterize);
      const excludedKeys = new Set(a.detections.filter((d) => !selected.has(d.id)).map(detectionKey));
      onRedacted(result, { excludedKeys, manual, rasterize });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Redaction failed. Nothing was saved.");
      setBusy(false);
    }
  };

  // Keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest?.("input, textarea, [role=dialog]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "r") setMode("draw");
      else if (k === "v") setMode("select");
      else if (k === "p") setPreviewMode((v) => !v);
      else if (k === "escape") {
        setMode("select");
        setPreviewMode(false);
        setActiveManual(null);
      } else if ((k === "backspace" || k === "delete") && activeManual) {
        e.preventDefault();
        setManual((m) => m.filter((r) => r.id !== activeManual));
        setActiveManual(null);
      } else if (k === "arrowright" && pageCount > 1) setPage((n) => Math.min(pageCount - 1, n + 1));
      else if (k === "arrowleft" && pageCount > 1) setPage((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeManual, pageCount]);

  const pageDetections = a.detections.filter((d) => d.page === page);
  const pageManual = manual.filter((m) => m.page === page);

  return (
    <div className="flex h-screen flex-col animate-fade">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-zinc-100 px-4">
        <Logo compact onClick={() => (!dirty || confirm("Discard this file and start over?")) && onExit()} />
        <div className="h-5 w-px bg-zinc-200" />
        <p className="min-w-0 truncate text-[13px] font-medium" title={a.filename}>
          {a.filename}
        </p>

        {pageCount > 1 && (
          <div className="ml-2 hidden items-center gap-0.5 text-[13px] text-zinc-500 sm:flex">
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

        <div className="ml-auto flex items-center gap-1">
          <div className="mr-1 hidden items-center rounded-lg border border-zinc-200 p-0.5 md:flex" role="toolbar" aria-label="Tools">
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={mode === "select"}
              onClick={() => setMode("select")}
              className={mode === "select" ? "bg-zinc-100 text-ink" : ""}
            >
              <MousePointer2 className="h-3.5 w-3.5" /> Select <Kbd>V</Kbd>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={mode === "draw"}
              onClick={() => {
                setMode("draw");
                setPreviewMode(false);
              }}
              className={mode === "draw" ? "bg-zinc-100 text-ink" : ""}
            >
              <SquareDashed className="h-3.5 w-3.5" /> Draw box <Kbd>R</Kbd>
            </Button>
          </div>
          <Button variant="ghost" size="sm" aria-pressed={preview} onClick={() => setPreviewMode(!preview)}>
            {preview ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{preview ? "Exit preview" : "Preview"}</span>
            <Kbd>P</Kbd>
          </Button>
          <Button variant="ghost" size="sm" onClick={reset} disabled={!dirty}>
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </Button>
          <Button variant="primary" size="md" className="ml-2" onClick={redact} disabled={busy}>
            {busy ? <Spinner className="h-3.5 w-3.5" /> : null}
            {busy ? "Redacting…" : total ? `Redact file` : "Export clean copy"}
          </Button>
        </div>
      </header>

      {error && (
        <div role="alert" className="border-b border-red-100 bg-red-50 px-4 py-2 text-center text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="relative min-h-[50vh] flex-1 overflow-auto bg-zinc-50/70 p-6 sm:p-10">
          <PageCanvas
            src={previews[page] ?? null}
            width={dims.width}
            height={dims.height}
            page={page}
            detections={pageDetections}
            selected={selected}
            hovered={hovered}
            manual={pageManual}
            activeManual={activeManual}
            mode={mode}
            preview={preview}
            onToggle={(id) => toggle(id, !selected.has(id))}
            onHover={setHovered}
            onAddManual={(r) => setManual((m) => [...m, r])}
            onUpdateManual={(r) => setManual((m) => m.map((x) => (x.id === r.id ? r : x)))}
            onRemoveManual={(id) => setManual((m) => m.filter((x) => x.id !== id))}
            onActivateManual={setActiveManual}
          />
          <p className="pointer-events-none mt-4 text-center text-[12px] text-zinc-400">
            {preview
              ? "Previewing the redacted result"
              : mode === "draw"
                ? "Drag to cover anything we missed · Esc to finish"
                : "Click a highlight to keep or redact it"}
          </p>
          {pageCount > 1 && (
            <div className="mt-2 flex items-center justify-center gap-2 text-[13px] text-zinc-500 sm:hidden">
              <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              {page + 1} / {pageCount}
              <Button variant="ghost" size="sm" disabled={page === pageCount - 1} onClick={() => setPage(page + 1)} aria-label="Next page">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </main>
        <div className="border-t border-zinc-100 lg:w-[340px] lg:shrink-0 lg:border-t-0 lg:border-l">
          <DetectionPanel
            detections={a.detections}
            selected={selected}
            hovered={hovered}
            manual={manual}
            metadata={a.metadata}
            notes={a.notes}
            multiPage={pageCount > 1}
            isPdf={a.kind === "pdf"}
            rasterize={rasterize}
            onRasterize={setRasterize}
            onToggle={toggle}
            onToggleMany={(ids, on) =>
              setSelected((s) => {
                const n = new Set(s);
                ids.forEach((id) => (on ? n.add(id) : n.delete(id)));
                return n;
              })
            }
            onHover={setHovered}
            onFocus={(d) => {
              setPage(d.page);
              setHovered(d.id);
            }}
            onRemoveManual={(id) => setManual((m) => m.filter((x) => x.id !== id))}
            onFocusManual={(m) => {
              setPage(m.page);
              setMode("select");
              setActiveManual(m.id);
            }}
          />
        </div>
      </div>
    </div>
  );
}
