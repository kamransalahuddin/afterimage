import { useCallback, useRef, useState } from "react";
import { Logo } from "./components/ui";
import { SCANNING, Voxels } from "./components/Voxels";
import { ApiError, analyzeFile } from "./lib/api";
import type { Analysis, RedactResult } from "./lib/types";
import { Landing } from "./pages/Landing";
import { Recipient } from "./pages/Recipient";
import { Result } from "./pages/Result";
import { Workspace, type WorkspaceSeed } from "./pages/Workspace";

type Stage =
  | { name: "landing"; error: string | null }
  | { name: "analyzing"; file: File; progress: number }
  | { name: "workspace"; file: File; analysis: Analysis; seed?: WorkspaceSeed }
  | { name: "result"; file: File; analysis: Analysis; result: RedactResult; seed: WorkspaceSeed };

export default function App() {
  if (window.location.pathname.startsWith("/s")) return <Recipient />;
  return <Editor />;
}

function Editor() {
  const [stage, setStage] = useState<Stage>({ name: "landing", error: null });
  const [previews, setPreviews] = useState<Record<number, string>>({});
  const run = useRef(0);

  const clearPreviews = () =>
    setPreviews((p) => {
      Object.values(p).forEach(URL.revokeObjectURL);
      return {};
    });

  const start = useCallback(async (file: File, seed?: WorkspaceSeed) => {
    const id = ++run.current;
    clearPreviews();
    setStage({ name: "analyzing", file, progress: 0 });
    try {
      const analysis = await analyzeFile(file, (progress) => {
        if (run.current === id) setStage({ name: "analyzing", file, progress });
      });
      if (run.current === id) setStage({ name: "workspace", file, analysis, seed });
    } catch (e) {
      if (run.current === id)
        setStage({ name: "landing", error: e instanceof ApiError ? e.message : "The file could not be processed." });
    }
  }, []);

  const home = () => {
    run.current++;
    clearPreviews();
    setStage({ name: "landing", error: null });
  };

  const setPreview = useCallback((page: number, url: string) => setPreviews((p) => ({ ...p, [page]: url })), []);

  switch (stage.name) {
    case "landing":
      return <Landing onFile={(f) => start(f)} error={stage.error} />;
    case "analyzing":
      return <Analyzing file={stage.file} progress={stage.progress} onCancel={home} />;
    case "workspace":
      return (
        <Workspace
          key={stage.analysis.session_id}
          analysis={stage.analysis}
          previews={previews}
          setPreview={setPreview}
          seed={stage.seed}
          onExit={home}
          onRedacted={(result, seed) => setStage({ name: "result", file: stage.file, analysis: stage.analysis, result, seed })}
        />
      );
    case "result":
      return (
        <Result
          analysis={stage.analysis}
          result={stage.result}
          before={previews}
          onNew={home}
          onEdit={() => start(stage.file, stage.seed)}
        />
      );
  }
}

function Analyzing({ file, progress, onCancel }: { file: File; progress: number; onCancel: () => void }) {
  const uploading = progress < 1;
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
        <Logo onClick={onCancel} />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-32 animate-fade" aria-live="polite">
        <Voxels voxels={SCANNING} size={10} pulse className="h-20 w-auto" />
        <p className="mt-10 text-[15px] font-medium">{uploading ? "Uploading securely" : "Scanning for sensitive information"}</p>
        <p className="mt-1.5 max-w-xs truncate text-[13px] text-zinc-500">{file.name}</p>
        <div className="mt-6 h-1 w-56 overflow-hidden rounded-full bg-zinc-100" role="progressbar" aria-label="Progress" aria-valuenow={uploading ? Math.round(progress * 100) : undefined}>
          {uploading ? (
            <div className="h-full rounded-full bg-ink transition-[width] duration-200" style={{ width: `${Math.max(4, progress * 100)}%` }} />
          ) : (
            <div className="h-full w-1/3 animate-[scan_1.2s_ease-in-out_infinite] rounded-full bg-accent" />
          )}
        </div>
        <p className="mt-6 text-[12px] text-zinc-400">
          {uploading ? `${Math.round(progress * 100)}%` : "Reading text, checking patterns, looking for faces"}
        </p>
        <button type="button" onClick={onCancel} className="mt-10 text-[13px] text-zinc-500 hover:text-ink">
          Cancel
        </button>
      </main>
      <style>{`@keyframes scan { 0% { transform: translateX(-100%); } 100% { transform: translateX(300%); } }`}</style>
    </div>
  );
}
