/**
 * A tiny isometric voxel renderer. Scenes are plain arrays of cubes; faces
 * hidden by neighbours are culled and the rest painted back-to-front.
 */
import { useMemo } from "react";

export type Material = "paper" | "stone" | "ink" | "accent";

export interface Voxel {
  x: number;
  y: number;
  z: number;
  m: Material;
  o?: number; // opacity
  g?: number; // optional group index (for staggered animation)
}

const PALETTE: Record<Material, [top: string, left: string, right: string]> = {
  paper: ["#fafafa", "#e4e4e7", "#d4d4d8"],
  stone: ["#d4d4d8", "#a1a1aa", "#8a8a93"],
  ink: ["#3f3f46", "#18181b", "#0b0b0f"],
  accent: ["#a5b4fc", "#6366f1", "#4338ca"],
};

const COS30 = Math.sqrt(3) / 2;

interface Props {
  voxels: Voxel[];
  size?: number;
  className?: string;
  title?: string;
  pulse?: boolean;
}

export function Voxels({ voxels, size = 10, className, title, pulse }: Props) {
  const { faces, viewBox } = useMemo(() => build(voxels, size), [voxels, size]);
  return (
    <svg
      viewBox={viewBox}
      className={`${className ?? ""} ${pulse ? "voxel-pulse" : ""}`}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      shapeRendering="geometricPrecision"
    >
      {title && <title>{title}</title>}
      {faces.map((group, i) => (
        <g key={i} opacity={group.o} style={pulse ? { animationDelay: `${(group.g ?? 0) * 0.12}s` } : undefined}>
          {group.paths.map((p, j) => (
            <path key={j} d={p.d} fill={p.fill} stroke={p.fill} strokeWidth={0.6} strokeLinejoin="round" />
          ))}
        </g>
      ))}
    </svg>
  );
}

function build(voxels: Voxel[], s: number) {
  const a = s * COS30;
  const occupied = new Set(voxels.filter((v) => (v.o ?? 1) >= 1).map((v) => `${v.x},${v.y},${v.z}`));
  const has = (x: number, y: number, z: number) => occupied.has(`${x},${y},${z}`);
  const sorted = [...voxels].sort((p, q) => p.x + p.y - (q.x + q.y) || p.z - q.z || p.x - q.x);

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const faces = sorted.map((v) => {
    const px = (v.x - v.y) * a;
    const py = (v.x + v.y) * (s / 2) - v.z * s;
    minX = Math.min(minX, px - a);
    maxX = Math.max(maxX, px + a);
    minY = Math.min(minY, py);
    maxY = Math.max(maxY, py + 2 * s);
    const [top, left, right] = PALETTE[v.m];
    const solid = (v.o ?? 1) >= 1;
    const pt = (x: number, y: number) => `${x.toFixed(2)},${y.toFixed(2)}`;
    const paths: { d: string; fill: string }[] = [];
    if (!solid || !has(v.x, v.y + 1, v.z))
      paths.push({ fill: left, d: `M${pt(px - a, py + s / 2)}L${pt(px, py + s)}L${pt(px, py + 2 * s)}L${pt(px - a, py + 1.5 * s)}Z` });
    if (!solid || !has(v.x + 1, v.y, v.z))
      paths.push({ fill: right, d: `M${pt(px, py + s)}L${pt(px + a, py + s / 2)}L${pt(px + a, py + 1.5 * s)}L${pt(px, py + 2 * s)}Z` });
    if (!solid || !has(v.x, v.y, v.z + 1))
      paths.push({ fill: top, d: `M${pt(px, py)}L${pt(px + a, py + s / 2)}L${pt(px, py + s)}L${pt(px - a, py + s / 2)}Z` });
    return { paths, o: v.o, g: v.g };
  });
  const pad = 1;
  return {
    faces,
    viewBox: `${(minX - pad).toFixed(1)} ${(minY - pad).toFixed(1)} ${(maxX - minX + 2 * pad).toFixed(1)} ${(maxY - minY + 2 * pad).toFixed(1)}`,
  };
}

/* ------------------------------------------------------------------ scenes */

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

function slab(w: number, d: number, m: Material = "paper"): Voxel[] {
  return range(w).flatMap((x) => range(d).map((y) => ({ x, y, z: 0, m })));
}

function row(y: number, x0: number, x1: number, m: Material, z = 1, o?: number): Voxel[] {
  return range(x1 - x0).map((i) => ({ x: x0 + i, y, z, m, o }));
}

/** Logo: a block whose top corner has lifted away. */
export const LOGO: Voxel[] = [
  { x: 0, y: 0, z: 0, m: "paper" },
  { x: 1, y: 0, z: 0, m: "paper" },
  { x: 0, y: 1, z: 0, m: "paper" },
  { x: 1, y: 1, z: 0, m: "paper" },
  { x: 0, y: 1, z: 1, m: "stone" },
  { x: 1, y: 1, z: 1, m: "stone" },
  { x: 1, y: 0, z: 1, m: "stone" },
  { x: 0, y: 0, z: 2.35, m: "accent" },
];

/** Hero: a document whose sensitive line lifts out and fades — an afterimage. */
export const HERO: Voxel[] = [
  ...slab(9, 7),
  ...row(1, 1, 7, "stone"),
  ...row(3, 1, 5, "ink"),
  ...row(3, 6, 8, "stone"),
  ...row(5, 1, 6, "stone"),
  ...row(3, 1, 5, "accent", 3.2, 0.55),
  ...row(3, 1, 5, "accent", 5.2, 0.22),
];

export const STEPS: Record<"upload" | "detect" | "review" | "redact" | "share", Voxel[]> = {
  upload: [...slab(3, 3), { x: 1, y: 1, z: 1, m: "stone" }, { x: 1, y: 1, z: 2.4, m: "accent" }],
  detect: [...slab(3, 3), ...row(0, 0, 3, "stone"), ...row(2, 0, 2, "accent")],
  review: [...slab(3, 3), ...row(0, 0, 3, "stone"), ...row(2, 0, 2, "accent", 1, 0.45), { x: 2, y: 2, z: 1, m: "stone" }],
  redact: [...slab(3, 3), ...row(0, 0, 3, "stone"), ...row(2, 0, 3, "ink")],
  share: [...slab(2, 2), { x: 0, y: 0, z: 1, m: "stone" }, { x: 3, y: 1, z: 0, m: "accent" }, { x: 3, y: 0, z: 0, m: "accent", o: 0.5 }],
};

/** Gone: an empty outline of where something used to be. */
export const GONE: Voxel[] = [
  ...slab(3, 3, "paper"),
  { x: 1, y: 1, z: 1.6, m: "stone", o: 0.35 },
  { x: 1, y: 1, z: 3, m: "stone", o: 0.15 },
];

/** Scanning: a slab whose cells pulse in sequence. */
export const SCANNING: Voxel[] = range(4).flatMap((x) =>
  range(4).map((y) => ({ x, y, z: 0, m: (x + y) % 3 === 0 ? "accent" : "paper", g: x + y }) as Voxel),
);
