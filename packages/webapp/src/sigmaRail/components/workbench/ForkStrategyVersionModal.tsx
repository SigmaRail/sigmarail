import { useEffect, useState } from "react";
import type { BacktestSpecSummary } from "../../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";

interface ForkStrategyVersionModalProps {
  isOpen: boolean;
  onClose: () => void;
  sourceSpec: BacktestSpecSummary | null;
  currentTitle: string;
  onConfirmFork: (newIrId: string, newTitle: string, changelogNotes: string) => Promise<void> | void;
  isPending?: boolean;
}

function suggestNextVersion(sourceIrId: string, sourceTitle: string): { nextId: string; nextTitle: string } {
  const cleanId = (sourceIrId || "strat-new").replace(/^catalog:/, "strat-");
  const idMatch = cleanId.match(/^(.*)-v(\d+)$/);
  const nextId = idMatch ? `${idMatch[1]}-v${parseInt(idMatch[2], 10) + 1}` : `${cleanId}-v2`;

  const cleanTitle = (sourceTitle || "Strategy").trim();
  const titleMatch = cleanTitle.match(/^(.*?)\s*\(v(\d+)\)$/i);
  const nextTitle = titleMatch
    ? `${titleMatch[1]} (v${parseInt(titleMatch[2], 10) + 1})`
    : `${cleanTitle} (v2)`;
  return { nextId, nextTitle };
}

export function ForkStrategyVersionModal({
  isOpen,
  onClose,
  sourceSpec,
  currentTitle,
  onConfirmFork,
  isPending = false,
}: ForkStrategyVersionModalProps) {
  const [newId, setNewId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [changelogNotes, setChangelogNotes] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !sourceSpec) return;
    const { nextId, nextTitle } = suggestNextVersion(sourceSpec.ir_id, currentTitle || sourceSpec.title || "");
    setNewId(nextId);
    setNewTitle(nextTitle);
    setChangelogNotes(`Forked from ${sourceSpec.ir_id}${sourceSpec.ir_content_hash ? ` (#${sourceSpec.ir_content_hash.slice(0, 8)})` : ""}`);
    setErrorMsg(null);
  }, [isOpen, sourceSpec, currentTitle]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMsg(null);
    const trimmedId = newId.trim();
    const trimmedTitle = newTitle.trim();
    if (!trimmedId) return setErrorMsg("Strategy ID is required.");
    if (!trimmedTitle) return setErrorMsg("Strategy title is required.");

    try {
      await onConfirmFork(trimmedId, trimmedTitle, changelogNotes.trim());
      onClose();
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "Failed to create strategy version.");
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent size="md" className="max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Fork strategy version</DialogTitle>
          <DialogDescription>
            Create a separate strategy specification. Existing backtest records stay linked to their original version.
          </DialogDescription>
        </DialogHeader>

        {sourceSpec ? (
          <Card className="flex flex-wrap items-center justify-between gap-2 p-3 shadow-none">
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Based on</div>
              <div className="truncate font-mono text-sm font-medium">{sourceSpec.ir_id}</div>
            </div>
            {sourceSpec.ir_content_hash ? (
              <span className="rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
                {sourceSpec.ir_content_hash.slice(0, 8)}
              </span>
            ) : null}
          </Card>
        ) : null}

        <form id="fork-strategy-version-form" onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
          {errorMsg ? <p role="alert" className="text-sm text-destructive">{errorMsg}</p> : null}
          <div className="space-y-1.5">
            <label htmlFor="fork-strategy-id" className="text-sm font-medium">New strategy ID</label>
            <Input id="fork-strategy-id" value={newId} onChange={(event) => setNewId(event.target.value)} required />
            <p className="text-xs text-muted-foreground">The next version ID is suggested automatically and can be edited.</p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="fork-strategy-title" className="text-sm font-medium">New strategy name</label>
            <Input id="fork-strategy-title" value={newTitle} onChange={(event) => setNewTitle(event.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="fork-strategy-changelog" className="text-sm font-medium">What changed in this version?</label>
            <Textarea
              id="fork-strategy-changelog"
              value={changelogNotes}
              onChange={(event) => setChangelogNotes(event.target.value)}
              placeholder="Record the change or hypothesis that distinguishes this version."
              rows={3}
              className="resize-y"
            />
          </div>
        </form>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button type="submit" form="fork-strategy-version-form" disabled={isPending || !newId.trim() || !newTitle.trim()}>
            {isPending ? "Creating version…" : "Create version"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
