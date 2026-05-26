export type BrowserProviderTypeKey = "chrome" | "camoufox" | "geekez" | "browserbase";
export type BrowserProviderGroupKey = "local-page" | "remote-session";
export type BrowserStrategyProfile =
  | "balanced"
  | "local-first"
  | "remote-first"
  | "stealth-first"
  | "chrome-first"
  | "camoufox-first"
  | "browserbase-first"
  | "latency-first"
  | "stability-first"
  | "cost-aware";

export interface BrowserProviderGroupDescriptor {
  key: BrowserProviderGroupKey;
  displayName: string;
  providerTypeKeys: BrowserProviderTypeKey[];
  description: string;
}

export interface BrowserStrategyDescriptor {
  id: BrowserStrategyProfile;
  displayName: string;
  description: string;
  providerGroupOrder: BrowserProviderGroupKey[];
  preferredProviders?: BrowserProviderTypeKey[];
}

export interface BrowserStrategyResolution {
  service: "browser";
  modeId: BrowserStrategyProfile;
  providerSelections: BrowserProviderGroupKey[];
  eligibleProviderGroups: BrowserProviderGroupKey[];
  providerGroupOrder: BrowserProviderGroupKey[];
  preferredProviders?: BrowserProviderTypeKey[];
  warnings: string[];
  explain: string[];
}

export interface BrowserEnvelope<T> {
  success: boolean;
  code: string;
  message: string;
  data?: T;
  error?: {
    category?: string;
    code?: string;
    message?: string;
    retriable?: boolean;
    cooldown_candidate?: boolean;
    raw?: Record<string, unknown>;
  };
  trace?: {
    request_id?: string;
    task_id?: string;
    runtime_id?: string;
    provider_id?: string;
  };
}

export interface BrowserSessionAcquireRequest {
  request_id?: string;
  mode?: "strategy" | "direct";
  strategy_profile?: BrowserStrategyProfile;
  provider_hint?: BrowserProviderTypeKey;
  runtime_reuse?: "prefer_reuse" | "require_reuse" | "prefer_fresh" | "require_fresh";
  timeout_ms?: number;
  proxy?: string;
  captcha_provider?: string;
  startup_url?: string;
  session_ttl_seconds?: number;
  metadata?: Record<string, unknown>;
}

export interface BrowserSessionRenewRequest {
  session_ttl_seconds?: number;
}

export type BrowserSessionStepType =
  | "navigate"
  | "click"
  | "input_text"
  | "submit"
  | "wait_for"
  | "read_value"
  | "evaluate_script";

export type BrowserSessionFlowType = "login" | "register" | "repair";
export type BrowserSessionFlowStepType =
  | "openai_web_login"
  | "register_auth"
  | "register_profile"
  | "register_finalize"
  | "register_oauth_auth"
  | "register_oauth_finalize"
  | "repair_login"
  | "repair_finalize";

export interface BrowserSessionStepRequest {
  request_id?: string;
  step_type: BrowserSessionStepType;
  target?: Record<string, unknown>;
  input?: Record<string, unknown>;
  timeout_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface BrowserSessionFlowStep {
  step_type: BrowserSessionFlowStepType;
  target?: Record<string, unknown>;
  input?: Record<string, unknown>;
  timeout_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface BrowserSessionFlowRequest {
  request_id?: string;
  flow_type: BrowserSessionFlowType;
  steps: BrowserSessionFlowStep[];
  timeout_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface BrowserSessionPayload {
  session_id: string;
  provider_id?: string;
  runtime_id?: string;
  resource_id?: string;
  resource_kind?: string;
  proxy?: string;
  captcha_provider?: string;
  created_at?: string;
  expires_at?: string;
  current_url?: string;
  state_summary?: Record<string, unknown>;
  history_tail?: Array<Record<string, unknown>>;
  attach?: Record<string, unknown>;
}

export interface BrowserSessionResponse {
  session: BrowserSessionPayload;
}

export interface BrowserTaskStatusData {
  task_id: string;
  state: string;
  mode: string;
  route: Record<string, unknown>;
  timing: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: Record<string, unknown>;
}

export interface BrowserExecuteAcceptedData {
  task_id: string;
  state: string;
  route: Record<string, unknown>;
}

export interface JsonHttpClient {
  get<TResponse>(path: string): Promise<TResponse>;
  post<TRequest, TResponse>(path: string, body: TRequest): Promise<TResponse>;
}

interface FetchJsonHttpClientInit {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export function normalizeBrowserProviderTypeKey(value: unknown): BrowserProviderTypeKey | undefined {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "chrome" || normalized === "custom") return "chrome";
  if (normalized === "camoufox") return "camoufox";
  if (normalized === "browserbase") return "browserbase";
  return undefined;
}

export const BROWSER_PROVIDER_GROUPS: BrowserProviderGroupDescriptor[] = [
  {
    key: "local-page",
    displayName: "Local browser runtimes",
    providerTypeKeys: ["chrome", "camoufox", "geekez"],
    description: "Local page-capable browser runtimes managed by EasyBrowser.",
  },
  {
    key: "remote-session",
    displayName: "Remote browser sessions",
    providerTypeKeys: ["browserbase"],
    description: "Remote session providers such as Browserbase.",
  },
];

export const BROWSER_STRATEGIES: BrowserStrategyDescriptor[] = [
  {
    id: "balanced",
    displayName: "Balanced",
    description: "Let EasyBrowser choose the best available local browser runtime.",
    providerGroupOrder: ["local-page", "remote-session"],
  },
  {
    id: "local-first",
    displayName: "Local-first",
    description: "Prefer local browser runtimes before any remote browser provider.",
    providerGroupOrder: ["local-page", "remote-session"],
    preferredProviders: ["chrome", "camoufox", "geekez"],
  },
  {
    id: "remote-first",
    displayName: "Remote-first",
    description: "Prefer remote browser/session providers when the task allows it.",
    providerGroupOrder: ["remote-session", "local-page"],
    preferredProviders: ["browserbase"],
  },
  {
    id: "stealth-first",
    displayName: "Stealth-first",
    description: "Prefer camoufox for stealth-sensitive browser tasks and fall back to chrome.",
    providerGroupOrder: ["local-page"],
    preferredProviders: ["camoufox", "geekez", "chrome"],
  },
  {
    id: "chrome-first",
    displayName: "Chrome-first",
    description: "Prefer the custom chrome runtime.",
    providerGroupOrder: ["local-page"],
    preferredProviders: ["chrome", "camoufox", "geekez"],
  },
  {
    id: "camoufox-first",
    displayName: "Camoufox-first",
    description: "Prefer the camoufox runtime.",
    providerGroupOrder: ["local-page"],
    preferredProviders: ["camoufox", "geekez", "chrome"],
  },
  {
    id: "browserbase-first",
    displayName: "Browserbase-first",
    description: "Prefer Browserbase when the task is explicitly remote-session compatible.",
    providerGroupOrder: ["remote-session", "local-page"],
    preferredProviders: ["browserbase"],
  },
  {
    id: "latency-first",
    displayName: "Latency-first",
    description: "Prefer providers with ready runtimes and reuse capacity.",
    providerGroupOrder: ["local-page", "remote-session"],
  },
  {
    id: "stability-first",
    displayName: "Stability-first",
    description: "Prefer providers with low recent failure counts.",
    providerGroupOrder: ["local-page", "remote-session"],
  },
  {
    id: "cost-aware",
    displayName: "Cost-aware",
    description: "Prefer local providers before remote sessions to reduce cost.",
    providerGroupOrder: ["local-page", "remote-session"],
  },
];

export function resolveBrowserStrategyProfile(value: unknown): BrowserStrategyProfile {
  const normalized = String(value ?? "").trim().toLowerCase();
  switch (normalized) {
    case "local-first":
      return "local-first";
    case "remote-first":
      return "remote-first";
    case "stealth-first":
    case "stealth":
      return "stealth-first";
    case "chrome-first":
    case "chrome":
      return "chrome-first";
    case "camoufox-first":
    case "camoufox":
      return "camoufox-first";
    case "browserbase-first":
    case "browserbase":
      return "browserbase-first";
    case "latency-first":
    case "latency":
      return "latency-first";
    case "stability-first":
    case "stability":
      return "stability-first";
    case "cost-aware":
      return "cost-aware";
    default:
      return "balanced";
  }
}

export function resolveBrowserStrategyMode(
  input?: Partial<{ profile: BrowserStrategyProfile; providerHint?: BrowserProviderTypeKey }>,
): BrowserStrategyResolution {
  const profile = resolveBrowserStrategyProfile(input?.profile);
  const descriptor = BROWSER_STRATEGIES.find((item) => item.id === profile) ?? BROWSER_STRATEGIES[0];
  const warnings: string[] = [];
  const explain: string[] = [];

  if (input?.providerHint) {
    explain.push(`provider_hint=${input.providerHint}`);
  }

  return {
    service: "browser",
    modeId: descriptor.id,
    providerSelections: descriptor.providerGroupOrder,
    eligibleProviderGroups: descriptor.providerGroupOrder,
    providerGroupOrder: descriptor.providerGroupOrder,
    preferredProviders: descriptor.preferredProviders,
    warnings,
    explain,
  };
}

export function createFetchJsonHttpClient(baseUrl: string, init?: FetchJsonHttpClientInit): JsonHttpClient {
  const normalized = baseUrl.replace(/\/$/, "");
  const headers = {
    "content-type": "application/json",
    ...(init?.headers ?? {}),
  } as Record<string, string>;

  return {
    async get<TResponse>(path: string): Promise<TResponse> {
      const res = await fetch(`${normalized}${path}`, { ...init, method: "GET", headers });
      return (await res.json()) as TResponse;
    },
    async post<TRequest, TResponse>(path: string, body: TRequest): Promise<TResponse> {
      const res = await fetch(`${normalized}${path}`, {
        ...init,
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      return (await res.json()) as TResponse;
    },
  };
}

export class HttpEasyBrowserClient {
  constructor(private readonly httpClient: JsonHttpClient) {}

  public health(): Promise<Record<string, unknown>> {
    return this.httpClient.get<Record<string, unknown>>("/healthz");
  }

  public acquireSession(
    request: BrowserSessionAcquireRequest,
  ): Promise<BrowserEnvelope<BrowserSessionResponse>> {
    return this.httpClient.post<BrowserSessionAcquireRequest, BrowserEnvelope<BrowserSessionResponse>>(
      "/v1/browser/sessions/acquire",
      request,
    );
  }

  public renewSession(
    sessionId: string,
    request: BrowserSessionRenewRequest,
  ): Promise<BrowserEnvelope<BrowserSessionResponse>> {
    return this.httpClient.post<BrowserSessionRenewRequest, BrowserEnvelope<BrowserSessionResponse>>(
      `/v1/browser/sessions/${sessionId}/renew`,
      request,
    );
  }

  public releaseSession(sessionId: string): Promise<BrowserEnvelope<BrowserSessionResponse>> {
    return this.httpClient.post<undefined, BrowserEnvelope<BrowserSessionResponse>>(
      `/v1/browser/sessions/${sessionId}/release`,
      undefined,
    );
  }

  public stepSession(
    sessionId: string,
    request: BrowserSessionStepRequest,
  ): Promise<BrowserEnvelope<BrowserTaskStatusData>> {
    return this.httpClient.post<BrowserSessionStepRequest, BrowserEnvelope<BrowserTaskStatusData>>(
      `/v1/browser/sessions/${sessionId}/steps`,
      request,
    );
  }

  public executeSessionFlow(
    sessionId: string,
    request: BrowserSessionFlowRequest,
  ): Promise<BrowserEnvelope<BrowserExecuteAcceptedData>> {
    return this.httpClient.post<BrowserSessionFlowRequest, BrowserEnvelope<BrowserExecuteAcceptedData>>(
      `/v1/browser/sessions/${sessionId}/flows/execute`,
      request,
    );
  }

  public taskStatus(taskId: string): Promise<BrowserEnvelope<BrowserTaskStatusData>> {
    return this.httpClient.get<BrowserEnvelope<BrowserTaskStatusData>>(`/v1/tasks/${taskId}`);
  }
}
