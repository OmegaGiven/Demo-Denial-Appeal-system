import type {
  AppealOut,
  AppealStatusUpdateRequest,
  AuditEventOut,
  ConfidenceDistributionResponse,
  CorrectionCreateRequest,
  DemoResetOut,
  DenialCreateRequest,
  DenialDetail,
  DenialListItem,
  DenialListResponse,
  EvalRunOut,
  ProcessResponse,
  ProfileDetailOut,
  ProfileOut,
  UsageResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, `Could not reach the API at ${API_BASE_URL}. Is the backend running?`);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* body wasn't JSON, fall back to statusText */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface ListDenialsParams {
  source_company?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

function asRecord<T extends object>(v: T): Record<string, string | number | undefined> {
  return v as unknown as Record<string, string | number | undefined>;
}

export const api = {
  listDenials: (params: ListDenialsParams = {}) =>
    request<DenialListResponse>(`/denials${toQuery(asRecord(params))}`),

  getDenial: (id: string) => request<DenialDetail>(`/denials/${id}`),

  createDenial: (body: DenialCreateRequest) =>
    request<DenialListItem>(`/denials`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  processDenial: (id: string) =>
    request<ProcessResponse>(`/denials/${id}/process`, { method: "POST" }),

  draftAppeal: (id: string) =>
    request<ProcessResponse>(`/denials/${id}/appeal/draft`, { method: "POST" }),

  updateAppealStatus: (id: string, body: AppealStatusUpdateRequest) =>
    request<AppealOut>(`/denials/${id}/appeal/status`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  createCorrection: (id: string, body: CorrectionCreateRequest) =>
    request<AuditEventOut>(`/denials/${id}/corrections`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listProfiles: () => request<ProfileOut[]>(`/profiles`),
  getProfileDetail: (key: string) => request<ProfileDetailOut>(`/profiles/${key}`),

  resetDemoSample: (source_company: string) =>
    request<DemoResetOut>(`/demo/reset-sample${toQuery({ source_company })}`, { method: "POST" }),

  getUsage: (source_company?: string) =>
    request<UsageResponse>(`/usage${toQuery({ source_company })}`),

  listEvalRuns: () => request<EvalRunOut[]>(`/eval/runs`),
  triggerEvalRun: () => request<EvalRunOut>(`/eval/run`, { method: "POST" }),

  getConfidenceDistribution: (source_company?: string) =>
    request<ConfidenceDistributionResponse>(`/analytics/confidence-distribution${toQuery({ source_company })}`),
};
