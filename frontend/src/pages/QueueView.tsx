import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { DENIAL_STATUSES } from "../api/types";
import { StatusPill } from "../components/StatusPill";
import { TableSkeleton, ErrorState, EmptyState } from "../components/States";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const PAGE_SIZE = 40;

export function QueueView() {
  const navigate = useNavigate();
  const [company, setCompany] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.listProfiles(),
  });

  const denialsQuery = useQuery({
    queryKey: ["denials", { company, status, page }],
    queryFn: () =>
      api.listDenials({
        source_company: company || undefined,
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const totalPages = denialsQuery.data ? Math.max(1, Math.ceil(denialsQuery.data.total / PAGE_SIZE)) : 1;

  function resetAndSet<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(1);
    };
  }

  return (
    <div>
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-900">Denial Queue</h1>
          <p className="mt-1 text-sm text-ink-500">
            Review incoming claim denials, run AI triage, and manage appeal drafts.
          </p>
        </div>
        <button className="btn-primary shrink-0" onClick={() => navigate("/denials/new")}>
          New Denial
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-[220px]">
          <label className="label" htmlFor="company-filter">
            Company
          </label>
          <select
            id="company-filter"
            className="input"
            value={company}
            onChange={(e) => resetAndSet(setCompany)(e.target.value)}
          >
            <option value="">All companies</option>
            {profilesQuery.data?.map((p) => (
              <option key={p.key} value={p.key}>
                {p.display_name}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-[220px]">
          <label className="label" htmlFor="status-filter">
            Status
          </label>
          <select
            id="status-filter"
            className="input"
            value={status}
            onChange={(e) => resetAndSet(setStatus)(e.target.value)}
          >
            <option value="">All statuses</option>
            {DENIAL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>
        {(company || status) && (
          <button
            className="btn-secondary mt-6"
            onClick={() => {
              setCompany("");
              setStatus("");
              setPage(1);
            }}
          >
            Clear filters
          </button>
        )}
        {denialsQuery.data && (
          <div className="ml-auto mt-6 text-sm text-ink-500">
            {denialsQuery.data.total} denial{denialsQuery.data.total === 1 ? "" : "s"}
          </div>
        )}
      </div>

      {denialsQuery.isLoading && <TableSkeleton />}

      {denialsQuery.isError && (
        <ErrorState
          message={
            denialsQuery.error instanceof ApiError
              ? denialsQuery.error.message
              : "Failed to load denials."
          }
          onRetry={() => denialsQuery.refetch()}
        />
      )}

      {denialsQuery.isSuccess && denialsQuery.data.items.length === 0 && (
        <EmptyState
          title="No denials match these filters"
          message="Try clearing the company or status filter to see the full queue."
        />
      )}

      {denialsQuery.isSuccess && denialsQuery.data.items.length > 0 && (
        <>
          <div className="card overflow-hidden">
            <div className="table-scroll">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50/60 text-left text-xs font-semibold uppercase tracking-wide text-ink-500">
                    <th className="px-5 py-3">Status</th>
                    <th className="px-5 py-3">Claim Ref</th>
                    <th className="px-5 py-3">Payer</th>
                    <th className="px-5 py-3">Received</th>
                    <th className="px-5 py-3">Pipeline</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {denialsQuery.data.items.map((d) => (
                    <tr
                      key={d.id}
                      onClick={() => navigate(`/denials/${d.id}`)}
                      className="cursor-pointer transition-colors hover:bg-brand-50/40"
                    >
                      <td className="px-5 py-3.5">
                        <StatusPill status={d.status} />
                      </td>
                      <td className="px-5 py-3.5 font-medium text-ink-800">{d.claim_ref}</td>
                      <td className="px-5 py-3.5 text-ink-600">{d.payer}</td>
                      <td className="px-5 py-3.5 text-ink-500">{formatDate(d.received_at)}</td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-1.5 text-xs text-ink-400">
                          <PipelineDot done={d.has_classification} label="Classified" />
                          <PipelineDot done={d.has_appeal} label="Appeal" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-ink-500">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                className="btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <button
                className="btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PipelineDot({ done, label }: { done: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${
        done ? "bg-status-approved-bg text-status-approved-fg" : "bg-ink-100 text-ink-400"
      }`}
      title={label}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${done ? "bg-status-approved" : "bg-ink-300"}`} />
      {label}
    </span>
  );
}
