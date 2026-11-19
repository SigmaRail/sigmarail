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
import { PageHeadline } from "@sb/webapp-core/components/pageHeadline";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

function ProfileSelectField({
  label,
  value,
  onValueChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  return (
    <div className="min-w-0">
      <label className="mb-1.5 block text-sm font-medium">{label}</label>
      <Select value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectTrigger className="h-9 w-full text-sm"><SelectValue /></SelectTrigger>
        <SelectContent>{options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
}

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
    <div className="rounded-md border bg-card px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-semibold tabular-nums">{value}</div>
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
    <Button
      type="button"
      onClick={onSelect}
      variant={selected ? "secondary" : "ghost"}
      className="h-auto w-full justify-start rounded-none border-b px-3 py-2.5 text-left"
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
        {deployment.is_shared ? <Badge variant="muted">Shared</Badge> : null}
        {deployment.lean_environment ? (
          <span className="text-ink-faint">{deployment.lean_environment}</span>
        ) : null}
      </div>
    </Button>
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
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b px-3 py-3 sm:px-4">
        <PageHeadline
          header="Deploy"
          subheader="Choose a backtest, configure an account, and manage a local runtime."
          className="space-y-1"
        />
      </header>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <aside className="flex max-h-48 w-full shrink-0 flex-col border-b bg-background lg:max-h-none lg:w-72 lg:border-b-0 lg:border-r">
        <div className="border-b px-3 py-2.5">
          <h2 className="text-sm font-semibold">Backtest runs</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">Select a run to review its deployment gate.</p>
        </div>
        <div className="flex min-h-0 flex-1 gap-2 overflow-x-auto overflow-y-hidden p-2 lg:block lg:space-y-1 lg:overflow-x-hidden lg:overflow-y-auto">
          {runsQuery.isLoading ? (
            <div className="px-3 py-6 text-sm text-muted-foreground">Loading runs…</div>
          ) : runs.length === 0 ? (
            <div className="min-w-48 px-3 py-6 text-center text-sm text-muted-foreground lg:min-w-0">
              No completed runs yet.
            </div>
          ) : (
            runs.map((run) => (
              <Button
                key={run.run_id}
                type="button"
                onClick={() => {
                  setRegisterError(null);
                  setRegisterSuccess(null);
                  setSelectedRunId(run.run_id);
                }}
                variant={run.run_id === selectedRunId ? "secondary" : "ghost"}
                className="h-auto min-w-48 shrink-0 justify-start rounded-md border px-3 py-2.5 text-left lg:w-full lg:min-w-0 lg:rounded-none lg:border-x-0 lg:border-t-0"
              >
                <div className="font-mono text-[11px] font-medium text-ink">
                  {truncateId(run.run_id)}
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-ink-faint">
                  {run.ir_id ?? "—"}
                </div>
              </Button>
            ))
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface-raised p-4">
        <section className="mb-6 max-w-5xl space-y-3">
          <div>
            <h2 className="text-lg font-semibold">Local runtime</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Configure a brokerage profile and review the selected backtest before starting a local runtime.
            </p>
          </div>

          <Card className="p-3 shadow-none sm:p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">Brokerage account</h3>
                <p className="mt-1 text-xs text-muted-foreground">Account settings are stored locally. Broker credentials go to the operating-system credential vault.</p>
              </div>
              <Badge variant={account?.credentials_configured ? "success" : "muted"}>
                {account?.credentials_configured ? "Credentials secured" : "Not connected"}
              </Badge>
            </div>
            <div className="mt-4 max-w-lg">
              <ProfileSelectField
                label="Account profile"
                value={creatingAccount ? "new" : (account?.id ?? "new")}
                onValueChange={(value) => {
                  if (value === "new") {
                    setCreatingAccount(true); setSelectedAccountId(null); setAccountProvider("alpaca"); setAccountDataProvider("alpaca"); setAccountEnvironment("paper"); setAccountName("Alpaca paper"); setAccountIdentifier(""); setCredentialValues({});
                  } else {
                    setCreatingAccount(false); setSelectedAccountId(value);
                  }
                }}
                options={[
                  ...accounts.map((item) => ({ value: item.id, label: `${item.display_name} · ${item.provider} · ${item.environment}` })),
                  { value: "new", label: "Add account" },
                ]}
              />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <ProfileSelectField label="Brokerage" value={accountProvider} disabled={!creatingAccount && Boolean(account)} onValueChange={(value) => {
                  const next = brokerages.find((item) => item.id === value);
                  setAccountProvider(value);
                  setAccountDataProvider(next?.default_data_provider ?? "alpaca");
                  const nextEnv = next?.environments.paper ? "paper" : "live";
                  setAccountEnvironment(nextEnv);
                  setAccountName(`${next?.label ?? value} ${nextEnv}`);
                  setCredentialValues({});
                }} options={brokerages.map((item) => ({ value: item.id, label: item.label }))} />
              <ProfileSelectField label="Market data provider" value={accountDataProvider} disabled={!creatingAccount && Boolean(account)} onValueChange={(value) => { setAccountDataProvider(value); setCredentialValues({}); }} options={dataProviders.map((item) => ({ value: item.id, label: item.label }))} />
              <ProfileSelectField label="Account environment" value={accountEnvironment} disabled={!creatingAccount && Boolean(account)} onValueChange={(value) => { setAccountEnvironment(value as "paper" | "live"); setAccountName(`${selectedBrokerage?.label ?? accountProvider} ${value}`); }} options={(Object.keys(selectedBrokerage?.environments ?? { paper: "paper" }) as Array<"paper" | "live">).map((env) => ({ value: env, label: env === "live" ? "Live account" : "Paper / test account" }))} />
              <label className="block text-sm font-medium">Account name
                <Input value={accountName} onChange={(e) => setAccountName(e.target.value)} className="mt-1.5 h-9" />
              </label>
              <label className="block text-sm font-medium">Account ID or label (optional)
                <Input value={accountIdentifier} onChange={(e) => setAccountIdentifier(e.target.value)} className="mt-1.5 h-9" />
              </label>
              {credentialFields.map((field) => <div key={field.key}>
                {field.choices ? (
                  <ProfileSelectField label={field.label} value={credentialValues[field.key] || "__unset__"} onValueChange={(value) => setCredentialValues((current) => ({ ...current, [field.key]: value === "__unset__" ? "" : value }))} options={[{ value: "__unset__", label: "Choose…" }, ...field.choices.map((choice) => ({ value: choice, label: choice }))]} />
                ) : (
                  <label className="block text-sm font-medium">{field.label}<Input type={field.secret ? "password" : "text"} autoComplete="new-password" value={credentialValues[field.key] ?? ""} onChange={(e) => setCredentialValues((current) => ({ ...current, [field.key]: e.target.value }))} className="mt-1.5 h-9 font-mono" /></label>
                )}
              </div>)}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">Market-data coverage depends on your provider plan and instrument entitlements. Paper trading can use a separate market-data provider.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" disabled={saveAccountMutation.isPending || !accountName.trim()} onClick={() => saveAccountMutation.mutate()}>
                {saveAccountMutation.isPending ? "Saving…" : "Save account and vault credentials"}
              </Button>
              {account ? (
                <>
                  {account.connection_verification_available ? (
                    <Button type="button" variant="outline" size="sm" disabled={!account.credentials_configured || verifyAccountMutation.isPending} onClick={() => verifyAccountMutation.mutate(account.id)}>
                      {verifyAccountMutation.isPending ? "Verifying…" : "Verify broker connection"}
                    </Button>
                  ) : null}
                  <Button type="button" variant="outline" size="sm" disabled={accountActiveMutation.isPending} onClick={() => accountActiveMutation.mutate({ profileId: account.id, active: !account.active })}>
                    {account.active ? "Disable account" : "Enable account"}
                  </Button>
                  <Button type="button" variant="destructive" size="sm" disabled={deleteAccountMutation.isPending} onClick={() => {
                    if (window.confirm(`Remove ${account.display_name} and its credentials from the OS vault? This cannot be undone.`)) deleteAccountMutation.mutate(account.id);
                  }}>
                    Remove account
                  </Button>
                </>
              ) : null}
              {account?.account_identifier ? <span className="text-[10px] text-ink-faint">Account: {account.account_identifier}</span> : null}
            </div>
            {accountError ? <p className="mt-2 text-[11px] text-danger">{accountError}</p> : null}
            {accountMessage ? <p className="mt-2 text-[11px] text-accent">{accountMessage}</p> : null}
            {verificationMessage ? <p className="mt-2 text-[11px] text-accent">{verificationMessage}</p> : account?.credentials_configured ? <p className="mt-2 text-[11px] text-ink-muted">Credentials configured; connection not verified. A broker check does not confirm market-data entitlement.</p> : null}
          </Card>

          <Card className="p-3 shadow-none sm:p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-[12px] font-semibold text-ink">Runtime: {runtime?.status ?? "checking"}</div>
                <div className="mt-0.5 text-[10px] text-ink-muted">{runtime?.active_count ?? 0}/{runtime?.max_concurrent ?? 2} local deployments active · {runtimeDeployment ? `${runtimeDeployment.account_name ?? "Unmanaged runtime"} · ${runtimeDeployment.project} · ${runtimeDeployment.mode}` : "SigmaRail LEAN runtime · local Docker"}</div>
                {runtimeDeployment?.container_name ? <div className="mt-0.5 font-mono text-[10px] text-ink-faint">{runtimeDeployment.container_name} · Docker {runtimeDeployment.container_status ?? "unknown"}</div> : null}
              </div>
              {runtimeDeployment?.deployment_id && runtimeDeployment.account_profile_id && runtimeDeployment.status === "running" ? (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" size="sm" disabled={runtimeAction.isPending || runtime?.remote_stop_supported === false} onClick={() => {
                    const deploymentId = runtimeDeployment.deployment_id!;
                    if (runtimeDeployment.mode === "live") {
                      const expected = `STOP ${deploymentId.slice(-8)}`;
                      if (window.prompt(`This stops the LIVE algorithm; any open positions remain at the broker. Type ${expected} to continue.`) === expected) runtimeAction.mutate({ action: "stop", deployment_id: deploymentId, confirmation: expected });
                    } else if (window.confirm("Stop this LEAN algorithm and Docker container? Existing paper positions will remain open.")) {
                      runtimeAction.mutate({ action: "stop", deployment_id: deploymentId });
                    }
                  }}>Stop selected</Button>
                  {runtime?.remote_liquidation_supported !== false ? <Button type="button" variant="destructive" size="sm" disabled={runtimeAction.isPending} onClick={() => {
                    const deploymentId = runtimeDeployment.deployment_id!;
                    const isLive = runtimeDeployment.mode === "live";
                    if (isLive) {
                      const expected = `LIQUIDATE ${deploymentId.slice(-8)}`;
                      if (window.prompt(`This submits liquidation orders to a LIVE account. Type ${expected} to continue.`) === expected) runtimeAction.mutate({ action: "liquidate", deployment_id: deploymentId, confirmation: expected });
                    } else if (window.confirm("Send market liquidation orders for all open paper positions? LEAN will stay running so you can confirm fills.")) {
                      runtimeAction.mutate({ action: "liquidate", deployment_id: deploymentId });
                    }
                  }}>Liquidate selected</Button> : null}
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
                  <Button key={deployment.deployment_id} type="button" variant={deployment.deployment_id === selectedLocalDeploymentId ? "secondary" : "ghost"} onClick={() => setSelectedLocalDeploymentId(deployment.deployment_id ?? null)} className="flex h-auto w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs">
                    <span className="min-w-0 truncate">{deployment.account_name ?? "Paper account"} · {deployment.ir_id ?? "strategy"}</span>
                    <span className="shrink-0 font-mono">{deployment.status}</span>
                  </Button>
                ))}
              </div>
            ) : null}
          </Card>

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
                <Button
                  type="button"
                  disabled={!canPromote || !runtime?.enabled || runtime?.remote_start_supported === false || !account?.active || !account?.credentials_configured || runtimeLimitReached || runtimeAction.isPending}
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
                  size="sm"
                >
                  {runtimeAction.isPending ? "Starting…" : `Start ${account?.environment === "live" ? "LIVE" : "paper"} ${selectedBrokerage?.label ?? "LEAN"} deployment`}
                </Button>
                {runtimeLimitReached ? <span className="text-[11px] text-warn">{runtime?.status === "external_running" ? "Stop the unmanaged LEAN runtime before starting a Studio deployment." : `Stop a managed run before starting another (limit ${runtime?.max_concurrent ?? 2}).`}</span> : null}
                {runtime?.remote_start_supported === false ? <span className="text-[11px] text-warn">Remote deployment starts are disabled during the AppTension migration.</span> : null}
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
    </div>
  );
}
