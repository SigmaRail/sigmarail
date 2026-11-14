import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  controlLocalLiveRuntime,
  fetchLiveAccountProfiles,
  fetchLiveBrokerages,
  fetchLiveDeploymentStatus,
  fetchLiveDeployments,
  fetchLocalLiveRuntime,
  fetchPromotionGate,
  registerPaperDeployment,
  saveLiveAccountProfile,
  verifyLiveAccountProfile,
  setLiveAccountProfileActive,
  deleteLiveAccountProfile,
} from "../api/live";
import { fetchBacktestRuns } from "../api/backtests";
import type {
  BacktestRunSummary,
  LiveDeploymentSummary,
  LiveAccountProfile,
  LiveBrokerageDescriptor,
  LocalLiveRuntime,
  PromotionGateResult,
} from "../types";
import { CopyIdBadge } from "./CopyIdBadge";
import { studioAgentBridge } from "../lib/studioAgentBridge";

function truncateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function formatNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function GateMetrics({ gate }: { gate: PromotionGateResult | undefined }) {
  if (!gate?.ok) return null;
  const summary = gate.run_summary;
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <MetricChip label="Total return" value={formatPct(summary?.total_return)} />
      <MetricChip label="Sharpe" value={formatNum(summary?.sharpe_ratio)} />
      <MetricChip label="Max DD" value={formatPct(summary?.max_drawdown)} />
      <MetricChip label="Annual" value={formatPct(summary?.annual_return)} />
    </div>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-surface px-2.5 py-2">
      <div className="text-[10px] text-ink-muted">{label}</div>
      <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function DeploymentRow({
  deployment,
  selected,
  onSelect,
}: {
  deployment: LiveDeploymentSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full border-b border-line px-3 py-2.5 text-left transition-colors ${
        selected
          ? "border-l-2 border-l-accent bg-accent-soft/60"
          : "border-l-2 border-l-transparent hover:bg-surface-sunk"
      }`}
    >
      <div className="font-mono text-[11px] font-medium text-ink">
        {truncateId(deployment.deployment_id)}
      </div>
      <div className="mt-0.5 truncate font-mono text-[10px] text-ink-faint">
        {deployment.ir_id ?? "—"}
      </div>
      <div className="mt-1 flex flex-wrap gap-2 text-[10px]">
        <span className="rounded bg-surface-sunk px-1.5 py-0.5 text-ink-muted">
          {deployment.status ?? "unknown"}
        </span>
        {deployment.lean_environment ? (
          <span className="text-ink-faint">{deployment.lean_environment}</span>
        ) : null}
      </div>
    </button>
  );
}

export function PromotePanel({
  initialRunId,
}: {
  initialRunId?: string | null;
}) {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    initialRunId ?? null,
  );
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string | null>(
    null,
  );
  const [selectedLocalDeploymentId, setSelectedLocalDeploymentId] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registerSuccess, setRegisterSuccess] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [accountProvider, setAccountProvider] = useState("alpaca");
  const [accountDataProvider, setAccountDataProvider] = useState("alpaca");
  const [accountEnvironment, setAccountEnvironment] = useState<"paper" | "live">("paper");
  const [accountName, setAccountName] = useState("Alpaca paper");
  const [accountIdentifier, setAccountIdentifier] = useState("");
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
  const [accountMessage, setAccountMessage] = useState<string | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [verificationMessage, setVerificationMessage] = useState<string | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["backtest-runs"],
    queryFn: () => fetchBacktestRuns(30),
  });

  const deploymentsQuery = useQuery({
    queryKey: ["live-deployments"],
    queryFn: () => fetchLiveDeployments(20),
  });

  const accountQuery = useQuery({
    queryKey: ["live-account-profiles"],
    queryFn: fetchLiveAccountProfiles,
  });
  const brokerageQuery = useQuery({ queryKey: ["live-brokerages"], queryFn: fetchLiveBrokerages });
  const brokerages = brokerageQuery.data?.brokerages ?? [];
  const dataProviders = brokerageQuery.data?.data_providers ?? [];
  const accounts = accountQuery.data ?? [];
  const account: LiveAccountProfile | undefined = creatingAccount ? undefined : (accounts.find((item) => item.id === selectedAccountId) ?? accounts[0]);
  const selectedBrokerage: LiveBrokerageDescriptor | undefined = brokerages.find((item) => item.id === accountProvider);
  const selectedDataProvider = dataProviders.find((item) => item.id === accountDataProvider);
  const credentialFields = Array.from(new Map(
    [...(selectedBrokerage?.credentials ?? []), ...(selectedDataProvider?.credentials ?? [])].map((field) => [field.key, field]),
  ).values());

  const runtimeQuery = useQuery({
    queryKey: ["local-live-runtime"],
    queryFn: fetchLocalLiveRuntime,
    refetchInterval: (query) =>
      ["starting", "running", "stopping"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  const runtime: LocalLiveRuntime | undefined = runtimeQuery.data;

  useEffect(() => {
    const localDeployments = runtime?.deployments ?? [];
    if (localDeployments.length === 0) {
      setSelectedLocalDeploymentId(null);
      return;
    }
    if (!selectedLocalDeploymentId || !localDeployments.some((item) => item.deployment_id === selectedLocalDeploymentId)) {
      setSelectedLocalDeploymentId(localDeployments[0].deployment_id ?? null);
    }
  }, [runtime?.deployments, selectedLocalDeploymentId]);

  useEffect(() => {
    if (account) {
      setVerificationMessage(null);
      setSelectedAccountId(account.id);
      setAccountProvider(account.provider);
      setAccountDataProvider(account.data_provider);
      setAccountEnvironment(account.environment);
      setAccountName(account.display_name);
      setAccountIdentifier(account.account_identifier);
    }
  }, [account?.id]);

  const runs = runsQuery.data ?? [];
  const deployments = deploymentsQuery.data ?? [];

  const selectedRun: BacktestRunSummary | undefined = useMemo(
    () => runs.find((r) => r.run_id === selectedRunId),
    [runs, selectedRunId],
  );

  const irId = selectedRun?.ir_id?.trim() ?? "";

  useEffect(() => {
    if (initialRunId) {
      setSelectedRunId(initialRunId);
    }
  }, [initialRunId]);

  useEffect(() => {
    if (runs.length === 0) {
      setSelectedRunId(null);
      return;
    }
    if (!selectedRunId || !runs.some((r) => r.run_id === selectedRunId)) {
      setSelectedRunId(initialRunId ?? runs[0].run_id);
    }
  }, [runs, selectedRunId, initialRunId]);

  useEffect(() => {
    if (deployments.length === 0) {
      setSelectedDeploymentId(null);
      return;
    }
    if (
      !selectedDeploymentId ||
      !deployments.some((d) => d.deployment_id === selectedDeploymentId)
    ) {
      setSelectedDeploymentId(deployments[0].deployment_id);
    }
  }, [deployments, selectedDeploymentId]);

  const gateQuery = useQuery({
    queryKey: ["promotion-gate", selectedRunId, irId],
    queryFn: () => fetchPromotionGate(irId, selectedRunId!),
    enabled: Boolean(selectedRunId && irId),
    retry: false,
  });

  const statusQuery = useQuery({
    queryKey: ["live-deployment-status", selectedDeploymentId],
    queryFn: () => fetchLiveDeploymentStatus(selectedDeploymentId!),
    enabled: Boolean(selectedDeploymentId),
  });

  const saveAccountMutation = useMutation({
    mutationFn: () => saveLiveAccountProfile({
      ...(account && account.id === selectedAccountId ? { id: account.id } : {}),
      provider: accountProvider,
      data_provider: accountDataProvider,
      environment: accountEnvironment,
      display_name: accountName,
      account_identifier: accountIdentifier,
      ...(Object.values(credentialValues).some(Boolean) ? { credentials: credentialValues } : {}),
    }),
    onSuccess: (profile) => {
      setAccountError(null);
      setAccountMessage(profile.credentials_configured ? "Account details saved; credentials are secured in the OS vault." : "Account details saved. Add the required broker credentials to enable deployment.");
      setVerificationMessage(null);
      setSelectedAccountId(profile.id);
      setCreatingAccount(false);
      setCredentialValues({});
      void queryClient.invalidateQueries({ queryKey: ["live-account-profiles"] });
    },
    onError: (err: Error) => {
      setAccountMessage(null);
      setAccountError(err.message);
    },
  });

  const verifyAccountMutation = useMutation({
    mutationFn: (profileId: string) => verifyLiveAccountProfile(profileId),
    onSuccess: (result) => {
      setAccountError(null);
      setVerificationMessage(result.message);
    },
    onError: (err: Error) => setAccountError(err.message),
  });

  const accountActiveMutation = useMutation({
    mutationFn: ({ profileId, active }: { profileId: string; active: boolean }) => setLiveAccountProfileActive(profileId, active),
    onSuccess: (profile) => {
      setAccountError(null);
      setAccountMessage(profile.active ? "Account enabled for new launches." : "Account disabled for new launches; deployment history and credentials are preserved.");
      void queryClient.invalidateQueries({ queryKey: ["live-account-profiles"] });
    },
    onError: (err: Error) => setAccountError(err.message),
  });

  const deleteAccountMutation = useMutation({
    mutationFn: (profileId: string) => deleteLiveAccountProfile(profileId),
    onSuccess: () => {
      setAccountError(null);
      setAccountMessage("Account profile and its OS-vault credentials were removed.");
      setSelectedAccountId(null);
      setCreatingAccount(true);
      setVerificationMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["live-account-profiles"] });
    },
    onError: (err: Error) => setAccountError(err.message),
  });

  const runtimeAction = useMutation({
    mutationFn: (body:
      | { action: "start-paper" | "start-live"; ir_id: string; approval_backtest_run_id: string; account_profile_id: string; live_confirmation?: string }
      | { action: "stop" | "liquidate"; deployment_id: string; confirmation?: string }) => controlLocalLiveRuntime(body),
    onSuccess: (result) => {
      setRuntimeError(null);
      const deploymentId = result.deployment.deployment_id;
      setRegisterSuccess(result.deployment.last_action === "liquidate_orders_submitted"
        ? `Liquidation orders submitted for ${deploymentId ? truncateId(deploymentId) : "the deployment"}; LEAN remains running.`
        : `${result.deployment.mode === "live" ? "Live" : "Paper"} runtime ${result.deployment.status}: ${deploymentId ? truncateId(deploymentId) : "unknown"}`);
      void queryClient.invalidateQueries({ queryKey: ["local-live-runtime"] });
      void queryClient.invalidateQueries({ queryKey: ["live-deployments"] });
      if (deploymentId) {
        setSelectedDeploymentId(deploymentId);
        setSelectedLocalDeploymentId(deploymentId);
      }
    },
    onError: (err: Error) => setRuntimeError(err.message),
  });

  const canPromote = Boolean(gateQuery.data?.ok && irId && selectedRunId);
  const runtimeDeployments = runtime?.deployments ?? [];
  const runtimeDeployment = runtimeDeployments.find((item) => item.deployment_id === selectedLocalDeploymentId) ?? runtime?.deployment;
  const runtimeLimitReached = runtime?.status === "external_running" || (runtime?.active_count ?? 0) >= (runtime?.max_concurrent ?? 2);

  // --- WebMCP action bindings (Component 3: agent control of the deploy panel) ---
  useEffect(() => {
    const unregSelect = studioAgentBridge.registerAction(
      "deploySelectRun",
      ({ run_id }: { run_id: string }) => {
        setRegisterError(null);
        setRegisterSuccess(null);
        setSelectedRunId(run_id);
        return { selected_run_id: run_id };
      }
    );
    const unregRegister = studioAgentBridge.registerAction("deployRegisterPaper", async () => {
      const data = await registerPaperDeployment({
        ir_id: irId,
        approval_backtest_run_id: selectedRunId!,
      });
      setRegisterError(null);
      setRegisterSuccess(`Registered paper deployment ${truncateId(data.deployment_id)}`);
      void queryClient.invalidateQueries({ queryKey: ["live-deployments"] });
      setSelectedDeploymentId(data.deployment_id);
      return { registered: true, run_id: selectedRunId, ir_id: irId, deployment_id: data.deployment_id };
    });
    return () => {
      unregSelect();
      unregRegister();
    };
  }, [queryClient, irId, selectedRunId]);

  useEffect(() => {
    studioAgentBridge.updateState({
      selectedDeploymentId,
      promotionGateStatus: gateQuery.data ?? null,
    });
  }, [selectedDeploymentId, gateQuery.data]);

  return (
    <div className="flex min-h-0 flex-1 bg-surface">
      <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-surface-raised">
        <div className="border-b border-line px-3 py-3">
          <h2 className="text-sm font-semibold text-ink">Backtest runs</h2>
          <p className="mt-0.5 text-[11px] text-ink-muted">Select run to promote</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {runsQuery.isLoading ? (
            <div className="px-3 py-6 text-[12px] text-ink-muted">Loading runs…</div>
          ) : runs.length === 0 ? (
            <div className="px-3 py-8 text-center text-[11px] text-ink-muted">
              No completed runs yet.
            </div>
          ) : (
            runs.map((run) => (
              <button
                key={run.run_id}
                type="button"
                onClick={() => {
                  setRegisterError(null);
                  setRegisterSuccess(null);
                  setSelectedRunId(run.run_id);
                }}
                className={`w-full border-b border-line px-3 py-2.5 text-left ${
                  run.run_id === selectedRunId
                    ? "border-l-2 border-l-accent bg-accent-soft/60"
                    : "border-l-2 border-l-transparent hover:bg-surface-sunk"
                }`}
              >
                <div className="font-mono text-[11px] font-medium text-ink">
                  {truncateId(run.run_id)}
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-ink-faint">
                  {run.ir_id ?? "—"}
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface-raised p-4">
        <section className="mb-6 max-w-5xl">
          <h2 className="text-sm font-semibold text-ink">Local LEAN trading</h2>
          <p className="mt-1 text-[12px] text-ink-muted">
            Run up to two isolated local LEAN Docker deployments with a supported brokerage and account profile.
          </p>

          <div className="mt-4 rounded border border-line bg-surface p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="text-[13px] font-semibold text-ink">Brokerage account</h3>
                <p className="mt-0.5 text-[11px] text-ink-muted">Account details are stored in Studio’s local database. Broker credentials go to the operating-system credential vault.</p>
              </div>
              <span className={`rounded px-2 py-1 text-[10px] ${account?.credentials_configured ? "bg-accent-soft text-accent" : "bg-surface-sunk text-ink-muted"}`}>
                {account?.credentials_configured ? "Credentials secured" : "Not connected"}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <label className="text-[11px] text-ink-muted">Saved account
                <select value={creatingAccount ? "new" : (account?.id ?? "new")} onChange={(e) => {
                  if (e.target.value === "new") {
                    setCreatingAccount(true); setSelectedAccountId(null); setAccountProvider("alpaca"); setAccountDataProvider("alpaca"); setAccountEnvironment("paper"); setAccountName("Alpaca paper"); setAccountIdentifier(""); setCredentialValues({});
                  } else {
                    setCreatingAccount(false); setSelectedAccountId(e.target.value);
                  }
                }} className="ml-2 rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink">
                  {accounts.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.provider} · {item.environment} · {item.data_provider} feed{item.active ? "" : " · disabled"}</option>)}
                  <option value="new">+ Add account</option>
                </select>
              </label>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="text-[11px] text-ink-muted">LEAN brokerage
                <select value={accountProvider} disabled={!creatingAccount && Boolean(account)} onChange={(e) => {
                  const next = brokerages.find((item) => item.id === e.target.value);
                  setAccountProvider(e.target.value);
                  setAccountDataProvider(next?.default_data_provider ?? "alpaca");
                  const nextEnv = next?.environments.paper ? "paper" : "live";
                  setAccountEnvironment(nextEnv);
                  setAccountName(`${next?.label ?? e.target.value} ${nextEnv}`);
                  setCredentialValues({});
                }} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink">
                  {brokerages.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-ink-muted">Live data provider (separate from brokerage)
                <select value={accountDataProvider} disabled={!creatingAccount && Boolean(account)} onChange={(e) => { setAccountDataProvider(e.target.value); setCredentialValues({}); }} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink">
                  {dataProviders.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-ink-muted">Account environment
                <select value={accountEnvironment} disabled={!creatingAccount && Boolean(account)} onChange={(e) => { setAccountEnvironment(e.target.value as "paper" | "live"); setAccountName(`${selectedBrokerage?.label ?? accountProvider} ${e.target.value}`); }} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink">
                  {(Object.keys(selectedBrokerage?.environments ?? { paper: "paper" }) as Array<"paper" | "live">).map((env) => <option key={env} value={env}>{env === "live" ? "Live account" : "Paper / test account"}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-ink-muted">Account label
                <input value={accountName} onChange={(e) => setAccountName(e.target.value)} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink" />
              </label>
              <label className="text-[11px] text-ink-muted">Account ID / label (optional)
                <input value={accountIdentifier} onChange={(e) => setAccountIdentifier(e.target.value)} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink" />
              </label>
              {credentialFields.map((field) => <label key={field.key} className="text-[11px] text-ink-muted">{field.label}
                {field.choices ? (
                  <select value={credentialValues[field.key] ?? ""} onChange={(e) => setCredentialValues((current) => ({ ...current, [field.key]: e.target.value }))} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 text-[12px] text-ink">
                    <option value="">Choose…</option>
                    {field.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
                  </select>
                ) : (
                  <input type={field.secret ? "password" : "text"} autoComplete="new-password" value={credentialValues[field.key] ?? ""} onChange={(e) => setCredentialValues((current) => ({ ...current, [field.key]: e.target.value }))} className="mt-1 w-full rounded border border-line bg-surface-raised px-2 py-1.5 font-mono text-[12px] text-ink" />
                )}
              </label>)}
            </div>
            <p className="mt-2 text-[10px] text-ink-faint">Real-time coverage depends on the selected provider’s subscription, market, and instrument entitlements. A paper brokerage account can still use a separate live-data provider.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button type="button" disabled={saveAccountMutation.isPending || !accountName.trim()} onClick={() => saveAccountMutation.mutate()} className="rounded border border-line px-3 py-1.5 text-[11px] font-medium text-ink disabled:opacity-40">
                {saveAccountMutation.isPending ? "Saving…" : "Save account and vault credentials"}
              </button>
              {account ? (
                <>
                  {account.connection_verification_available ? (
                    <button type="button" disabled={!account.credentials_configured || verifyAccountMutation.isPending} onClick={() => verifyAccountMutation.mutate(account.id)} className="rounded border border-line px-3 py-1.5 text-[11px] font-medium text-ink disabled:opacity-40">
                      {verifyAccountMutation.isPending ? "Verifying…" : "Verify broker connection"}
                    </button>
                  ) : null}
                  <button type="button" disabled={accountActiveMutation.isPending} onClick={() => accountActiveMutation.mutate({ profileId: account.id, active: !account.active })} className="rounded border border-line px-3 py-1.5 text-[11px] font-medium text-ink disabled:opacity-40">
                    {account.active ? "Disable account" : "Enable account"}
                  </button>
                  <button type="button" disabled={deleteAccountMutation.isPending} onClick={() => {
                    if (window.confirm(`Remove ${account.display_name} and its credentials from the OS vault? This cannot be undone.`)) deleteAccountMutation.mutate(account.id);
                  }} className="rounded border border-danger/50 px-3 py-1.5 text-[11px] font-medium text-danger disabled:opacity-40">
                    Remove account
                  </button>
                </>
              ) : null}
              {account?.account_identifier ? <span className="text-[10px] text-ink-faint">Account: {account.account_identifier}</span> : null}
            </div>
            {accountError ? <p className="mt-2 text-[11px] text-danger">{accountError}</p> : null}
            {accountMessage ? <p className="mt-2 text-[11px] text-accent">{accountMessage}</p> : null}
            {verificationMessage ? <p className="mt-2 text-[11px] text-accent">{verificationMessage}</p> : account?.credentials_configured ? <p className="mt-2 text-[11px] text-ink-muted">Credentials configured; connection not verified. A broker check does not confirm market-data entitlement.</p> : null}
          </div>

          <div className="mt-3 rounded border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-[12px] font-semibold text-ink">Runtime: {runtime?.status ?? "checking"}</div>
                <div className="mt-0.5 text-[10px] text-ink-muted">{runtime?.active_count ?? 0}/{runtime?.max_concurrent ?? 2} local deployments active · {runtimeDeployment ? `${runtimeDeployment.account_name ?? "Unmanaged runtime"} · ${runtimeDeployment.project} · ${runtimeDeployment.mode}` : "VeraTradingLab · local Docker"}</div>
                {runtimeDeployment?.container_name ? <div className="mt-0.5 font-mono text-[10px] text-ink-faint">{runtimeDeployment.container_name} · Docker {runtimeDeployment.container_status ?? "unknown"}</div> : null}
              </div>
              {runtimeDeployment?.deployment_id && runtimeDeployment.account_profile_id && runtimeDeployment.status === "running" ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={runtimeAction.isPending} onClick={() => {
                    const deploymentId = runtimeDeployment.deployment_id!;
                    if (runtimeDeployment.mode === "live") {
                      const expected = `STOP ${deploymentId.slice(-8)}`;
                      if (window.prompt(`This stops the LIVE algorithm; any open positions remain at the broker. Type ${expected} to continue.`) === expected) runtimeAction.mutate({ action: "stop", deployment_id: deploymentId, confirmation: expected });
                    } else if (window.confirm("Stop this LEAN algorithm and Docker container? Existing paper positions will remain open.")) {
                      runtimeAction.mutate({ action: "stop", deployment_id: deploymentId });
                    }
                  }} className="rounded border border-line px-3 py-1.5 text-[11px] font-medium text-ink disabled:opacity-40">Stop selected</button>
                  <button type="button" disabled={runtimeAction.isPending} onClick={() => {
                    const deploymentId = runtimeDeployment.deployment_id!;
                    const isLive = runtimeDeployment.mode === "live";
                    if (isLive) {
                      const expected = `LIQUIDATE ${deploymentId.slice(-8)}`;
                      if (window.prompt(`This submits liquidation orders to a LIVE account. Type ${expected} to continue.`) === expected) runtimeAction.mutate({ action: "liquidate", deployment_id: deploymentId, confirmation: expected });
                    } else if (window.confirm("Send market liquidation orders for all open paper positions? LEAN will stay running so you can confirm fills.")) {
                      runtimeAction.mutate({ action: "liquidate", deployment_id: deploymentId });
                    }
                  }} className="rounded border border-danger/50 px-3 py-1.5 text-[11px] font-medium text-danger disabled:opacity-40">Liquidate selected</button>
                </div>
              ) : null}
            </div>
            {runtime?.status === "external_running" ? <p className="mt-2 text-[11px] text-warn">A LEAN container is running outside Studio’s managed state. Studio will not stop or liquidate it.</p> : null}
            {!runtime?.enabled ? <p className="mt-2 text-[11px] text-warn">Controls are disabled. Set <code>VERA_ENABLE_LOCAL_LEAN_CONTROL=1</code> for the Studio API process and restart it.</p> : null}
            {runtimeError ? <p className="mt-2 text-[11px] text-danger">{runtimeError}</p> : null}
            {runtimeDeployment?.output_dir ? <p className="mt-2 break-all font-mono text-[10px] text-ink-faint">LEAN output: {runtimeDeployment.output_dir}</p> : null}
            {runtimeDeployments.length > 0 ? (
              <div className="mt-3 space-y-1 border-t border-line pt-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Managed deployments</div>
                {runtimeDeployments.map((deployment) => (
                  <button key={deployment.deployment_id} type="button" onClick={() => setSelectedLocalDeploymentId(deployment.deployment_id ?? null)} className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-[11px] ${deployment.deployment_id === selectedLocalDeploymentId ? "bg-accent-soft text-accent" : "text-ink hover:bg-surface-sunk"}`}>
                    <span className="min-w-0 truncate">{deployment.account_name ?? "Paper account"} · {deployment.ir_id ?? "strategy"}</span>
                    <span className="shrink-0 font-mono">{deployment.status}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {selectedRun ? (
            <div className="mt-4 rounded border border-line bg-surface p-3">
              <dl className="grid gap-2 text-[12px] sm:grid-cols-2">
                <div>
                  <dt className="font-mono text-[10px] text-ink-faint">run_id</dt>
                  <dd className="font-mono break-all text-ink">{selectedRun.run_id}</dd>
                </div>
                <div>
                  <dt className="font-mono text-[10px] text-ink-faint">ir_id</dt>
                  <dd className="font-mono break-all text-ink">{irId || "—"}</dd>
                </div>
              </dl>

              {gateQuery.isLoading ? (
                <p className="mt-3 text-[12px] text-ink-muted">Checking promotion gate…</p>
              ) : gateQuery.isError ? (
                <p className="mt-3 text-[12px] text-danger">
                  {(gateQuery.error as Error).message}
                </p>
              ) : gateQuery.data && !gateQuery.data.ok ? (
                <p className="mt-3 text-[12px] text-warn">
                  {gateQuery.data.error ?? "Run is not eligible for promotion"}
                </p>
              ) : (
                <>
                  <GateMetrics gate={gateQuery.data} />
                  {gateQuery.data?.warnings && gateQuery.data.warnings.length > 0 ? (
                    <ul className="mt-3 space-y-1">
                      {gateQuery.data.warnings.map((w) => (
                        <li
                          key={w}
                          className="rounded border border-warn/40 bg-warn-soft px-2 py-1 text-[11px] text-warn"
                        >
                          {w}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {gateQuery.data?.highlights && gateQuery.data.highlights.length > 0 ? (
                    <ul className="mt-3 space-y-1">
                      {gateQuery.data.highlights.map((h) => (
                        <li
                          key={h}
                          className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] text-ink-muted"
                        >
                          {h}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              )}

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!canPromote || !runtime?.enabled || !account?.active || !account?.credentials_configured || runtimeLimitReached || runtimeAction.isPending}
                  onClick={() => {
                    if (!account) return;
                    if (account.environment === "paper") {
                      if (window.confirm(`Start a PAPER LEAN deployment for ${account.display_name}? This will submit orders to the paper account.`)) {
                        runtimeAction.mutate({ action: "start-paper", ir_id: irId, approval_backtest_run_id: selectedRunId!, account_profile_id: account.id });
                      }
                    } else {
                      const expected = `LIVE ${account.display_name}`;
                      if (window.prompt(`This starts a LIVE brokerage account and may place real orders. Type ${expected} to continue.`) === expected) runtimeAction.mutate({ action: "start-live", ir_id: irId, approval_backtest_run_id: selectedRunId!, account_profile_id: account.id, live_confirmation: expected });
                    }
                  }}
                  className="rounded bg-ink px-3 py-1.5 text-[12px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {runtimeAction.isPending ? "Starting…" : `Start ${account?.environment === "live" ? "LIVE" : "paper"} ${selectedBrokerage?.label ?? "LEAN"} deployment`}
                </button>
                {runtimeLimitReached ? <span className="text-[11px] text-warn">{runtime?.status === "external_running" ? "Stop the unmanaged LEAN runtime before starting a Studio deployment." : `Stop a managed run before starting another (limit ${runtime?.max_concurrent ?? 2}).`}</span> : null}
                {!account?.credentials_configured ? <span className="text-[11px] text-warn">Save this account and its credentials first</span> : null}
                {account?.environment === "live" ? <span className="rounded bg-danger-soft px-2 py-1 text-[11px] font-semibold text-danger">LIVE account — orders can move real money</span> : null}
                {!irId ? (
                  <span className="text-[11px] text-warn">Run has no ir_id</span>
                ) : null}
              </div>

              {registerError ? (
                <p className="mt-2 text-[12px] text-danger">{registerError}</p>
              ) : null}
              {registerSuccess ? (
                <p className="mt-2 text-[12px] text-accent">{registerSuccess}</p>
              ) : null}
            </div>
          ) : (
            <p className="mt-4 text-[12px] text-ink-muted">Select a backtest run.</p>
          )}
        </section>

        <section className="flex min-h-0 flex-1 flex-col border-t border-line pt-4">
          <h3 className="text-sm font-semibold text-ink">Active deployments</h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">live_deployments · ClickHouse</p>

          <div className="mt-3 flex min-h-0 flex-1 gap-0 rounded border border-line bg-surface">
            <div className="w-72 shrink-0 overflow-y-auto border-r border-line">
              {deploymentsQuery.isLoading ? (
                <div className="px-3 py-6 text-[12px] text-ink-muted">Loading…</div>
              ) : deployments.length === 0 ? (
                <div className="px-3 py-8 text-center text-[11px] text-ink-muted">
                  No paper deployments registered.
                </div>
              ) : (
                deployments.map((d) => (
                  <DeploymentRow
                    key={d.deployment_id}
                    deployment={d}
                    selected={d.deployment_id === selectedDeploymentId}
                    onSelect={() => setSelectedDeploymentId(d.deployment_id)}
                  />
                ))
              )}
            </div>
            <div className="min-w-0 flex-1 overflow-y-auto p-4">
              {!selectedDeploymentId ? (
                <p className="text-[12px] text-ink-muted">Select a deployment.</p>
              ) : statusQuery.isLoading ? (
                <p className="text-[12px] text-ink-muted">Loading status…</p>
              ) : statusQuery.isError ? (
                <p className="text-[12px] text-danger">
                  {(statusQuery.error as Error).message}
                </p>
              ) : statusQuery.data ? (
                <div className="space-y-3 text-[12px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <CopyIdBadge
                      id={selectedDeploymentId}
                      label="Deployment"
                      head={10}
                      tail={8}
                      sqlQuery={`SELECT * FROM live_deployments FINAL WHERE deployment_id = '${selectedDeploymentId}'`}
                    />
                  </div>
                  {statusQuery.data.highlights?.map((h) => (
                    <div
                      key={h}
                      className="rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-ink"
                    >
                      {h}
                    </div>
                  ))}
                  {statusQuery.data.latest_snapshot ? (
                    <pre className="overflow-x-auto rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] text-ink-muted">
                      {JSON.stringify(statusQuery.data.latest_snapshot, null, 2)}
                    </pre>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
