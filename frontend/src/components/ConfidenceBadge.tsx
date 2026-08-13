function bandFor(confidence: number): { label: string; color: string; barColor: string } {
  if (confidence >= 0.85) {
    return { label: "High confidence", color: "text-confidence-high", barColor: "bg-confidence-high" };
  }
  if (confidence >= 0.6) {
    return { label: "Moderate confidence", color: "text-confidence-mid", barColor: "bg-confidence-mid" };
  }
  return { label: "Low confidence — needs attention", color: "text-confidence-low", barColor: "bg-confidence-low" };
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const { label, color, barColor } = bandFor(confidence);
  const pct = Math.round(confidence * 100);
  return (
    <div className="w-full max-w-xs">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className={`font-medium ${color}`}>{label}</span>
        <span className="text-ink-500 tabular-nums">{pct}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-ink-100 overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
