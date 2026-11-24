import { forwardRef, useEffect, useId, useRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "ui-button-primary",
  secondary: "ui-button-secondary",
  ghost: "ui-button-ghost",
  danger: "ui-button-danger",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }>(function Button({ variant = "secondary", className = "", ...props }, ref) {
  return <button {...props} ref={ref} className={`ui-button ${buttonVariants[variant]} ${className}`} />;
});

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className = "", ...props }, ref) {
  return <input {...props} ref={ref} className={`ui-input ${className}`} />;
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className = "", ...props }, ref) {
  return <textarea {...props} ref={ref} className={`ui-input ui-textarea ${className}`} />;
});

export function SelectInput({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`ui-input ui-select ${className}`} />;
}

export function FormField({ label, hint, children, className = "" }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`ui-field ${className}`}>
      <span className="ui-field-label">{label}</span>
      {children}
      {hint && <span className="ui-field-hint">{hint}</span>}
    </label>
  );
}

export function Panel({ className = "", ...props }: HTMLAttributes<HTMLElement>) {
  return <section {...props} className={`ui-panel ${className}`} />;
}

export function ResponsiveTable({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`ui-table-scroll ${className}`} />;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="ui-page-header">
      <div className="min-w-0">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="ui-page-actions">{actions}</div>}
    </header>
  );
}

export function Dialog({ open, title, onClose, children, footer, className = "" }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; className?: string }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={dialogRef} className={`ui-dialog ${className}`} aria-labelledby={titleId}
      onCancel={event => { event.preventDefault(); onClose(); }}>
      <div className="ui-dialog-panel">
        <header className="ui-dialog-header"><h2 id={titleId}>{title}</h2><Button type="button" variant="ghost" aria-label="Close dialog" onClick={onClose}>×</Button></header>
        <div className="ui-dialog-content">{children}</div>
        {footer && <footer className="ui-dialog-footer">{footer}</footer>}
      </div>
    </dialog>
  );
}
