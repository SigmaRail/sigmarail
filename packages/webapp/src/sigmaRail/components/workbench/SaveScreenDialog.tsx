import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import { Input } from "@sb/webapp-core/components/ui/input";

interface SaveScreenDialogProps {
  open: boolean;
  /** Default name to prefill */
  defaultName: string;
  /** Whether we are updating an existing screen (vs creating new) */
  isUpdate?: boolean;
  /** Shared catalog screens are copied into the active workspace when saved. */
  isShared?: boolean;
  /** Show description field */
  showDescription?: boolean;
  /** Optional error message to display above the action buttons */
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: { name: string; description?: string }) => void;
}

export function SaveScreenDialog({
  open,
  defaultName,
  isUpdate = false,
  isShared = false,
  showDescription = false,
  onCancel,
  onConfirm,
  error,
}: SaveScreenDialogProps) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (open) {
      setName(defaultName);
      setDescription("");
    }
  }, [open, defaultName]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanName = name.trim();
    if (!cleanName) return;
    onConfirm({ name: cleanName, description: description.trim() || undefined });
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()}>
      <DialogContent size="sm" className="max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isShared ? "Save shared screen to my library" : isUpdate ? "Update universe screen" : "Save universe screen"}</DialogTitle>
          <DialogDescription>
            {isShared
              ? "Create a copy in your screen library. The shared catalog screen will stay unchanged."
              : isUpdate
              ? "Update the loaded screen or rename it to save a separate copy."
              : "Name this screen so you can load it again from your screen library."}
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-1.5">
            <label htmlFor="save-screen-name" className="text-sm font-medium text-foreground">
              Screen name
            </label>
            <Input
              id="save-screen-name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. My Momentum Screen"
              required
              maxLength={120}
            />
          </div>

          {showDescription && (
            <div className="space-y-1.5">
              <label htmlFor="save-screen-description" className="text-sm font-medium text-foreground">
                Description <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <textarea
                id="save-screen-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                placeholder="What does this screen select?"
                className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
              />
            </div>
          )}

          {error && (
            <p className="text-sm font-medium text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim()}>
              {isShared ? "Save to my library" : isUpdate ? "Update screen" : "Save screen"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default SaveScreenDialog;
