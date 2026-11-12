import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  createSavedScreen,
  deleteSavedScreen,
  fetchAsOfRange,
  fetchFields,
  fetchPresets,
  fetchSavedScreens,
  fetchTemplate,
  fetchTemplates,
  fetchTurnover,
  previewIr,
  previewScreen,
  updateSavedScreen,
} from "./api/screens";
import { BacktestView } from "./components/BacktestView";
import { MarketView } from "./components/studio/MarketView";
import { stockFromPath, stockPath, strategyIrIdFromPath, strategyPath, tabForPath, TAB_PATHS } from "./routes";
import { buildScreenerSearch, readScreenerState } from "./lib/screenerUrl";
import { whereToAst } from "./lib/screenAst";
import { MonitorView } from "./components/MonitorView";
import { NameDialog } from "./components/NameDialog";
import {
  RESULTS_GRID_CHUNK,
} from "./components/ResultsGrid";
import { TopBar } from "./components/TopBar";
import { FieldPickerProvider } from "./components/studio/FieldPickerProvider";
import { ScreenerStudioModal } from "./components/studio/ScreenerStudioModal";
import { ScreensView } from "./components/studio/ScreensView";
import { ChartsView } from "./components/studio/ChartsView";
import { WatchlistsView } from "./components/studio/WatchlistsView";
import {
  applyFiltersToSpec,
  extractAppliedFilters,
} from "./lib/irFilters";
import { studioAgentBridge } from "./lib/studioAgentBridge";
import { initWebMCP } from "./lib/webmcpProvider";
import {
  computeTurnover,
  enrichRows,
  priorDateInRange,
} from "./lib/utils";
import type {
  AppliedFilterRow,
  BacktestPrefill,
  RankedRow,
  SavedScreen,
  ScreenSource,
  TurnoverResponse,
  UniverseQueryV1,
  ViewMode,
  WorkbenchTab,
} from "./types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

/**
 * There is deliberately **no default preset**. Starting on one (it used to be `minervini_tt`)
 * meant the screener opened with someone else's conditions already applied — including a
 * pre-baked `*_all_conditions_full` flag, which makes a screen unreadable and un-relaxable.
 * An empty screen is the honest starting point; presets are something you pick.
 */
const NO_PRESET = "";
const PREVIEW_LIMIT = 50;
const IR_DEBOUNCE_MS = 400;

function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function StudioApp() {
  const queryClient = useQueryClient();

  // Today's date as YYYY-MM-DD (local time)
  const todayIso = useMemo(() => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }, []);

  // Read initial route state from URL query parameters
  const initialParams = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const ticker = params.get("ticker") || "";
    const date = params.get("as_of") || todayIso;
    const presetParam = params.get("preset") || null;
    const templateParam = params.get("template") || null;
    return { ticker, date, preset: presetParam, template: templateParam };
  }, [todayIso]);

  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = tabForPath(location.pathname);
  const routeStrategyIrId = strategyIrIdFromPath(location.pathname);
  // The ticker lives in the path (/stock/NVDA/chart); ?ticker= stays readable for old links.
  const stock = stockFromPath(location.pathname);
  const urlState = useMemo(() => readScreenerState(location.search), [location.search]);
  const [screenerView, setScreenerView] = useState<"list" | "grid">(urlState.view ?? "list");
  const firstSyncRef = useRef(true);
  const [selectedChartTicker, setSelectedChartTicker] = useState<string>(
    stock.ticker ?? initialParams.ticker,
  );
  const [isScreenerModalOpen, setIsScreenerModalOpen] = useState(false);
  const [source, setSource] = useState<ScreenSource>("preset");
  const [preset, setPreset] = useState<string>(NO_PRESET);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [spec, setSpec] = useState<UniverseQueryV1 | null>(null);
  const [filterRows, setFilterRows] = useState<AppliedFilterRow[]>([]);
  const [asOf, setAsOf] = useState(initialParams.date);
  const [selected, setSelected] = useState<RankedRow | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [gridVisibleCount, setGridVisibleCount] = useState(RESULTS_GRID_CHUNK);
  const [savedScreenId, setSavedScreenId] = useState<number | string | null>(
    null,
  );
  const [baselineSpecJson, setBaselineSpecJson] = useState("");
  // A load is not an edit: the address keeps the reference until the user changes the screen.
  const [screenEdited, setScreenEdited] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveFlash, setSaveFlash] = useState<string | null>(null);
  const [nameDialog, setNameDialog] = useState<null | {
    mode: "save-as" | "rename" | "save-for-backtest";
    initial: string;
    screenId?: number | string;
  }>(null);
  const nameDialogResolverRef = useRef<((value: string | null) => void) | null>(
    null,
  );
  const [backtestPrefill, setBacktestPrefill] = useState<BacktestPrefill | null>(
    null,
  );

  const flashSaved = useCallback((msg: string) => {
    setSaveFlash(msg);
    window.setTimeout(() => setSaveFlash(null), 2500);
  }, []);

  // Keep the chart tab's ticker in step with the path (deep links, back/forward).
  useEffect(() => {
    if (stock.ticker && stock.ticker !== selectedChartTicker) {
      setSelectedChartTicker(stock.ticker);
    }
  }, [stock.ticker, selectedChartTicker]);

  // A history entry drives the screener inputs back (back/forward, shared links).
  useEffect(() => {
    if (urlState.asOf && urlState.asOf !== asOf) setAsOf(urlState.asOf);
    if (urlState.template && urlState.template !== templateId) {
      // Load through the state machine so the spec + baseline come back too, not just the id.
      void selectTemplate(urlState.template);
    } else if (urlState.preset && urlState.preset !== preset) {
      selectPreset(urlState.preset);
    }
    if (urlState.view && urlState.view !== screenerView) setScreenerView(urlState.view);
    // Chips present means the sharer had altered the screen: keep it that way so the
    // address keeps carrying them (and the tree shows them).
    if (urlState.where ?? urlState.filters) setScreenEdited(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlState.template, urlState.preset, urlState.asOf, urlState.view]);

  // Redirect bare root to the default tab.
  useEffect(() => {
    if (location.pathname === "/") {
      navigate(TAB_PATHS.screens, { replace: true });
    }
  }, [location.pathname, navigate]);

  // History entries written by the older build can carry a query as the pathname
  // (/screen=10&filters=v1…). Recover them as the screener's search instead of
  // failing to load — Back must work even for entries already in the history.
  useEffect(() => {
    const seg = location.pathname.replace(/^\/+/, "");
    if (seg.includes("=")) {
      navigate(`${TAB_PATHS.screens}?${seg}`, { replace: true });
    }
  }, [location.pathname, navigate]);

  // Address as the source of truth. The screener carries its settings (reference or
  // applied chips); the chart tab carries only as_of, because the ticker lives in the
  // path (/stock/NVDA/chart). The first pass normalises with replace, later changes push
  // so back/forward walks the state changes (C: screener <-> chart).
  useEffect(() => {
    const path = location.pathname;
    const current = `${window.location.pathname}${window.location.search}`;
    const replace = firstSyncRef.current;

    let target = path;
    if (activeTab === "screens") {
      // Unaltered -> the address carries the spec reference. Altered -> it carries the
      // applied filter chips (the reference stays alongside as provenance).
      const altered = screenEdited && spec !== null;
      const search = buildScreenerSearch(
        {
          template: source === "ir" ? templateId : null,
          preset: source === "preset" && preset ? preset : null,
          screen: savedScreenId != null ? String(savedScreenId) : null,
          asOf,
          view: screenerView,
          where: altered && spec ? whereToAst(spec.where) : null,
        },
        { today: todayIso },
      );
      target = search ? `${path}?${search}` : path;
    } else {
      const params = new URLSearchParams(window.location.search);
      for (const key of ["ticker", "template", "preset", "screen", "filters", "view", "universe", "deprecated"]) {
        params.delete(key);
      }
      if (asOf && asOf !== todayIso) params.set("as_of", asOf);
      else params.delete("as_of");
      const search = params.toString();
      target = search ? `${path}?${search}` : path;
    }

    firstSyncRef.current = false;
    if (target !== current) navigate(target, { replace });
  }, [
    activeTab,
    asOf,
    todayIso,
    source,
    preset,
    templateId,
    savedScreenId,
    screenerView,
    spec,
    screenEdited,
    location.pathname,
    navigate,
  ]);

  const closeNameDialog = useCallback((value: string | null) => {
    const resolve = nameDialogResolverRef.current;
    nameDialogResolverRef.current = null;
    setNameDialog(null);
    resolve?.(value);
  }, []);

  const askScreenName = useCallback(
    (opts: {
      mode: "save-as" | "rename" | "save-for-backtest";
      initial: string;
      screenId?: number | string;
    }) =>
      new Promise<string | null>((resolve) => {
        nameDialogResolverRef.current = resolve;
        setNameDialog(opts);
      }),
    [],
  );

  const presetsQuery = useQuery({
    queryKey: ["presets"],
    queryFn: fetchPresets,
  });

  const templatesQuery = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  const savedScreensQuery = useQuery({
    queryKey: ["saved-screens"],
    queryFn: fetchSavedScreens,
  });

  // Going back/forward onto a ?screen= entry re-opens that saved screen (spec + baseline).
  useEffect(() => {
    if (!urlState.screen) return;
    if (String(savedScreenId ?? "") === urlState.screen) return;
    const found = (savedScreensQuery.data ?? []).find((s) => String(s.id) === urlState.screen);
    if (found) selectSavedScreen(found);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlState.screen, savedScreensQuery.data]);

  const fieldsQuery = useQuery({
    queryKey: ["fields"],
    queryFn: fetchFields,
  });

  const rangeQuery = useQuery({
    queryKey: ["as-of-range"],
    queryFn: () => fetchAsOfRange(10000),
  });

  const datesDesc = rangeQuery.data ?? [];

  useEffect(() => {
    if (!asOf && datesDesc.length > 0) {
      setAsOf(datesDesc[0]!);
    }
  }, [asOf, datesDesc]);

  useEffect(() => {
    const list = presetsQuery.data;
    if (!list?.length) return;
    if (preset && !list.some((p) => p.id === preset)) {
      // The selection no longer exists: clear it rather than silently jumping to whichever
      // preset happens to be first — an empty screen beats an arbitrary one.
      setPreset(NO_PRESET);
    }
  }, [presetsQuery.data, preset]);

  const liveSpec = useMemo(() => {
    if (!spec) return null;
    return applyFiltersToSpec(spec, filterRows);
  }, [spec, filterRows]);

  const liveSpecJson = useMemo(
    () => (liveSpec ? JSON.stringify(liveSpec) : ""),
    [liveSpec],
  );

  const dirty =
    source === "ir" &&
    Boolean(liveSpec) &&
    liveSpecJson !== baselineSpecJson;

  const debouncedSpec = useDebouncedValue(liveSpec, IR_DEBOUNCE_MS);
  const debouncedSpecKey = useMemo(
    () => (debouncedSpec ? JSON.stringify(debouncedSpec) : ""),
    [debouncedSpec],
  );

  const presetPreviewQuery = useQuery({
    queryKey: ["preview", "preset", asOf, preset, PREVIEW_LIMIT],
    queryFn: () =>
      previewScreen({ as_of: asOf, preset, limit: PREVIEW_LIMIT }),
    enabled:
      source === "preset" && Boolean(asOf && preset) && isScreenerModalOpen,
  });

  const irPreviewQuery = useQuery({
    queryKey: ["preview", "ir", asOf, debouncedSpecKey],
    queryFn: () => previewIr({ as_of: asOf, spec: debouncedSpec! }),
    enabled:
      source === "ir" &&
      Boolean(asOf && debouncedSpec) &&
      isScreenerModalOpen,
  });

  const previewQuery =
    source === "ir" ? irPreviewQuery : presetPreviewQuery;

  const priorAsOf = useMemo(
    () => (asOf ? priorDateInRange(datesDesc, asOf) : null),
    [asOf, datesDesc],
  );

  const priorPresetPreviewQuery = useQuery({
    queryKey: ["preview", "preset", priorAsOf, preset, PREVIEW_LIMIT],
    queryFn: () =>
      previewScreen({
        as_of: priorAsOf!,
        preset,
        limit: PREVIEW_LIMIT,
      }),
    enabled:
      source === "preset" &&
      Boolean(priorAsOf && preset) &&
      isScreenerModalOpen,
  });

  const priorIrPreviewQuery = useQuery({
    queryKey: ["preview", "ir", priorAsOf, debouncedSpecKey],
    queryFn: () => previewIr({ as_of: priorAsOf!, spec: debouncedSpec! }),
    enabled:
      source === "ir" &&
      Boolean(priorAsOf && debouncedSpec) &&
      isScreenerModalOpen,
  });

  const priorPreviewQuery =
    source === "ir" ? priorIrPreviewQuery : priorPresetPreviewQuery;

  const turnoverApiQuery = useQuery({
    queryKey: ["turnover", asOf, preset, PREVIEW_LIMIT],
    queryFn: () =>
      fetchTurnover({ as_of: asOf, preset, limit: PREVIEW_LIMIT }),
    enabled: source === "preset" && Boolean(asOf && preset) && isScreenerModalOpen,
  });

  const turnover: TurnoverResponse | null = useMemo(() => {
    if (source === "preset" && turnoverApiQuery.data) {
      return turnoverApiQuery.data;
    }
    if (!previewQuery.data) return null;
    if (priorAsOf && priorPreviewQuery.isLoading) return null;
    return computeTurnover(
      previewQuery.data,
      priorPreviewQuery.data ?? null,
      priorAsOf,
    );
  }, [
    source,
    turnoverApiQuery.data,
    previewQuery.data,
    priorPreviewQuery.data,
    priorPreviewQuery.isLoading,
    priorAsOf,
  ]);

  const rankedRows = useMemo(() => {
    if (!previewQuery.data) return [];
    return enrichRows(
      previewQuery.data,
      priorPreviewQuery.data ?? null,
      turnover,
    );
  }, [previewQuery.data, priorPreviewQuery.data, turnover]);

  useEffect(() => {
    setSelected(null);
  }, [asOf, preset, templateId, savedScreenId, source]);

  useEffect(() => {
    setGridVisibleCount(RESULTS_GRID_CHUNK);
  }, [asOf, preset, templateId, savedScreenId, source, debouncedSpecKey]);

  const bootError =
    presetsQuery.error?.message ||
    rangeQuery.error?.message ||
    templatesQuery.error?.message ||
    null;

  const selectPreset = (id: string) => {
    setScreenEdited(false);
    setSource("preset");
    setPreset(id);
    setTemplateId(null);
    setSpec(null);
    setFilterRows([]);
    setSavedScreenId(null);
    setBaselineSpecJson("");
  };

  const selectTemplate = async (id: string) => {
    setScreenEdited(false);
    setSource("ir");
    setTemplateId(id);
    setSavedScreenId(null);
    try {
      const detail = await fetchTemplate(id);
      setSpec(detail.spec);
      const { rows } = extractAppliedFilters(detail.spec.where);
      setFilterRows(rows);
      setBaselineSpecJson(
        JSON.stringify(applyFiltersToSpec(detail.spec, rows)),
      );
    } catch (err) {
      console.error(err);
      setSpec(null);
      setFilterRows([]);
      setBaselineSpecJson("");
    }
  };

  const selectSavedScreen = (screen: SavedScreen) => {
    setScreenEdited(false);
    setSource("ir");
    setTemplateId(null);
    setSavedScreenId(screen.id);
    setSpec(screen.spec);
    const { rows } = extractAppliedFilters(screen.spec.where);
    setFilterRows(rows);
    setBaselineSpecJson(
      JSON.stringify(applyFiltersToSpec(screen.spec, rows)),
    );
  };

  const revertToDefaultTemplate = async () => {
    const templates = templatesQuery.data ?? [];
    const fallback =
      templates.find((t) => t.id === "minervini") ??
      templates.find((t) => t.id === "canslim") ??
      templates[0];
    if (fallback) {
      await selectTemplate(fallback.id);
    } else {
      setSource("preset");
      setSpec(null);
      setFilterRows([]);
      setSavedScreenId(null);
      setTemplateId(null);
      setBaselineSpecJson("");
    }
  };

  // Apply preset or template from URL query params on initial mount
  const bootPresetApplied = useRef(false);
  useEffect(() => {
    if (bootPresetApplied.current) return;
    bootPresetApplied.current = true;
    const tid = initialParams.template || initialParams.preset;
    if (tid) {
      // Try template first (loads full AST filter tree); fall back to preset
      selectTemplate(tid).catch(() => {
        selectPreset(tid);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRenameSaved = (screen: SavedScreen) => {
    void (async () => {
      const name = await askScreenName({
        mode: "rename",
        initial: screen.name,
        screenId: screen.id,
      });
      if (!name || name === screen.name) return;
      try {
        await updateSavedScreen(screen.id, { name });
        await queryClient.invalidateQueries({ queryKey: ["saved-screens"] });
        flashSaved(`Renamed to “${name}”`);
      } catch (err) {
        console.error(err);
        window.alert(
          err instanceof Error ? err.message : "Rename failed",
        );
      }
    })();
  };

  const handleDeleteSaved = async (screen: SavedScreen) => {
    if (
      !window.confirm(`Delete saved screen "${screen.name}"? This cannot be undone.`)
    ) {
      return;
    }
    try {
      await deleteSavedScreen(screen.id);
      await queryClient.invalidateQueries({ queryKey: ["saved-screens"] });
      if (savedScreenId === screen.id) {
        await revertToDefaultTemplate();
      }
    } catch (err) {
      console.error(err);
      window.alert(
        err instanceof Error ? err.message : "Delete failed",
      );
    }
  };

  const persistNewScreen = async (name: string) => {
    if (!liveSpec || source !== "ir") return null;
    setSaving(true);
    try {
      const created = await createSavedScreen({
        name,
        spec: liveSpec,
      });
      markSaved(created.id, liveSpec);
      await invalidateSavedScreens();
      flashSaved(`Saved “${created.name}”`);
      return created;
    } catch (err) {
      console.error(err);
      window.alert(
        err instanceof Error ? err.message : "Save failed",
      );
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    if (!liveSpec || source !== "ir") return;
    if (savedScreenId != null) {
      setSaving(true);
      try {
        const updated = await updateSavedScreen(savedScreenId, {
          spec: liveSpec,
        });
        markSaved(updated.id, liveSpec);
        await invalidateSavedScreens();
        flashSaved(`Saved “${updated.name}”`);
      } catch (err) {
        console.error(err);
        window.alert(
          err instanceof Error ? err.message : "Save failed",
        );
      } finally {
        setSaving(false);
      }
      return;
    }
    void (async () => {
      const name = await askScreenName({
        mode: "save-as",
        initial: backtestScreenTitle ?? "Screen",
      });
      if (!name) return;
      await persistNewScreen(name);
    })();
  };

  const handleSaveAs = () => {
    if (!liveSpec || source !== "ir") return;
    void (async () => {
      const name = await askScreenName({
        mode: "save-as",
        initial: backtestScreenTitle ?? "Screen",
      });
      if (!name) return;
      await persistNewScreen(name);
    })();
  };

  const onFilterRowsChange = (rows: AppliedFilterRow[]) => {
    setFilterRows(rows);
  };

  const onSpecChange = (next: UniverseQueryV1) => {
    setSpec(next);
  };

  const markSaved = (id: number | string, savedSpec: UniverseQueryV1) => {
    setSavedScreenId(id);
    setTemplateId(null);
    setBaselineSpecJson(JSON.stringify(savedSpec));
  };

  const invalidateSavedScreens = () =>
    queryClient.invalidateQueries({ queryKey: ["saved-screens"] });

  const savedScreens = savedScreensQuery.data ?? [];
  const templates = templatesQuery.data ?? [];

  const backtestScreenTitle = useMemo(() => {
    if (savedScreenId != null) {
      return savedScreens.find((s) => s.id === savedScreenId)?.name;
    }
    if (templateId != null) {
      return templates.find((t) => t.id === templateId)?.label;
    }
    return "Custom screen";
  }, [savedScreenId, savedScreens, templateId, templates]);

  const buildBacktestPrefill = useCallback((): BacktestPrefill | null => {
    if (source === "preset" && preset) {
      const presetMeta = (presetsQuery.data ?? []).find((p) => p.id === preset);
      if (presetMeta?.backtestable === false) return null;
      return {
        universeSource: "preset",
        presetId: preset,
        title: presetMeta?.label ?? preset,
        dirty: false,
      };
    }
    if (source !== "ir" || !liveSpec) return null;
    const title = backtestScreenTitle ?? "Custom screen";
    if (savedScreenId != null && !dirty) {
      return {
        universeSource: "saved",
        savedScreenId,
        inlineSpec: liveSpec,
        title,
        dirty: false,
      };
    }
    return {
      universeSource: "inline",
      inlineSpec: liveSpec,
      savedScreenId: savedScreenId ?? undefined,
      title,
      dirty,
    };
  }, [
    source,
    preset,
    presetsQuery.data,
    liveSpec,
    savedScreenId,
    dirty,
    backtestScreenTitle,
  ]);

  useEffect(() => {
    if (activeTab !== "compose") return;
    const next = buildBacktestPrefill();
    if (!next) return;
    setBacktestPrefill((prev) => {
      const prevKey = prev ? JSON.stringify(prev) : "";
      const nextKey = JSON.stringify(next);
      return prevKey === nextKey ? prev : next;
    });
  }, [activeTab, source, liveSpecJson, preset, buildBacktestPrefill]);

  const handleTabChange = (next: WorkbenchTab) => {
    if (next === "compose") {
      const prefill = buildBacktestPrefill();
      if (prefill) setBacktestPrefill(prefill);
      // Stay on the open strategy when already composing; else untitled draft.
      const current = strategyIrIdFromPath(location.pathname);
      navigate(strategyPath(current));
      return;
    }
    navigate(TAB_PATHS[next]);
  };

  // Keep StudioAgentBridge state in sync with active React state
  useEffect(() => {
    studioAgentBridge.updateState({
      activeTab,
      selectedTicker: selectedChartTicker,
      asOf: asOf || todayIso,
      preset,
      templateId,
      savedScreenId,
      rankedRowCount: rankedRows.length,
      dirty,
      backtestPrefill,
      liveSpec,
    });
  }, [
    activeTab,
    selectedChartTicker,
    asOf,
    todayIso,
    preset,
    templateId,
    savedScreenId,
    rankedRows.length,
    dirty,
    backtestPrefill,
    liveSpec,
  ]);

  // Register WebMCP action handlers bound to React state and navigation
  useEffect(() => {
    const unregNav = studioAgentBridge.registerAction("navigate", async (args: any) => {
      const route = (args.route || "").trim().toLowerCase();
      if (args.ticker) setSelectedChartTicker(args.ticker.toUpperCase());
      if (args.as_of) setAsOf(args.as_of);

      if (route === "backtests" && args.run_id) {
        const subview = args.section_view || "overview";
        navigate(`/backtests/${args.run_id}/${subview}`);
      } else if (route === "strategies" && (args.ir_id || args.strategy_id)) {
        const id = args.ir_id || args.strategy_id;
        navigate(`/strategies/${id}`);
      } else if (route in TAB_PATHS) {
        handleTabChange(route as WorkbenchTab);
      } else if (!route || route.includes("=") || route.startsWith("?")) {
        // A client passed a query/URL fragment instead of a tab name. Keep it as the
        // screener's search — navigating it as a path produced /screen=10&filters=…
        // and poisoned a history entry (Back landed there and failed to load).
        const search = route.replace(/^\?/, "");
        navigate(search && search !== location.search.slice(1) ? `/screens?${search}` : "/screens");
      } else {
        navigate(`/${route}`);
      }
    });

    const unregSymbol = studioAgentBridge.registerAction("selectSymbol", async (args: any) => {
      setSelectedChartTicker(args.ticker);
      if (args.as_of) setAsOf(args.as_of);
      if (activeTab !== "charts") {
        handleTabChange("charts");
      }
    });

    const unregPreset = studioAgentBridge.registerAction("setPreset", async (args: any) => {
      selectPreset(args.preset_id);
      if (activeTab !== "screens") {
        handleTabChange("screens");
      }
    });

    const unregTemplate = studioAgentBridge.registerAction("setTemplate", async (args: any) => {
      const tid = (args.template_id || args.id || "").trim();
      if (tid) {
        await selectTemplate(tid);
        if (activeTab !== "screens") {
          handleTabChange("screens");
        }
      }
    });

    const unregScrub = studioAgentBridge.registerAction("scrubToDate", async (args: any) => {
      setAsOf(args.date);
    });

    // Initialize WebMCP tools and resources
    initWebMCP();

    return () => {
      unregNav();
      unregSymbol();
      unregPreset();
      unregTemplate();
      unregScrub();
    };
  }, [navigate, activeTab, selectPreset, selectTemplate, handleTabChange]);

  const handleSaveForBacktest = async (): Promise<number | string | null> => {
    if (!liveSpec || source !== "ir") return null;
    try {
      if (savedScreenId != null) {
        setSaving(true);
        const updated = await updateSavedScreen(savedScreenId, {
          spec: liveSpec,
        });
        markSaved(updated.id, liveSpec);
        await invalidateSavedScreens();
        setBacktestPrefill({
          universeSource: "saved",
          savedScreenId: updated.id,
          inlineSpec: liveSpec,
          title: backtestScreenTitle ?? updated.name,
          dirty: false,
        });
        flashSaved(`Saved “${updated.name}”`);
        return updated.id;
      }
      const prompted = await askScreenName({
        mode: "save-for-backtest",
        initial: backtestScreenTitle ?? "Screen",
      });
      if (!prompted) return null;
      const created = await persistNewScreen(prompted);
      if (!created) return null;
      setBacktestPrefill({
        universeSource: "saved",
        savedScreenId: created.id,
        inlineSpec: liveSpec,
        title: created.name,
        dirty: false,
      });
      return created.id;
    } catch (err) {
      console.error(err);
      window.alert(
        err instanceof Error ? err.message : "Save failed",
      );
      return null;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <NameDialog
        open={nameDialog != null}
        title={
          nameDialog?.mode === "rename"
            ? "Rename screen"
            : nameDialog?.mode === "save-for-backtest"
              ? "Save screen for backtest"
              : "Save screen as"
        }
        initialValue={nameDialog?.initial ?? ""}
        confirmLabel={nameDialog?.mode === "rename" ? "Rename" : "Save"}
        onCancel={() => closeNameDialog(null)}
        onConfirm={(value) => closeNameDialog(value)}
      />
      <TopBar
        dirty={dirty}
        saving={saving}
        onSave={() => {
          void handleSave();
        }}
        onSaveAs={() => {
          void handleSaveAs();
        }}
      />

      {saveFlash ? (
        <div className="border-b border-accent/30 bg-accent-soft px-4 py-1.5 text-[12px] text-ink">
          {saveFlash}
        </div>
      ) : null}

      {bootError ? (
        <div className="border-b border-danger/30 bg-danger-soft px-4 py-2 text-[12px] text-danger">
          API bootstrap failed: {bootError}. Is Django running on :8001?
        </div>
      ) : null}

      {activeTab === "screens" ? (
        <ScreensView
          initialTemplateId={templateId || (source === "preset" ? preset : undefined)}
          initialAsOfDate={asOf || todayIso}
          onNavigateToChart={(t, d) => {
            // Push so back/forward walks screener -> chart -> screener.
            setSelectedChartTicker(t);
            setAsOf(d);
            navigate(`${stockPath(t)}?as_of=${d}`);
          }}
          initialViewMode={urlState.view}
          onViewModeChange={setScreenerView}
          initialWhere={urlState.where}
          onTemplateChange={(id) => {
            void selectTemplate(id);
          }}
          onSavedScreenChange={(screen) => {
            if (screen) selectSavedScreen(screen);
          }}
          onSpecChange={(sp) => {
            setSpec(sp);
            setScreenEdited(true);
          }}
          onAsOfChange={setAsOf}
          onSendToStrategy={(sp, name) => {
            setBacktestPrefill({
              universeSource: "inline",
              inlineSpec: sp,
              title: name || "Custom Screen",
              dirty: true,
            });
            handleTabChange("compose");
          }}
        />
      ) : activeTab === "charts" ? (
        <ChartsView
          initialTicker={selectedChartTicker || "UBER"}
          initialAsOfDate={asOf || todayIso}
          onSelectTicker={(t) => navigate(stockPath(t))}
          onSelectDate={(d) => setAsOf(d)}
        />
      ) : activeTab === "watchlists" ? (
        <WatchlistsView
          onSelectTicker={(t) => {
            setSelectedChartTicker(t);
            handleTabChange("charts");
          }}
        />
      ) : activeTab === "market" ? (
        <MarketView
          initialAsOfDate={asOf || todayIso}
          onSelectDate={(d) => setAsOf(d)}
        />
      ) : activeTab === "monitor" ? (
        <MonitorView onModeChange={(m) => handleTabChange(m as WorkbenchTab)} />
      ) : (
        <BacktestView
          activeTab={activeTab}
          onTabChange={handleTabChange}
          savedScreens={savedScreens}
          savedScreenId={savedScreenId}
          liveSpec={liveSpec}
          backtestPrefill={backtestPrefill}
          presets={presetsQuery.data ?? []}
          routeStrategyIrId={routeStrategyIrId}
        />
      )}

      {/* Screener Studio Modal (Slot 1 Universe Laboratory) */}
      <ScreenerStudioModal
        isOpen={isScreenerModalOpen}
        onClose={() => setIsScreenerModalOpen(false)}
        onApplyToStrategy={() => {
          if (liveSpec && source === "ir") {
            void handleSaveForBacktest();
          }
          setIsScreenerModalOpen(false);
          handleTabChange("compose");
        }}
        presets={presetsQuery.data ?? []}
        templates={templatesQuery.data ?? []}
        savedScreens={savedScreensQuery.data ?? []}
        source={source}
        preset={preset}
        templateId={templateId}
        savedScreenId={savedScreenId}
        onSelectPreset={selectPreset}
        onSelectTemplate={(id) => {
          void selectTemplate(id);
        }}
        onSelectSaved={selectSavedScreen}
        onRenameSaved={(screen) => {
          void handleRenameSaved(screen);
        }}
        onDeleteSaved={(screen) => {
          void handleDeleteSaved(screen);
        }}
        rankedRows={rankedRows}
        selected={selected}
        onSelectRow={setSelected}
        loading={previewQuery.isFetching}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        gridVisibleCount={gridVisibleCount}
        onLoadMoreGrid={() => setGridVisibleCount((n) => n + RESULTS_GRID_CHUNK)}
        filterRows={filterRows}
        fields={fieldsQuery.data ?? []}
        spec={spec}
        onFilterRowsChange={onFilterRowsChange}
        onSpecChange={onSpecChange}
        previewData={previewQuery.data ?? null}
        datesDesc={datesDesc}
        asOf={asOf}
        onAsOfChange={setAsOf}
        turnover={turnover}
        turnoverLoading={
          previewQuery.isFetching ||
          priorPreviewQuery.isFetching ||
          turnoverApiQuery.isFetching
        }
      />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <FieldPickerProvider>
        <StudioApp />
      </FieldPickerProvider>
    </QueryClientProvider>
  );
}
