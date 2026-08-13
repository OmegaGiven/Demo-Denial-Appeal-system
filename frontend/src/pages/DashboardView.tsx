import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ErrorState } from "../components/States";
import {
  AccuracyTrendChart,
  ComparisonBarChart,
  ConfidenceHistogram,
  MagnitudeBarRow,
  StatTile,
} from "../components/charts";

const REGRESSION_THRESHOLD_PP = 5.0;

const COMPANY_LABELS: Record<string, string> = {
  meridian_eyecare_partners: "Meridian Eye Care Partners",
  summit_dme_providers: "Summit DME Providers",
};

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtUsd(n: number): string {
  return n < 1 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

function RegressionBanner({
  latest,
  prior,
}: {
  latest: { score: number; runAt: string } | null;
  prior: { score: number; runAt: string } | null;
}) {
  if (!latest) {
    return (
      <div className="card flex items-center gap-3 border-status-new/30 px-5 py-4">
        <span className="text-sm text-ink-500">No eval runs recorded yet.</span>
      </div>
    );
  }

  if (!prior) {
    return (
      <div className="card flex items-center gap-3 border-status-new/40 bg-status-new-bg/40 px-5 py-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-status-new-bg text-status-new-fg">
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <div>
          <div className="text-sm font-semibold text-ink-800">No prior baseline</div>
          <div className="text-sm text-ink-500">
            First eval run scored {(latest.score * 100).toFixed(1)}%. Regression checks begin on the next run.
          </div>
        </div>
      </div>
    );
  }

  const deltaPp = (latest.score - prior.score) * 100;
  const regressed = deltaPp < -REGRESSION_THRESHOLD_PP;

  return (
    <div
      className={`card flex items-center gap-3 px-5 py-4 ${
        regressed ? "border-status-rejected/40 bg-status-rejected-bg/50" : "border-status-approved/40 bg-status-approved-bg/50"
      }`}
    >
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
          regressed ? "bg-status-rejected-bg text-status-rejected-fg" : "bg-status-approved-bg text-status-approved-fg"
        }`}
      >
        {regressed ? (
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.72-1.36 3.486 0l6.28 11.16c.75 1.334-.213 2.99-1.743 2.99H3.72c-1.53 0-2.493-1.656-1.743-2.99l6.28-11.16zM11 13a1 1 0 10-2 0 1 1 0 002 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className={`text-sm font-semibold ${regressed ? "text-status-rejected-fg" : "text-status-approved-fg"}`}>
          {regressed ? "Regression detected" : "No regression"}
        </div>
        <div className="text-sm text-ink-600">
          Latest run {(latest.score * 100).toFixed(1)}% vs prior {(prior.score * 100).toFixed(1)}% &mdash;{" "}
          <span className="font-medium tabular-nums">
            {deltaPp >= 0 ? "+" : ""}
            {deltaPp.toFixed(2)}pp
          </span>{" "}
          (flag threshold: &minus;{REGRESSION_THRESHOLD_PP}pp)
        </div>
      </div>
    </div>
  );
}

export function DashboardView() {
  const evalRunsQuery = useQuery({ queryKey: ["eval-runs"], queryFn: () => api.listEvalRuns() });
  const usageQuery = useQuery({ queryKey: ["usage"], queryFn: () => api.getUsage() });
  const confidenceQuery = useQuery({
    queryKey: ["confidence-distribution"],
    queryFn: () => api.getConfidenceDistribution(),
  });
  const denialsQuery = useQuery({ queryKey: ["denials-total"], queryFn: () => api.listDenials({ page_size: 1 }) });
  const cepUsageQuery = useQuery({
    queryKey: ["usage", "meridian_eyecare_partners"],
    queryFn: () => api.getUsage("meridian_eyecare_partners"),
  });
  const dmeUsageQuery = useQuery({
    queryKey: ["usage", "summit_dme_providers"],
    queryFn: () => api.getUsage("summit_dme_providers"),
  });

  const loading =
    evalRunsQuery.isLoading || usageQuery.isLoading || confidenceQuery.isLoading || denialsQuery.isLoading;
  const anyError = evalRunsQuery.error || usageQuery.error || confidenceQuery.error || denialsQuery.error;

  if (anyError) {
    return (
      <ErrorState
        message={anyError instanceof Error ? anyError.message : "Failed to load dashboard data."}
        onRetry={() => window.location.reload()}
      />
    );
  }

  const runsAsc = [...(evalRunsQuery.data ?? [])].sort(
    (a, b) => new Date(a.run_at).getTime() - new Date(b.run_at).getTime(),
  );
  const latestRun = runsAsc.length > 0 ? runsAsc[runsAsc.length - 1] : null;
  const priorRun = runsAsc.length > 1 ? runsAsc[runsAsc.length - 2] : null;

  const details = latestRun?.details as
    | { classification_accuracy?: number; extraction_accuracy?: number; appeal_completeness?: number }
    | undefined;

  const totalDenials = denialsQuery.data?.total ?? 0;
  const usage = usageQuery.data;
  const costPerDenial = usage && totalDenials > 0 ? usage.total_estimated_cost_usd / totalDenials : 0;

  const stageOrder = ["extraction", "classification", "appeal_drafting"];
  const byStage = usage
    ? [...usage.by_stage].sort((a, b) => stageOrder.indexOf(a.stage) - stageOrder.indexOf(b.stage))
    : [];

  const dayCount = usage?.by_day.length ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">Monitoring &amp; Eval</h1>
        <p className="mt-1 text-sm text-ink-500">
          Pipeline accuracy, regression status, confidence distribution, and token/cost usage &mdash; how we'd know
          if this system stopped working or regressed.
        </p>
      </div>

      {!loading && (
        <RegressionBanner
          latest={latestRun ? { score: latestRun.accuracy_score ?? 0, runAt: latestRun.run_at } : null}
          prior={priorRun ? { score: priorRun.accuracy_score ?? 0, runAt: priorRun.run_at } : null}
        />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-ink-800">Eval accuracy over time</h2>
          <p className="mt-0.5 text-xs text-ink-500">
            Overall weighted score per eval run (0.4 classification + 0.3 extraction + 0.3 appeal completeness).
          </p>
          <div className="mt-2">
            {!evalRunsQuery.isLoading && (
              <AccuracyTrendChart
                points={runsAsc.map((r) => ({ id: r.id, runAt: r.run_at, score: r.accuracy_score ?? 0 }))}
              />
            )}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-ink-800">Latest run &mdash; per-dimension breakdown</h2>
          <p className="mt-0.5 text-xs text-ink-500">
            {latestRun ? `Run #${latestRun.id}, ${new Date(latestRun.run_at).toLocaleDateString()}` : "—"}
          </p>
          <div className="mt-4 space-y-4">
            {details ? (
              <>
                <MagnitudeBarRow
                  label="Classification accuracy"
                  value={details.classification_accuracy ?? 0}
                  formatted={`${((details.classification_accuracy ?? 0) * 100).toFixed(1)}%`}
                />
                <MagnitudeBarRow
                  label="Extraction accuracy (CARC)"
                  value={details.extraction_accuracy ?? 0}
                  formatted={`${((details.extraction_accuracy ?? 0) * 100).toFixed(1)}%`}
                />
                <MagnitudeBarRow
                  label="Appeal completeness"
                  value={details.appeal_completeness ?? 0}
                  formatted={`${((details.appeal_completeness ?? 0) * 100).toFixed(1)}%`}
                />
              </>
            ) : (
              <div className="text-sm text-ink-500">No eval run yet.</div>
            )}
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold text-ink-800">Classification confidence distribution</h2>
        <p className="mt-0.5 text-xs text-ink-500">
          {confidenceQuery.data
            ? `Live population — ${confidenceQuery.data.total_classified} classified denials (most recent classification per denial).`
            : "—"}
        </p>
        <div className="mt-2">
          {confidenceQuery.data && <ConfidenceHistogram buckets={confidenceQuery.data.buckets} />}
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-base font-semibold tracking-tight text-ink-900">Token &amp; cost usage</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatTile
            label="Total tokens"
            value={usage ? fmtTokens(usage.total_tokens) : "—"}
            sub={usage ? `${usage.total_calls} pipeline calls` : undefined}
          />
          <StatTile
            label="Total cost"
            value={usage ? fmtUsd(usage.total_estimated_cost_usd) : "—"}
            sub="estimated, across all stages"
          />
          <StatTile
            label="Cost per denial"
            value={usage ? fmtUsd(costPerDenial) : "—"}
            sub={`total cost / ${totalDenials} denials processed`}
          />
          <StatTile
            label="Denials in system"
            value={String(totalDenials)}
            sub={confidenceQuery.data ? `${confidenceQuery.data.total_classified} classified` : undefined}
          />
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-ink-800">Cost by pipeline stage</h3>
            <p className="mt-0.5 text-xs text-ink-500">Estimated cost, extraction &rarr; classification &rarr; appeal drafting.</p>
            <div className="mt-4">
              {byStage.length > 0 ? (
                <ComparisonBarChart
                  items={byStage.map((s) => ({
                    label: s.stage.replace("_", " "),
                    value: s.estimated_cost_usd,
                    formatted: fmtUsd(s.estimated_cost_usd),
                  }))}
                />
              ) : (
                <div className="text-sm text-ink-500">No usage data yet.</div>
              )}
            </div>
          </div>

          <div className="card p-5">
            <h3 className="text-sm font-semibold text-ink-800">Cost by company</h3>
            <p className="mt-0.5 text-xs text-ink-500">Same pipeline code, two client companies.</p>
            <div className="mt-4">
              {cepUsageQuery.data && dmeUsageQuery.data ? (
                <ComparisonBarChart
                  items={[
                    {
                      label: COMPANY_LABELS.meridian_eyecare_partners,
                      value: cepUsageQuery.data.total_estimated_cost_usd,
                      formatted: fmtUsd(cepUsageQuery.data.total_estimated_cost_usd),
                    },
                    {
                      label: COMPANY_LABELS.summit_dme_providers,
                      value: dmeUsageQuery.data.total_estimated_cost_usd,
                      formatted: fmtUsd(dmeUsageQuery.data.total_estimated_cost_usd),
                    },
                  ]}
                />
              ) : (
                <div className="text-sm text-ink-500">Loading&hellip;</div>
              )}
            </div>
          </div>
        </div>

        {dayCount > 1 ? (
          <div className="card mt-6 p-5">
            <h3 className="text-sm font-semibold text-ink-800">Usage by day</h3>
            <div className="mt-4">
              <ComparisonBarChart
                items={(usage?.by_day ?? []).map((d) => ({
                  label: d.day,
                  value: d.estimated_cost_usd,
                  formatted: fmtUsd(d.estimated_cost_usd),
                }))}
              />
            </div>
          </div>
        ) : (
          usage && (
            <p className="mt-4 text-xs text-ink-400">
              All recorded usage falls within a single day so far ({usage.by_day[0]?.day ?? "n/a"}) &mdash; a daily
              time series would just show one spike, so it's omitted here in favor of the stat tiles above. Revisit
              once usage spans multiple days.
            </p>
          )
        )}
      </div>
    </div>
  );
}
