import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { compilePipeline } from "../../api/strategy";
import { fetchFields } from "../../api/screens";
import type { ScreenField } from "../../types";
import type { FilterTree, PipelineDocument } from "./StrategyDocument";
import { isFilterGroup, isFilterNot } from "./StrategyDocument";
import { PipelineCanvas } from "./PipelineCanvas";

interface StrategyEditorViewProps {
  initialDocument?: PipelineDocument | null;
  onChangeSpec?: (spec: Record<string, unknown>) => void;
  onChangeDocument?: (doc: PipelineDocument) => void;
  /** Adjust the DTO immediately before compile (e.g. attach universe.screen). */
  prepareDocument?: (doc: PipelineDocument) => PipelineDocument;
  /** Bump when Universe screen / source changes so compile re-runs. */
  prepareRevision?: string;
  /** As-of / range end for stage-prefix probe panes. */
  asOf?: string;
  /** Range start for probe panes (backtest start). */
  startDate?: string;
}

const EMPTY_DOCUMENT: PipelineDocument = {
  strategy_name: "Untitled Strategy",
  stages: [],
  gate_combine: "count",
  min_screens: 1,
  sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
  risk: { max_positions: 10 },
  execution: { type: "market_order" },
};

export function StrategyEditorView({
  initialDocument,
  onChangeSpec,
  onChangeDocument,
  prepareDocument,
  prepareRevision,
  asOf = "",
  startDate = "",
}: StrategyEditorViewProps) {
  const [document, setDocument] = useState<PipelineDocument>(
    initialDocument ?? EMPTY_DOCUMENT,
  );
  const [compileError, setCompileError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const onChangeSpecRef = useRef(onChangeSpec);
  onChangeSpecRef.current = onChangeSpec;

  const onChangeDocumentRef = useRef(onChangeDocument);
  onChangeDocumentRef.current = onChangeDocument;

  const lastHydrateKeyRef = useRef<string | null>(null);
  const updateDocument = useCallback((next: PipelineDocument) => {
    lastHydrateKeyRef.current = JSON.stringify(next);
    setDocument(next);
    // Synchronous parent sync so Save always sees the latest binding ids / stages.
    onChangeDocumentRef.current?.(next);
  }, []);

  const initialHydrateKey = JSON.stringify(initialDocument ?? null);
  useEffect(() => {
    // Only re-hydrate when parent loads a different document (not echo of our own edits).
    if (lastHydrateKeyRef.current === initialHydrateKey) return;
    lastHydrateKeyRef.current = initialHydrateKey;
    setDocument(initialDocument ?? EMPTY_DOCUMENT);
    setCompileError(null);
    setValidationError(null);
  }, [initialDocument, initialHydrateKey]);

  const fieldsQuery = useQuery({
    queryKey: ["screen-fields"],
    queryFn: fetchFields,
    staleTime: 5 * 60_000,
  });
  const fields: ScreenField[] = fieldsQuery.data ?? [];

  const prepareDocumentRef = useRef(prepareDocument);
  prepareDocumentRef.current = prepareDocument;

  /** Live probe payload: local Alpha edits + parent Universe.screen (prepareRevision). */
  const probePipeline = useMemo(() => {
    const prep = prepareDocumentRef.current;
    return prep ? prep(document) : document;
  }, [document, prepareRevision]);

  const doCompile = useCallback(async () => {
    if (!document.stages.length && !(document.universe?.screen?.length)) {
      setCompileError("Add Alpha stages or a Universe screen before compiling.");
      return;
    }

    const filterStages = document.stages.filter((stage) => stage.mode === "filter");
    const hasIncompleteFilter = (nodes: FilterTree[]): boolean => {
      for (const node of nodes) {
        if (isFilterGroup(node)) {
          if (hasIncompleteFilter(node.conditions)) return true;
        } else if (isFilterNot(node)) {
          if (hasIncompleteFilter([node.item])) return true;
        } else if (!node.left || node.right === "") {
          return true;
        }
      }
      return false;
    };

    for (const stage of filterStages) {
      if (hasIncompleteFilter(stage.filters ?? [])) {
        setValidationError(
          `Stage "${stage.name}" has an incomplete filter: left and right are required.`,
        );
        return;
      }
    }

    setValidationError(null);
    try {
      const prepared = prepareDocumentRef.current
        ? prepareDocumentRef.current(document)
        : document;
      const spec = await compilePipeline(prepared);
      setCompileError(null);
      onChangeSpecRef.current?.(spec);
    } catch (error) {
      setCompileError(error instanceof Error ? error.message : String(error));
    }
  }, [document]);

  useEffect(() => {
    if (!document.stages.length && !(document.universe?.screen?.length)) return;
    const timeout = window.setTimeout(() => void doCompile(), 400);
    return () => window.clearTimeout(timeout);
  }, [document, doCompile, prepareRevision]);

  return (
    <div className="space-y-3">
      {(validationError || compileError) && (
        <div className="rounded border border-warn/50 bg-warn/10 px-3 py-2 text-[11px] text-warn">
          {validationError ?? compileError}
        </div>
      )}
      <PipelineCanvas
        document={document}
        probePipeline={probePipeline}
        onChange={updateDocument}
        fields={fields}
        asOf={asOf}
        startDate={startDate}
      />
    </div>
  );
}
