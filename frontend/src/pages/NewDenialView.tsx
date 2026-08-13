import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";

export function NewDenialView() {
  const navigate = useNavigate();
  const [sourceCompany, setSourceCompany] = useState("");
  const [rawText, setRawText] = useState("");
  const [payer, setPayer] = useState("");
  const [claimRef, setClaimRef] = useState("");

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.listProfiles(),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.createDenial({
        source_company: sourceCompany,
        raw_text: rawText,
        payer: payer || null,
        claim_ref: claimRef || null,
      }),
    onSuccess: (denial) => {
      navigate(`/denials/${denial.id}`);
    },
  });

  const canSubmit = sourceCompany.trim().length > 0 && rawText.trim().length > 0;

  return (
    <div>
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

      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">New Denial</h1>
        <p className="mt-1 text-sm text-ink-500">
          Paste in a denial letter's raw text and pick the company it belongs to. It's saved
          as a new record ready for the "Process with AI" pipeline on the next screen.
        </p>
      </div>

      <form
        className="card max-w-3xl space-y-5 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) createMutation.mutate();
        }}
      >
        <div>
          <label className="label" htmlFor="new-denial-company">
            Company
          </label>
          <select
            id="new-denial-company"
            className="input"
            value={sourceCompany}
            onChange={(e) => setSourceCompany(e.target.value)}
            required
          >
            <option value="" disabled>
              Select a company profile
            </option>
            {profilesQuery.data?.map((p) => (
              <option key={p.key} value={p.key}>
                {p.display_name}
              </option>
            ))}
          </select>
          {profilesQuery.isError && (
            <p className="mt-1 text-sm text-status-rejected-fg">Failed to load company profiles.</p>
          )}
        </div>

        <div>
          <label className="label" htmlFor="new-denial-raw-text">
            Denial letter text
          </label>
          <textarea
            id="new-denial-raw-text"
            className="input h-64 font-mono text-[13px] leading-relaxed"
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste the full text of the denial letter here…"
            required
          />
          <p className="mt-1 text-xs text-ink-400">
            The primary input — this is what extraction, classification, and appeal drafting
            run against.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="new-denial-payer">
              Payer <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="new-denial-payer"
              className="input"
              value={payer}
              onChange={(e) => setPayer(e.target.value)}
              placeholder='Leave blank for "Unknown (manual entry)"'
            />
          </div>
          <div>
            <label className="label" htmlFor="new-denial-claim-ref">
              Claim ref <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="new-denial-claim-ref"
              className="input"
              value={claimRef}
              onChange={(e) => setClaimRef(e.target.value)}
              placeholder="Leave blank to auto-generate"
            />
          </div>
        </div>

        {createMutation.isError && (
          <p className="text-sm text-status-rejected-fg">
            {createMutation.error instanceof ApiError
              ? createMutation.error.message
              : "Failed to create denial."}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={() => navigate("/denials")}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={!canSubmit || createMutation.isPending}>
            {createMutation.isPending ? "Creating…" : "Create denial"}
          </button>
        </div>
      </form>
    </div>
  );
}
