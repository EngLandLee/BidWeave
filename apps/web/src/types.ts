/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * API contract types shared by workspace views.
 */
export type Role = "coordinator" | "contributor" | "reviewer";
export type CaseStatus = "draft" | "in_review" | "approved";
export type RequirementKind = "document" | "count" | "validity" | "text";
export type RequirementStatus = "missing" | "needs_review" | "verified";
export interface User {
  id: string;
  username: string;
  tenant_id: string;
  roles: string[];
}
export interface CaseSummary {
  id: string;
  title: string;
  description?: string;
  deadline: string;
  current_revision: number;
  status: CaseStatus;
  owner_id: string;
  created_at: string;
}
export interface Requirement {
  id: string;
  key: string;
  title: string;
  description?: string;
  kind: RequirementKind;
  minimum?: number;
  mandatory: boolean;
  source_ref: string;
  owner: string;
  revision: number;
  status: RequirementStatus;
  evidence_ids: string[];
}
export interface Evidence {
  id: string;
  requirement_key: string;
  filename: string;
  sha256: string;
  valid_until?: string;
  quantity?: number;
  notes?: string;
  verified: boolean;
  uploaded_by: string;
  revision: number;
  created_at: string;
}
export interface Task {
  id: string;
  title?: string;
  requirement_key?: string;
  status: "open" | "done";
  assignee?: string;
  revision?: number;
}
export interface Comment {
  id: string;
  author: string;
  body: string;
  created_at: string;
}
export interface Revision {
  id: string;
  number: number;
  deadline: string;
  reason: string;
  created_at: string;
  created_by: string;
}
export interface Approval {
  id: string;
  decision: "approve" | "reject" | "pending" | "superseded";
  reviewer_id: string;
  comment: string;
  revision: number;
  created_at: string;
}
export interface Impact {
  id: string;
  revision: number;
  requirement_key: string;
  kind: string;
  detail: string;
}
export interface CaseDetail extends CaseSummary {
  requirements: Requirement[];
  evidence: Evidence[];
  tasks: Task[];
  comments: Comment[];
  revisions: Revision[];
  approvals: Approval[];
  impact: Impact[];
  workflow_id?: string;
}
export interface Analytics {
  case_count: number;
  approved_count: number;
  pending_review_count: number;
  open_tasks: number;
  requirements_count: number;
  verified_requirements: number;
  events: Array<{ type?: string; at?: string; label?: string }>;
}
export interface AgentResponse {
  answer: string;
  sources: Array<{ source_id: string; label: string; quote: string }>;
  suggested_actions: Array<{ type: string; title: string; rationale: string }>;
  model: string;
  limitations: string[];
}
export interface ExtractResponse {
  requirements: Array<
    Omit<Requirement, "id" | "revision" | "status" | "evidence_ids">
  >;
  source: string;
  needs_review: boolean;
  model: string;
}
