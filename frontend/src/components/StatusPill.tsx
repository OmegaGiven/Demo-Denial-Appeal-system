const STATUS_LABEL: Record<string, string> = {
  new: "New",
  processing: "Processing",
  classified: "Classified",
  appeal_drafted: "Appeal Drafted",
  needs_review: "Needs Review",
  closed: "Closed",
  draft: "Draft",
  approved: "Approved",
  rejected: "Rejected",
  sent: "Sent",
};

// Tailwind can't see dynamically-built class names at build time, so the
// status -> class mapping is spelled out explicitly rather than
// interpolated (`bg-status-${status}-bg` would be purged).
const STATUS_CLASSES: Record<string, string> = {
  new: "bg-status-new-bg text-status-new-fg",
  processing: "bg-status-processing-bg text-status-processing-fg",
  classified: "bg-status-classified-bg text-status-classified-fg",
  appeal_drafted: "bg-status-appeal_drafted-bg text-status-appeal_drafted-fg",
  needs_review: "bg-status-needs_review-bg text-status-needs_review-fg",
  closed: "bg-ink-100 text-ink-600",
  draft: "bg-status-new-bg text-status-new-fg",
  approved: "bg-status-approved-bg text-status-approved-fg",
  rejected: "bg-status-rejected-bg text-status-rejected-fg",
  sent: "bg-status-sent-bg text-status-sent-fg",
};

export function StatusPill({ status }: { status: string }) {
  const cls = STATUS_CLASSES[status] ?? "bg-ink-100 text-ink-600";
  const label = STATUS_LABEL[status] ?? status;
  return (
    <span
      className={`inline-flex items-center rounded-[var(--radius-pill)] px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {status === "needs_review" && (
        <svg className="mr-1 h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.72-1.36 3.486 0l6.28 11.16c.75 1.334-.213 2.99-1.743 2.99H3.72c-1.53 0-2.493-1.656-1.743-2.99l6.28-11.16zM11 13a1 1 0 10-2 0 1 1 0 002 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z"
            clipRule="evenodd"
          />
        </svg>
      )}
      {label}
    </span>
  );
}
