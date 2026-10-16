/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * Licensed under Apache-2.0; see LICENSE. No warranties.
 */
import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  type RequirementSearch,
  type CaseHistory,
  type AuditVerification,
} from "./api";
import type { CaseDetail, User } from "./types";

export function DataServices({
  detail,
  user,
  openCase,
  onReceipt,
}: {
  detail: CaseDetail;
  user: User;
  openCase: (id: string) => void;
  onReceipt: () => Promise<boolean>;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RequirementSearch>();
  const [history, setHistory] = useState<CaseHistory>();
  const [audit, setAudit] = useState<AuditVerification>();
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const coordinator = user.roles.includes("coordinator");

  useEffect(() => {
    let active = true;
    setHistory(undefined);
    api
      .history(detail.id)
      .then((value) => {
        if (active) setHistory(value);
      })
      .catch((value) => {
        if (active)
          setError(
            value instanceof Error ? value.message : "Không đọc được lịch sử",
          );
      });
    return () => {
      active = false;
    };
  }, [detail.id, detail.current_revision, detail.status]);

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    setMessage("");
    try {
      await operation();
    } catch (value) {
      setError(
        value instanceof Error
          ? value.message
          : "Dịch vụ chưa xác nhận thao tác",
      );
    } finally {
      setBusy(false);
    }
  }
  function search(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      setResults(await api.search(query.trim()));
    });
  }

  return (
    <section className="panel history-panel data-services">
      <div className="panel-head">
        <h3>Dữ liệu, đồng bộ và kiểm chứng</h3>
        <span>Phạm vi: {user.tenant_id}</span>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      <form className="inline-form" onSubmit={search}>
        <label className="field">
          <span>Tìm yêu cầu trong đơn vị</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            maxLength={120}
            placeholder="Từ khóa trong yêu cầu hiện tại"
          />
        </label>
        <button className="button ghost" disabled={busy || !query.trim()}>
          Tìm toàn văn
        </button>
      </form>
      {results && (
        <div className="notice-results">
          {results.results.length ? (
            results.results.map((row) => (
              <button
                className="notice-choice"
                key={`${row.case_id}-${row.requirement_key}`}
                onClick={() => openCase(row.case_id)}
              >
                <strong>
                  {row.requirement_key} · {row.title}
                </strong>
                <span>
                  {row.case_title} · {row.source_ref}
                </span>
              </button>
            ))
          ) : (
            <p>Không tìm thấy yêu cầu hiện tại phù hợp trong đơn vị của bạn.</p>
          )}
        </div>
      )}
      <div className="heading-actions data-actions">
        <button
          className="button ghost"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              setHistory(await api.history(detail.id));
            })
          }
        >
          Đọc lại lịch sử
        </button>
        {coordinator && (
          <>
            <button
              className="button ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const value = await api.publishLineage(detail.id);
                  setMessage(
                    `Đã ghi ${value.triple_count} triple vào kho RDF riêng. Graph: ${value.graph_uri}`,
                  );
                })
              }
            >
              Ghi đồ thị vào Fuseki
            </button>
            <button
              className="button ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setAudit(await api.audit());
                })
              }
            >
              Kiểm tra chuỗi nhật ký
            </button>
            <button
              className="button dark"
              disabled={busy || detail.status !== "approved"}
              onClick={() =>
                void run(async () => {
                  if (await onReceipt())
                    setMessage(
                      `n8n đã ghi biên nhận R${detail.current_revision}. Trao đổi đã được cập nhật; đây không phải biên nhận nộp thầu.`,
                    );
                })
              }
            >
              Gửi biên nhận qua n8n
            </button>
          </>
        )}
      </div>
      {audit && (
        <p className="notice" role="status">
          {audit.valid ? "Chuỗi băm hợp lệ" : "Phát hiện đứt hoặc sửa chuỗi"} ·{" "}
          {audit.event_count} sự kiện.
          {audit.broken_event_id && (
            <>
              {" "}
              Sự kiện cần kiểm tra: <code>{audit.broken_event_id}</code>.
            </>
          )}{" "}
          Kiểm tra toàn vẹn này không thay thế chữ ký số hay chứng cứ pháp lý.
        </p>
      )}
      <h4>Ảnh chụp sau phê duyệt · DuckDB / Parquet</h4>
      {!history ? (
        <p className="muted">Đang đọc lịch sử…</p>
      ) : history.snapshots.length === 0 ? (
        <p className="muted">
          Chưa có ảnh chụp. Worker ghi lịch sử sau sự kiện phê duyệt; dùng “Đọc
          lại lịch sử” khi sự kiện đã được xử lý.
        </p>
      ) : (
        <div className="history-list">
          {history.snapshots.map((snapshot) => (
            <details key={snapshot.revision_number}>
              <summary>
                R{snapshot.revision_number} ·{" "}
                {new Date(snapshot.captured_at).toLocaleString("vi-VN")} · SHA{" "}
                {snapshot.content_sha256.slice(0, 12)}
              </summary>
              <pre className="lineage" tabIndex={0}>
                {JSON.stringify(snapshot.payload, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      )}
      <p className="field-note">
        Đồ thị và ảnh chụp thuộc đơn vị hiện tại, không công khai theo metadata
        TED. Connector n8n cần profile automation đã được kích hoạt.
      </p>
    </section>
  );
}
