import { useMemo } from "react";
import {
  CreditCard,
  FileText,
  KeyRound,
  Mail,
  MapPin,
  Phone,
  ScanFace,
  ShieldAlert,
  Square,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { CATEGORY_META, type Category, type Detection, type ManualRegion, type MetadataItem } from "../lib/types";
import { Switch } from "./ui";

export const CATEGORY_ICON: Record<Category, LucideIcon> = {
  face: ScanFace,
  email: Mail,
  phone: Phone,
  address: MapPin,
  secret: KeyRound,
  card: CreditCard,
  other: FileText,
};

interface Props {
  detections: Detection[];
  selected: Set<string>;
  hovered: string | null;
  manual: ManualRegion[];
  metadata: MetadataItem[];
  notes: string[];
  multiPage: boolean;
  isPdf: boolean;
  rasterize: boolean;
  onRasterize: (v: boolean) => void;
  onToggle: (id: string, on: boolean) => void;
  onToggleMany: (ids: string[], on: boolean) => void;
  onHover: (id: string | null) => void;
  onFocus: (d: Detection) => void;
  onRemoveManual: (id: string) => void;
  onFocusManual: (m: ManualRegion) => void;
}

export function DetectionPanel(p: Props) {
  const groups = useMemo(() => {
    const map = new Map<Category, Detection[]>();
    for (const d of p.detections) map.set(d.category, [...(map.get(d.category) ?? []), d]);
    return [...map.entries()].sort((a, b) => CATEGORY_META[a[0]].order - CATEGORY_META[b[0]].order);
  }, [p.detections]);

  const count = p.detections.length;
  const chosen = p.detections.filter((d) => p.selected.has(d.id)).length;

  return (
    <aside className="flex h-full min-h-0 flex-col" aria-label="Potential exposures">
      <div className="border-b border-zinc-100 px-5 pt-5 pb-4">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
          {count === 0 ? "No exposures found" : `${count} potential exposure${count === 1 ? "" : "s"}`}
        </h2>
        <p className="mt-1 text-[13px] text-zinc-500">
          {count === 0
            ? "Nothing matched automatically. Draw boxes over anything you want removed."
            : `${chosen} selected for redaction${p.manual.length ? ` · ${p.manual.length} manual` : ""}`}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {groups.map(([cat, items]) => {
          const Icon = CATEGORY_ICON[cat];
          const allOn = items.every((d) => p.selected.has(d.id));
          return (
            <section key={cat} className="border-b border-zinc-100 px-2 py-2">
              <div className="flex items-center justify-between px-3 py-1.5">
                <h3 className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-zinc-400 uppercase">
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                  {CATEGORY_META[cat].label}
                  <span className="text-zinc-300">{items.length}</span>
                </h3>
                {items.length > 1 && (
                  <button
                    type="button"
                    onClick={() => p.onToggleMany(items.map((d) => d.id), !allOn)}
                    className="rounded px-1.5 py-0.5 text-[11px] text-zinc-400 transition-colors hover:text-ink"
                  >
                    {allOn ? "Keep all" : "Redact all"}
                  </button>
                )}
              </div>
              <ul>
                {items.map((d) => {
                  const on = p.selected.has(d.id);
                  return (
                    <li key={d.id}>
                      <div
                        role="button"
                        tabIndex={0}
                        onMouseEnter={() => p.onHover(d.id)}
                        onMouseLeave={() => p.onHover(null)}
                        onFocus={() => p.onHover(d.id)}
                        onBlur={() => p.onHover(null)}
                        onClick={() => p.onFocus(d)}
                        onKeyDown={(e) => {
                          if (e.key === " " || e.key === "Enter") {
                            e.preventDefault();
                            p.onToggle(d.id, !on);
                          }
                        }}
                        aria-label={`${d.label} ${d.preview}. ${on ? "Will be redacted" : "Kept"}. Press space to toggle.`}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors duration-100 ${
                          p.hovered === d.id ? "bg-zinc-50" : ""
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className={`truncate font-mono text-[12.5px] ${on ? "text-ink" : "text-zinc-400 line-through decoration-zinc-300"}`}>
                            {d.preview}
                          </p>
                          <p className="mt-0.5 truncate text-[12px] text-zinc-500">
                            {d.label}
                            {p.multiPage && <span className="text-zinc-400"> · p.{d.page + 1}</span>}
                            {d.confidence < 0.6 ? (
                              <span className="text-amber-600"> · uncertain</span>
                            ) : (
                              <span className="text-zinc-400"> · {Math.round(d.confidence * 100)}%</span>
                            )}
                          </p>
                        </div>
                        <Switch checked={on} onChange={(v) => p.onToggle(d.id, v)} label={`Redact ${d.label}`} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}

        {p.manual.length > 0 && (
          <section className="border-b border-zinc-100 px-2 py-2">
            <h3 className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-medium tracking-wider text-zinc-400 uppercase">
              <Square className="h-3.5 w-3.5" strokeWidth={1.75} />
              Manual redactions
              <span className="text-zinc-300">{p.manual.length}</span>
            </h3>
            <ul>
              {p.manual.map((m, i) => (
                <li key={m.id} className="flex items-center gap-3 rounded-lg px-3 py-1.5 hover:bg-zinc-50">
                  <button type="button" onClick={() => p.onFocusManual(m)} className="flex-1 text-left text-[13px] text-zinc-600">
                    Area {i + 1}
                    {p.multiPage && <span className="text-zinc-400"> · p.{m.page + 1}</span>}
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove area ${i + 1}`}
                    onClick={() => p.onRemoveManual(m.id)}
                    className="rounded p-1 text-zinc-400 transition-colors hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {p.metadata.length > 0 && (
          <section className="px-5 py-4">
            <h3 className="text-[11px] font-medium tracking-wider text-zinc-400 uppercase">Hidden metadata</h3>
            <p className="mt-1 text-[12px] text-zinc-500">Always removed from the exported file.</p>
            <dl className="mt-3 space-y-1.5">
              {p.metadata.map((m, i) => (
                <div key={`${m.key}-${i}`} className="flex items-baseline justify-between gap-3 text-[12.5px]">
                  <dt className="text-zinc-500">{m.label}</dt>
                  <dd className="truncate font-mono text-[12px] text-zinc-700 line-through decoration-zinc-300">{m.value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {p.notes.map((n) => (
          <p key={n} className="mx-5 my-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            {n}
          </p>
        ))}
      </div>

      <div className="space-y-3 border-t border-zinc-100 px-5 py-4">
        {p.isPdf && (
          <label className="flex cursor-pointer items-start justify-between gap-3">
            <span>
              <span className="block text-[13px] font-medium">Flatten pages</span>
              <span className="block text-[12px] leading-snug text-zinc-500">
                Convert pages to images. Strongest removal; text won't be selectable.
              </span>
            </span>
            <Switch checked={p.rasterize} onChange={p.onRasterize} label="Flatten pages to images" />
          </label>
        )}
        <p className="flex gap-2 text-[12px] leading-snug text-zinc-500">
          <ShieldAlert className="mt-px h-3.5 w-3.5 shrink-0 text-zinc-400" />
          These are possible matches, and automated scanning can miss things. Check the preview before
          sharing.
        </p>
      </div>
    </aside>
  );
}
