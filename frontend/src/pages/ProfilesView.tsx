import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { DenialDetail, ProfileDetailOut, ProfileOut } from "../api/types";
import { StatusPill } from "../components/StatusPill";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { KeyValueGrid } from "../components/KeyValue";
import { Spinner, ErrorState } from "../components/States";

function humanizeCategory(category: string): string {
  return category.replace(/_/g, " ");
}

/** Extraction fields as a compact comma list -- the single most visually
 * convincing piece of the page: MEC's CPT-code fields sitting right next
 * to DME's HCPCS-code fields, same layout, same component. */
function FieldList({ fields }: { fields: ProfileDetailOut["extraction_fields"] }) {
  return (
    <ul className="space-y-1.5">
      {fields.map((f) => (
        <li key={f.name} className="flex items-baseline gap-2 text-sm">
          <span className="font-medium text-ink-800">{f.name}</span>
          {f.required && (
            <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-700">
              required
            </span>
          )}
          <span className="text-ink-400 text-xs truncate">{f.description}</span>
        </li>
      ))}
    </ul>
  );
}

function ProfileColumn({ profile }: { profile: ProfileDetailOut }) {
  return (
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-ink-900">{profile.display_name}</h2>
        <p className="text-xs text-ink-400 font-mono">source_company = "{profile.key}"</p>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Extraction fields ({profile.extraction_fields.length})
        </h3>
        <FieldList fields={profile.extraction_fields} />
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Appeal guidance by category
        </h3>
        <ul className="space-y-2.5">
          {profile.appeal_guidance.map((g) => (
            <li key={g.category}>
              <div className="text-xs font-semibold text-brand-700">{humanizeCategory(g.category)}</div>
              <p className="text-sm text-ink-500">{g.excerpt}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** One company's live-demo card: reset a sample denial to status="new",
 * then process it with the real, existing POST /denials/{id}/process
 * endpoint -- same mutation, same loading copy as DetailView's "Process
 * with AI" button, just embedded here. */
function LiveDemoCard({ company }: { company: ProfileOut }) {
  const queryClient = useQueryClient();
  const [denialId, setDenialId] = useState<string | null>(null);

  // On mount, pick up a denial this company already has sitting at
  // status="new" (e.g. from a reset earlier in the session) so a page
  // reload during the Loom recording doesn't lose the demo state.
  const existingNewQuery = useQuery({
    queryKey: ["demo-existing-new", company.key],
    queryFn: () => api.listDenials({ source_company: company.key, status: "new", page_size: 1 }),
  });
  useEffect(() => {
    if (!denialId && existingNewQuery.data && existingNewQuery.data.items.length > 0) {
      setDenialId(existingNewQuery.data.items[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingNewQuery.data]);

  const denialQuery = useQuery({
    queryKey: ["denial", denialId],
    queryFn: () => api.getDenial(denialId!),
    enabled: !!denialId,
  });

  const resetMutation = useMutation({
    mutationFn: () => api.resetDemoSample(company.key),
    onSuccess: (data) => {
      setDenialId(data.denial_id);
      queryClient.invalidateQueries({ queryKey: ["denial", data.denial_id] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  const processMutation = useMutation({
    mutationFn: () => api.processDenial(denialId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["denial", denialId] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  const denial: DenialDetail | undefined = denialQuery.data;

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-ink-900">{company.display_name}</h3>
        {denial && <StatusPill status={denial.status} />}
      </div>

      {!denialId && (
        <div className="space-y-2">
          <p className="text-sm text-ink-500">
            No sample denial is staged for this company right now. Use the Demo Tools reset
            below, then come back here to process it.
          </p>
        </div>
      )}

      {resetMutation.isError && (
        <p className="text-sm text-status-rejected-fg">
          {resetMutation.error instanceof ApiError
            ? resetMutation.error.message
            : "Reset failed."}
        </p>
      )}

      {denialId && (
        <>
          {denialQuery.isLoading ? (
            <Spinner className="h-4 w-4 text-ink-400" />
          ) : denial ? (
            <>
              <p className="text-xs text-ink-400">
                Claim {denial.claim_ref} · {denial.payer}
              </p>

              {denial.status === "new" && (
                <button
                  className="btn-primary"
                  disabled={processMutation.isPending}
                  onClick={() => processMutation.mutate()}
                >
                  {processMutation.isPending ? (
                    <>
                      <Spinner className="h-4 w-4" />
                      Processing (this can take 10-30s)…
                    </>
                  ) : (
                    "Process with AI"
                  )}
                </button>
              )}

              {processMutation.isPending && (
                <div className="flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs text-brand-800">
                  <Spinner className="h-3.5 w-3.5 text-brand-600" />
                  Running extraction, classification, and appeal drafting against the real
                  Anthropic API for {company.display_name}.
                </div>
              )}

              {processMutation.isError && (
                <p className="text-sm text-status-rejected-fg">
                  Processing failed: {(processMutation.error as Error).message}
                </p>
              )}

              {denial.extraction && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Extracted fields
                  </h4>
                  <KeyValueGrid fields={denial.extraction.extracted_fields} />
                </div>
              )}

              {denial.classification && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Classification
                  </h4>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="rounded-md bg-brand-50 px-2.5 py-1 text-sm font-semibold text-brand-700">
                      {humanizeCategory(denial.classification.category)}
                    </span>
                  </div>
                  <ConfidenceBadge confidence={denial.classification.confidence} />
                </div>
              )}

              {denial.appeal && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Drafted appeal (excerpt)
                  </h4>
                  <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md bg-ink-50 p-3 font-mono text-[12px] leading-relaxed text-ink-700 border border-ink-100">
                    {denial.appeal.draft_text.slice(0, 500)}
                    {denial.appeal.draft_text.length > 500 ? "…" : ""}
                  </pre>
                </div>
              )}

              <Link
                to={`/denials/${denial.id}`}
                className="inline-block text-sm font-medium text-brand-600 hover:text-brand-700"
              >
                Open full record →
              </Link>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}

function ResetButton({
  company,
  onReset,
}: {
  company: ProfileOut;
  onReset: (claimRef: string) => void;
}) {
  const queryClient = useQueryClient();
  const resetMutation = useMutation({
    mutationFn: () => api.resetDemoSample(company.key),
    onSuccess: (data) => {
      onReset(data.claim_ref);
      queryClient.invalidateQueries({ queryKey: ["demo-existing-new", company.key] });
      queryClient.invalidateQueries({ queryKey: ["denials"] });
    },
  });

  return (
    <button className="btn-secondary" disabled={resetMutation.isPending} onClick={() => resetMutation.mutate()}>
      {resetMutation.isPending ? <Spinner className="h-4 w-4" /> : null}
      Reset a sample {company.display_name} denial for live demo
    </button>
  );
}

function DemoTools({ profiles }: { profiles: ProfileOut[] }) {
  const [lastReset, setLastReset] = useState<Record<string, string>>({});

  return (
    <div className="card border-2 border-dashed border-status-processing/40 bg-status-processing-bg/30 p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-status-processing-bg text-status-processing-fg">
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-ink-900">
            Demo Tools <span className="font-normal text-ink-500">— case-study only, not production</span>
          </h2>
          <p className="mt-1 text-sm text-ink-600">
            All 62 denials in this dataset were already batch-processed in earlier phases, so
            there's nothing left sitting at <code className="text-xs">status="new"</code> to
            demo live. This resets one already-processed denial per company back to{" "}
            <code className="text-xs">new</code> — deleting its prior extraction/
            classification/appeal rows — so the "Process with AI" flow above can run for real,
            on screen, against the live Anthropic API.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            {profiles.map((p) => (
              <ResetButton
                key={p.key}
                company={p}
                onReset={(claimRef) => setLastReset((prev) => ({ ...prev, [p.key]: claimRef }))}
              />
            ))}
          </div>
          {Object.entries(lastReset).length > 0 && (
            <p className="mt-2 text-xs text-ink-500">
              {Object.entries(lastReset)
                .map(([key, claimRef]) => `${key}: ${claimRef} reset to "new"`)
                .join(" · ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function ProfilesView() {
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: () => api.listProfiles() });

  const detailQueries = useQueries({
    queries: (profilesQuery.data ?? []).map((p) => ({
      queryKey: ["profile-detail", p.key],
      queryFn: () => api.getProfileDetail(p.key),
      enabled: !!profilesQuery.data,
    })),
  });

  if (profilesQuery.isLoading || detailQueries.some((q) => q.isLoading)) {
    return (
      <div className="card p-10 text-center text-sm text-ink-400">
        <Spinner className="mx-auto h-5 w-5" />
        <p className="mt-2">Loading company profiles…</p>
      </div>
    );
  }

  if (profilesQuery.isError) {
    return (
      <ErrorState
        message={
          profilesQuery.error instanceof ApiError
            ? profilesQuery.error.message
            : "Failed to load company profiles."
        }
        onRetry={() => profilesQuery.refetch()}
      />
    );
  }

  const profiles = profilesQuery.data!;
  const details = detailQueries.map((q) => q.data).filter((d): d is ProfileDetailOut => !!d);
  const sharedCategories = details[0]?.category_taxonomy ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">Company Profiles</h1>
        <p className="mt-1 text-sm text-ink-500 max-w-3xl">
          One pipeline, driven entirely by config: the same extract → classify → draft-appeal
          code runs both companies below, with the different fields, language, and appeal
          guidance coming from each company's <code className="text-xs">CompanyProfile</code>{" "}
          object — not a code branch. This is the answer to "how would you adapt this for a
          second client company": you write a new profile, not new pipeline code.
        </p>
      </div>

      <div className="card p-5">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Shared category taxonomy — reused, not duplicated
        </h2>
        <p className="mb-3 text-sm text-ink-500">
          Both companies classify denials into the exact same six root-cause categories. This
          taxonomy lives once in <code className="text-xs">db/models.py</code>, not per-profile —
          it's genuinely universal across healthcare claim types.
        </p>
        <div className="flex flex-wrap gap-2">
          {sharedCategories.map((c) => (
            <span
              key={c}
              className="rounded-md bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-700"
            >
              {humanizeCategory(c)}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {details.map((d) => (
          <ProfileColumn key={d.key} profile={d} />
        ))}
      </div>

      <div>
        <h2 className="text-lg font-semibold text-ink-900 mb-1">Live processing demo</h2>
        <p className="text-sm text-ink-500 mb-4">
          Run the real pipeline for each company back-to-back and watch the extracted fields,
          classification, and appeal draft populate on screen.
        </p>
        <DemoTools profiles={profiles} />
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
          {profiles.map((p) => (
            <LiveDemoCard key={p.key} company={p} />
          ))}
        </div>
      </div>
    </div>
  );
}
