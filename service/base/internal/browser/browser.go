package browser

import (
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/processmanager"
	"github.com/aiaimimi0920/EasyBrowser/internal/provider"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

const (
	defaultBrowserExecTimeout = 90 * time.Second
	defaultSessionTTL         = 15 * time.Minute
	defaultWaitPoll           = 150 * time.Millisecond
)

type HTTPError struct {
	StatusCode int
	Code       string
	Message    string
	Stage      string
}

func (e *HTTPError) Error() string {
	if e == nil {
		return ""
	}
	return e.Message
}

type SessionRecord struct {
	SessionID       string
	RuntimeID       string
	ProviderID      string
	ResourceID      string
	ResourceKind    string
	Proxy           string
	CaptchaProvider string
	CreatedAt       time.Time
	ExpiresAt       time.Time
	CurrentURL      string
	StateSummary    map[string]any
	HistoryTail     []map[string]any
	Attach          map[string]any
}

type API struct {
	service        *service.Service
	processes      *processmanager.Manager
	executionLimit time.Duration
	sessionTTL     time.Duration
	waitPoll       time.Duration

	mu       sync.Mutex
	sessions map[string]*SessionRecord
}

func New(service *service.Service, processes *processmanager.Manager) *API {
	return &API{
		service:        service,
		processes:      processes,
		executionLimit: durationFromEnvMs("EASYBROWSER_BROWSER_EXECUTE_TIMEOUT_MS", defaultBrowserExecTimeout),
		sessionTTL:     durationFromEnvMs("EASYBROWSER_BROWSER_SESSION_TTL_MS", defaultSessionTTL),
		waitPoll:       defaultWaitPoll,
		sessions:       make(map[string]*SessionRecord),
	}
}

func (b *API) AcquireSession(req model.BrowserSessionAcquireRequest) (model.BrowserSessionResponse, error) {
	if b.processes == nil || b.service == nil {
		return model.BrowserSessionResponse{}, &HTTPError{
			StatusCode: 501,
			Code:       "not_available",
			Message:    "browser execution unavailable",
			Stage:      "acquire",
		}
	}

	mode := strings.ToLower(strings.TrimSpace(req.Mode))
	if mode == "" {
		mode = "strategy"
	}

	if mode == "direct" && strings.TrimSpace(req.ProviderHint) == "" {
		return model.BrowserSessionResponse{}, &HTTPError{
			StatusCode: 400,
			Code:       "invalid_request",
			Message:    "direct mode requires provider_hint",
			Stage:      "acquire",
		}
	}

	resourceKind := "page"
	if req.ProviderHint != "" {
		resourceKind = provider.InferResourceKindForProvider(req.ProviderHint)
		if resourceKind == "" {
			resourceKind = "page"
		}
	}

	execReq := model.ExecuteRequest{
		RequestID: req.RequestID,
		Mode:      mode,
		Target: model.TargetSpec{
			Provider: req.ProviderHint,
		},
		Operation: model.OperationSpec{
			Kind: "open_resource",
			Payload: map[string]any{
				"action":           "open_resource",
				"resource_kind":    resourceKind,
				"url":              coalesce(req.StartupURL, "about:blank"),
				"startup_url":      coalesce(req.StartupURL, "about:blank"),
				"proxy":            strings.TrimSpace(req.Proxy),
				"captcha_provider": strings.TrimSpace(req.CaptchaProvider),
				"browser_backend":  strings.TrimSpace(req.BrowserBackend),
			},
		},
		Isolation: model.IsolationSpec{
			RequireSeparateProcess: true,
			RuntimeReuse:           coalesce(req.RuntimeReuse, "require_reuse"),
		},
		Metadata: model.MetadataSpec{
			Caller: "easybrowser",
			Tags:   []string{"browser_session_acquire"},
		},
		Timeout: model.TimeoutSpec{
			TotalMS: req.TimeoutMS,
		},
	}

	status, err := b.executeAndWait(execReq, resolveExecutionTimeout(req.TimeoutMS, b.executionLimit))
	if err != nil {
		return model.BrowserSessionResponse{}, err
	}

	resource := nestedMap(status.Result, "resource")
	resourceID := lookupString(resource, "id")
	if resourceID == "" {
		return model.BrowserSessionResponse{}, &HTTPError{
			StatusCode: 502,
			Code:       "invalid_response",
			Message:    "session acquire missing resource id",
			Stage:      "acquire",
		}
	}

	now := time.Now().UTC()
	sessionID := nextID("sess")
	record := &SessionRecord{
		SessionID:       sessionID,
		RuntimeID:       status.Route.SelectedRuntimeID,
		ProviderID:      status.Route.SelectedProvider,
		ResourceID:      resourceID,
		ResourceKind:    resourceKind,
		Proxy:           strings.TrimSpace(req.Proxy),
		CaptchaProvider: strings.TrimSpace(req.CaptchaProvider),
		CreatedAt:       now,
		ExpiresAt:       now.Add(resolveTTL(req.SessionTTLSeconds, b.sessionTTL)),
		CurrentURL:      lookupString(resource, "url"),
		StateSummary: map[string]any{
			"provider_id": status.Route.SelectedProvider,
			"runtime_id":  status.Route.SelectedRuntimeID,
			"resource_id": resourceID,
			"state":       status.State,
			"action":      lookupString(status.Result, "action"),
		},
		Attach: nestedMap(status.Result, "attach"),
	}

	b.mu.Lock()
	b.sessions[sessionID] = record
	b.mu.Unlock()

	return model.BrowserSessionResponse{Session: record.toPayload()}, nil
}

func (b *API) RenewSession(sessionID string, req model.BrowserSessionRenewRequest) (model.BrowserSessionResponse, error) {
	record, err := b.getSession(sessionID)
	if err != nil {
		return model.BrowserSessionResponse{}, err
	}
	b.mu.Lock()
	record.ExpiresAt = time.Now().UTC().Add(resolveTTL(req.SessionTTLSeconds, b.sessionTTL))
	b.mu.Unlock()
	return model.BrowserSessionResponse{Session: record.toPayload()}, nil
}

func (b *API) ReleaseSession(sessionID string) (model.BrowserSessionResponse, error) {
	record, err := b.getSession(sessionID)
	if err != nil {
		return model.BrowserSessionResponse{}, err
	}
	_, _ = b.executeOnSession(record, model.ExecuteRequest{
		Mode: "direct",
		Operation: model.OperationSpec{
			Kind: "close_resource",
			Payload: map[string]any{
				"action":        "close_resource",
				"resource_kind": record.ResourceKind,
				"resource_id":   record.ResourceID,
			},
		},
		Metadata: model.MetadataSpec{
			Caller: "easybrowser",
			Tags:   []string{"browser_session_release"},
		},
	}, b.executionLimit)

	if record.RuntimeID != "" && b.processes != nil {
		_ = b.processes.ShutdownRuntime(record.RuntimeID)
	}

	b.mu.Lock()
	delete(b.sessions, record.SessionID)
	b.mu.Unlock()
	return model.BrowserSessionResponse{Session: record.toPayload()}, nil
}

func (b *API) StepSession(sessionID string, req model.BrowserSessionStepRequest) (model.TaskStatusData, error) {
	record, err := b.getSession(sessionID)
	if err != nil {
		return model.TaskStatusData{}, err
	}

	action := provider.CanonicalActionName(req.StepType)
	if action == "" {
		return model.TaskStatusData{}, &HTTPError{
			StatusCode: 400,
			Code:       "invalid_request",
			Message:    "step_type is required",
			Stage:      "step",
		}
	}
	if provider.IsHighLevelBrowserAction(action) {
		return model.TaskStatusData{}, &HTTPError{
			StatusCode: 400,
			Code:       "deprecated_high_level_step_type",
			Message:    fmt.Sprintf("step_type %q must be executed via /v1/browser/sessions/{sessionId}/flows/execute", req.StepType),
			Stage:      "step",
		}
	}

	execReq := model.ExecuteRequest{
		RequestID: req.RequestID,
		Mode:      "direct",
		Target: model.TargetSpec{
			RuntimeID: record.RuntimeID,
		},
		Operation: model.OperationSpec{
			Kind: action,
			Payload: map[string]any{
				"action":        action,
				"resource_kind": record.ResourceKind,
				"resource_id":   record.ResourceID,
				"target":        req.Target,
				"input":         req.Input,
			},
		},
		Metadata: model.MetadataSpec{
			Caller: "easybrowser",
			Tags:   []string{"browser_session_step", action},
		},
		Timeout: model.TimeoutSpec{
			TotalMS: req.TimeoutMS,
		},
	}

	if action == "navigate" {
		if url, ok := req.Target["url"].(string); ok && strings.TrimSpace(url) != "" {
			execReq.Operation.Payload["url"] = strings.TrimSpace(url)
		}
	}

	status, err := b.executeOnSession(record, execReq, resolveExecutionTimeout(req.TimeoutMS, b.executionLimit))
	if err != nil {
		return model.TaskStatusData{}, err
	}

	record.refreshFromTask(status)
	return status, nil
}

func (b *API) executeOnSession(record *SessionRecord, req model.ExecuteRequest, timeout time.Duration) (model.TaskStatusData, error) {
	req.Mode = "direct"
	req.Target.RuntimeID = record.RuntimeID
	status, err := b.executeAndWait(req, timeout)
	if err != nil {
		return model.TaskStatusData{}, err
	}
	return status, nil
}

func (b *API) executeAndWait(req model.ExecuteRequest, timeout time.Duration) (model.TaskStatusData, error) {
	if b.service == nil || b.processes == nil {
		return model.TaskStatusData{}, errors.New("browser execution unavailable")
	}
	explicitRuntime := strings.TrimSpace(req.Target.RuntimeID) != ""
	data, _, err := b.service.SubmitTask(req)
	if err != nil {
		return model.TaskStatusData{}, err
	}

	if data.State == "allocating" && data.Route.SelectedProvider != "" && data.Route.RuntimeID == "" && !explicitRuntime {
		runtimeView, spawnErr := b.processes.SpawnRuntime(data.Route.SelectedProvider)
		if spawnErr != nil {
			_, _, _ = b.service.RecordCompletion(model.RuntimeCompletionRequest{
				RuntimeID:  data.Route.RuntimeID,
				TaskID:     data.TaskID,
				Success:    false,
				FinishedAt: time.Now().UTC().Format(time.RFC3339),
				Error: &model.NormalizedError{
					Category:          "startup",
					Code:              "spawn_failed",
					Message:           spawnErr.Error(),
					Retriable:         true,
					CooldownCandidate: true,
				},
			})
			return model.TaskStatusData{}, spawnErr
		}
		if _, _, assignErr := b.service.AssignRuntimeToTask(data.TaskID, runtimeView.RuntimeID); assignErr != nil {
			return model.TaskStatusData{}, assignErr
		}
		data.Route.RuntimeID = runtimeView.RuntimeID
	}

	if data.Route.RuntimeID == "" {
		if explicitRuntime {
			return model.TaskStatusData{}, &HTTPError{
				StatusCode: 409,
				Code:       "target_runtime_unavailable",
				Message:    fmt.Sprintf("requested runtime %s is unavailable for direct execution", req.Target.RuntimeID),
				Stage:      "dispatch",
			}
		}
		return model.TaskStatusData{}, &HTTPError{
			StatusCode: 500,
			Code:       "allocation_failed",
			Message:    "task runtime allocation failed",
			Stage:      "dispatch",
		}
	}
	if err := b.processes.DispatchTask(data.TaskID, data.Route.RuntimeID, req); err != nil {
		return model.TaskStatusData{}, err
	}

	deadline := time.Now().Add(timeout)
	for {
		status, _, statusErr := b.service.GetTask(data.TaskID)
		if statusErr != nil {
			return model.TaskStatusData{}, statusErr
		}
		switch status.State {
		case "succeeded":
			return status, nil
		case "failed", "cancelled", "timed_out":
			if status.Error != nil {
				return status, &HTTPError{
					StatusCode: 502,
					Code:       status.Error.Code,
					Message:    status.Error.Message,
					Stage:      "dispatch",
				}
			}
			return status, &HTTPError{
				StatusCode: 500,
				Code:       "execution_failed",
				Message:    fmt.Sprintf("task %s ended in state %s", status.TaskID, status.State),
				Stage:      "dispatch",
			}
		}
		if time.Now().After(deadline) {
			return model.TaskStatusData{}, &HTTPError{
				StatusCode: 504,
				Code:       "timeout",
				Message:    fmt.Sprintf("task %s did not finish before timeout", data.TaskID),
				Stage:      "dispatch",
			}
		}
		time.Sleep(b.waitPoll)
	}
}

func (b *API) getSession(sessionID string) (*SessionRecord, error) {
	id := strings.TrimSpace(sessionID)
	if id == "" {
		return nil, &HTTPError{StatusCode: 400, Code: "invalid_request", Message: "session_id is required", Stage: "session"}
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	record, ok := b.sessions[id]
	if !ok {
		return nil, &HTTPError{StatusCode: 404, Code: "not_found", Message: fmt.Sprintf("unknown session_id %q", id), Stage: "session"}
	}
	return record, nil
}

func (r *SessionRecord) refreshFromTask(status model.TaskStatusData) {
	if status.Route.SelectedRuntimeID != "" {
		r.RuntimeID = status.Route.SelectedRuntimeID
	}
	if status.Route.SelectedProvider != "" {
		r.ProviderID = status.Route.SelectedProvider
	}
	if url := lookupString(nestedMap(status.Result, "resource"), "url"); url != "" {
		r.CurrentURL = url
	}
	if attach := nestedMap(status.Result, "attach"); attach != nil {
		r.Attach = attach
	}
}

func (r *SessionRecord) toPayload() model.BrowserSessionPayload {
	return model.BrowserSessionPayload{
		SessionID:       r.SessionID,
		ProviderID:      r.ProviderID,
		RuntimeID:       r.RuntimeID,
		ResourceID:      r.ResourceID,
		ResourceKind:    r.ResourceKind,
		Proxy:           r.Proxy,
		CaptchaProvider: r.CaptchaProvider,
		CreatedAt:       r.CreatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:       r.ExpiresAt.UTC().Format(time.RFC3339),
		CurrentURL:      r.CurrentURL,
		StateSummary:    r.StateSummary,
		HistoryTail:     r.HistoryTail,
		Attach:          r.Attach,
	}
}

func durationFromEnvMs(name string, fallback time.Duration) time.Duration {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(raw + "ms")
	if err != nil {
		return fallback
	}
	if parsed <= 0 {
		return fallback
	}
	return parsed
}

func resolveExecutionTimeout(timeoutMS int, fallback time.Duration) time.Duration {
	if timeoutMS <= 0 {
		return fallback
	}
	parsed := time.Duration(timeoutMS) * time.Millisecond
	if parsed <= 0 {
		return fallback
	}
	return parsed
}

func resolveTTL(value int, fallback time.Duration) time.Duration {
	if value <= 0 {
		return fallback
	}
	return time.Duration(value) * time.Second
}

func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func nextID(prefix string) string {
	return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
}

func lookupString(value map[string]any, key string) string {
	if value == nil {
		return ""
	}
	raw, ok := value[key]
	if !ok || raw == nil {
		return ""
	}
	if str, ok := raw.(string); ok {
		return str
	}
	return fmt.Sprint(raw)
}

func nestedMap(value map[string]any, key string) map[string]any {
	if value == nil {
		return nil
	}
	raw, ok := value[key]
	if !ok || raw == nil {
		return nil
	}
	if typed, ok := raw.(map[string]any); ok {
		return typed
	}
	return nil
}
