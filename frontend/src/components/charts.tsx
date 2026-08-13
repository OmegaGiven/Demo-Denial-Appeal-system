import { useId, useState } from "react";

/* ---------------------------------------------------------------------
 * Small chart primitives for the Phase 7 monitoring dashboard.
 *
 * Built as plain inline SVG/HTML per the dataviz skill rather than pulling
 * in a charting library (none is installed, and this dashboard's charts are
 * simple enough not to need one). Color usage follows the skill's
 * color-formula: sequential/ordinal for magnitude, categorical (fixed
 * 3-slot order, see index.css) for named-series identity, status tokens
 * for state, always paired with a label -- never color alone.
 * ------------------------------------------------------------------- */

export function StatTile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="card px-5 py-4">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight text-ink-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-500">{sub}</div>}
    </div>
  );
}

/* ------------------------------- Accuracy trend line chart ------------------------------- */

export interface TrendPoint {
  runAt: string;
  score: number;
  id: number;
}

export function AccuracyTrendChart({ points }: { points: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const gradId = useId();

  if (points.length === 0) {
    return <div className="py-10 text-center text-sm text-ink-500">No eval runs yet.</div>;
  }

  // Single-point case: nothing to draw a line between -- show one deliberate
  // dot plus a caption instead of a fake flat line, so it reads as "this is
  // the first data point" rather than a broken chart.
  if (points.length === 1) {
    const pct = Math.round(points[0].score * 100);
    return (
      <div className="flex items-center gap-5 py-6">
        <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-4 border-brand-500 bg-brand-50">
          <span className="text-lg font-semibold text-brand-700">{pct}%</span>
        </div>
        <div className="text-sm text-ink-600">
          <div className="font-medium text-ink-800">First eval run recorded.</div>
          <div className="mt-0.5 text-ink-500">
            {new Date(points[0].runAt).toLocaleString()} &mdash; this becomes the baseline for future
            regression checks. The trend line appears once a second run exists.
          </div>
        </div>
      </div>
    );
  }

  const width = 640;
  const height = 220;
  const padL = 42;
  const padR = 16;
  const padT = 16;
  const padB = 30;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const minScore = Math.min(...points.map((p) => p.score), 0.7);
  const maxScore = 1.0;
  const yFor = (s: number) => padT + plotH * (1 - (s - minScore) / (maxScore - minScore || 1));
  const xFor = (i: number) => padL + (points.length === 1 ? plotW / 2 : (plotW * i) / (points.length - 1));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i)} ${yFor(p.score)}`).join(" ");
  const areaPath = `${linePath} L ${xFor(points.length - 1)} ${padT + plotH} L ${xFor(0)} ${padT + plotH} Z`;

  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((t) => minScore + (maxScore - minScore) * t);

  // All runs so far happened on the same calendar day in this demo dataset
  // -- fall back to a time-of-day label in that case so the x-axis doesn't
  // show three identical "Aug 12" ticks.
  const sameDay = new Set(points.map((p) => new Date(p.runAt).toDateString())).size === 1;
  const xLabel = (iso: string) =>
    sameDay
      ? new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
      : new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Eval accuracy over time">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-brand-500)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--color-brand-500)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* gridlines -- recessive, hairline */}
        {gridLines.map((s) => (
          <g key={s}>
            <line
              x1={padL}
              x2={width - padR}
              y1={yFor(s)}
              y2={yFor(s)}
              stroke="var(--color-ink-200)"
              strokeWidth={1}
            />
            <text x={padL - 8} y={yFor(s) + 3} textAnchor="end" className="fill-ink-400 text-[10px]">
              {Math.round(s * 100)}%
            </text>
          </g>
        ))}

        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke="var(--color-brand-500)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {points.map((p, i) => (
          <g
            key={p.id}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
            onFocus={() => setHover(i)}
            onBlur={() => setHover((h) => (h === i ? null : h))}
            tabIndex={0}
            className="cursor-pointer outline-none"
          >
            {/* generous invisible hit target, per interaction.md */}
            <circle cx={xFor(i)} cy={yFor(p.score)} r={14} fill="transparent" />
            <circle
              cx={xFor(i)}
              cy={yFor(p.score)}
              r={hover === i ? 6 : 4.5}
              fill="var(--color-brand-500)"
              stroke="var(--color-surface)"
              strokeWidth={2}
              className="transition-[r] duration-100"
            />
          </g>
        ))}

        {points.map((p, i) => (
          <text key={p.id} x={xFor(i)} y={height - 8} textAnchor="middle" className="fill-ink-400 text-[10px]">
            {xLabel(p.runAt)}
          </text>
        ))}
      </svg>

      {hover !== null && (
        <div
          className="pointer-events-none absolute rounded-md border border-ink-200 bg-surface px-2.5 py-1.5 text-xs shadow-card"
          style={{
            left: `${(xFor(hover) / width) * 100}%`,
            top: `${(yFor(points[hover].score) / height) * 100}%`,
            transform: "translate(-50%, -130%)",
          }}
        >
          <div className="font-semibold text-ink-900">{(points[hover].score * 100).toFixed(1)}%</div>
          <div className="text-ink-500">{new Date(points[hover].runAt).toLocaleString()}</div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------- Single-hue magnitude bar rows ------------------------------- */

export function MagnitudeBarRow({
  label,
  value,
  formatted,
}: {
  label: string;
  value: number; // 0..1
  formatted: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="text-ink-700">{label}</span>
        <span className="font-semibold tabular-nums text-ink-900">{formatted}</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-ink-100">
        <div
          className="h-full rounded-full bg-brand-500 transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ------------------------------- Confidence histogram (ordinal ramp) ------------------------------- */

// References the --color-ordinal-1..4 tokens (index.css @theme + .dark
// block) rather than bg-brand-400/500/700/900 directly -- the brand
// scale's own dark end is too dark to read against a dark card, so the
// dark-mode-validated ordinal ramp lives on its own token names.
const ORDINAL_STEPS = [
  "bg-[var(--color-ordinal-1)]",
  "bg-[var(--color-ordinal-2)]",
  "bg-[var(--color-ordinal-3)]",
  "bg-[var(--color-ordinal-4)]",
];

export function ConfidenceHistogram({
  buckets,
}: {
  buckets: { label: string; count: number; max_confidence: number }[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = buckets.reduce((s, b) => s + b.count, 0);
  const max = Math.max(...buckets.map((b) => b.count), 1);

  // The 0.7 threshold is the pipeline's real needs_review routing cutoff
  // (see backend/pipeline/run.py / README "Phase 4"), which happens to sit
  // exactly on the boundary between the 2nd and 3rd bucket given how the
  // buckets are defined -- draw it as a real reference line, not a color.
  const thresholdIndex = buckets.findIndex((b) => b.max_confidence === 0.7);

  return (
    <div>
      <div className="relative flex items-end gap-4 pb-8" style={{ height: 180 }}>
        {thresholdIndex >= 0 && thresholdIndex < buckets.length - 1 && (
          <div
            className="pointer-events-none absolute top-0 bottom-8 border-l-2 border-dashed border-status-needs_review"
            style={{ left: `${((thresholdIndex + 1) / buckets.length) * 100}%` }}
          >
            <span className="absolute -top-1 left-1.5 whitespace-nowrap text-[10px] font-medium text-status-needs_review-fg">
              0.70 needs_review threshold
            </span>
          </div>
        )}
        {buckets.map((b, i) => {
          const h = total === 0 ? 0 : (b.count / max) * 130;
          return (
            <div key={b.label} className="relative flex flex-1 flex-col items-center">
              <div
                className="relative flex w-full max-w-14 flex-col items-center justify-end"
                style={{ height: 130 }}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover((h2) => (h2 === i ? null : h2))}
              >
                {hover === i && (
                  <div className="pointer-events-none absolute -top-8 rounded-md border border-ink-200 bg-surface px-2 py-1 text-xs font-semibold text-ink-900 shadow-card">
                    {b.count} denial{b.count === 1 ? "" : "s"}
                  </div>
                )}
                <div
                  className={`w-full rounded-t-[4px] ${ORDINAL_STEPS[i] ?? "bg-brand-500"} transition-[height] duration-500`}
                  style={{ height: `${h}px` }}
                />
              </div>
              <div className="mt-2 text-[11px] font-medium tabular-nums text-ink-600">{b.count}</div>
              <div className="text-[10px] text-ink-400">{b.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------- Small comparison bar chart (categorical identity) ------------------------------- */

const CAT_CLASSES = ["bg-brand-500", "bg-viz-amber", "bg-viz-teal"];

export function ComparisonBarChart({
  items,
}: {
  items: { label: string; value: number; formatted: string }[];
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={item.label} className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 w-44 shrink-0 text-xs text-ink-600" title={item.label}>
            <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${CAT_CLASSES[i % CAT_CLASSES.length]}`} />
            <span className="truncate">{item.label}</span>
          </div>
          <div className="h-5 flex-1 overflow-hidden rounded-[4px] bg-ink-100">
            <div
              className={`h-full rounded-[4px] ${CAT_CLASSES[i % CAT_CLASSES.length]} transition-[width] duration-500`}
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
          <div className="w-24 shrink-0 text-right text-xs font-semibold tabular-nums text-ink-900">
            {item.formatted}
          </div>
        </div>
      ))}
    </div>
  );
}
