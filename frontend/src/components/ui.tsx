/** Shared UI primitives. Pages compose these instead of repeating class strings. */
import type { ButtonHTMLAttributes, ChangeEvent, ReactNode } from "react";
import { Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import type { ApplicationStatus } from "../applications";

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(" ");

// --- Formatting --------------------------------------------------------------------------

export const formatDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

export const formatDateTime = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

/** Display an extracted value: ISO dates as "25 Jul 2021", records as comma-separated fields. */
export function formatValue(value: unknown): string {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(`${value}T00:00:00`);
  if (value && typeof value === "object") return Object.values(value).join(", ");
  return String(value);
}

/** A human-readable case reference, e.g. "EoA/2026-27/2944A6". */
export function caseRef(app: { id: string; application_type: string; academic_year: string }) {
  const type = app.application_type === "extension_of_approval" ? "EoA" : app.application_type;
  return `${type}/${app.academic_year}/${app.id.slice(0, 6).toUpperCase()}`;
}

// --- Buttons -----------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "danger" | "approve" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink-hover",
  secondary: "border border-rule-strong bg-sheet text-ink hover:bg-paper",
  danger: "border border-fail/40 bg-sheet text-fail hover:bg-fail-soft",
  approve: "bg-pass text-white hover:brightness-110",
  ghost: "text-muted hover:bg-paper hover:text-ink",
};
const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
};

export const buttonClass = (variant: Variant = "secondary", size: Size = "md") =>
  cx(
    "inline-flex shrink-0 items-center justify-center rounded-[var(--radius-control)] font-medium",
    "transition-colors disabled:cursor-not-allowed disabled:opacity-45",
    VARIANTS[variant],
    SIZES[size],
  );

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button {...props} className={cx(buttonClass(variant, size), className)} />;
}

/** A file picker that looks like a button. */
export function FileButton({
  children,
  onFiles,
  multiple,
  disabled,
  variant = "secondary",
  size = "sm",
}: {
  children: ReactNode;
  onFiles: (e: ChangeEvent<HTMLInputElement>) => void;
  multiple?: boolean;
  disabled?: boolean;
  variant?: Variant;
  size?: Size;
}) {
  return (
    <label className={cx(buttonClass(variant, size), "cursor-pointer", disabled && "pointer-events-none opacity-45")}>
      {children}
      <input
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        multiple={multiple}
        disabled={disabled}
        onChange={onFiles}
        className="sr-only"
      />
    </label>
  );
}

// --- Layout pieces -----------------------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { to: string; label: string };
}) {
  return (
    <header className="mb-8">
      {back && (
        <Link to={back.to} className="mb-3 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <ArrowLeft size={15} aria-hidden />
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-[1.75rem] leading-tight font-bold tracking-[-0.015em]">{title}</h1>
          {description && <p className="mt-1.5 text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  id,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cx("rounded-[var(--radius-panel)] border bg-sheet", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3.5">
          {title && <h2 className="text-[15px] font-bold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-panel)] border border-dashed border-rule-strong px-6 py-12 text-center">
      <p className="font-bold">{title}</p>
      {body && <p className="mx-auto mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// --- Status ------------------------------------------------------------------------------

export type Tone = "pass" | "fail" | "review" | "neutral" | "stamp" | "info";

const TONES: Record<Tone, string> = {
  pass: "bg-pass-soft text-pass",
  fail: "bg-fail-soft text-fail",
  review: "bg-review-soft text-review",
  neutral: "bg-paper text-muted ring-1 ring-inset ring-rule",
  stamp: "bg-stamp-soft text-stamp",
  info: "bg-[#e8eef7] text-[#24467a]",
};

export function Pill({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONES[tone])}
    >
      {children}
    </span>
  );
}

const STATUS: Record<ApplicationStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "neutral" },
  submitted: { label: "Submitted", tone: "info" },
  processing: { label: "Checking", tone: "info" },
  needs_review: { label: "Needs review", tone: "review" },
  clarification_requested: { label: "Clarification requested", tone: "review" },
  ready_for_decision: { label: "Ready for decision", tone: "stamp" },
  approved: { label: "Approved", tone: "pass" },
  rejected: { label: "Rejected", tone: "fail" },
};

export function StatusPill({ status }: { status: ApplicationStatus }) {
  const s = STATUS[status];
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

export const statusLabel = (status: ApplicationStatus) => STATUS[status].label;

export function Notice({
  tone,
  title,
  children,
  action,
}: {
  tone: "review" | "fail" | "pass" | "info";
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const styles = {
    review: "border-review/30 bg-review-soft",
    fail: "border-fail/30 bg-fail-soft",
    pass: "border-pass/30 bg-pass-soft",
    info: "border-rule bg-sheet",
  }[tone];
  return (
    <div className={cx("rounded-[var(--radius-panel)] border px-5 py-4", styles)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-bold">{title}</p>
          {children && <div className="mt-1 text-sm text-ink/85">{children}</div>}
        </div>
        {action}
      </div>
    </div>
  );
}

// --- Forms -------------------------------------------------------------------------------

export const inputClass =
  "mt-1.5 block h-10 w-full rounded-[var(--radius-control)] border border-rule-strong bg-sheet px-3 text-[15px] " +
  "placeholder:text-faint focus:border-stamp focus:outline-none focus:ring-2 focus:ring-stamp/20";

export const textareaClass = inputClass.replace("h-10", "min-h-24 py-2");

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[13px] text-muted">{hint}</span>}
    </label>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-[var(--radius-control)] border border-fail/30 bg-fail-soft px-3 py-2 text-sm text-fail">
      {children}
    </p>
  );
}
