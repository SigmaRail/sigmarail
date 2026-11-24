import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchTemplates,
  fetchTemplate,
  fetchFields,
  fetchSavedScreens,
  createSavedScreen,
  updateSavedScreen,
} from "../../api/screens";
import { InlineScreenerPanel } from "./InlineScreenerPanel";
import { SaveScreenDialog } from "./SaveScreenDialog";
import type {
  IrWhereNode,
  SavedScreen,
  ScreenTemplateSummary,
  UniverseQueryV1,
} from "../../types";
import { PageHeader } from "../ui/primitives";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

interface ScreensViewProps {
  initialTemplateId?: string;
  routeScreenId?: string | null;
  initialAsOfDate?: string;
  onNavigateToChart: (ticker: string, asOfDate: string) => void;
  onSendToStrategy?: (spec: UniverseQueryV1, name?: string) => void;
  /** Results layout from the URL (`?view=`). */
  initialViewMode?: "list" | "grid" | null;
  /** Report layout changes so the address can carry them. */
  onViewModeChange?: (mode: "list" | "grid") => void;
  /** Report the selected template so the address can carry it (?template=). */
  onTemplateChange?: (templateId: string) => void;
  /** Report the selected saved screen (App reloads its spec + baseline) or null. */
  onSavedScreenChange?: (screen: SavedScreen | null) => void;
  /** Report the live spec so an altered screen can be shared as filter chips. */
  onSpecChange?: (spec: UniverseQueryV1) => void;
  /** Report the as-of date so the address can carry it (?as_of=). */
  onAsOfChange?: (date: string) => void;
  /** Applied filter chips from the address, if the screen was altered. */
  initialWhere?: IrWhereNode | null;
}

export function ScreensView({
  initialTemplateId = "minervini_trend_template",
  routeScreenId,
  initialAsOfDate = todayIso(),
  onNavigateToChart,
  onSendToStrategy,
  initialViewMode,
  onViewModeChange,
  onTemplateChange,
  onSavedScreenChange,
  onSpecChange,
  onAsOfChange,
  initialWhere,
}: ScreensViewProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState(initialTemplateId);
  const [asOfDate, setAsOfDate] = useState(initialAsOfDate);

  useEffect(() => {
    if (initialTemplateId && initialTemplateId !== selectedTemplateId) {
      setSelectedTemplateId(initialTemplateId);
    }
  }, [initialTemplateId]);

  useEffect(() => {
    if (initialAsOfDate && initialAsOfDate !== asOfDate) {
      setAsOfDate(initialAsOfDate);
    }
  }, [initialAsOfDate]);


  const templatesQuery = useQuery({
    queryKey: ["screen-templates"],
    queryFn: () => fetchTemplates(),
    staleTime: 600_000,
  });
  const templates: ScreenTemplateSummary[] = useMemo(
    () => templatesQuery.data || [],
    [templatesQuery.data],
  );

  const templateDetailQuery = useQuery({
    queryKey: ["screen-template-detail", selectedTemplateId],
    queryFn: () => fetchTemplate(selectedTemplateId),
    enabled: !!selectedTemplateId,
    staleTime: 600_000,
  });

  const fieldsQuery = useQuery({
    queryKey: ["screen-fields"],
    queryFn: fetchFields,
    staleTime: 600_000,
  });

  const savedScreensQuery = useQuery({
    queryKey: ["saved-screens"],
    queryFn: fetchSavedScreens,
    staleTime: 60_000,
  });
  const savedScreens = savedScreensQuery.data ?? [];

  const baseSpec = templateDetailQuery.data?.spec || null;

  // inlineSpec is the live spec the panel is editing (from template or loaded screen).
  const [inlineSpec, setInlineSpec] = useState<UniverseQueryV1 | null>(baseSpec);
  // Which custom saved screen (if any) is loaded → Save overwrites it instead of creating new.
  const [activeSaved, setActiveSaved] = useState<SavedScreen | null>(null);

  const routeScreen = savedScreens.find(screen => String(screen.id) === routeScreenId);
  useEffect(() => {
    if (routeScreenId) {
      setActiveSaved(routeScreen ?? null);
      setInlineSpec(routeScreen?.spec ?? null);
    } else {
      setActiveSaved(null);
      setInlineSpec(baseSpec);
    }
  }, [baseSpec, routeScreenId, routeScreen]);

  const handleInlineSpecChange = useCallback(
    (newSpec: UniverseQueryV1) => {
      setInlineSpec(newSpec);
      onSpecChange?.(newSpec);
    },
    [onSpecChange],
  );

  const handleSelectTemplate = useCallback(
    (id: string) => {
      setActiveSaved(null);
      setSelectedTemplateId(id);
      onSavedScreenChange?.(null);
      onTemplateChange?.(id);
    },
    [onSavedScreenChange, onTemplateChange],
  );

  // ---- Load a saved screen (system template or custom) ----
  const handleSelectSaved = useCallback(
    (screen: SavedScreen) => {
      if (screen.is_system) {
        // A system screen id matches a template id → load via template detail.
        setActiveSaved(null);
        setSelectedTemplateId(String(screen.id));
        onSavedScreenChange?.(null);
        onTemplateChange?.(String(screen.id));
        if (screen.spec) {
          setInlineSpec(screen.spec);
          onSpecChange?.(screen.spec);
        }
      } else {
        setActiveSaved(screen);
        // Keep the dropdown on its current template but swap the live spec.
        setSelectedTemplateId((cur) => cur || initialTemplateId);
        onSavedScreenChange?.(screen);
        setInlineSpec(screen.spec);
        onSpecChange?.(screen.spec);
      }
    },
    [initialTemplateId, onSavedScreenChange, onSpecChange, onTemplateChange],
  );

  // ---- Save dialog state ----
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveSpec, setSaveSpec] = useState<UniverseQueryV1 | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const defaultSaveName = useMemo(() => {
    if (activeSaved) return activeSaved.name;
    const t = templates.find((x) => x.id === selectedTemplateId);
    return t ? `${t.label} (edited)` : "My Custom Screen";
  }, [activeSaved, templates, selectedTemplateId]);

  const openSave = useCallback(
    (spec: UniverseQueryV1) => {
      setSaveSpec(spec);
      setSaveName(activeSaved?.name ?? defaultSaveName);
      setSaveError(null);
      setSaveOpen(true);
    },
    [activeSaved, defaultSaveName],
  );

  const persistMutation = useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => {
      if (!saveSpec) throw new Error("Nothing to save");
      const cleanName = payload.name.trim();
      if (!cleanName) throw new Error("Screen name is required.");
      const body = { name: cleanName, spec: saveSpec };
      if (activeSaved) {
        return updateSavedScreen(activeSaved.id, body);
      }
      return createSavedScreen(body);
    },
    onSuccess: () => {
      setSaveOpen(false);
      savedScreensQuery.refetch();
    },
    onError: (err: Error) => {
      setSaveError(err?.message || "Failed to save screen.");
    },
  });

  const confirmSave = (payload: { name: string; description?: string }) => {
    setSaveName(payload.name.trim());
    persistMutation.mutate(payload);
  };

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-surface">
      <PageHeader title="Stock screener" description="Build a point-in-time universe and inspect matching stocks." />
      <div className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
        <InlineScreenerPanel
          spec={inlineSpec}
          activePresetId={null}
          asOf={asOfDate}
          onAsOfChange={(d) => {
            setAsOfDate(d);
            onAsOfChange?.(d);
          }}
          presets={templates}
          savedScreens={savedScreens}
          fields={fieldsQuery.data ?? []}
          onSpecChange={handleInlineSpecChange}
          onSelectPreset={handleSelectTemplate}
          onSelectSaved={handleSelectSaved}
          onSaveTemplate={openSave}
          onSendToStrategy={
            onSendToStrategy
              ? (sp) => onSendToStrategy(sp, activeSaved?.name ?? defaultSaveName)
              : undefined
          }
          onOpenTicker={(ticker) => onNavigateToChart(ticker, asOfDate)}
          initialViewMode={initialViewMode}
          onViewModeChange={onViewModeChange}
          initialWhere={initialWhere}
        />
      </div>
      <SaveScreenDialog
        open={saveOpen}
        defaultName={saveName}
        isUpdate={!!activeSaved}
        error={saveError}
        onCancel={() => setSaveOpen(false)}
        onConfirm={confirmSave}
      />
    </div>
  );
}
