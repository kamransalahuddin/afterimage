import { useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { X } from "lucide-react";
import type { BoxN, Detection, ManualRegion } from "../lib/types";
import { Spinner } from "./ui";

export type Mode = "select" | "draw";

interface Props {
  src: string | null;
  width: number;
  height: number;
  page: number;
  detections: Detection[];
  selected: Set<string>;
  hovered: string | null;
  manual: ManualRegion[];
  activeManual: string | null;
  mode: Mode;
  preview: boolean;
  onToggle: (id: string) => void;
  onHover: (id: string | null) => void;
  onAddManual: (r: ManualRegion) => void;
  onUpdateManual: (r: ManualRegion) => void;
  onRemoveManual: (id: string) => void;
  onActivateManual: (id: string | null) => void;
}

const MIN = 0.004;
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const pct = (b: BoxN) => ({ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` });

type Drag =
  | { kind: "draw"; x0: number; y0: number }
  | { kind: "move"; id: string; dx: number; dy: number; orig: ManualRegion }
  | { kind: "resize"; id: string; orig: ManualRegion };

export function PageCanvas(p: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const [draft, setDraftState] = useState<BoxN | null>(null);
  const draftRef = useRef<BoxN | null>(null);
  const setDraft = (b: BoxN | null) => {
    draftRef.current = b;
    setDraftState(b);
  };
  const capture = (e: RPointerEvent) => {
    try {
      ref.current!.setPointerCapture(e.pointerId);
    } catch {
      /* synthetic or already-released pointer */
    }
  };

  const point = (e: RPointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };

  const onDown = (e: RPointerEvent) => {
    if (p.mode !== "draw" || e.button !== 0) return;
    const { x, y } = point(e);
    drag.current = { kind: "draw", x0: x, y0: y };
    capture(e);
    setDraft({ x, y, w: 0, h: 0 });
    p.onActivateManual(null);
  };

  const onMove = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const { x, y } = point(e);
    if (d.kind === "draw") {
      setDraft({ x: Math.min(x, d.x0), y: Math.min(y, d.y0), w: Math.abs(x - d.x0), h: Math.abs(y - d.y0) });
    } else if (d.kind === "move") {
      const nx = clamp(x - d.dx, 0, 1 - d.orig.w);
      const ny = clamp(y - d.dy, 0, 1 - d.orig.h);
      p.onUpdateManual({ ...d.orig, x: nx, y: ny });
    } else {
      p.onUpdateManual({ ...d.orig, w: clamp(x - d.orig.x, MIN, 1 - d.orig.x), h: clamp(y - d.orig.y, MIN, 1 - d.orig.y) });
    }
  };

  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    const draft = draftRef.current;
    if (d?.kind === "draw" && draft && draft.w > MIN && draft.h > MIN) {
      const id = crypto.randomUUID();
      p.onAddManual({ id, page: p.page, ...draft });
      p.onActivateManual(id);
    }
    setDraft(null);
  };

  const startManualDrag = (e: RPointerEvent, m: ManualRegion, kind: "move" | "resize") => {
    if (p.mode === "draw" && kind === "move") return;
    e.stopPropagation();
    const { x, y } = point(e);
    drag.current = kind === "move" ? { kind, id: m.id, dx: x - m.x, dy: y - m.y, orig: m } : { kind, id: m.id, orig: m };
    capture(e);
    p.onActivateManual(m.id);
  };

  return (
    <div
      className="relative mx-auto select-none"
      style={{
        aspectRatio: `${p.width} / ${p.height}`,
        width: `min(100%, calc((100vh - 9.5rem) * ${p.width / p.height}))`,
      }}
    >
      <div className="absolute inset-0 overflow-hidden rounded-[3px] bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.06),0_8px_24px_-12px_rgba(0,0,0,0.12)]">
        {p.src ? (
          <img src={p.src} alt={`Page ${p.page + 1} preview`} className="h-full w-full" draggable={false} />
        ) : (
          <div className="flex h-full items-center justify-center text-zinc-400">
            <Spinner />
          </div>
        )}
      </div>

      <div
        ref={ref}
        className={`absolute inset-0 ${p.mode === "draw" ? "cursor-crosshair" : ""}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onClick={(e) => {
          if (e.target === ref.current) p.onActivateManual(null);
        }}
      >
        {p.detections.map((d) => {
          const on = p.selected.has(d.id);
          const hot = p.hovered === d.id;
          return d.boxes.map((b, i) => (
            <button
              key={`${d.id}-${i}`}
              type="button"
              tabIndex={-1}
              aria-label={`${d.label}, ${on ? "will be redacted" : "kept"}`}
              onClick={(e) => {
                e.stopPropagation();
                if (p.mode === "select") p.onToggle(d.id);
              }}
              onPointerEnter={() => p.onHover(d.id)}
              onPointerLeave={() => p.onHover(null)}
              style={pct(b)}
              className={`absolute rounded-[2px] transition-[background-color,box-shadow,border-color] duration-150 ${
                p.mode === "draw" ? "pointer-events-none" : "cursor-pointer"
              } ${
                p.preview
                  ? on
                    ? "bg-black"
                    : "border border-dashed border-transparent"
                  : on
                    ? hot
                      ? "border border-accent bg-accent/25 shadow-[0_0_0_3px_rgba(79,70,229,0.18)]"
                      : "border border-accent/70 bg-accent/10"
                    : hot
                      ? "border border-dashed border-zinc-500 bg-zinc-500/10"
                      : "border border-dashed border-zinc-400/70"
              }`}
            />
          ));
        })}

        {p.manual.map((m) => {
          const active = p.activeManual === m.id;
          return (
            <div
              key={m.id}
              style={pct(m)}
              onPointerDown={(e) => startManualDrag(e, m, "move")}
              className={`group absolute rounded-[2px] ${p.mode === "select" ? "cursor-move" : "pointer-events-none"} ${
                p.preview ? "bg-black" : `bg-black/70 ${active ? "ring-2 ring-accent ring-offset-1" : "ring-1 ring-black/40"}`
              }`}
            >
              {!p.preview && p.mode === "select" && (
                <>
                  <button
                    type="button"
                    aria-label="Remove manual redaction"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      p.onRemoveManual(m.id);
                    }}
                    className={`absolute -top-2.5 -right-2.5 flex h-5 w-5 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-600 shadow-sm transition-opacity hover:text-ink ${
                      active ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                    }`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                  <span
                    onPointerDown={(e) => startManualDrag(e, m, "resize")}
                    className={`absolute -right-1 -bottom-1 h-2.5 w-2.5 cursor-se-resize rounded-[2px] border border-accent bg-white ${
                      active ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                    }`}
                  />
                </>
              )}
            </div>
          );
        })}

        {draft && <div style={pct(draft)} className="pointer-events-none absolute rounded-[2px] border border-accent bg-black/50" />}
      </div>
    </div>
  );
}
