import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { CLASSIFICATION_CATEGORIES } from "../api/types";

const CORRECTABLE_FIELDS = [
  { value: "classification.category", label: "Classification category" },
  { value: "appeal.draft_text", label: "Appeal letter text" },
  { value: "extraction.extracted_fields", label: "Extracted field" },
] as const;

export function CorrectionForm({
  denialId,
  currentCategory,
  currentAppealText,
  onDone,
}: {
  denialId: string;
  currentCategory?: string;
  currentAppealText?: string;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [fieldCorrected, setFieldCorrected] = useState<string>("classification.category");
  const [oldValue, setOldValue] = useState(currentCategory ?? "");
  const [newValue, setNewValue] = useState(currentCategory ?? "");
  const [correctedBy, setCorrectedBy] = useState("");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      api.createCorrection(denialId, {
        field_corrected: fieldCorrected,
        old_value: oldValue,
        new_value: newValue,
        corrected_by: correctedBy,
        notes: notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["denial", denialId] });
      onDone();
    },
  });

  function handleFieldChange(value: string) {
    setFieldCorrected(value);
    if (value === "classification.category") {
      setOldValue(currentCategory ?? "");
      setNewValue(currentCategory ?? "");
    } else if (value === "appeal.draft_text") {
      setOldValue(currentAppealText ?? "");
      setNewValue(currentAppealText ?? "");
    } else {
      setOldValue("");
      setNewValue("");
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <p className="text-sm text-ink-500">
        Logs a correction to the audit trail. This does not overwrite the AI's original
        output — it records what a human reviewer determined the correct value should be,
        alongside a reason, for compliance review.
      </p>

      <div>
        <label className="label" htmlFor="field-corrected">
          Field being corrected
        </label>
        <select
          id="field-corrected"
          className="input"
          value={fieldCorrected}
          onChange={(e) => handleFieldChange(e.target.value)}
        >
          {CORRECTABLE_FIELDS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="label" htmlFor="old-value">
            AI's original value
          </label>
          {fieldCorrected === "appeal.draft_text" ? (
            <textarea
              id="old-value"
              className="input h-24 font-mono text-xs"
              value={oldValue}
              readOnly
            />
          ) : (
            <input id="old-value" className="input bg-ink-50" value={oldValue} readOnly />
          )}
        </div>
        <div>
          <label className="label" htmlFor="new-value">
            Corrected value
          </label>
          {fieldCorrected === "classification.category" ? (
            <select
              id="new-value"
              className="input"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              required
            >
              <option value="" disabled>
                Select a category
              </option>
              {CLASSIFICATION_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          ) : fieldCorrected === "appeal.draft_text" ? (
            <textarea
              id="new-value"
              className="input h-24 font-mono text-xs"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              required
            />
          ) : (
            <input
              id="new-value"
              className="input"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              required
            />
          )}
        </div>
      </div>

      <div>
        <label className="label" htmlFor="corrected-by">
          Your name / email (reviewer)
        </label>
        <input
          id="corrected-by"
          className="input"
          value={correctedBy}
          onChange={(e) => setCorrectedBy(e.target.value)}
          placeholder="jane.compliance@example.com"
          required
        />
      </div>

      <div>
        <label className="label" htmlFor="notes">
          Reason / notes
        </label>
        <textarea
          id="notes"
          className="input h-20"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Why is this correction being made?"
        />
      </div>

      {mutation.isError && (
        <p className="text-sm text-status-rejected-fg">
          Failed to submit correction: {(mutation.error as Error).message}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="btn-secondary" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Submitting…" : "Submit correction"}
        </button>
      </div>
    </form>
  );
}
