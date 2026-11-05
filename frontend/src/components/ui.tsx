import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LOGO, Voxels } from "./Voxels";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-zinc-800 disabled:bg-zinc-300",
  secondary: "bg-white text-ink border border-zinc-200 hover:bg-zinc-50 hover:border-zinc-300 disabled:text-zinc-400",
  ghost: "text-zinc-600 hover:text-ink hover:bg-zinc-100 disabled:text-zinc-300",
  danger: "text-red-600 hover:bg-red-50 disabled:text-red-300",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-8 px-2.5 text-[13px] gap-1.5", md: "h-9 px-3.5 text-sm gap-2", lg: "h-11 px-5 text-sm gap-2" };
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors duration-150 disabled:cursor-not-allowed select-none ${sizes[size]} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className={`relative inline-flex h-[18px] w-8 shrink-0 items-center rounded-full transition-colors duration-150 ${
        checked ? "bg-accent" : "bg-zinc-200 hover:bg-zinc-300"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-150 ${
          checked ? "translate-x-[16px]" : "translate-x-[2px]"
        }`}
      />
    </button>
  );
}

export function Segmented<T extends string | number | null>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid auto-cols-fr grid-flow-col rounded-lg bg-zinc-100 p-0.5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`h-8 rounded-md text-[13px] font-medium transition-all duration-150 ${
            o.value === value ? "bg-white text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]" : "text-zinc-500 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ onClick, compact }: { onClick?: () => void; compact?: boolean }) {
  return (
    <a
      href="/"
      onClick={(e) => {
        if (onClick) {
          e.preventDefault();
          onClick();
        }
      }}
      className="group inline-flex items-center gap-2.5 rounded-md"
      aria-label="AFTERIMAGE home"
    >
      <Voxels voxels={LOGO} size={7} className="h-6 w-6" />
      {!compact && <span className="text-[13px] font-semibold tracking-[0.18em] text-ink">AFTERIMAGE</span>}
    </a>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="ml-1 hidden rounded border border-zinc-200 px-1 font-sans text-[10px] font-medium text-zinc-400 lg:inline">
      {children}
    </kbd>
  );
}

export function GitHubIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
