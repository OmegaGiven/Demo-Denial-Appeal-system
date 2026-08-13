function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return String(value);
  return String(value);
}

export function KeyValueGrid({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields);
  if (entries.length === 0) {
    return <p className="text-sm text-ink-400">No extracted fields.</p>;
  }
  return (
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
      {entries.map(([key, value]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">
            {humanizeKey(key)}
          </dt>
          <dd className="mt-0.5 truncate text-sm font-medium text-ink-800" title={formatValue(value)}>
            {formatValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
