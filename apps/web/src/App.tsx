/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * Licensed under Apache-2.0; see LICENSE. No warranties.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import { DataServices } from "./DataServices";
import type {
  AgentResponse,
  Analytics,
  CaseDetail,
  CaseSummary,
  ExtractResponse,
  Requirement,
  RequirementKind,
  User,
} from "./types";
import "./styles.css";

type Tab = "H" | "P" | "D" | "I";
type Mutation = (
  operation: () => Promise<unknown>,
  message: string,
) => Promise<boolean>;
type ViewProps = { detail: CaseDetail; user: User; mutate: Mutation };
type RequirementDraft = Omit<
  Requirement,
  "id" | "revision" | "status" | "evidence_ids"
>;
const REPO = "https://github.com/EngLandLee/BidWeave";
const STATIC = import.meta.env.VITE_STATIC_SITE === "true";
const tabs: { key: Tab; label: string }[] = [
  { key: "H", label: "Cộng tác" },
  { key: "P", label: "Quy trình" },
  { key: "D", label: "Minh chứng" },
  { key: "I", label: "Trợ lý" },
];
const labels: Record<string, string> = {
  draft: "Bản nháp",
  in_review: "Đang xét duyệt",
  approved: "Đã duyệt",
  approve: "Chấp thuận",
  reject: "Yêu cầu sửa",
  pending: "Chờ duyệt",
  superseded: "Đã thay thế",
  verified: "Đã xác nhận",
  needs_review: "Cần xác nhận",
  missing: "Chưa đáp ứng",
  open: "Đang mở",
  done: "Hoàn thành",
  historical: "Phiên bản cũ",
};
type ThemePreference = "light" | "dark" | "system";
type ThemeState = {
  preference: ThemePreference;
  resolved: "light" | "dark";
  setPreference: (preference: ThemePreference) => void;
};
function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem("bidweave.theme");
    if (stored === "light" || stored === "dark" || stored === "system")
      return stored;
    const cookie = document.cookie
      .split("; ")
      .find((entry) => entry.startsWith("bidweave-theme="))
      ?.split("=")[1];
    return cookie === "light" || cookie === "dark" || cookie === "system"
      ? cookie
      : "system";
  } catch {
    return "system";
  }
}
function resolveTheme(preference: ThemePreference): "light" | "dark" {
  if (preference !== "system") return preference;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}
function useThemePreference(): ThemeState {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    readThemePreference(),
  );
  const [resolved, setResolved] = useState<"light" | "dark">(() =>
    resolveTheme(preference),
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => setResolved(resolveTheme(preference));
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [preference]);
  const setPreference = (next: ThemePreference) => {
    setPreferenceState(next);
    setResolved(resolveTheme(next));
    try {
      window.localStorage.setItem("bidweave.theme", next);
      document.cookie = `bidweave-theme=${next}; Path=/; SameSite=Lax${
        window.location.protocol === "https:" ? "; Secure" : ""
      }`;
    } catch {
      // A blocked storage environment still follows the in-memory preference.
    }
  };
  return { preference, resolved, setPreference };
}
function ThemeSelect({ theme }: { theme: ThemeState }) {
  return (
    <label className="theme-select">
      <span>Giao diện</span>
      <select
        aria-label="Chọn giao diện"
        value={theme.preference}
        onChange={(event) =>
          theme.setPreference(event.target.value as ThemePreference)
        }
      >
        <option value="system">Theo hệ thống</option>
        <option value="light">Sáng</option>
        <option value="dark">Tối</option>
      </select>
    </label>
  );
}
function Mark() {
  return (
    <svg
      className="mark"
      width="32"
      height="32"
      viewBox="0 0 40 40"
      aria-hidden="true"
    >
      <path
        d="M5 8h30v24H5zM10 14h16M10 20h20M10 26h12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path d="m29 10 5 5-8 8-5 1 1-5z" fill="currentColor" />
    </svg>
  );
}
function Spinner() {
  return <span className="spinner" role="status" aria-label="Đang xử lý" />;
}
function ErrorNotice({ error }: { error: unknown }) {
  const notice = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice.current?.closest("dialog[open]")) notice.current.focus();
  }, [error]);
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Không thể hoàn tất yêu cầu.";
  return (
    <div ref={notice} className="notice error" role="alert" tabIndex={-1}>
      <strong>
        {error instanceof ApiError && error.status === 409
          ? "Dữ liệu hoặc trạng thái đã thay đổi."
          : "Yêu cầu chưa được thực hiện."}
      </strong>
      <span>{message}</span>
    </div>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span className={`status status-${value.replaceAll("_", "-")}`}>
      {labels[value] || value}
    </span>
  );
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal wide"
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="button ghost small" onClick={onClose} type="button">
          Đóng
        </button>
      </div>
      {children}
    </dialog>
  );
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
function localDate(value: string) {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function draftOf(req: Requirement): RequirementDraft {
  return {
    key: req.key,
    title: req.title,
    description: req.description || "",
    kind: req.kind,
    minimum: req.minimum,
    mandatory: req.mandatory,
    source_ref: req.source_ref,
    owner: req.owner,
  };
}

export function App() {
  return /\/app(?:\/|$)/.test(window.location.pathname) ? (
    <Workspace />
  ) : (
    <Landing />
  );
}
function Landing() {
  const auth = useAuth();
  return (
    <main className="landing">
      <nav className="landing-nav" aria-label="Điều hướng chính">
        <a className="brand" href={import.meta.env.BASE_URL}>
          <Mark />
          BidWeave
        </a>
        <div className="nav-links">
          <a href={REPO}>Mã nguồn</a>
          <a href={`${REPO}/tree/main/docs`}>Tài liệu</a>
          {STATIC ? (
            <a className="button dark" href={`${REPO}#chạy-cục-bộ`}>
              Hướng dẫn chạy
            </a>
          ) : (
            <button className="button dark" onClick={auth.login}>
              Mở không gian làm việc
            </button>
          )}
        </div>
      </nav>
      <section className="hero">
        <div className="hero-copy">
          <h1>
            Yêu cầu đổi.
            <br />
            Hồ sơ vẫn
            <br />
            đúng phiên bản.
          </h1>
          <p className="hero-lede">
            Kết nối từng yêu cầu với minh chứng, người phụ trách và quyết định
            phê duyệt. Khi hồ sơ mời thầu thay đổi, biết chính xác phần việc
            phải xem lại.
          </p>
          <div className="hero-actions">
            {STATIC ? (
              <a
                className="button rust"
                href={`${REPO}/blob/main/docs/operations.md`}
              >
                Chạy BidWeave từ mã nguồn
              </a>
            ) : (
              <button className="button rust" onClick={auth.login}>
                Đăng nhập SSO
              </button>
            )}
            <a className="text-link" href="#mechanism">
              Tìm hiểu cách hoạt động
            </a>
          </div>
          <p className="hero-note">
            Apache‑2.0 · Thiết kế headless · Con người giữ quyền phê duyệt
          </p>
          {STATIC && (
            <p className="field-note">
              Đây là trang giới thiệu GitHub Pages. Backend và SSO chạy trong
              môi trường triển khai của bạn.
            </p>
          )}
          {auth.error && !STATIC && <ErrorNotice error={auth.error} />}
        </div>
        <article
          className="hero-sheet"
          aria-label="Ví dụ minh họa, không phải hồ sơ thật"
        >
          <div className="sheet-top">
            <span>VÍ DỤ TỔNG HỢP</span>
            <span>R1 → R2</span>
          </div>
          <h2>Dịch vụ hỗ trợ CNTT</h2>
          <p className="sheet-meta">Một thay đổi. Đúng phần việc cần mở lại.</p>
          <div className="sheet-line">
            <strong>Kinh nghiệm tương tự</strong>
            <span>2 → 3 dự án</span>
          </div>
          <div className="sheet-line">
            <strong>Minh chứng năng lực</strong>
            <Status value="needs_review" />
          </div>
          <div className="sheet-line">
            <strong>Phê duyệt R1</strong>
            <Status value="historical" />
          </div>
          <div className="sheet-footer">
            <span>Lịch sử được giữ nguyên.</span>
            <span>Không tự duyệt R2.</span>
          </div>
        </article>
      </section>
      <section id="mechanism" className="landing-section">
        <div>
          <h2>Từ tài liệu rời rạc đến công việc có căn cứ.</h2>
        </div>
        <div className="mechanism-grid">
          {[
            [
              "H",
              "Cộng tác có người chịu trách nhiệm",
              "Phân công, trao đổi và theo dõi công việc ngay trên hồ sơ.",
            ],
            [
              "P",
              "Phê duyệt đúng phiên bản",
              "SSO và workflow độc lập ngăn tự duyệt hoặc dùng quyết định đã cũ.",
            ],
            [
              "D",
              "Minh chứng truy lại được",
              "Nguồn tài liệu, mã băm, lịch sử sửa đổi và dữ liệu TED liên kết.",
            ],
            [
              "I",
              "Agent hỗ trợ, không quyết định thay",
              "Đề xuất có nguồn, công cụ MCP theo quyền và kiểm tra bởi con người.",
            ],
          ].map(([letter, title, text]) => (
            <div key={letter}>
              <b>{letter}</b>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="landing-proof">
        <div>
          <h2>Mở mã nguồn. Rõ ranh giới.</h2>
          <p>
            BidWeave tích hợp Keycloak, APISIX, PostgreSQL và Flowable. Dữ liệu
            ví dụ được ghi rõ là tổng hợp; sản phẩm không chứng nhận tính hợp
            pháp hay bảo đảm trúng thầu.
          </p>
        </div>
        <a
          className="text-link"
          href={`${REPO}/blob/main/docs/architecture.md`}
        >
          Đọc kiến trúc ba tầng
        </a>
      </section>
      <footer>
        <span>BidWeave · OLP Phần mềm nguồn mở 2026</span>
        <a href={`${REPO}/blob/main/docs/licensing.md`}>
          Giấy phép và nguồn tích hợp
        </a>
      </footer>
    </main>
  );
}

function Workspace() {
  const auth = useAuth();
  const theme = useThemePreference();
  const [user, setUser] = useState<User>();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [detail, setDetail] = useState<CaseDetail>();
  const [analytics, setAnalytics] = useState<Analytics>();
  const [tab, setTab] = useState<Tab>("P");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [proposed, setProposed] = useState<RequirementDraft[]>();
  const sequence = useRef(0);
  const load = useCallback(async (caseId?: string) => {
    const generation = ++sequence.current;
    setError(undefined);
    try {
      const [me, rows, stats] = await Promise.all([
        api.me(),
        api.cases(),
        api.analytics(),
      ]);
      const id = caseId || rows[0]?.id;
      const selected = id ? await api.detail(id) : undefined;
      if (generation !== sequence.current) return;
      setUser(me);
      setCases(rows);
      setAnalytics(stats);
      setDetail(selected);
    } catch (e) {
      if (generation === sequence.current) setError(e);
    } finally {
      if (generation === sequence.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (auth.ready && auth.authenticated) void load();
    else if (auth.ready) setLoading(false);
  }, [auth.ready, auth.authenticated, load]);
  const mutate: Mutation = async (operation, success) => {
    setError(undefined);
    try {
      await operation();
      await load(detail?.id);
      setMessage(success);
      return true;
    } catch (e) {
      setError(e);
      return false;
    }
  };
  if (auth.error)
    return (
      <div className="app-shell center-state" data-bw-theme={theme.resolved}>
        <ErrorNotice error={auth.error} />
        <a className="button dark" href={import.meta.env.BASE_URL}>
          Về trang giới thiệu
        </a>
      </div>
    );
  if (!auth.ready || loading)
    return (
      <div className="app-shell center-state" data-bw-theme={theme.resolved}>
        <Spinner />
        <p>Đang kết nối SSO và dữ liệu…</p>
      </div>
    );
  if (!auth.authenticated)
    return (
      <div className="app-shell center-state" data-bw-theme={theme.resolved}>
        <h1>Không gian BidWeave</h1>
        <button className="button dark" onClick={auth.login}>
          Đăng nhập
        </button>
      </div>
    );
  return (
    <div className="app-shell" data-bw-theme={theme.resolved}>
      <aside className="sidebar">
        <a className="brand" href={import.meta.env.BASE_URL}>
          <Mark />
          BidWeave
        </a>
        <div className="side-context">
          <span>Đơn vị</span>
          <strong>{user?.tenant_id || "Đang kết nối"}</strong>
        </div>
        <nav aria-label="Không gian HPDI">
          {tabs.map((item) => (
            <button
              className={`nav-item ${tab === item.key ? "active" : ""}`}
              key={item.key}
              onClick={() => setTab(item.key)}
              aria-current={tab === item.key ? "page" : undefined}
            >
              <span className="nav-key">{item.key}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="user-chip">
            <span className="avatar">
              {user?.username.slice(0, 1).toUpperCase()}
            </span>
            <span>
              <strong>{user?.username}</strong>
              <small>
                {user?.roles
                  .filter((r) =>
                    ["coordinator", "reviewer", "contributor"].includes(r),
                  )
                  .join(" · ")}
              </small>
            </span>
          </div>
          <button className="text-button" onClick={auth.logout}>
            Đăng xuất
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="workspace-header">
          <h1>{detail?.title || "Hồ sơ dự thầu"}</h1>
          <div className="header-actions">
            <Field label="Chọn hồ sơ">
              <select
                value={detail?.id || ""}
                onChange={(e) => {
                  setProposed(undefined);
                  void load(e.target.value);
                }}
                disabled={!cases.length}
              >
                <option value="">Chọn hồ sơ</option>
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </Field>
            <ThemeSelect theme={theme} />
            {user?.roles.includes("coordinator") && (
              <button
                className="button rust"
                onClick={() => setShowCreate(true)}
              >
                Tạo hồ sơ
              </button>
            )}
            <button
              className="button ghost"
              onClick={() => void load(detail?.id)}
            >
              Làm mới
            </button>
          </div>
        </header>
        {error !== undefined && <ErrorNotice error={error} />}
        {!detail && (
          <Empty title="Chưa có hồ sơ">
            <p>
              Tạo hồ sơ đầu tiên để kết nối yêu cầu, minh chứng và quy trình
              duyệt.
            </p>
          </Empty>
        )}
        {detail && user && (
          <div key={detail.id}>
            {tab === "H" && (
              <TeamView detail={detail} user={user} mutate={mutate} />
            )}
            {tab === "P" && (
              <ProcessView
                detail={detail}
                user={user}
                mutate={mutate}
                error={error}
                proposed={proposed}
                clearProposal={() => setProposed(undefined)}
              />
            )}
            {tab === "D" && (
              <DataView
                detail={detail}
                user={user}
                mutate={mutate}
                openCase={(id) => {
                  setProposed(undefined);
                  void load(id);
                }}
              />
            )}{" "}
            {tab === "I" && (
              <IntelligenceView
                detail={detail}
                user={user}
                propose={(rows) => {
                  setProposed(rows);
                  setTab("P");
                }}
              />
            )}
          </div>
        )}
        {analytics && (
          <footer className="workspace-foot">
            <span>{analytics.case_count} hồ sơ</span>
            <span>{analytics.open_tasks} việc đang mở</span>
            <span>
              {analytics.verified_requirements}/{analytics.requirements_count}{" "}
              yêu cầu đáp ứng
            </span>
            <span>{analytics.approved_count} hồ sơ đã duyệt</span>
          </footer>
        )}
      </main>
      {showCreate && (
        <CreateCase
          onClose={() => setShowCreate(false)}
          onCreated={async (id) => {
            setShowCreate(false);
            setTab("P");
            await load(id);
          }}
        />
      )}{" "}
      {message && (
        <div className="toast" role="status">
          <span>{message}</span>
          <button aria-label="Đóng thông báo" onClick={() => setMessage("")}>
            Đóng
          </button>
        </div>
      )}
    </div>
  );
}
function CreateCase({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [deadline, setDeadline] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const c = await api.createCase({
        title,
        deadline: new Date(deadline).toISOString(),
        description,
      });
      await onCreated(c.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Tạo hồ sơ dự thầu" onClose={onClose}>
      <form onSubmit={submit}>
        {error !== undefined && <ErrorNotice error={error} />}
        <Field label="Tên hồ sơ">
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={500}
          />
        </Field>
        <Field label="Hạn nộp (giờ địa phương)">
          <input
            required
            type="datetime-local"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </Field>
        <Field label="Mô tả phạm vi">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
        </Field>
        <div className="modal-actions">
          <button className="button rust" disabled={busy}>
            {busy ? <Spinner /> : "Tạo hồ sơ"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function TeamView({ detail, user, mutate }: ViewProps) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    if (
      await mutate(
        () => api.comment(detail.id, comment.trim()),
        "Đã thêm trao đổi",
      )
    )
      setComment("");
    setBusy(false);
  };
  return (
    <section className="view">
      <div className="view-heading">
        <div>
          <h2>Cộng tác trên từng thay đổi</h2>
          <p className="lede">
            Hoàn thành công việc không thay thế việc xác nhận minh chứng.
          </p>
        </div>
        <span className="revision-tag">R{detail.current_revision}</span>
      </div>
      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <h3>Công việc cần xử lý</h3>
            <span>
              {detail.tasks.filter((t) => t.status === "open").length} đang mở
            </span>
          </div>
          {detail.tasks.length ? (
            <ul className="task-list">
              {detail.tasks.map((task) => (
                <li key={task.id}>
                  <input
                    type="checkbox"
                    aria-label={`Hoàn thành: ${task.title}`}
                    checked={task.status === "done"}
                    onChange={(e) =>
                      void mutate(
                        () =>
                          api.task(detail.id, task.id, {
                            status: e.target.checked ? "done" : "open",
                          }),
                        "Đã cập nhật công việc",
                      )
                    }
                  />
                  <span>
                    <strong>{task.title}</strong>
                    <small>
                      R{task.revision} · {task.assignee || "Chưa phân công"}
                    </small>
                  </span>
                  <button
                    className="button tiny"
                    onClick={() =>
                      void mutate(
                        () =>
                          api.task(detail.id, task.id, {
                            status: task.status,
                            assignee: user.id,
                          }),
                        "Đã nhận việc",
                      )
                    }
                  >
                    Nhận việc
                  </button>
                  <Status value={task.status} />
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="Chưa phát sinh công việc" />
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <h3>Trao đổi và bàn giao</h3>
          </div>
          <div className="comment-list">
            {detail.comments.map((c) => (
              <article key={c.id}>
                <div className="comment-meta">
                  <strong>
                    {c.author === user.id
                      ? user.username
                      : c.author.slice(0, 12)}
                  </strong>
                  <time>{formatDate(c.created_at)}</time>
                </div>
                <p>{c.body}</p>
              </article>
            ))}
          </div>
          <form className="comment-form" onSubmit={submit}>
            <Field label="Nội dung trao đổi">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                required
                rows={3}
                maxLength={10000}
              />
            </Field>
            <button className="button dark" disabled={busy || !comment.trim()}>
              Gửi trao đổi
            </button>
          </form>
        </section>
      </div>
    </section>
  );
}
function ProcessView({
  detail,
  user,
  mutate,
  proposed,
  clearProposal,
  error,
}: ViewProps & {
  proposed?: RequirementDraft[];
  clearProposal: () => void;
  error: unknown;
}) {
  const [editing, setEditing] = useState(false);
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const coordinator = user.roles.includes("coordinator");
  const reviewer = user.roles.includes("reviewer");
  const review = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    await mutate(
      () =>
        api.review(detail.id, {
          expected_revision: detail.current_revision,
          decision,
          comment: note,
        }),
      "Đã ghi nhận quyết định",
    );
    setBusy(false);
  };
  const currentImpact = detail.impact.filter(
    (i) => i.revision === detail.current_revision,
  );
  return (
    <section className="view">
      <div className="view-heading">
        <div>
          <h2>
            Phiên bản R{detail.current_revision}{" "}
            <Status value={detail.status} />
          </h2>
          <p className="lede">
            Hạn nộp: {formatDate(detail.deadline)}. Phê duyệt chỉ có giá trị với
            đúng phiên bản.
          </p>
        </div>
        {coordinator && (
          <div className="heading-actions">
            <button
              className="button rust"
              disabled={
                detail.status !== "draft" || detail.current_revision === 0
              }
              onClick={() =>
                void mutate(
                  () => api.submit(detail.id, detail.current_revision),
                  "Đã gửi workflow xét duyệt",
                )
              }
            >
              Gửi xét duyệt
            </button>
            <button className="button ghost" onClick={() => setEditing(true)}>
              {detail.current_revision
                ? "Tạo bản sửa đổi"
                : "Thêm yêu cầu đầu tiên"}
            </button>
          </div>
        )}
      </div>
      {proposed && (
        <div className="notice">
          <span>
            Agent đề xuất {proposed.length} yêu cầu. Cần kiểm tra, bổ sung
            ngưỡng và nguồn trước khi lưu.
          </span>
          <button className="button ghost" onClick={() => setEditing(true)}>
            Rà soát đề xuất
          </button>
        </div>
      )}
      <div className="process-grid">
        <section className="panel">
          <div className="panel-head">
            <h3>Ma trận yêu cầu</h3>
            <span>{detail.requirements.length} mục</span>
          </div>
          {detail.requirements.map((req) => (
            <div className="requirement-row" key={req.key}>
              <span
                aria-label={
                  currentImpact.some((i) => i.requirement_key === req.key)
                    ? "Có thay đổi"
                    : undefined
                }
                className={
                  currentImpact.some((i) => i.requirement_key === req.key)
                    ? "change-marker"
                    : ""
                }
              />
              <span className="req-key mono">{req.key}</span>
              <span className="req-main">
                <strong>{req.title}</strong>
                <small>
                  {req.kind}
                  {req.minimum != null ? ` ≥ ${req.minimum}` : ""} ·{" "}
                  {req.mandatory ? "Bắt buộc" : "Tùy chọn"} · {req.owner}
                </small>
                <small>{req.source_ref}</small>
              </span>
              <Status value={req.status} />
            </div>
          ))}
          {!detail.requirements.length && (
            <Empty title="Chưa có yêu cầu">
              <p>Tạo phiên bản đầu tiên trước khi tải minh chứng.</p>
            </Empty>
          )}
        </section>
        <section className="panel decision-panel">
          <h3>Xét duyệt độc lập</h3>
          {reviewer ? (
            <form onSubmit={review}>
              <p className="muted">
                Không thể tự duyệt hồ sơ do mình tạo hoặc gửi. Backend kiểm tra
                vai trò, phiên bản và workflow.
              </p>
              <Field label="Quyết định">
                <select
                  value={decision}
                  onChange={(e) =>
                    setDecision(e.target.value as "approve" | "reject")
                  }
                >
                  <option value="approve">Chấp thuận</option>
                  <option value="reject">Yêu cầu sửa</option>
                </select>
              </Field>
              <Field label="Căn cứ quyết định">
                <textarea
                  required
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={4}
                />
              </Field>
              <button
                className="button dark"
                disabled={
                  busy ||
                  detail.status !== "in_review" ||
                  detail.owner_id === user.id
                }
              >
                Ghi nhận quyết định
              </button>
            </form>
          ) : (
            <p className="muted">
              Người có vai trò reviewer thực hiện bước này.
            </p>
          )}
          {detail.workflow_id && (
            <small className="mono">Workflow: {detail.workflow_id}</small>
          )}
        </section>
      </div>
      {currentImpact.length > 0 && (
        <section className="panel history-panel">
          <h3>Ảnh hưởng của phiên bản hiện tại</h3>
          <ul>
            {currentImpact.map((i) => (
              <li key={i.id}>
                <strong>{i.requirement_key}</strong> — {i.detail}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel history-panel">
        <h3>Lịch sử, không ghi đè</h3>
        <div className="history-list">
          {detail.revisions.map((r) => (
            <article key={r.id}>
              <strong>
                R{r.number} · {r.reason}
              </strong>
              <small>
                {formatDate(r.created_at)} · hạn nộp {formatDate(r.deadline)}
              </small>
              {detail.approvals
                .filter((a) => a.revision === r.number)
                .map((a) => (
                  <p key={a.id}>
                    <Status value={a.decision} />{" "}
                    {a.comment || "Đang chờ quyết định"}{" "}
                    <small>· {a.reviewer_id.slice(0, 12)}</small>
                  </p>
                ))}
            </article>
          ))}
        </div>
      </section>
      {editing && (
        <RevisionEditor
          detail={detail}
          proposed={proposed}
          error={error}
          onClose={() => setEditing(false)}
          onSave={async (body) => {
            const ok = await mutate(
              () => api.revision(detail.id, body),
              "Đã tạo phiên bản mới",
            );
            if (ok) {
              setEditing(false);
              clearProposal();
            }
            return ok;
          }}
        />
      )}
    </section>
  );
}
function RevisionEditor({
  detail,
  proposed,
  onClose,
  onSave,
  error,
}: {
  detail: CaseDetail;
  proposed?: RequirementDraft[];
  onClose: () => void;
  onSave: (body: unknown) => Promise<boolean>;
  error: unknown;
}) {
  const [deadline, setDeadline] = useState(localDate(detail.deadline));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState<RequirementDraft[]>(
    proposed || detail.requirements.map(draftOf),
  );
  const update = (index: number, patch: Partial<RequirementDraft>) =>
    setRows((old) =>
      old.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSave({
        expected_revision: detail.current_revision,
        deadline: new Date(deadline).toISOString(),
        reason,
        requirements: rows,
      });
    } finally {
      setBusy(false);
    }
  };
  const add = () =>
    setRows((old) => [
      ...old,
      {
        key: `R-${Date.now().toString().slice(-6)}`,
        title: "",
        description: "",
        kind: "document",
        mandatory: true,
        source_ref: "",
        owner: "contributor",
      },
    ]);
  return (
    <Modal
      title={`Soạn phiên bản R${detail.current_revision + 1}`}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        {error !== undefined && <ErrorNotice error={error} />}
        <p className="revision-intro">
          Bản sửa đổi giữ nguyên lịch sử trước đó. Kiểm tra cả yêu cầu bị xóa,
          nguồn và hiệu lực của minh chứng.
        </p>
        <Field label="Hạn nộp mới (giờ địa phương)">
          <input
            type="datetime-local"
            required
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </Field>
        <Field label="Lý do thay đổi">
          <textarea
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
        </Field>
        <div className="editor-head">
          <h3>Yêu cầu và ràng buộc</h3>
          <button type="button" className="button ghost" onClick={add}>
            Thêm yêu cầu
          </button>
        </div>
        <div className="requirement-editor">
          {rows.map((row, index) => (
            <fieldset className="editor-row" key={index}>
              <legend>Yêu cầu {index + 1}</legend>
              <Field label="Mã ổn định">
                <input
                  required
                  value={row.key}
                  onChange={(e) => update(index, { key: e.target.value })}
                />
              </Field>
              <Field label="Tên yêu cầu">
                <input
                  required
                  value={row.title}
                  onChange={(e) => update(index, { title: e.target.value })}
                />
              </Field>
              <Field label="Loại">
                <select
                  value={row.kind}
                  onChange={(e) =>
                    update(index, {
                      kind: e.target.value as RequirementKind,
                      minimum:
                        e.target.value === "count"
                          ? (row.minimum ?? 1)
                          : undefined,
                    })
                  }
                >
                  <option value="document">Tài liệu</option>
                  <option value="count">Số lượng</option>
                  <option value="validity">Hiệu lực</option>
                  <option value="text">Nội dung</option>
                </select>
              </Field>
              {row.kind === "count" && (
                <Field label="Ngưỡng tối thiểu">
                  <input
                    type="number"
                    min="1"
                    required
                    value={row.minimum ?? ""}
                    onChange={(e) =>
                      update(index, { minimum: Number(e.target.value) })
                    }
                  />
                </Field>
              )}
              <Field label="Người phụ trách">
                <input
                  required
                  value={row.owner}
                  onChange={(e) => update(index, { owner: e.target.value })}
                />
              </Field>
              <Field label="Vị trí nguồn">
                <input
                  required
                  value={row.source_ref}
                  onChange={(e) =>
                    update(index, { source_ref: e.target.value })
                  }
                />
              </Field>
              <Field label="Nội dung / cách hiểu">
                <textarea
                  value={row.description || ""}
                  onChange={(e) =>
                    update(index, { description: e.target.value })
                  }
                />
              </Field>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={row.mandatory}
                  onChange={(e) =>
                    update(index, { mandatory: e.target.checked })
                  }
                />{" "}
                Bắt buộc
              </label>
              <button
                type="button"
                className="button ghost small"
                onClick={() =>
                  setRows((old) => old.filter((_, i) => i !== index))
                }
              >
                Xóa yêu cầu
              </button>
            </fieldset>
          ))}
        </div>
        <div className="modal-actions">
          <button className="button rust" disabled={busy || !rows.length}>
            {busy ? <Spinner /> : "Lưu phiên bản"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function DataView({
  detail,
  user,
  mutate,
  openCase,
}: ViewProps & { openCase: (id: string) => void }) {
  const [requirement, setRequirement] = useState("");
  const [file, setFile] = useState<File>();
  const [quantity, setQuantity] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [lineage, setLineage] = useState<Record<string, unknown>>();
  const [preview, setPreview] = useState<{ filename: string; text: string }>();
  const [notice, setNotice] = useState("");
  const [tedDate, setTedDate] = useState("2024-11-04");
  const [notices, setNotices] =
    useState<
      Array<{
        publication_number: string;
        cpv_label: string;
        source_graph: string;
      }>
    >();
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    const data = new FormData();
    data.append("file", file);
    data.append("requirement_key", requirement);
    data.append("expected_revision", String(detail.current_revision));
    if (quantity) data.append("quantity", quantity);
    if (validUntil) data.append("valid_until", `${validUntil}T23:59:59Z`);
    data.append("notes", notes);
    if (
      await mutate(
        () => api.evidence(detail.id, data),
        "Đã quét và lưu minh chứng",
      )
    ) {
      setFile(undefined);
      if (inputRef.current) inputRef.current.value = "";
    }
    setBusy(false);
  };
  const save = async (operation: () => Promise<Blob>, filename: string) => {
    setError(undefined);
    setBusy(true);
    try {
      const blob = await operation();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const inspect = async (id: string) => {
    try {
      setPreview(await api.preview(detail.id, id));
    } catch (e) {
      setError(e);
    }
  };
  const findNotices = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.notices(tedDate);
      setNotices(result.notices);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="view">
      <div className="view-heading">
        <div>
          <h2>Minh chứng có nguồn gốc</h2>
          <p className="lede">
            Chỉ minh chứng được người khác xác nhận ở phiên bản hiện tại mới
            tham gia kiểm tra đáp ứng.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button ghost"
            onClick={() =>
              void api.lineage(detail.id).then(setLineage).catch(setError)
            }
          >
            Xem liên kết dữ liệu
          </button>
          <button
            className="button dark"
            disabled={busy || detail.status !== "approved"}
            onClick={() =>
              void save(
                () => api.exportArchive(detail.id, detail.current_revision),
                `bidweave-r${detail.current_revision}.tar.gz`,
              )
            }
          >
            Xuất gói đã duyệt
          </button>
        </div>
      </div>
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="evidence-layout">
        <section className="panel evidence-matrix">
          <div className="panel-head">
            <h3>Yêu cầu và tệp minh chứng</h3>
            <span>R{detail.current_revision}</span>
          </div>
          {detail.requirements.map((req) => (
            <article className="matrix-row" key={req.key}>
              <div>
                <span className="req-key mono">{req.key}</span>
                <strong>{req.title}</strong>
                <Status value={req.status} />
                <small>
                  {req.minimum != null
                    ? `Ngưỡng tối thiểu: ${req.minimum}`
                    : req.kind}
                </small>
              </div>
              <div>
                {detail.evidence
                  .filter((ev) => ev.requirement_key === req.key)
                  .map((ev) => {
                    const current = ev.revision === detail.current_revision;
                    return (
                      <div className="file-row" key={ev.id}>
                        <span className="file-icon">TỆP</span>
                        <span>
                          <strong>{ev.filename}</strong>
                          <small>
                            R{ev.revision} · SHA {ev.sha256.slice(0, 12)}
                          </small>
                          {ev.valid_until && (
                            <small>
                              Hiệu lực: {formatDate(ev.valid_until)}
                            </small>
                          )}
                          {ev.quantity != null && (
                            <small>Số lượng: {ev.quantity}</small>
                          )}
                          <Status
                            value={
                              !current
                                ? "historical"
                                : ev.verified
                                  ? "verified"
                                  : "needs_review"
                            }
                          />
                        </span>
                        <div className="file-actions">
                          {user.roles.includes("reviewer") &&
                            ev.uploaded_by !== user.id &&
                            (!current || !ev.verified) &&
                            detail.status !== "approved" && (
                              <button
                                className="button tiny"
                                onClick={() =>
                                  void mutate(
                                    () =>
                                      api.verify(
                                        detail.id,
                                        ev.id,
                                        detail.current_revision,
                                      ),
                                    "Đã xác nhận minh chứng ở phiên bản hiện tại",
                                  )
                                }
                              >
                                {current ? "Xác nhận" : "Xác nhận lại"}
                              </button>
                            )}
                          <button
                            className="button ghost tiny"
                            onClick={() => void inspect(ev.id)}
                          >
                            Đọc
                          </button>
                          <button
                            className="button ghost tiny"
                            onClick={() =>
                              void save(
                                () => api.download(detail.id, ev.id),
                                ev.filename,
                              )
                            }
                          >
                            Tải
                          </button>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </article>
          ))}
          {!detail.requirements.length && (
            <Empty title="Thêm yêu cầu ở không gian Quy trình trước" />
          )}
        </section>
        <form className="panel upload-panel" onSubmit={upload}>
          <h3>Bổ sung minh chứng</h3>
          <Field label="Yêu cầu liên quan">
            <select
              required
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
            >
              <option value="">Chọn yêu cầu</option>
              {detail.requirements.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.key} — {r.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Tệp gốc">
            <input
              ref={inputRef}
              type="file"
              required
              onChange={(e) => setFile(e.target.files?.[0])}
            />
          </Field>
          <Field label="Số lượng được chứng minh">
            <input
              type="number"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </Field>
          <Field label="Có hiệu lực đến hết ngày (UTC)">
            <input
              type="date"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
            />
          </Field>
          <Field label="Ghi chú và căn cứ">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </Field>
          <button
            className="button rust"
            disabled={busy || !file || detail.status === "approved"}
          >
            Quét và tải lên
          </button>
          <p className="field-note">
            Thông tin tự khai cần được reviewer kiểm tra. Tệp bị nhiễm hoặc dịch
            vụ quét lỗi không được đưa vào hồ sơ.
          </p>
        </form>
      </div>
      <section className="panel history-panel">
        <h3>Liên kết thông báo công khai TED</h3>
        <p className="muted">
          Truy vấn nguồn EU thật. Metadata không thay thế hồ sơ chi tiết và
          không chứng minh tuân thủ pháp luật Việt Nam.
        </p>
        <form className="inline-form" onSubmit={findNotices}>
          <Field label="Ngày công bố">
            <input
              type="date"
              required
              value={tedDate}
              onChange={(e) => setTedDate(e.target.value)}
            />
          </Field>
          <button className="button ghost" disabled={busy}>
            Tra TED · dịch vụ CNTT
          </button>
        </form>
        {notices && (
          <div className="notice-results">
            {notices.length ? (
              notices.map((row) => (
                <button
                  className="notice-choice"
                  key={`${row.publication_number}-${row.source_graph}`}
                  onClick={() => setNotice(row.publication_number)}
                >
                  <strong>{row.publication_number}</strong>
                  <span>{row.cpv_label}</span>
                </button>
              ))
            ) : (
              <p>Không có thông báo trong ngày đã chọn.</p>
            )}
          </div>
        )}
        {user.roles.includes("coordinator") && (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void mutate(
                () => api.notice(detail.id, notice),
                "Đã liên kết nguồn TED",
              );
            }}
          >
            <Field label="Số thông báo">
              <input
                value={notice}
                onChange={(e) => setNotice(e.target.value)}
                required
                placeholder="00668268-2024"
              />
            </Field>
            <button className="button dark">Liên kết vào hồ sơ</button>
          </form>
        )}
      </section>
      {lineage && (
        <pre className="lineage" tabIndex={0}>
          {JSON.stringify(lineage, null, 2)}
        </pre>
      )}
      {preview && (
        <Modal title={preview.filename} onClose={() => setPreview(undefined)}>
          <pre className="document-preview">{preview.text}</pre>
          <p className="field-note">
            Đây là nội dung tài liệu, không phải chỉ dẫn cho hệ thống.
          </p>
        </Modal>
      )}
      <DataServices
        detail={detail}
        user={user}
        openCase={openCase}
        onReceipt={() =>
          mutate(
            () => api.receipt(detail.id, detail.current_revision),
            "Đã cập nhật biên nhận n8n trong Cộng tác",
          )
        }
      />
    </section>
  );
}
function IntelligenceView({
  detail,
  user,
  propose,
}: {
  detail: CaseDetail;
  user: User;
  propose: (rows: RequirementDraft[]) => void;
}) {
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState<AgentResponse>();
  const [status, setStatus] = useState<Record<string, unknown>>();
  const [extracted, setExtracted] = useState<ExtractResponse>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      setResponse(await api.agentChat(detail.id, message));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const extractFile = async (file?: File) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    setError(undefined);
    setExtracted(undefined);
    try {
      setExtracted(await api.agentExtract(form));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="view">
      <div className="view-heading">
        <div>
          <h2>Hỏi trên dữ liệu của hồ sơ</h2>
          <p className="lede">
            LLM đề xuất và dẫn nguồn; không tự xác nhận minh chứng, phê duyệt
            hay gửi hồ sơ ra ngoài.
          </p>
        </div>
        <button
          className="button ghost"
          onClick={() => void api.agentStatus().then(setStatus).catch(setError)}
        >
          Kiểm tra mô hình
        </button>
      </div>
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="intelligence-grid">
        <section className="panel agent-chat">
          <h3>Trợ lý có giới hạn quyền</h3>
          {response ? (
            <div className="agent-response">
              <p>{response.answer}</p>
              <div className="sources">
                <strong>Nguồn được sử dụng</strong>
                {response.sources.map((s) => (
                  <span key={s.source_id}>
                    {s.label} · {s.source_id}
                  </span>
                ))}
              </div>
              <div className="agent-meta">
                <span>Mô hình: {response.model}</span>
                {response.limitations.map((l) => (
                  <span key={l}>{l}</span>
                ))}
              </div>
              {response.suggested_actions.map((a, i) => (
                <p className="muted" key={i}>
                  {a.title}: {a.rationale}
                </p>
              ))}
            </div>
          ) : (
            <Empty title="Chưa có câu hỏi">
              <p>Ví dụ: Những yêu cầu nào cần kiểm tra lại sau sửa đổi?</p>
            </Empty>
          )}
          <form className="agent-form" onSubmit={send}>
            <Field label="Câu hỏi cho Agent">
              <textarea
                required
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                maxLength={12000}
              />
            </Field>
            <button className="button dark" disabled={busy || !message.trim()}>
              {busy ? <Spinner /> : "Hỏi Agent"}
            </button>
          </form>
        </section>
        <section className="panel extract-panel">
          <h3>Trích xuất yêu cầu đề xuất</h3>
          <p className="muted">
            Chỉ tải tài liệu bạn có quyền xử lý. Đầu ra là bản nháp cần con
            người rà soát.
          </p>
          <Field label="Tài liệu PDF hoặc văn bản">
            <input
              type="file"
              accept=".pdf,.txt"
              disabled={busy}
              onChange={(e) => void extractFile(e.target.files?.[0])}
            />
          </Field>
          {extracted && (
            <div className="extract-result">
              <strong>{extracted.requirements.length} yêu cầu đề xuất</strong>
              {extracted.requirements.map((r) => (
                <div className="extract-row" key={r.key}>
                  <span>{r.key}</span>
                  <span>{r.title}</span>
                  <small>{r.source_ref}</small>
                </div>
              ))}
              <p className="field-note">
                {extracted.source} · {extracted.model}
              </p>
              {user.roles.includes("coordinator") && (
                <button
                  className="button rust"
                  disabled={!extracted.requirements.length}
                  onClick={() => propose(extracted.requirements)}
                >
                  Rà soát trong trình soạn phiên bản
                </button>
              )}
            </div>
          )}
          {status && (
            <pre className="status-json">{JSON.stringify(status, null, 2)}</pre>
          )}
        </section>
      </div>
    </section>
  );
}
