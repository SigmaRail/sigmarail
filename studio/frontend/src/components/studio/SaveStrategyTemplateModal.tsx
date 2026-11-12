import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { saveBacktestSpec } from "../../api/backtests";
import type { AssembledFrameworkSpec } from "./AlgorithmStudioView";
import type { EvaluationConfig } from "../../types";
import { stampEvaluation } from "../../lib/evaluationSpec";

interface SaveStrategyTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  assembledSpec: AssembledFrameworkSpec;
  /** Full compilePipeline output. Wins over a reconstructed stub Universe. */
  compiledSpec?: Record<string, unknown> | null;
  evaluationConfig?: EvaluationConfig;
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
  evaluationConfig,
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
      const compiledVera =
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
            VeraBase: { ...compiledVera },
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
      const specPayload = evaluationConfig
        ? stampEvaluation(basePayload, {
            start_date: evaluationConfig.start_date,
            end_date: evaluationConfig.end_date,
            initial_cash: evaluationConfig.initial_cash,
            benchmark: evaluationConfig.benchmark,
          })
        : basePayload;

      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      return saveBacktestSpec({
        ir_id: irId,
        title: cleanTitle,
        spec: specPayload,
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
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="flex w-full max-w-lg flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">💾</span>
            <div>
              <h3 className="text-sm font-bold text-ink">Save as Strategy Template</h3>
              <p className="text-[11px] text-ink-muted">
                Save the current 5-slot composition for future reuse in the Composer.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink hover:bg-surface-raised"
          >
            ✕
          </button>
        </div>

        {/* Form Body */}
        <div className="p-5 space-y-4 text-xs">
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
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Minervini Trend & Trailing Stop V2"
              className="w-full rounded-md border border-line bg-surface-raised px-3 py-2 text-xs font-semibold text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
            />
          </div>

          {/* Category & Tags */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-ink mb-1">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border border-line bg-surface-raised px-2.5 py-2 text-xs text-ink focus:border-accent focus:outline-none"
              >
                <option value="Trend Following">Trend Following</option>
                <option value="Momentum">Momentum</option>
                <option value="Mean Reversion">Mean Reversion</option>
                <option value="Multi-Factor">Multi-Factor</option>
                <option value="Ensemble">Ensemble</option>
                <option value="Custom Strategy">Custom Strategy</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-ink mb-1">Tags</label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="e.g. rsi, daily, tech"
                className="w-full rounded-md border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-[11px] font-semibold text-ink mb-1">Description / Notes</label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Strategy rationale, intended regime, entry/exit criteria…"
              className="w-full rounded-md border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none resize-none"
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
        <div className="flex items-center justify-between border-t border-line bg-surface-raised px-5 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-sunk"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saveMutation.isPending || !title.trim()}
            onClick={() => saveMutation.mutate()}
            className="rounded-md bg-accent text-accent-fg px-4 py-1.5 text-xs font-semibold hover:opacity-90 shadow-sm disabled:opacity-50 flex items-center gap-1.5"
          >
            {saveMutation.isPending ? "Saving Template…" : "💾 Save Template"}
          </button>
        </div>
      </div>
    </div>
  );
}
