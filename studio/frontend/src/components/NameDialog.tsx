import { useEffect, useId, useRef, useState } from "react";
import { Button, Dialog, FormField, TextInput } from "./ui/primitives";

/** In-app name dialog — replaces window.prompt (often blocked in embedded browsers). */
export function NameDialog({
  open,
  title,
  label = "Name",
  initialValue = "",
  confirmLabel = "Save",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  label?: string;
  initialValue?: string;
  confirmLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [value, setValue] = useState(initialValue);

  useEffect(() => {
    if (!open) return;
    setValue(initialValue);
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, initialValue]);

  const trimmed = value.trim();

  return (
    <Dialog open={open} title={title} onClose={onCancel} footer={<>
      <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
      <Button type="button" variant="primary" disabled={!trimmed} onClick={() => onConfirm(trimmed)}>{confirmLabel}</Button>
    </>}>
      <FormField label={label}>
        <TextInput
          ref={inputRef}
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && trimmed) {
              e.preventDefault();
              onConfirm(trimmed);
            }
          }}
          className="mt-1"
        />
      </FormField>
    </Dialog>
  );
}
