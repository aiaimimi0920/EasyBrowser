package model

type Envelope[T any] struct {
	Success bool             `json:"success"`
	Code    string           `json:"code"`
	Message string           `json:"message"`
	Data    T                `json:"data,omitempty"`
	Error   *NormalizedError `json:"error,omitempty"`
	Trace   Trace            `json:"trace,omitempty"`
}

type Trace struct {
	RequestID  string `json:"request_id,omitempty"`
	TaskID     string `json:"task_id,omitempty"`
	RuntimeID  string `json:"runtime_id,omitempty"`
	ProviderID string `json:"provider_id,omitempty"`
}

type NormalizedError struct {
	Category          string         `json:"category,omitempty"`
	Code              string         `json:"code,omitempty"`
	Message           string         `json:"message,omitempty"`
	Retriable         bool           `json:"retriable,omitempty"`
	CooldownCandidate bool           `json:"cooldown_candidate,omitempty"`
	Raw               map[string]any `json:"raw,omitempty"`
}

type ExecuteRequest struct {
	RequestID string        `json:"request_id,omitempty"`
	Mode      string        `json:"mode,omitempty"`
	Target    TargetSpec    `json:"target,omitempty"`
	Operation OperationSpec `json:"operation"`
	Timeout   TimeoutSpec   `json:"timeout,omitempty"`
	Retry     RetrySpec     `json:"retry,omitempty"`
	Isolation IsolationSpec `json:"isolation,omitempty"`
	Metadata  MetadataSpec  `json:"metadata,omitempty"`
}

type TargetSpec struct {
	Provider         string   `json:"provider,omitempty"`
	RuntimeID        string   `json:"runtime_id,omitempty"`
	AllowedProviders []string `json:"allowed_providers,omitempty"`
	StrategyProfile  string   `json:"strategy_profile,omitempty"`
}

type OperationSpec struct {
	Kind    string         `json:"kind"`
	Payload map[string]any `json:"payload,omitempty"`
}

type TimeoutSpec struct {
	TotalMS   int `json:"total_ms,omitempty"`
	StartupMS int `json:"startup_ms,omitempty"`
}

type RetrySpec struct {
	AllowRetry  bool `json:"allow_retry,omitempty"`
	MaxAttempts int  `json:"max_attempts,omitempty"`
}

type IsolationSpec struct {
	RequireSeparateProcess bool   `json:"require_separate_process,omitempty"`
	RuntimeReuse           string `json:"runtime_reuse,omitempty"`
}

type MetadataSpec struct {
	Caller string   `json:"caller,omitempty"`
	Tags   []string `json:"tags,omitempty"`
}

type CancelRequest struct {
	Reason      string `json:"reason,omitempty"`
	RequestedBy string `json:"requested_by,omitempty"`
}

type RuntimeRegistrationRequest struct {
	RuntimeID  string `json:"runtime_id"`
	ProviderID string `json:"provider_id"`
	PID        int    `json:"pid,omitempty"`
	State      string `json:"state,omitempty"`
	StartedAt  string `json:"started_at,omitempty"`
}

type RuntimeHeartbeatRequest struct {
	RuntimeID  string           `json:"runtime_id"`
	ProviderID string           `json:"provider_id"`
	Healthy    bool             `json:"healthy"`
	Timestamp  string           `json:"timestamp,omitempty"`
	Signals    HeartbeatSignals `json:"signals,omitempty"`
}

type HeartbeatSignals struct {
	RecentFailures int  `json:"recent_failures,omitempty"`
	CooldownActive bool `json:"cooldown_active,omitempty"`
}

type RuntimeCompletionRequest struct {
	RuntimeID  string           `json:"runtime_id"`
	TaskID     string           `json:"task_id"`
	Success    bool             `json:"success"`
	Result     map[string]any   `json:"result,omitempty"`
	Error      *NormalizedError `json:"error,omitempty"`
	FinishedAt string           `json:"finished_at,omitempty"`
}

type ExecuteAcceptedData struct {
	TaskID string           `json:"task_id"`
	State  string           `json:"state"`
	Route  ExecuteRouteView `json:"route"`
}

type ExecuteRouteView struct {
	Mode             string                `json:"mode"`
	StrategyProfile  string                `json:"strategy_profile,omitempty"`
	SelectedProvider string                `json:"selected_provider,omitempty"`
	RuntimeID        string                `json:"runtime_id,omitempty"`
	Diagnostics      *RouteDiagnosticsView `json:"diagnostics,omitempty"`
}

type TaskStatusData struct {
	TaskID string            `json:"task_id"`
	State  string            `json:"state"`
	Mode   string            `json:"mode"`
	Route  RouteDecisionView `json:"route"`
	Timing TaskTiming        `json:"timing"`
	Result map[string]any    `json:"result,omitempty"`
	Error  *NormalizedError  `json:"error,omitempty"`
}

type TaskTiming struct {
	QueuedAt   string `json:"queued_at,omitempty"`
	StartedAt  string `json:"started_at,omitempty"`
	FinishedAt string `json:"finished_at,omitempty"`
}

type CancelData struct {
	TaskID      string `json:"task_id"`
	CancelState string `json:"cancel_state"`
}

type CapabilityFlags struct {
	SupportsDirectMode      bool `json:"supports_direct_mode"`
	SupportsStrategyMode    bool `json:"supports_strategy_mode"`
	SupportsFreshRuntime    bool `json:"supports_fresh_runtime"`
	SupportsRuntimeReuse    bool `json:"supports_runtime_reuse"`
	SupportsRemoteExecution bool `json:"supports_remote_execution"`
	SupportsLocalProcess    bool `json:"supports_local_process"`
}

type ProviderLimits struct {
	MaxRuntimes      int `json:"max_runtimes"`
	MaxParallelTasks int `json:"max_parallel_tasks"`
}

type ProviderStatsSummary struct {
	TotalRequests  int    `json:"total_requests"`
	TotalFailures  int    `json:"total_failures"`
	RecentFailures int    `json:"recent_failures"`
	CooldownUntil  string `json:"cooldown_until,omitempty"`
	LastError      string `json:"last_error,omitempty"`
}

type ProviderView struct {
	ProviderID     string               `json:"provider_id"`
	Kind           string               `json:"kind"`
	Enabled        bool                 `json:"enabled"`
	DisabledReason string               `json:"disabled_reason,omitempty"`
	CooldownActive bool                 `json:"cooldown_active"`
	CooldownUntil  string               `json:"cooldown_until,omitempty"`
	Healthy        bool                 `json:"healthy"`
	FailureCount   int                  `json:"failure_count"`
	LastError      string               `json:"last_error,omitempty"`
	LastFailureAt  string               `json:"last_failure_at,omitempty"`
	LastSuccessAt  string               `json:"last_success_at,omitempty"`
	Capabilities   CapabilityFlags      `json:"capabilities"`
	Limits         ProviderLimits       `json:"limits"`
	StatsSummary   ProviderStatsSummary `json:"stats_summary"`
}

type ProviderListData struct {
	Providers []ProviderView `json:"providers"`
}

type RuntimeView struct {
	RuntimeID       string `json:"runtime_id"`
	ProviderID      string `json:"provider_id"`
	State           string `json:"state"`
	Healthy         bool   `json:"healthy"`
	PID             int    `json:"pid,omitempty"`
	CurrentTaskID   string `json:"current_task_id,omitempty"`
	LeaseID         string `json:"lease_id,omitempty"`
	CooldownActive  bool   `json:"cooldown_active"`
	CooldownUntil   string `json:"cooldown_until,omitempty"`
	FailureCount    int    `json:"failure_count"`
	LastError       string `json:"last_error,omitempty"`
	LastFailureAt   string `json:"last_failure_at,omitempty"`
	LastSuccessAt   string `json:"last_success_at,omitempty"`
	LastHeartbeatAt string `json:"last_heartbeat_at,omitempty"`
}

type RuntimeListData struct {
	Runtimes           []RuntimeView `json:"runtimes"`
	ActiveRuntimes     []RuntimeView `json:"active_runtimes,omitempty"`
	HistoricalRuntimes []RuntimeView `json:"historical_runtimes,omitempty"`
}

type ProviderStatsView struct {
	ProviderID     string         `json:"provider_id"`
	TotalRequests  int            `json:"total_requests"`
	TotalSuccesses int            `json:"total_successes"`
	TotalFailures  int            `json:"total_failures"`
	CooldownCount  int            `json:"cooldown_count"`
	RecentFailures int            `json:"recent_failures"`
	ErrorCounts    map[string]int `json:"error_counts,omitempty"`
	LastError      string         `json:"last_error,omitempty"`
	LastFailureAt  string         `json:"last_failure_at,omitempty"`
	LastSuccessAt  string         `json:"last_success_at,omitempty"`
	CooldownUntil  string         `json:"cooldown_until,omitempty"`
}

type ProviderStatsData struct {
	Providers []ProviderStatsView `json:"providers"`
}

type RuntimeStatsView struct {
	RuntimeID         string         `json:"runtime_id"`
	ProviderID        string         `json:"provider_id"`
	TotalLeases       int            `json:"total_leases"`
	RestartCount      int            `json:"restart_count"`
	AbnormalExitCount int            `json:"abnormal_exit_count"`
	RecentFailures    int            `json:"recent_failures"`
	ErrorCounts       map[string]int `json:"error_counts,omitempty"`
	LastError         string         `json:"last_error,omitempty"`
	LastFailureAt     string         `json:"last_failure_at,omitempty"`
	LastSuccessAt     string         `json:"last_success_at,omitempty"`
	CooldownUntil     string         `json:"cooldown_until,omitempty"`
}

type RuntimeStatsData struct {
	Runtimes []RuntimeStatsView `json:"runtimes"`
}

type RouteHistoryEntry struct {
	TaskID              string                `json:"task_id"`
	RequestID           string                `json:"request_id,omitempty"`
	State               string                `json:"state"`
	Mode                string                `json:"mode"`
	StrategyProfile     string                `json:"strategy_profile,omitempty"`
	SelectedProvider    string                `json:"selected_provider,omitempty"`
	SelectedRuntimeID   string                `json:"runtime_id,omitempty"`
	FallbackUsed        bool                  `json:"fallback_used,omitempty"`
	StrategyReason      string                `json:"strategy_reason,omitempty"`
	ConsideredProviders []string              `json:"considered_providers,omitempty"`
	RejectedProviders   []string              `json:"rejected_providers,omitempty"`
	Diagnostics         *RouteDiagnosticsView `json:"diagnostics,omitempty"`
	Candidates          []RouteCandidateView  `json:"candidates,omitempty"`
	QueuedAt            string                `json:"queued_at,omitempty"`
	StartedAt           string                `json:"started_at,omitempty"`
	FinishedAt          string                `json:"finished_at,omitempty"`
	Error               *NormalizedError      `json:"error,omitempty"`
}

type RouteHistoryData struct {
	Routes []RouteHistoryEntry `json:"routes"`
}

type FallbackHistoryData struct {
	Fallbacks []RouteHistoryEntry `json:"fallbacks"`
}

type RouteRejectionSummaryEntry struct {
	ProviderID      string `json:"provider_id"`
	RejectionReason string `json:"rejection_reason"`
	Count           int    `json:"count"`
}

type RouteRejectionSummaryData struct {
	Rejections []RouteRejectionSummaryEntry `json:"rejections"`
}

type RouteSelectionSummaryEntry struct {
	ProviderID string `json:"provider_id"`
	Count      int    `json:"count"`
}

type RouteProfileUsageEntry struct {
	StrategyProfile string `json:"strategy_profile"`
	Count           int    `json:"count"`
}

type RouteSummaryTotals struct {
	TotalRoutes    int `json:"total_routes"`
	TotalFallbacks int `json:"total_fallbacks"`
}

type ProviderHealthWindowSummary struct {
	Window                 string  `json:"window"`
	Since                  string  `json:"since"`
	TaskSucceededCount     int     `json:"task_succeeded_count"`
	TaskFailedCount        int     `json:"task_failed_count"`
	TaskCancelledCount     int     `json:"task_cancelled_count"`
	SpawnStartedCount      int     `json:"spawn_started_count"`
	StartupFailedCount     int     `json:"startup_failed_count"`
	ReadyTimeoutCount      int     `json:"ready_timeout_count"`
	HeartbeatMissedCount   int     `json:"heartbeat_missed_count"`
	HeartbeatRestoredCount int     `json:"heartbeat_restored_count"`
	HealthDegradedCount    int     `json:"health_degraded_count"`
	SuccessRate            float64 `json:"success_rate,omitempty"`
	FailureRate            float64 `json:"failure_rate,omitempty"`
}

type ProviderHealthSummaryEntry struct {
	ProviderID                  string                        `json:"provider_id"`
	Enabled                     bool                          `json:"enabled"`
	Healthy                     bool                          `json:"healthy"`
	CooldownActive              bool                          `json:"cooldown_active"`
	FailureCount                int                           `json:"failure_count"`
	LastError                   string                        `json:"last_error,omitempty"`
	LastFailureAt               string                        `json:"last_failure_at,omitempty"`
	LastSuccessAt               string                        `json:"last_success_at,omitempty"`
	TotalTaskSucceededCount     int                           `json:"total_task_succeeded_count"`
	TotalTaskFailedCount        int                           `json:"total_task_failed_count"`
	TotalTaskCancelledCount     int                           `json:"total_task_cancelled_count"`
	TotalSpawnStartedCount      int                           `json:"total_spawn_started_count"`
	TotalStartupFailedCount     int                           `json:"total_startup_failed_count"`
	TotalReadyTimeoutCount      int                           `json:"total_ready_timeout_count"`
	TotalHeartbeatMissedCount   int                           `json:"total_heartbeat_missed_count"`
	TotalHeartbeatRestoredCount int                           `json:"total_heartbeat_restored_count"`
	TotalHealthDegradedCount    int                           `json:"total_health_degraded_count"`
	Windows                     []ProviderHealthWindowSummary `json:"windows,omitempty"`
}

type ProviderHealthSummaryData struct {
	Providers []ProviderHealthSummaryEntry `json:"providers,omitempty"`
}

type OperationalEvent struct {
	EventID    string         `json:"event_id"`
	Kind       string         `json:"kind"`
	Severity   string         `json:"severity"`
	ProviderID string         `json:"provider_id,omitempty"`
	RuntimeID  string         `json:"runtime_id,omitempty"`
	TaskID     string         `json:"task_id,omitempty"`
	RequestID  string         `json:"request_id,omitempty"`
	OccurredAt string         `json:"occurred_at"`
	Message    string         `json:"message,omitempty"`
	Details    map[string]any `json:"details,omitempty"`
}

type OperationalEventData struct {
	Events []OperationalEvent `json:"events"`
}

type RouteControlSummaryData struct {
	Totals                  RouteSummaryTotals           `json:"totals"`
	RecentEvents            []RouteHistoryEntry          `json:"recent_events,omitempty"`
	RecentFallbacks         []RouteHistoryEntry          `json:"recent_fallbacks,omitempty"`
	TopRejections           []RouteRejectionSummaryEntry `json:"top_rejections,omitempty"`
	ProviderSelections      []RouteSelectionSummaryEntry `json:"provider_selections,omitempty"`
	ProfileUsage            []RouteProfileUsageEntry     `json:"profile_usage,omitempty"`
	ProviderHealth          []ProviderHealthSummaryEntry `json:"provider_health,omitempty"`
	RecentOperationalEvents []OperationalEvent           `json:"recent_operational_events,omitempty"`
	WindowStats             []RouteWindowSummary         `json:"window_stats,omitempty"`
}

type RouteProviderInsight struct {
	ProviderID            string         `json:"provider_id"`
	SelectedCount         int            `json:"selected_count"`
	FallbackSelectedCount int            `json:"fallback_selected_count"`
	SucceededCount        int            `json:"succeeded_count"`
	FailedCount           int            `json:"failed_count"`
	RejectionCounts       map[string]int `json:"rejection_counts,omitempty"`
	EventCounts           map[string]int `json:"event_counts,omitempty"`
	LastSelectedAt        string         `json:"last_selected_at,omitempty"`
}

type RouteProfileInsight struct {
	StrategyProfile    string         `json:"strategy_profile"`
	TotalRoutes        int            `json:"total_routes"`
	FallbackRoutes     int            `json:"fallback_routes"`
	SucceededCount     int            `json:"succeeded_count"`
	FailedCount        int            `json:"failed_count"`
	ProviderSelections map[string]int `json:"provider_selections,omitempty"`
}

type RouteInsightsData struct {
	Providers []RouteProviderInsight `json:"providers,omitempty"`
	Profiles  []RouteProfileInsight  `json:"profiles,omitempty"`
}

type RouteInsightsWindow struct {
	Window    string                 `json:"window"`
	Since     string                 `json:"since"`
	Providers []RouteProviderInsight `json:"providers,omitempty"`
	Profiles  []RouteProfileInsight  `json:"profiles,omitempty"`
}

type RouteWindowInsightsData struct {
	Windows []RouteInsightsWindow `json:"windows"`
}

type RouteWindowSummary struct {
	Window             string                       `json:"window"`
	Since              string                       `json:"since"`
	TotalRoutes        int                          `json:"total_routes"`
	TotalFallbacks     int                          `json:"total_fallbacks"`
	TotalFailures      int                          `json:"total_failures"`
	ProviderSelections []RouteSelectionSummaryEntry `json:"provider_selections,omitempty"`
	ProfileUsage       []RouteProfileUsageEntry     `json:"profile_usage,omitempty"`
	Rejections         []RouteRejectionSummaryEntry `json:"rejections,omitempty"`
	EventCounts        map[string]int               `json:"event_counts,omitempty"`
}

type RouteWindowStatsData struct {
	Windows []RouteWindowSummary `json:"windows"`
}

type CapabilityView struct {
	ProviderID   string          `json:"provider_id"`
	Kind         string          `json:"kind"`
	Enabled      bool            `json:"enabled"`
	Capabilities CapabilityFlags `json:"capabilities"`
	Limits       ProviderLimits  `json:"limits"`
	Notes        string          `json:"notes,omitempty"`
}

type RouteDecisionView struct {
	Mode                string                `json:"mode"`
	StrategyProfile     string                `json:"strategy_profile,omitempty"`
	SelectedProvider    string                `json:"selected_provider,omitempty"`
	SelectedRuntimeID   string                `json:"runtime_id,omitempty"`
	StrategyReason      string                `json:"strategy_reason,omitempty"`
	FallbackUsed        bool                  `json:"fallback_used,omitempty"`
	ConsideredProviders []string              `json:"considered_providers,omitempty"`
	RejectedProviders   []string              `json:"rejected_providers,omitempty"`
	Diagnostics         *RouteDiagnosticsView `json:"diagnostics,omitempty"`
	Candidates          []RouteCandidateView  `json:"candidates,omitempty"`
}

type RouteScoreBreakdownView struct {
	BaseScore            int `json:"base_score,omitempty"`
	ProfileBonus         int `json:"profile_bonus,omitempty"`
	ReuseBonus           int `json:"reuse_bonus,omitempty"`
	ReadyRuntimeBonus    int `json:"ready_runtime_bonus,omitempty"`
	RecentFailurePenalty int `json:"recent_failure_penalty,omitempty"`
	TotalFailurePenalty  int `json:"total_failure_penalty,omitempty"`
}

type RouteDiagnosticsView struct {
	Action         string                   `json:"action,omitempty"`
	ActionClass    string                   `json:"action_class,omitempty"`
	ResourceKind   string                   `json:"resource_kind,omitempty"`
	RuntimeReuse   string                   `json:"runtime_reuse,omitempty"`
	Profile        string                   `json:"profile,omitempty"`
	ProfileRank    int                      `json:"profile_rank,omitempty"`
	Score          int                      `json:"score,omitempty"`
	ReadyRuntimes  int                      `json:"ready_runtimes,omitempty"`
	RecentFailures int                      `json:"recent_failures,omitempty"`
	TotalFailures  int                      `json:"total_failures,omitempty"`
	Breakdown      *RouteScoreBreakdownView `json:"breakdown,omitempty"`
}

type RouteCandidateView struct {
	ProviderID      string                   `json:"provider_id"`
	Eligible        bool                     `json:"eligible"`
	Selected        bool                     `json:"selected,omitempty"`
	ProfileRank     int                      `json:"profile_rank,omitempty"`
	Score           int                      `json:"score,omitempty"`
	ReadyRuntimes   int                      `json:"ready_runtimes,omitempty"`
	RecentFailures  int                      `json:"recent_failures,omitempty"`
	TotalFailures   int                      `json:"total_failures,omitempty"`
	RejectionReason string                   `json:"rejection_reason,omitempty"`
	SupportsAction  bool                     `json:"supports_action,omitempty"`
	SupportsMode    bool                     `json:"supports_mode,omitempty"`
	CooldownActive  bool                     `json:"cooldown_active,omitempty"`
	ProviderEnabled bool                     `json:"provider_enabled,omitempty"`
	Breakdown       *RouteScoreBreakdownView `json:"breakdown,omitempty"`
}

type RuntimeAllocationView struct {
	Success    bool `json:"success"`
	Allocation struct {
		RuntimeID  string `json:"runtime_id,omitempty"`
		ProviderID string `json:"provider_id,omitempty"`
		Source     string `json:"source,omitempty"`
		LeaseID    string `json:"lease_id,omitempty"`
	} `json:"allocation,omitempty"`
	Reason struct {
		Code    string `json:"code,omitempty"`
		Message string `json:"message,omitempty"`
	} `json:"reason,omitempty"`
}

type RuntimeHealthView struct {
	RuntimeID       string `json:"runtime_id,omitempty"`
	ProviderID      string `json:"provider_id,omitempty"`
	Healthy         bool   `json:"healthy"`
	LastHeartbeatAt string `json:"last_heartbeat_at,omitempty"`
	RecentFailures  int    `json:"recent_failures,omitempty"`
	CooldownActive  bool   `json:"cooldown_active,omitempty"`
	CooldownUntil   string `json:"cooldown_until,omitempty"`
	Notes           string `json:"notes,omitempty"`
}

type ProviderExecutionResult struct {
	ProviderID string           `json:"provider_id,omitempty"`
	RuntimeID  string           `json:"runtime_id,omitempty"`
	Success    bool             `json:"success"`
	Result     map[string]any   `json:"result,omitempty"`
	Error      *NormalizedError `json:"error,omitempty"`
}

type BrowserSessionAcquireRequest struct {
	RequestID         string         `json:"request_id,omitempty"`
	Mode              string         `json:"mode,omitempty"`
	StrategyProfile   string         `json:"strategy_profile,omitempty"`
	ProviderHint      string         `json:"provider_hint,omitempty"`
	BrowserBackend    string         `json:"browser_backend,omitempty"`
	RuntimeReuse      string         `json:"runtime_reuse,omitempty"`
	TimeoutMS         int            `json:"timeout_ms,omitempty"`
	Proxy             string         `json:"proxy,omitempty"`
	CaptchaProvider   string         `json:"captcha_provider,omitempty"`
	StartupURL        string         `json:"startup_url,omitempty"`
	SessionTTLSeconds int            `json:"session_ttl_seconds,omitempty"`
	Metadata          map[string]any `json:"metadata,omitempty"`
}

type BrowserSessionRenewRequest struct {
	SessionTTLSeconds int `json:"session_ttl_seconds,omitempty"`
}

type BrowserSessionStepRequest struct {
	RequestID string         `json:"request_id,omitempty"`
	StepType  string         `json:"step_type"`
	Target    map[string]any `json:"target,omitempty"`
	Input     map[string]any `json:"input,omitempty"`
	TimeoutMS int            `json:"timeout_ms,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

type BrowserSessionFlowStep struct {
	StepType  string         `json:"step_type"`
	Target    map[string]any `json:"target,omitempty"`
	Input     map[string]any `json:"input,omitempty"`
	TimeoutMS int            `json:"timeout_ms,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

type BrowserSessionFlowRequest struct {
	RequestID string                   `json:"request_id,omitempty"`
	FlowType  string                   `json:"flow_type"`
	Steps     []BrowserSessionFlowStep `json:"steps"`
	TimeoutMS int                      `json:"timeout_ms,omitempty"`
	Metadata  map[string]any           `json:"metadata,omitempty"`
}

type BrowserSessionPayload struct {
	SessionID       string           `json:"session_id"`
	ProviderID      string           `json:"provider_id,omitempty"`
	RuntimeID       string           `json:"runtime_id,omitempty"`
	ResourceID      string           `json:"resource_id,omitempty"`
	ResourceKind    string           `json:"resource_kind,omitempty"`
	Proxy           string           `json:"proxy,omitempty"`
	CaptchaProvider string           `json:"captcha_provider,omitempty"`
	CreatedAt       string           `json:"created_at,omitempty"`
	ExpiresAt       string           `json:"expires_at,omitempty"`
	CurrentURL      string           `json:"current_url,omitempty"`
	StateSummary    map[string]any   `json:"state_summary,omitempty"`
	HistoryTail     []map[string]any `json:"history_tail,omitempty"`
	Attach          map[string]any   `json:"attach,omitempty"`
}

type BrowserSessionResponse struct {
	Session BrowserSessionPayload `json:"session"`
}
