import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { StatusPill } from "../components/StatusPill";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { KeyValueGrid } from "../components/KeyValue";
import { DetailSkeleton, ErrorState, Spinner } from "../components/States";
import { Modal } from "../components/Modal";
import { CorrectionForm } from "../components/CorrectionForm";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function DetailView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCorrectionForm, setShowCorrectionForm] = useState(false);
  const [reviewerName, setReviewerName] = useState("");

  const denialQuery = useQuery({
    queryKey: ["denial", id],
    queryFn: () => api.getDenial(id!),
    enabled: !!id,
  });

  const processMutation = useMutation({
    mutationFn: () => api.processDenial(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["denial", id] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  const draftAppealMutation = useMutation({
    mutationFn: () => api.draftAppeal(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["denial", id] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  const appealStatusMutation = useMutation({
    mutationFn: (status: "approved" | "rejected") =>
      api.updateAppealStatus(id!, { status, reviewer: reviewerName || "reviewer@example.com" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["denial", id] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  if (denialQuery.isLoading) {
    return (
      <div>
        <BackLink />
        <DetailSkeleton />
      </div>
    );
  }

  if (denialQuery.isError) {
    return (
      <div>
        <BackLink />
        <ErrorState
          message={
            denialQuery.error instanceof ApiError
              ? denialQuery.error.message
              : "Failed to load this denial."
          }
          onRetry={() => denialQuery.refetch()}
        />
      </div>
    );
  }

  const denial = denialQuery.data!;
  const hasBeenProcessed = denial.status !== "new";
  const hasClassification = !!denial.classification;
  const hasAppeal = !!denial.appeal;
  // Only offer a standalone "Draft Appeal Letter" once there's a
  // classification to draft from and no appeal yet -- once an appeal
  // exists, "Reprocess with AI" already covers "regenerate everything
  // including the appeal", so showing both would be two buttons doing
  // overlapping things. This is also exactly the needs_review-after-a-
  // human-correction case this button exists for: a classification is on
  // record (possibly hand-corrected) but low original confidence meant the
  // pipeline never reached appeal drafting.
  const showDraftAppealButton = hasClassification && !hasAppeal;

  function handleProcessClick() {
    if (hasBeenProcessed) {
      const confirmed = window.confirm(
        "This denial already has AI results. Reprocessing will run a brand-new extraction, " +
          "classification, and appeal draft and replace what's shown here — including a " +
          "new appeal starting back at \"draft\" status, even if the current one was already " +
          "approved or rejected by a reviewer. Continue?"
      );
      if (!confirmed) return;
    }
    processMutation.mutate();
  }

  return (
    <div>
      <BackLink />

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{denial.claim_ref}</h1>
            <StatusPill status={denial.status} />
          </div>
          <p className="mt-1 text-sm text-ink-500">
            {denial.payer} · Received {formatDateTime(denial.received_at)} ·{" "}
            {denial.source_company.replace(/_/g, " ")}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {showDraftAppealButton && (
            <button
              className="btn-primary"
              disabled={draftAppealMutation.isPending || processMutation.isPending}
              onClick={() => draftAppealMutation.mutate()}
            >
              {draftAppealMutation.isPending ? (
                <>
                  <Spinner className="h-4 w-4" />
                  Drafting appeal…
                </>
              ) : (
                "Draft Appeal Letter"
              )}
            </button>
          )}

          <button
            className={showDraftAppealButton || hasBeenProcessed ? "btn-secondary" : "btn-primary"}
            disabled={processMutation.isPending || draftAppealMutation.isPending}
            onClick={handleProcessClick}
          >
            {processMutation.isPending ? (
              <>
                <Spinner className="h-4 w-4" />
                Processing (this can take 10-30s)…
              </>
            ) : hasBeenProcessed ? (
              <>
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path
                    fillRule="evenodd"
                    d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
                    clipRule="evenodd"
                  />
                </svg>
                Reprocess with AI
              </>
            ) : (
              "Process with AI"
            )}
          </button>
        </div>
      </div>

      {draftAppealMutation.isPending && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          <Spinner className="h-4 w-4 text-brand-600" />
          Drafting an appeal from the current classification (including any human
          correction on record) — extraction and classification are not rerun. This can
          take up to 30 seconds.
        </div>
      )}

      {draftAppealMutation.isError && (
        <div className="mb-6 rounded-lg border border-status-rejected/30 bg-status-rejected-bg px-4 py-3 text-sm text-status-rejected-fg">
          Appeal drafting failed: {(draftAppealMutation.error as Error).message}
        </div>
      )}

      {processMutation.isPending && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          <Spinner className="h-4 w-4 text-brand-600" />
          Running extraction, classification, and appeal drafting against the real Anthropic
          API. This can take up to 30 seconds — the page will update automatically.
        </div>
      )}

      {processMutation.isError && (
        <div className="mb-6 rounded-lg border border-status-rejected/30 bg-status-rejected-bg px-4 py-3 text-sm text-status-rejected-fg">
          Processing failed: {(processMutation.error as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: evidence panel */}
        <div className="card p-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
            Original Denial Letter
          </h2>
          <pre className="max-h-[600px] overflow-y-auto whitespace-pre-wrap rounded-md bg-ink-50 p-4 font-mono text-[13px] leading-relaxed text-ink-700 border border-ink-100">
            {denial.raw_text}
          </pre>
        </div>

        {/* Right: extraction + classification + appeal */}
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
              Extracted Fields
            </h2>
            {denial.extraction ? (
              <KeyValueGrid fields={denial.extraction.extracted_fields} />
            ) : (
              <p className="text-sm text-ink-400">Not yet processed.</p>
            )}
          </div>

          <div className="card p-6">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
              Classification
            </h2>
            {denial.classification ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-brand-50 px-2.5 py-1 text-sm font-semibold text-brand-700">
                    {denial.classification.category.replace(/_/g, " ")}
                  </span>
                </div>
                <ConfidenceBadge confidence={denial.classification.confidence} />
              </div>
            ) : (
              <p className="text-sm text-ink-400">Not yet classified.</p>
            )}
          </div>
        </div>
      </div>

      {/* Appeal draft — full width, paired below for side-by-side comparison */}
      <div className="mt-6 card p-6">
        <div className="mb-3 flex items-center justify-between flex-wrap gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Drafted Appeal Letter
          </h2>
          {denial.appeal && <StatusPill status={denial.appeal.status} />}
        </div>

        {denial.appeal ? (
          <>
            <pre className="max-h-[500px] overflow-y-auto whitespace-pre-wrap rounded-md bg-ink-50 p-4 font-mono text-[13px] leading-relaxed text-ink-700 border border-ink-100">
              {denial.appeal.draft_text}
            </pre>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <input
                className="input max-w-xs"
                placeholder="Your name / email (reviewer)"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
              />
              <button
                className="btn-success"
                disabled={appealStatusMutation.isPending || !reviewerName}
                onClick={() => appealStatusMutation.mutate("approved")}
              >
                Approve Appeal
              </button>
              <button
                className="btn-danger"
                disabled={appealStatusMutation.isPending || !reviewerName}
                onClick={() => appealStatusMutation.mutate("rejected")}
              >
                Reject Appeal
              </button>
              <button className="btn-secondary" onClick={() => setShowCorrectionForm(true)}>
                Log a Correction
              </button>
              {appealStatusMutation.isPending && <Spinner className="h-4 w-4 text-ink-400" />}
            </div>
            {denial.appeal.reviewer && (
              <p className="mt-2 text-xs text-ink-400">
                Last reviewed by {denial.appeal.reviewer} on {formatDateTime(denial.appeal.reviewed_at)}
              </p>
            )}
            {appealStatusMutation.isError && (
              <p className="mt-2 text-sm text-status-rejected-fg">
                {(appealStatusMutation.error as Error).message}
              </p>
            )}
          </>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-sm text-ink-400">No appeal drafted yet.</p>
            {denial.classification && (
              <button className="btn-secondary" onClick={() => setShowCorrectionForm(true)}>
                Log a Correction
              </button>
            )}
          </div>
        )}
      </div>

      {/* Unified audit trail: corrections + appeal-review decisions, one
          permanent, append-only chronological timeline. */}
      <div className="mt-6 card p-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
          Audit History
          <span className="ml-2 rounded-full bg-ink-100 px-2 py-0.5 text-xs font-semibold text-ink-500">
            {denial.audit_events.length}
          </span>
        </h2>
        {denial.audit_events.length === 0 ? (
          <p className="text-sm text-ink-400">No audit events logged for this denial yet.</p>
        ) : (
          <ul className="divide-y divide-ink-100">
            {denial.audit_events.map((e) =>
              e.event_type === "ai_action" ? (
                <li key={e.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-800">
                      <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-status-new-bg px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-status-new-fg">
                        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                          <path d="M9 4.5a.75.75 0 01.721.544l.813 2.846a3.75 3.75 0 002.576 2.576l2.846.813a.75.75 0 010 1.442l-2.846.813a3.75 3.75 0 00-2.576 2.576l-.813 2.846a.75.75 0 01-1.442 0l-.813-2.846a3.75 3.75 0 00-2.576-2.576l-2.846-.813a.75.75 0 010-1.442l2.846-.813A3.75 3.75 0 007.466 7.89l.813-2.846A.75.75 0 019 4.5zM18 1.5a.75.75 0 01.728.568l.258 1.036c.236.94.97 1.674 1.91 1.91l1.036.258a.75.75 0 010 1.456l-1.036.258c-.94.236-1.674.97-1.91 1.91l-.258 1.036a.75.75 0 01-1.456 0l-.258-1.036a2.625 2.625 0 00-1.91-1.91l-1.036-.258a.75.75 0 010-1.456l1.036-.258a2.625 2.625 0 001.91-1.91l.258-1.036A.75.75 0 0118 1.5zM16.5 15a.75.75 0 01.712.513l.394 1.183c.15.447.5.799.948.948l1.183.395a.75.75 0 010 1.422l-1.183.395c-.447.15-.799.5-.948.948l-.395 1.183a.75.75 0 01-1.422 0l-.395-1.183a1.5 1.5 0 00-.948-.948l-1.183-.395a.75.75 0 010-1.422l1.183-.395c.447-.15.799-.5.948-.948l.395-1.183A.75.75 0 0116.5 15z" />
                        </svg>
                        AI action
                      </span>
                      {e.new_value}
                    </span>
                    <span className="text-xs text-ink-400">
                      {e.corrected_by} · {formatDateTime(e.corrected_at)}
                    </span>
                  </div>
                  {e.notes && <p className="mt-1.5 text-sm text-ink-500">{e.notes}</p>}
                </li>
              ) : e.event_type === "appeal_review" ? (
                <li key={e.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-800">
                      <span className="rounded-[var(--radius-pill)] bg-status-sent-bg px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-status-sent-fg">
                        Appeal review
                      </span>
                      Appeal {e.appeal_id ? `#${e.appeal_id}` : ""}
                    </span>
                    <span className="text-xs text-ink-400">
                      {e.corrected_by} · {formatDateTime(e.corrected_at)}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
                    <StatusPill status={e.old_value} />
                    <svg className="h-3.5 w-3.5 text-ink-300" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path
                        fillRule="evenodd"
                        d="M10.293 3.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L12.586 9H3a1 1 0 110-2h9.586l-2.293-2.293a1 1 0 010-1.414z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <StatusPill status={e.new_value} />
                  </div>
                </li>
              ) : (
                <li key={e.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-800">
                      <span className="rounded-[var(--radius-pill)] bg-status-classified-bg px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-status-classified-fg">
                        Correction
                      </span>
                      {e.field_corrected}
                    </span>
                    <span className="text-xs text-ink-400">
                      {e.corrected_by} · {formatDateTime(e.corrected_at)}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
                    <span className="rounded bg-status-rejected-bg px-2 py-0.5 text-status-rejected-fg line-through decoration-1">
                      {e.old_value || "—"}
                    </span>
                    <svg className="h-3.5 w-3.5 text-ink-300" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path
                        fillRule="evenodd"
                        d="M10.293 3.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L12.586 9H3a1 1 0 110-2h9.586l-2.293-2.293a1 1 0 010-1.414z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <span className="rounded bg-status-approved-bg px-2 py-0.5 text-status-approved-fg">
                      {e.new_value || "—"}
                    </span>
                  </div>
                  {e.notes && <p className="mt-1.5 text-sm text-ink-500">{e.notes}</p>}
                </li>
              )
            )}
          </ul>
        )}
      </div>

      {showCorrectionForm && (
        <Modal title="Log a correction" onClose={() => setShowCorrectionForm(false)}>
          <CorrectionForm
            denialId={denial.id}
            currentCategory={denial.classification?.category}
            currentAppealText={denial.appeal?.draft_text}
            onDone={() => setShowCorrectionForm(false)}
          />
        </Modal>
      )}
    </div>
  );

  function BackLink() {
    return (
      <button
        onClick={() => navigate("/denials")}
        className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-ink-500 hover:text-brand-600"
      >
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
        Back to queue
      </button>
    );
  }
}
