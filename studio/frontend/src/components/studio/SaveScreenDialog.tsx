import { useEffect, useRef, useState } from "react";
import { Button, Dialog, FormField, TextArea, TextInput } from "../ui/primitives";

interface SaveScreenDialogProps {
  open: boolean;
  defaultName: string;
  isUpdate?: boolean;
  showDescription?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: { name: string; description?: string }) => void;
}

export function SaveScreenDialog({
  open,
  defaultName,
  isUpdate = false,
  showDescription = false,
  onCancel,
  onConfirm,
  error,
}: SaveScreenDialogProps) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setDescription("");
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(focusTimer);
  }, [open, defaultName]);

  const submit = () => {
    if (!name.trim()) return;
    onConfirm({ name: name.trim(), description: description.trim() || undefined });
  };

  return (
    <Dialog
      open={open}
      title="Save universe screen"
      onClose={onCancel}
      footer={<>
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="button" variant="primary" disabled={!name.trim()} onClick={submit}>
          {isUpdate ? "Update screen" : "Save screen"}
        </Button>
      </>}
    >
      <div className="space-y-3">
        <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-semibold ${isUpdate ? "border-warn/30 bg-warn/10 text-warn" : "border-line bg-slate-50 text-ink-muted"}`}>
          {isUpdate ? "Updating loaded screen" : "New screen"}
        </span>
        <FormField label="Screen name">
          <TextInput
            ref={inputRef}
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); submit(); } }}
            placeholder="e.g. My Momentum Screen"
          />
        </FormField>
        {showDescription && (
          <FormField label="Description" hint="Optional. Describe what this screen selects.">
            <TextArea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
          </FormField>
        )}
        {isUpdate && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-ink-muted">
          Saving updates the loaded screen. Change its name to save a separate copy.
        </p>}
        {error && <p className="text-xs font-medium text-danger" role="alert">{error}</p>}
      </div>
    </Dialog>
  );
}

export default SaveScreenDialog;
