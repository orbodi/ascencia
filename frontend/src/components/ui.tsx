import { useEffect, useId, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6 md:mb-8 animate-fade-up">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-[2rem] leading-tight tracking-tight text-ink md:text-[2.35rem]">
          {title}
        </h1>
        {subtitle ? (
          <p className="text-sm text-ink-soft mt-1.5 max-w-xl leading-relaxed">
            {subtitle}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="w-full sm:w-auto shrink-0 flex flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : null}
    </div>
  );
}

/** Modal en portal (évite le clip overflow / stacking du layout). */
export function Modal({
  open,
  onClose,
  title,
  titleId,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  titleId: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-ink/55 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`w-full ${wide ? "max-w-2xl" : "max-w-lg"}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <Card className="w-full p-5 sm:p-6">
          <h3
            id={titleId}
            className="mb-4 text-xl font-[family-name:var(--font-display)]"
          >
            {title}
          </h3>
          {children}
        </Card>
      </div>
    </div>,
    document.body
  );
}

/**
 * Modale de confirmation générique pour les actions destructrices
 * (suppression...). Remplace `window.confirm`, qui bloque le thread JS,
 * n'est pas stylée et coupe court à tout état de chargement (le bouton ne
 * peut pas afficher "Suppression…" pendant l'appel réseau).
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Supprimer",
  cancelLabel = "Annuler",
  danger = true,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  return (
    <Modal open={open} onClose={onCancel} title={title} titleId={titleId}>
      <div className="text-sm text-ink-soft">{message}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant={danger ? "danger" : "primary"}
          disabled={pending}
          onClick={onConfirm}
        >
          {pending ? "Patientez…" : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-surface/90 backdrop-blur-sm border border-line/80 rounded-2xl shadow-[0_1px_0_rgba(16,42,42,0.04)] ${className}`}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
}) {
  const base =
    "inline-flex min-h-11 items-center justify-center rounded-xl px-4 py-2.5 text-sm font-semibold transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]";
  const styles = {
    primary:
      "bg-accent text-white hover:bg-accent-deep shadow-[0_1px_0_rgba(116,42,5,0.25)]",
    ghost: "bg-mist/80 text-ink hover:bg-mist border border-line/60",
    danger: "bg-warn text-white hover:bg-warn/90",
  }[variant];
  return (
    <button className={`${base} ${styles} ${className}`} {...props}>
      {children}
    </button>
  );
}

const fieldClass =
  "w-full min-h-11 rounded-xl border border-line bg-white/90 px-3.5 py-2.5 outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20";

export function Input(
  props: React.InputHTMLAttributes<HTMLInputElement> & { label?: string }
) {
  const { label, className = "", ...rest } = props;
  return (
    <label className="block text-sm">
      {label ? (
        <span className="text-ink-soft mb-1.5 block font-medium text-[0.8rem]">
          {label}
        </span>
      ) : null}
      <input className={`${fieldClass} ${className}`} {...rest} />
    </label>
  );
}

export function Select(
  props: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }
) {
  const { label, className = "", children, ...rest } = props;
  return (
    <label className="block text-sm">
      {label ? (
        <span className="text-ink-soft mb-1.5 block font-medium text-[0.8rem]">
          {label}
        </span>
      ) : null}
      <select className={`${fieldClass} ${className}`} {...rest}>
        {children}
      </select>
    </label>
  );
}

export function TextArea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }
) {
  const { label, className = "", ...rest } = props;
  return (
    <label className="block text-sm">
      {label ? (
        <span className="text-ink-soft mb-1.5 block font-medium text-[0.8rem]">
          {label}
        </span>
      ) : null}
      <textarea
        className={`${fieldClass} font-mono text-xs leading-relaxed ${className}`}
        {...rest}
      />
    </label>
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "accent" | "warn" | "muted";
}) {
  const tones = {
    default: "bg-mist text-ink-soft",
    accent: "bg-accent-soft text-accent-deep",
    warn: "bg-amber-50 text-amber-900",
    muted: "bg-white/10 text-white/80",
  }[tone];
  return (
    <span
      className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[11px] font-semibold tracking-wide ${tones}`}
    >
      {children}
    </span>
  );
}
