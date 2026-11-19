import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import type { BacktestSpecSummary } from "../../types";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";

interface StrategySettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  strategyName: string;
  onStrategyNameChange: (name: string) => void;
  strategyId: string;
  onStrategyIdChange?: (id: string) => void;
  notes: string;
  onNotesChange: (notes: string) => void;
  isTemplate: boolean;
  onTemplateChange?: (isTemplate: boolean) => void;
  loadedSpec?: BacktestSpecSummary | null;
  isNewDraft: boolean;
  isCatalog: boolean;
  isSharedSpec: boolean;
  isLegacySpec: boolean;
  hasUnsavedEdits: boolean;
  savePending: boolean;
  onSave: () => void;
  onFork: () => void;
  onSaveTemplate: () => void;
}

export function StrategySettingsDialog({
  open,
  onOpenChange,
  strategyName,
  onStrategyNameChange,
  strategyId,
  onStrategyIdChange,
  notes,
  onNotesChange,
  isTemplate,
  onTemplateChange,
  loadedSpec,
  isNewDraft,
  isCatalog,
  isSharedSpec,
  isLegacySpec,
  hasUnsavedEdits,
  savePending,
  onSave,
  onFork,
  onSaveTemplate,
}: StrategySettingsDialogProps) {
  const canSave = !isSharedSpec && (hasUnsavedEdits || isLegacySpec);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" className="max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Strategy settings</DialogTitle>
          {isSharedSpec ? (
            <DialogDescription>Shared legacy strategy. Fork to edit.</DialogDescription>
          ) : null}
        </DialogHeader>

        <section className="space-y-4 rounded-lg border border-border bg-card p-4">
          <div className="space-y-1.5">
            <label htmlFor="strategy-settings-name" className="text-sm font-medium text-foreground">
              Name
            </label>
            <Input
              id="strategy-settings-name"
              autoFocus
              value={strategyName}
              onChange={(event) => onStrategyNameChange(event.target.value)}
              placeholder="Strategy name"
              className="h-10 w-full"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="strategy-settings-id" className="text-sm font-medium text-foreground">
              Strategy ID
            </label>
            <Input
              id="strategy-settings-id"
              value={strategyId}
              onChange={(event) => onStrategyIdChange?.(event.target.value)}
              placeholder="Assigned when the strategy is composed"
              className="h-10 w-full font-mono text-sm"
            />
          </div>

          <Checkbox
            checked={isTemplate}
            onCheckedChange={(checked) => onTemplateChange?.(checked === true)}
            label="Show in the strategy template library"
          />

          <div className="space-y-1.5 border-t border-border pt-3">
            <label htmlFor="strategy-settings-notes" className="text-sm font-medium text-foreground">
              Notes
            </label>
            <Textarea
              id="strategy-settings-notes"
              value={notes}
              onChange={(event) => onNotesChange(event.target.value)}
              placeholder="Intent, assumptions, or changes…"
              rows={4}
              className="min-h-24 resize-y"
            />
          </div>

          {loadedSpec ? (
            <dl className="grid gap-3 border-t border-border pt-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
              <dt className="text-muted-foreground">Format</dt>
              <dd className="text-foreground">
              {isCatalog ? "System template" : isSharedSpec ? "Shared legacy strategy" : isLegacySpec ? "Legacy specification" : "Five-slot pipeline"}
              </dd>
              {loadedSpec.ir_content_hash ? (
                <>
                  <dt className="text-muted-foreground">Content version</dt>
                  <dd className="font-mono text-xs text-foreground">{loadedSpec.ir_content_hash}</dd>
                </>
              ) : null}
            </dl>
          ) : null}

          {loadedSpec ? (
            <div className="space-y-1.5 border-t border-border pt-3">
              <h3 className="text-sm font-semibold text-foreground">Version history</h3>
              <p className="text-xs text-muted-foreground">
                {loadedSpec.created_at
                  ? `Current version saved ${new Date(loadedSpec.created_at).toLocaleString()}.`
                  : "Current saved version."}
              </p>
              {(() => {
                const lineage = loadedSpec.lineage as {
                  parent_ir_id?: string | null;
                  mutation_type?: string | null;
                  changelog_notes?: string | null;
                } | undefined;
                return lineage?.parent_ir_id || lineage?.changelog_notes ? (
                  <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                    {lineage.mutation_type ? <div className="font-medium capitalize text-foreground">{lineage.mutation_type}</div> : null}
                    {lineage.parent_ir_id ? <div>Based on {lineage.parent_ir_id}</div> : null}
                    {lineage.changelog_notes ? <p className="mt-1">{lineage.changelog_notes}</p> : null}
                  </div>
                ) : null;
              })()}
            </div>
          ) : null}
        </section>

        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">Version actions</h3>
          <div className="flex flex-wrap gap-2">
            {isCatalog ? (
              <Button type="button" onClick={onFork} disabled={savePending}>
                Save as strategy
              </Button>
            ) : isSharedSpec ? (
              <Button type="button" disabled title="Fork this shared strategy before saving changes">
                Fork to save changes
              </Button>
            ) : (
              <Button type="button" onClick={onSave} disabled={!canSave || savePending}>
                {savePending ? "Saving…" : isLegacySpec ? "Upgrade and save" : isNewDraft ? "Save strategy" : "Save changes"}
              </Button>
            )}
            {loadedSpec && !isCatalog ? (
              <Button type="button" variant="outline" onClick={onFork} disabled={savePending}>
                Fork version
              </Button>
            ) : null}
            <Button type="button" variant="outline" onClick={onSaveTemplate}>
              Save as template
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
