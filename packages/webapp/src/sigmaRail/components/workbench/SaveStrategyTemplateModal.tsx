import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { saveBacktestSpec } from "../../api/backtests";
import type { AssembledFrameworkSpec } from "./AlgorithmStudioView";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";

interface SaveStrategyTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  assembledSpec: AssembledFrameworkSpec;
  /** Full compilePipeline output. Wins over a reconstructed stub Universe. */
  compiledSpec?: Record<string, unknown> | null;
  currentTitle?: string;
  /** Authored PipelineDocument for agent/Studio round-trip. */
  pipelineDocument?: Record<string, unknown> | null;
  onSaved?: (irId: string, title: string) => void;
}

export function SaveStrategyTemplateModal({
  isOpen,
  onClose,
  assembledSpec,
  compiledSpec,
  currentTitle = "",
  pipelineDocument = null,
  onSaved,
}: SaveStrategyTemplateModalProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(currentTitle || "Custom Strategy Template");
  const [category, setCategory] = useState("Trend Following");
  const [tags, setTags] = useState("momentum, daily, custom");
  const [notes, setNotes] = useState(
    "Custom strategy composition with 5-slot QuantConnect framework configuration."
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const previewFw =
    (compiledSpec?.Framework as AssembledFrameworkSpec | undefined) ?? assembledSpec;

  const saveMutation = useMutation({
    mutationFn: async () => {
      const cleanTitle = title.trim();
      if (!cleanTitle) throw new Error("Template title is required");

      const slug = cleanTitle
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
      const irId = `tmpl-${slug}-${Math.random().toString(36).slice(2, 8)}`;

      const compiled = compiledSpec && typeof compiledSpec === "object" ? compiledSpec : null;
      const compiledBase =
        compiled && typeof compiled.VeraBase === "object" && compiled.VeraBase
          ? (compiled.VeraBase as Record<string, unknown>)
          : {};
      const compiledAlgo =
        compiled && typeof compiled.AlgorithmParameters === "object" && compiled.AlgorithmParameters
          ? (compiled.AlgorithmParameters as Record<string, unknown>)
          : {};

      const basePayload = compiled
        ? {
            ...compiled,
            SchemaVersion: compiled.SchemaVersion ?? 2,
            Kind: compiled.Kind ?? "VeraLabV1",
            Framework: (compiled.Framework as AssembledFrameworkSpec) ?? assembledSpec,
            AlgorithmParameters: { ...compiledAlgo },
            VeraBase: { ...compiledBase },
          }
        : {
            SchemaVersion: 2,
            Kind: "VeraLabV1",
            Framework: assembledSpec,
            AlgorithmParameters: {},
            VeraBase: {
              Universe: {
                version: 1,
                from: "daily_screener",
                select: ["ticker", "close", "overall_score"],
                where: { type: "all", items: [] },
                order_by: [{ field: "overall_score", direction: "desc" }],
                limit_per_day: 50,
              },
            },
          };
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      return saveBacktestSpec({
        ir_id: irId,
        title: cleanTitle,
        spec: basePayload,
        is_template: true,
        category,
        tags: tagList,
        notes: notes.trim(),
        pipeline_document: pipelineDocument ?? undefined,
      });
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["strategy-specs-library"] });
      void queryClient.invalidateQueries({ queryKey: ["framework-templates"] });
      onSaved?.(data.ir_id, data.title);
      onClose();
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || "Failed to save strategy template.");
    },
  });

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="flex max-h-[92dvh] w-[calc(100vw-1rem)] max-w-lg flex-col gap-0 overflow-hidden border-line bg-surface p-0">
        {/* Header */}
        <DialogHeader className="flex flex-row items-center justify-between border-b border-line bg-surface-raised px-5 py-4 pr-12 text-left">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">💾</span>
            <div>
              <DialogTitle className="text-sm font-bold text-ink">Save as Strategy Template</DialogTitle>
              <DialogDescription className="text-[11px] text-ink-muted">
                Save the current 5-slot composition for future reuse in the Composer.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Form Body */}
        <div className="min-h-0 overflow-y-auto p-5 space-y-4 text-xs">
          {errorMsg ? (
            <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-danger text-[11.5px]">
              {errorMsg}
            </div>
          ) : null}

          {/* Title */}
          <div>
            <label className="block text-[11px] font-semibold text-ink mb-1">
              Template Title <span className="text-danger">*</span>
            </label>
            <Input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Minervini Trend & Trailing Stop V2"
              aria-label="Template title"
              className="h-10 w-full text-sm font-semibold"
            />
          </div>

          {/* Category & Tags */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-ink mb-1">Category</label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="h-10 w-full text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Trend Following">Trend Following</SelectItem>
                  <SelectItem value="Momentum">Momentum</SelectItem>
                  <SelectItem value="Mean Reversion">Mean Reversion</SelectItem>
                  <SelectItem value="Multi-Factor">Multi-Factor</SelectItem>
                  <SelectItem value="Ensemble">Ensemble</SelectItem>
                  <SelectItem value="Custom Strategy">Custom Strategy</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-ink mb-1">Tags</label>
              <Input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="e.g. rsi, daily, tech"
                aria-label="Template tags"
                className="h-10 w-full text-sm"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-[11px] font-semibold text-ink mb-1">Notes</label>
            <Textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Strategy rationale, intended regime, entry/exit criteria…"
              aria-label="Template notes"
              className="min-h-20 resize-y text-sm"
            />
          </div>

          {/* 5-Slot Configuration Preview */}
          <div className="rounded-lg border border-line/70 bg-surface-sunk/60 p-3 space-y-1.5 text-[11px]">
            <p className="text-[10px] font-semibold uppercase text-ink-faint tracking-wider mb-1">
              Included 5-Slot Architecture
            </p>
            <div className="flex items-center justify-between text-ink-muted">
              <span>Universe:</span>
              <span className="font-mono text-ink font-medium">{previewFw.UniverseSelection?.Type}</span>
            </div>
            <div className="flex items-center justify-between text-ink-muted">
              <span>Alpha Model:</span>
              <span className="font-mono text-ink font-medium">{previewFw.Alpha?.Type}</span>
            </div>
            <div className="flex items-center justify-between text-ink-muted">
              <span>Portfolio Construction:</span>
              <span className="font-mono text-ink font-medium">{previewFw.PortfolioConstruction?.Type}</span>
            </div>
            <div className="flex items-center justify-between text-ink-muted">
              <span>Risk Management:</span>
              <span className="font-mono text-ink font-medium">{previewFw.RiskManagement?.Type}</span>
            </div>
            <div className="flex items-center justify-between text-ink-muted">
              <span>Execution Model:</span>
              <span className="font-mono text-ink font-medium">{previewFw.Execution?.Type}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <DialogFooter className="flex-row items-center justify-between border-t border-line bg-surface-raised px-5 py-3.5">
          <Button
            type="button"
            onClick={onClose}
            variant="outline"
            size="sm"
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={saveMutation.isPending || !title.trim()}
            onClick={() => saveMutation.mutate()}
            size="sm"
            className="gap-1.5"
          >
            {saveMutation.isPending ? "Saving Template…" : "💾 Save Template"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
