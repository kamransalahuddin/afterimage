import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, ClipboardPaste } from "lucide-react";

const ACCEPT = ["image/png", "image/jpeg", "image/webp", "application/pdf"];
const EXT = /\.(png|jpe?g|webp|pdf)$/i;
export const MAX_MB = 20;

export function checkFile(file: File): string | null {
  if (!ACCEPT.includes(file.type) && !EXT.test(file.name)) return "Unsupported file. Use PNG, JPG, WEBP or PDF.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_MB * 1024 * 1024) return `Files must be ${MAX_MB} MB or smaller.`;
  return null;
}

export function Dropzone({ onFile, error }: { onFile: (f: File) => void; error?: string | null }) {
  const [over, setOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);

  const take = useCallback(
    (file: File | undefined | null) => {
      if (!file) return;
      const problem = checkFile(file);
      setLocalError(problem);
      if (!problem) onFile(file);
    },
    [onFile],
  );

  // Paste a screenshot from anywhere on the page.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = [...(e.clipboardData?.items ?? [])].find((i) => i.kind === "file");
      const file = item?.getAsFile();
      if (!file) return;
      e.preventDefault();
      const ext = file.type.split("/")[1] ?? "png";
      take(new File([file], file.name && file.name !== "image.png" ? file.name : `pasted-screenshot.${ext}`, { type: file.type }));
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [take]);

  const shown = localError ?? error;
  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a file. Drop a file here, press Enter to browse, or paste a screenshot."
        aria-describedby="dropzone-help"
        onClick={() => input.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            input.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          depth.current += 1;
          setOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => {
          depth.current -= 1;
          if (depth.current <= 0) setOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          depth.current = 0;
          setOver(false);
          take(e.dataTransfer.files?.[0]);
        }}
        className={`group relative flex h-64 w-full cursor-pointer flex-col items-center justify-center rounded-2xl border transition-all duration-200 sm:h-72 ${
          over
            ? "border-accent bg-accent-soft/60 shadow-[0_0_0_4px_rgba(79,70,229,0.08)]"
            : "border-zinc-200 bg-zinc-50/40 hover:border-zinc-300 hover:bg-zinc-50"
        }`}
      >
        <div
          className={`mb-5 flex h-10 w-10 items-center justify-center rounded-full border bg-white transition-all duration-200 ${
            over ? "-translate-y-0.5 border-accent text-accent" : "border-zinc-200 text-zinc-500 group-hover:text-ink"
          }`}
        >
          <ArrowUp className="h-4 w-4" strokeWidth={2} />
        </div>
        <p className="text-[15px] font-medium text-ink">{over ? "Release to scan" : "Drop a file, or click to browse"}</p>
        <p id="dropzone-help" className="mt-1.5 text-[13px] text-zinc-500">
          PNG, JPG, WEBP or PDF · up to {MAX_MB} MB
        </p>
        <p className="mt-5 inline-flex items-center gap-1.5 text-xs text-zinc-400">
          <ClipboardPaste className="h-3.5 w-3.5" />
          Or paste a screenshot with{" "}
          <kbd className="rounded border border-zinc-200 bg-white px-1 font-sans text-[11px] text-zinc-500">
            {isMac ? "⌘" : "Ctrl"} V
          </kbd>
        </p>
        <input
          ref={input}
          type="file"
          className="hidden"
          accept=".png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf"
          onChange={(e) => {
            take(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      <div aria-live="polite" className="min-h-6 pt-3 text-center text-[13px] text-red-600">
        {shown}
      </div>
    </div>
  );
}
