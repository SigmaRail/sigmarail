import { useEffect, useState } from "react";
import type { BacktestSpecSummary } from "../../types";

interface ForkStrategyVersionModalProps {
  isOpen: boolean;
  onClose: () => void;
  sourceSpec: BacktestSpecSummary | null;
  currentTitle: string;
  onConfirmFork: (newIrId: string, newTitle: string, notes: string) => Promise<void> | void;
  isPending?: boolean;
}

function suggestNextVersion(sourceIrId: string, sourceTitle: string): { nextId: string; nextTitle: string } {
  const cleanId = (sourceIrId || "strat-new").replace(/^catalog:/, "strat-");
  const idMatch = cleanId.match(/^(.*)-v(\d+)$/);
  let nextId: string;
  if (idMatch) {
    const base = idMatch[1];
    const ver = parseInt(idMatch[2], 10) + 1;
    nextId = `${base}-v${ver}`;
  } else {
    nextId = `${cleanId}-v2`;
  }

  const cleanTitle = (sourceTitle || "Strategy").trim();
  const titleMatch = cleanTitle.match(/^(.*?)\s*\(v(\d+)\)$/i);
  let nextTitle: string;
  if (titleMatch) {
    const base = titleMatch[1];
    const ver = parseInt(titleMatch[2], 10) + 1;
    nextTitle = `${base} (v${ver})`;
  } else {
    nextTitle = `${cleanTitle} (v2)`;
  }

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
  const [notes, setNotes] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && sourceSpec) {
      const { nextId, nextTitle } = suggestNextVersion(sourceSpec.ir_id, currentTitle || sourceSpec.title || "");
      setNewId(nextId);
      setNewTitle(nextTitle);
      setNotes(`Forked from ${sourceSpec.ir_id} (#${sourceSpec.ir_content_hash ? sourceSpec.ir_content_hash.slice(0, 8) : "head"})`);
      setErrorMsg(null);
    }
  }, [isOpen, sourceSpec, currentTitle]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    const trimmedId = newId.trim();
    const trimmedTitle = newTitle.trim();

    if (!trimmedId) {
      setErrorMsg("Strategy ID (ir_id) is required.");
      return;
    }
    if (!trimmedTitle) {
      setErrorMsg("Strategy title is required.");
      return;
    }

    try {
      await onConfirmFork(trimmedId, trimmedTitle, notes.trim());
      onClose();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to fork strategy version");
    }
  };

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="flex w-full max-w-xl flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 border border-accent/30 text-accent font-bold text-lg">
              🌱
            </div>
            <div>
              <h2 className="text-sm font-bold text-ink flex items-center gap-2">
                Fork as New Strategy Version
              </h2>
              <p className="text-[11.5px] text-ink-muted">
                Create an immutable revision. Historical backtest associations remain preserved.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-line bg-surface-sunk px-2.5 py-1 text-xs font-semibold text-ink hover:bg-surface-raised"
          >
            ✕
          </button>
        </div>

        {/* Source Spec Lineage Card */}
        {sourceSpec ? (
          <div className="bg-surface-sunk/70 border-b border-line px-6 py-3 text-xs flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-ink-muted">
              <span>Source:</span>
              <span className="font-mono text-ink font-semibold">{sourceSpec.ir_id}</span>
              {sourceSpec.ir_content_hash ? (
                <span className="font-mono rounded bg-surface border border-line px-1.5 py-0.5 text-[10px] text-ink-muted">
                  #{sourceSpec.ir_content_hash.slice(0, 8)}
                </span>
              ) : null}
            </div>
            <span className="rounded bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
              v2 Pipeline
            </span>
          </div>
        ) : null}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {errorMsg ? (
            <div className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-danger">
              {errorMsg}
            </div>
          ) : null}

          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              New Strategy ID (<code className="font-mono text-[11px]">ir_id</code>)
            </label>
            <input
              type="text"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              placeholder="e.g. strat-minervini-sepa-v2"
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs font-mono text-ink focus:border-accent focus:outline-none"
              required
            />
            <p className="mt-1 text-[11px] text-ink-muted">
              Must be unique. Automatically incremented from the base strategy ID.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              Strategy Version Title
            </label>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Minervini SEPA EPS Beat (v2)"
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink focus:border-accent focus:outline-none"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              Version Changelog / Notes (Optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What changes or hypotheses distinguish this version?"
              rows={3}
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink focus:border-accent focus:outline-none"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-line">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-line bg-surface-sunk px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-raised"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !newId.trim() || !newTitle.trim()}
              className="rounded-lg bg-accent text-accent-fg px-4 py-1.5 text-xs font-semibold hover:opacity-90 shadow-sm disabled:opacity-50 flex items-center gap-1.5"
            >
              {isPending ? "Creating Version…" : "🌱 Create New Version"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
