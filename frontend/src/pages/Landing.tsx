import { Lock } from "lucide-react";
import { Dropzone } from "../components/Dropzone";
import { GitHubIcon, Logo } from "../components/ui";
import { HERO, STEPS, Voxels } from "../components/Voxels";

const GITHUB_URL = import.meta.env.VITE_GITHUB_URL || "https://github.com/kamransalahuddin";

const STEP_COPY: { key: keyof typeof STEPS; title: string; body: string }[] = [
  { key: "upload", title: "Upload", body: "Drop in a screenshot, photo or PDF. It's encrypted as soon as it's uploaded." },
  { key: "detect", title: "Detect", body: "Text recognition, pattern checks and face detection flag anything that looks private." },
  { key: "review", title: "Review", body: "Turn each finding on or off, and draw boxes over anything that was missed." },
  { key: "redact", title: "Redact", body: "The selected text and pixels are deleted from the file, and metadata is removed." },
  { key: "share", title: "Share", body: "Send a link that expires, has a download limit, and can be turned off." },
];

const SAMPLES = [
  { file: "screenshot.png", type: "image/png", label: "screenshot" },
  { file: "record.pdf", type: "application/pdf", label: "PDF" },
  { file: "photo-with-gps.jpg", type: "image/jpeg", label: "photo with GPS" },
];

async function loadSample(file: string, type: string, onFile: (f: File) => void) {
  const res = await fetch(`/samples/${file}`);
  onFile(new File([await res.blob()], file, { type }));
}

export function Landing({ onFile, error }: { onFile: (f: File) => void; error: string | null }) {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Logo />
        <nav className="flex items-center gap-1 text-[13px] text-zinc-600">
          <a href="#how" className="rounded-md px-3 py-1.5 transition-colors hover:text-ink">
            How it works
          </a>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors hover:text-ink"
          >
            <GitHubIcon className="h-3.5 w-3.5" />
            GitHub
          </a>
        </nav>
      </header>

      <main>
        <section className="mx-auto flex max-w-2xl flex-col items-center px-6 pt-14 pb-24 text-center sm:pt-20">
          <Voxels voxels={HERO} size={9} className="voxel-float mb-10 h-24 w-auto sm:h-28" title="A document whose sensitive line lifts away" />
          <h1 className="text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-ink sm:text-[56px]">
            Redact files before you share them
          </h1>
          <p className="mt-5 max-w-md text-[17px] leading-relaxed text-zinc-500">
            Upload a screenshot or PDF. AFTERIMAGE finds things like emails, card numbers, API keys and faces, and you choose what to remove.
          </p>
          <div className="mt-12 w-full">
            <Dropzone onFile={onFile} error={error} />
          </div>
          <p className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500">
            <Lock className="h-3.5 w-3.5" strokeWidth={2} />
            Files are processed on this server and never sent to outside AI services.
          </p>
          <p className="mt-3 text-[12px] text-zinc-400">
            Or try a sample file with fake data:{" "}
            {SAMPLES.map((s, i) => (
              <span key={s.file}>
                {i > 0 && (i === SAMPLES.length - 1 ? " or " : ", ")}
                <button type="button" onClick={() => loadSample(s.file, s.type, onFile)} className="text-zinc-600 underline decoration-zinc-300 underline-offset-2 hover:text-ink">
                  {s.label}
                </button>
              </span>
            ))}
            .
          </p>
        </section>

        <section id="how" className="scroll-mt-8 border-t border-zinc-100 bg-zinc-50/50">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <div className="max-w-md">
              <h2 className="text-2xl font-semibold tracking-[-0.02em]">What happens to your file</h2>
              <p className="mt-3 text-[15px] leading-relaxed text-zinc-500">
                Drawing a black box over a PDF often leaves the text underneath, where anyone can copy it. AFTERIMAGE
                makes a new file with that text and those pixels removed.
              </p>
            </div>
            <ol className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-200 sm:grid-cols-2 lg:grid-cols-5">
              {STEP_COPY.map((s, i) => (
                <li key={s.key} className="flex flex-col bg-white p-6">
                  <Voxels voxels={STEPS[s.key]} size={7} className="mb-6 h-12 w-auto self-start" />
                  <p className="text-[11px] font-medium tracking-wider text-zinc-400">0{i + 1}</p>
                  <h3 className="mt-1 text-[15px] font-semibold">{s.title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-zinc-500">{s.body}</p>
                </li>
              ))}
            </ol>
            <div className="mt-12 grid gap-8 text-[13px] leading-relaxed text-zinc-500 sm:grid-cols-3">
              <p>
                <span className="font-medium text-ink">No account needed.</span> Detection runs on this server with local
                models. Files are not sent to third-party AI services.
              </p>
              <p>
                <span className="font-medium text-ink">Encrypted storage.</span> Each file is encrypted with AES-256-GCM and
                its own key. The original is deleted after redaction.
              </p>
              <p>
                <span className="font-medium text-ink">Check the result.</span> Automated scanning can miss things, so look
                over the preview before you share it.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl items-center justify-between px-6 py-8 text-xs text-zinc-400">
        <span>AFTERIMAGE</span>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer noopener" className="hover:text-ink">
          Source
        </a>
      </footer>
    </div>
  );
}
