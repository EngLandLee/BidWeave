/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * Authenticated fetch wrapper; HTTP errors remain visible to the operator.
 */
import type {
  AgentResponse,
  Analytics,
  CaseDetail,
  CaseSummary,
  Evidence,
  ExtractResponse,
  User,
} from "./types";

export interface RequirementSearch {
  query: string;
  results: Array<{
    case_id: string;
    case_title: string;
    requirement_key: string;
    title: string;
    source_ref: string;
  }>;
}
export interface AuditVerification {
  valid: boolean;
  event_count: number;
  head_hash: string;
  broken_event_id?: string;
}
export interface CaseHistory {
  snapshots: Array<{
    revision_number: number;
    captured_at: string;
    content_sha256: string;
    payload: Record<string, unknown>;
  }>;
}

const base = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");
let tokenProvider: (() => Promise<string | undefined>) | undefined;
export function setTokenProvider(provider: () => Promise<string | undefined>) {
  tokenProvider = provider;
}
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}
async function requestBinary(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = tokenProvider ? await tokenProvider() : undefined;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { headers });
  } catch {
    throw new ApiError(
      0,
      "Network unavailable. Check the API connection and retry.",
    );
  }
  if (!response.ok) {
    const text = await response.text();
    let detail = `Request failed (${response.status})`;
    try {
      const payload: unknown = JSON.parse(text);
      if (
        payload &&
        typeof payload === "object" &&
        "detail" in payload &&
        typeof payload.detail === "string"
      )
        detail = payload.detail;
    } catch {
      /* preserve HTTP status when an error body is not JSON */
    }
    throw new ApiError(response.status, detail);
  }
  return response.blob();
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const token = tokenProvider ? await tokenProvider() : undefined;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      0,
      "Network unavailable. Check the API connection and retry.",
    );
  }
  const text = await response.text();
  let payload: unknown = undefined;
  try {
    payload = text ? JSON.parse(text) : undefined;
  } catch {
    payload = undefined;
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    if (payload && typeof payload === "object" && "detail" in payload) {
      const candidate = payload.detail;
      if (typeof candidate === "string") detail = candidate;
    }
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}
const json = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});
export const api = {
  health: () => request<{ status?: string }>("/health"),
  me: () => request<User>("/me"),
  cases: () => request<CaseSummary[]>("/cases"),
  detail: (id: string) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(id)}`),
  analytics: () => request<Analytics>("/analytics"),
  createCase: (body: {
    title: string;
    deadline: string;
    description?: string;
  }) => request<CaseSummary>("/cases", json(body)),
  revision: (id: string, body: unknown) =>
    request<CaseDetail>(
      `/cases/${encodeURIComponent(id)}/revisions`,
      json(body),
    ),
  evidence: (id: string, form: FormData) =>
    request<Evidence>(`/cases/${encodeURIComponent(id)}/evidence`, {
      method: "POST",
      body: form,
    }),
  verify: (id: string, evidenceId: string, expected_revision: number) =>
    request<CaseDetail>(
      `/cases/${encodeURIComponent(id)}/evidence/${encodeURIComponent(evidenceId)}/verify`,
      json({ expected_revision }),
    ),
  submit: (id: string, expected_revision: number) =>
    request<CaseDetail>(
      `/cases/${encodeURIComponent(id)}/submit`,
      json({ expected_revision }),
    ),
  review: (
    id: string,
    body: {
      expected_revision: number;
      decision: "approve" | "reject";
      comment: string;
    },
  ) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(id)}/review`, json(body)),
  comment: (id: string, body: string) =>
    request<{ id: string; author: string; body: string; created_at: string }>(
      `/cases/${encodeURIComponent(id)}/comments`,
      json({ body }),
    ),
  task: (
    id: string,
    taskId: string,
    body: { status: "open" | "done"; assignee?: string },
  ) =>
    request<CaseDetail>(
      `/cases/${encodeURIComponent(id)}/tasks/${encodeURIComponent(taskId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      },
    ),
  lineage: (id: string) =>
    request<Record<string, unknown>>(
      `/cases/${encodeURIComponent(id)}/lineage`,
    ),
  preview: (id: string, evidenceId: string) =>
    request<{ filename: string; text: string }>(
      `/cases/${encodeURIComponent(id)}/evidence/${encodeURIComponent(evidenceId)}/preview`,
    ),
  notices: (date: string) =>
    request<{
      notices: Array<{
        publication_number: string;
        cpv_label: string;
        source_graph: string;
      }>;
    }>(`/lod/notices?date=${encodeURIComponent(date)}&cpv_prefix=72`),
  notice: (id: string, publication_number: string) =>
    request<{
      publication_number: string;
      source_graph: string;
      retrieved_at: string;
    }>(`/cases/${encodeURIComponent(id)}/notice`, json({ publication_number })),
  agentChat: (case_id: string, message: string) =>
    request<AgentResponse>("/agent/chat", json({ case_id, message })),
  agentStatus: () => request<Record<string, unknown>>("/agent/status"),
  agentExtract: (form: FormData) =>
    request<ExtractResponse>("/agent/extract", { method: "POST", body: form }),
  download: (id: string, evidenceId: string) =>
    requestBinary(
      `/cases/${encodeURIComponent(id)}/evidence/${encodeURIComponent(evidenceId)}/download`,
    ),
  exportArchive: (id: string, revision: number) =>
    requestBinary(
      `/cases/${encodeURIComponent(id)}/export?revision=${revision}`,
    ),
  search: (query: string) =>
    request<RequirementSearch>(
      `/search/requirements?q=${encodeURIComponent(query)}`,
    ),
  audit: () => request<AuditVerification>("/audit/verify"),
  history: (id: string) =>
    request<CaseHistory>(`/cases/${encodeURIComponent(id)}/history`),
  publishLineage: (id: string) =>
    request<{ graph_uri: string; triple_count: number }>(
      `/cases/${encodeURIComponent(id)}/lineage/publish`,
      { method: "POST" },
    ),
  receipt: (id: string, expected_revision: number) =>
    request<{ comment_id: string; revision: number }>(
      `/cases/${encodeURIComponent(id)}/automation/receipt`,
      json({ expected_revision }),
    ),
};
