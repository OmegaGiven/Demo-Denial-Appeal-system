export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="card divide-y divide-ink-100 overflow-hidden">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4 animate-pulse">
          <div className="h-5 w-24 rounded-full bg-ink-100" />
          <div className="h-4 w-28 rounded bg-ink-100" />
          <div className="h-4 flex-1 rounded bg-ink-100" />
          <div className="h-4 w-24 rounded bg-ink-100" />
        </div>
      ))}
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-pulse">
      <div className="card p-6 space-y-3">
        <div className="h-5 w-1/3 rounded bg-ink-100" />
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-ink-100" style={{ width: `${80 - i * 3}%` }} />
        ))}
      </div>
      <div className="card p-6 space-y-3">
        <div className="h-5 w-1/3 rounded bg-ink-100" />
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-ink-100" style={{ width: `${75 - i * 2}%` }} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-status-rejected-bg text-status-rejected-fg">
        <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
            clipRule="evenodd"
          />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-ink-800">{title}</h3>
      <p className="max-w-md text-sm text-ink-500">{message}</p>
      {onRetry && (
        <button className="btn-secondary mt-2" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-ink-100 text-ink-400">
        <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" />
          <path
            fillRule="evenodd"
            d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h2a1 1 0 110 2H5a1 1 0 01-1-1z"
            clipRule="evenodd"
          />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-ink-800">{title}</h3>
      <p className="max-w-md text-sm text-ink-500">{message}</p>
    </div>
  );
}
