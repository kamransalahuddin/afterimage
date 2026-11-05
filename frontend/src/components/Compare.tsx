import { useRef, useState } from "react";
import { Spinner } from "./ui";

/** Before/after slider. Drag, click, or use arrow keys on the handle. */
export function Compare({ before, after, width, height }: { before: string | null; after: string | null; width: number; height: number }) {
  const [pos, setPos] = useState(50);
  const ref = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const set = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    setPos(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)));
  };

  return (
    <div
      ref={ref}
      className="relative mx-auto touch-none select-none overflow-hidden rounded-[3px] bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.06),0_8px_24px_-12px_rgba(0,0,0,0.12)]"
      style={{ aspectRatio: `${width} / ${height}`, width: `min(100%, calc((100vh - 11rem) * ${width / height}))` }}
      onPointerDown={(e) => {
        dragging.current = true;
        ref.current!.setPointerCapture(e.pointerId);
        set(e.clientX);
      }}
      onPointerMove={(e) => dragging.current && set(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
    >
      {after ? (
        <img src={after} alt="Redacted result" className="absolute inset-0 h-full w-full" draggable={false} />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-zinc-400">
          <Spinner />
        </div>
      )}
      {before && (
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          <img src={before} alt="Original" className="h-full w-full" draggable={false} />
        </div>
      )}
      <span className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-white/90 px-2 py-0.5 text-[11px] font-medium text-zinc-600 shadow-sm">
        Original
      </span>
      <span className="pointer-events-none absolute bottom-3 right-3 rounded-md bg-ink/90 px-2 py-0.5 text-[11px] font-medium text-white shadow-sm">
        Redacted
      </span>
      <div className="pointer-events-none absolute inset-y-0 w-px bg-accent" style={{ left: `${pos}%` }} />
      <button
        type="button"
        role="slider"
        aria-label="Compare original and redacted"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 5));
          if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + 5));
        }}
        className="absolute top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border border-zinc-200 bg-white shadow-md"
        style={{ left: `${pos}%` }}
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-zinc-500" fill="currentColor" aria-hidden>
          <path d="M6 4 2 8l4 4V4Zm4 0v8l4-4-4-4Z" />
        </svg>
      </button>
    </div>
  );
}
