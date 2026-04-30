package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/browser"
	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/processmanager"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

type Router struct {
	service   *service.Service
	processes *processmanager.Manager
	browser   *browser.API
}

func NewRouter(service *service.Service, processes *processmanager.Manager) http.Handler {
	router := &Router{service: service, processes: processes, browser: browser.New(service, processes)}
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", router.healthz)
	mux.HandleFunc("POST /v1/browser/sessions/acquire", router.acquireBrowserSession)
	mux.HandleFunc("POST /v1/browser/sessions/{sessionId}/renew", router.renewBrowserSession)
	mux.HandleFunc("POST /v1/browser/sessions/{sessionId}/release", router.releaseBrowserSession)
	mux.HandleFunc("POST /v1/browser/sessions/{sessionId}/steps", router.stepBrowserSession)
	mux.HandleFunc("POST /v1/browser/sessions/{sessionId}/flows/execute", router.executeBrowserSessionFlow)
	mux.HandleFunc("POST /v1/execute", router.execute)
	mux.HandleFunc("GET /v1/tasks/{taskId}", router.taskStatus)
	mux.HandleFunc("POST /v1/tasks/{taskId}/cancel", router.cancelTask)

	mux.HandleFunc("GET /admin/providers", router.listProviders)
	mux.HandleFunc("GET /admin/providers/health-summary", router.providerHealthSummary)
	mux.HandleFunc("GET /admin/runtimes", router.listRuntimes)
	mux.HandleFunc("GET /admin/stats/providers", router.providerStats)
	mux.HandleFunc("GET /admin/stats/runtimes", router.runtimeStats)
	mux.HandleFunc("GET /admin/routes/history", router.routeHistory)
	mux.HandleFunc("GET /admin/routes/fallbacks", router.fallbackHistory)
	mux.HandleFunc("GET /admin/routes/rejections", router.routeRejections)
	mux.HandleFunc("GET /admin/routes/insights", router.routeInsights)
	mux.HandleFunc("GET /admin/routes/insights/windows", router.routeWindowInsights)
	mux.HandleFunc("GET /admin/routes/windows", router.routeWindows)
	mux.HandleFunc("GET /admin/events/recent", router.recentOperationalEvents)
	mux.HandleFunc("GET /admin/routes/summary", router.routeSummary)
	mux.HandleFunc("POST /admin/providers/{providerId}/cooldown/reset", router.resetProviderCooldown)
	mux.HandleFunc("POST /admin/providers/{providerId}/disable", router.disableProvider)
	mux.HandleFunc("POST /admin/providers/{providerId}/enable", router.enableProvider)
	mux.HandleFunc("POST /admin/runtimes/spawn/{providerId}", router.spawnRuntime)
	mux.HandleFunc("POST /admin/runtimes/spawn-stub/{providerId}", router.spawnStubRuntime)

	mux.HandleFunc("POST /internal/runtimes/register", router.registerRuntime)
	mux.HandleFunc("POST /internal/runtimes/heartbeat", router.runtimeHeartbeat)
	mux.HandleFunc("POST /internal/runtimes/completion", router.runtimeCompletion)

	return mux
}

func (r *Router) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[map[string]string]{
		Success: true,
		Code:    "ok",
		Message: "healthy",
		Data: map[string]string{
			"status": "ok",
		},
	})
}

func (r *Router) acquireBrowserSession(w http.ResponseWriter, req *http.Request) {
	var body model.BrowserSessionAcquireRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", err)
		return
	}
	response, err := r.browser.AcquireSession(body)
	if err != nil {
		writeBrowserError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, model.Envelope[model.BrowserSessionResponse]{
		Success: true,
		Code:    "session_acquired",
		Message: "",
		Data:    response,
	})
}

func (r *Router) renewBrowserSession(w http.ResponseWriter, req *http.Request) {
	var body model.BrowserSessionRenewRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", err)
		return
	}
	sessionID := req.PathValue("sessionId")
	response, err := r.browser.RenewSession(sessionID, body)
	if err != nil {
		writeBrowserError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, model.Envelope[model.BrowserSessionResponse]{
		Success: true,
		Code:    "session_renewed",
		Message: "",
		Data:    response,
	})
}

func (r *Router) releaseBrowserSession(w http.ResponseWriter, req *http.Request) {
	sessionID := req.PathValue("sessionId")
	response, err := r.browser.ReleaseSession(sessionID)
	if err != nil {
		writeBrowserError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, model.Envelope[model.BrowserSessionResponse]{
		Success: true,
		Code:    "session_released",
		Message: "",
		Data:    response,
	})
}

func (r *Router) stepBrowserSession(w http.ResponseWriter, req *http.Request) {
	var body model.BrowserSessionStepRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", err)
		return
	}
	sessionID := req.PathValue("sessionId")
	status, err := r.browser.StepSession(sessionID, body)
	if err != nil {
		writeBrowserError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, model.Envelope[model.TaskStatusData]{
		Success: true,
		Code:    "session_step_completed",
		Message: "",
		Data:    status,
	})
}

func (r *Router) executeBrowserSessionFlow(w http.ResponseWriter, req *http.Request) {
	var body model.BrowserSessionFlowRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", err)
		return
	}
	sessionID := req.PathValue("sessionId")
	data, err := r.browser.ExecuteSessionFlow(sessionID, body)
	if err != nil {
		writeBrowserError(w, err)
		return
	}
	writeJSON(w, http.StatusAccepted, model.Envelope[model.ExecuteAcceptedData]{
		Success: true,
		Code:    "browser_flow_accepted",
		Message: "Browser flow accepted",
		Data:    data,
		Trace: model.Trace{
			TaskID:     data.TaskID,
			RuntimeID:  data.Route.RuntimeID,
			ProviderID: data.Route.SelectedProvider,
		},
	})
}

func (r *Router) execute(w http.ResponseWriter, req *http.Request) {
	var body model.ExecuteRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err)
		return
	}
	explicitRuntime := body.Target.RuntimeID != ""

	data, trace, err := r.service.SubmitTask(body)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	if data.State == "allocating" && r.processes != nil && data.Route.SelectedProvider != "" && !explicitRuntime {
		if runtimeView, spawnErr := r.processes.SpawnRuntime(data.Route.SelectedProvider); spawnErr == nil {
			if updated, updatedTrace, assignErr := r.service.AssignRuntimeToTask(data.TaskID, runtimeView.RuntimeID); assignErr == nil {
				data.State = updated.State
				data.Route.RuntimeID = updated.Route.SelectedRuntimeID
				trace = updatedTrace
			}
		} else {
			_, _, _ = r.service.RecordCompletion(model.RuntimeCompletionRequest{
				RuntimeID:  data.Route.RuntimeID,
				TaskID:     data.TaskID,
				Success:    false,
				FinishedAt: time.Now().UTC().Format(time.RFC3339),
				Error:      normalizeSpawnError(spawnErr),
			})
			if status, statusTrace, statusErr := r.service.GetTask(data.TaskID); statusErr == nil {
				data.State = status.State
				trace = statusTrace
				data.Route.RuntimeID = status.Route.SelectedRuntimeID
			}
		}
	}

	if data.Route.RuntimeID == "" && explicitRuntime {
		writeError(w, http.StatusConflict, "target_runtime_unavailable", errors.New("requested runtime is unavailable for direct execution"))
		return
	}

	if data.Route.RuntimeID != "" && r.processes != nil {
		if dispatchErr := r.processes.DispatchTask(data.TaskID, data.Route.RuntimeID, body); dispatchErr != nil {
			_, _, _ = r.service.RecordCompletion(model.RuntimeCompletionRequest{
				RuntimeID: data.Route.RuntimeID,
				TaskID:    data.TaskID,
				Success:   false,
				Error: &model.NormalizedError{
					Category:          "transport",
					Code:              "dispatch_failed",
					Message:           dispatchErr.Error(),
					Retriable:         true,
					CooldownCandidate: true,
				},
			})
			if status, statusTrace, statusErr := r.service.GetTask(data.TaskID); statusErr == nil {
				data.State = status.State
				trace = statusTrace
				data.Route.RuntimeID = status.Route.SelectedRuntimeID
			}
		}
	}

	writeJSON(w, http.StatusAccepted, model.Envelope[model.ExecuteAcceptedData]{
		Success: true,
		Code:    "task_accepted",
		Message: "Task accepted",
		Data:    data,
		Trace:   trace,
	})
}

func (r *Router) spawnRuntime(w http.ResponseWriter, req *http.Request) {
	if r.processes == nil {
		writeError(w, http.StatusNotImplemented, "not_available", errors.New("process manager unavailable"))
		return
	}
	providerID := req.PathValue("providerId")
	view, err := r.processes.SpawnRuntime(providerID)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusCreated, model.Envelope[model.RuntimeView]{
		Success: true,
		Code:    "runtime_spawned",
		Message: "",
		Data:    view,
		Trace: model.Trace{
			RuntimeID:  view.RuntimeID,
			ProviderID: view.ProviderID,
		},
	})
}

func (r *Router) taskStatus(w http.ResponseWriter, req *http.Request) {
	taskID := req.PathValue("taskId")
	data, trace, err := r.service.GetTask(taskID)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.TaskStatusData]{
		Success: true,
		Code:    "task_status",
		Message: "",
		Data:    data,
		Trace:   trace,
	})
}

func (r *Router) cancelTask(w http.ResponseWriter, req *http.Request) {
	taskID := req.PathValue("taskId")
	var body model.CancelRequest
	if req.ContentLength > 0 {
		if err := decodeJSON(req, &body); err != nil {
			writeError(w, http.StatusBadRequest, "bad_request", err)
			return
		}
	}

	data, trace, err := r.service.CancelTask(taskID, body)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.CancelData]{
		Success: true,
		Code:    "task_cancel_requested",
		Message: "Cancellation requested",
		Data:    data,
		Trace:   trace,
	})
}

func (r *Router) listProviders(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderListData]{
		Success: true,
		Code:    "provider_list",
		Message: "",
		Data:    r.service.ListProviders(),
	})
}

func (r *Router) providerHealthSummary(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderHealthSummaryData]{
		Success: true,
		Code:    "provider_health_summary",
		Message: "",
		Data:    r.service.ProviderHealthSummary(),
	})
}

func (r *Router) listRuntimes(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RuntimeListData]{
		Success: true,
		Code:    "runtime_list",
		Message: "",
		Data:    r.service.ListRuntimes(),
	})
}

func (r *Router) providerStats(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderStatsData]{
		Success: true,
		Code:    "provider_stats",
		Message: "",
		Data:    r.service.ProviderStats(),
	})
}

func (r *Router) runtimeStats(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RuntimeStatsData]{
		Success: true,
		Code:    "runtime_stats",
		Message: "",
		Data:    r.service.RuntimeStats(),
	})
}

func (r *Router) routeHistory(w http.ResponseWriter, req *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteHistoryData]{
		Success: true,
		Code:    "route_history",
		Message: "",
		Data:    r.service.RouteHistory(queryLimit(req, 20)),
	})
}

func (r *Router) fallbackHistory(w http.ResponseWriter, req *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.FallbackHistoryData]{
		Success: true,
		Code:    "fallback_history",
		Message: "",
		Data:    r.service.FallbackHistory(queryLimit(req, 20)),
	})
}

func (r *Router) routeRejections(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteRejectionSummaryData]{
		Success: true,
		Code:    "route_rejections",
		Message: "",
		Data:    r.service.RouteRejectionSummary(),
	})
}

func (r *Router) routeInsights(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteInsightsData]{
		Success: true,
		Code:    "route_insights",
		Message: "",
		Data:    r.service.RouteInsights(),
	})
}

func (r *Router) routeWindowInsights(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteWindowInsightsData]{
		Success: true,
		Code:    "route_window_insights",
		Message: "",
		Data:    r.service.RouteWindowInsights(),
	})
}

func (r *Router) routeWindows(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteWindowStatsData]{
		Success: true,
		Code:    "route_windows",
		Message: "",
		Data:    r.service.RouteWindowStats(),
	})
}

func (r *Router) recentOperationalEvents(w http.ResponseWriter, req *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.OperationalEventData]{
		Success: true,
		Code:    "operational_events",
		Message: "",
		Data:    r.service.RecentOperationalEvents(queryLimit(req, 20)),
	})
}

func (r *Router) routeSummary(w http.ResponseWriter, req *http.Request) {
	writeJSON(w, http.StatusOK, model.Envelope[model.RouteControlSummaryData]{
		Success: true,
		Code:    "route_summary",
		Message: "",
		Data: r.service.RouteControlSummary(
			queryLimitByKey(req, "history_limit", 10),
			queryLimitByKey(req, "fallback_limit", 10),
			queryLimitByKey(req, "rejection_limit", 10),
			queryLimitByKey(req, "event_limit", 10),
		),
	})
}

func (r *Router) resetProviderCooldown(w http.ResponseWriter, req *http.Request) {
	providerID := req.PathValue("providerId")
	view, err := r.service.ResetProviderCooldown(providerID)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderView]{
		Success: true,
		Code:    "provider_cooldown_reset",
		Message: "",
		Data:    view,
		Trace: model.Trace{
			ProviderID: providerID,
		},
	})
}

func (r *Router) disableProvider(w http.ResponseWriter, req *http.Request) {
	providerID := req.PathValue("providerId")
	view, err := r.service.SetProviderEnabled(providerID, false, "admin_disabled")
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderView]{
		Success: true,
		Code:    "provider_disabled",
		Message: "",
		Data:    view,
		Trace: model.Trace{
			ProviderID: providerID,
		},
	})
}

func (r *Router) enableProvider(w http.ResponseWriter, req *http.Request) {
	providerID := req.PathValue("providerId")
	view, err := r.service.SetProviderEnabled(providerID, true, "")
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.ProviderView]{
		Success: true,
		Code:    "provider_enabled",
		Message: "",
		Data:    view,
		Trace: model.Trace{
			ProviderID: providerID,
		},
	})
}

func (r *Router) spawnStubRuntime(w http.ResponseWriter, req *http.Request) {
	if r.processes == nil {
		writeError(w, http.StatusNotImplemented, "not_available", errors.New("process manager unavailable"))
		return
	}
	providerID := req.PathValue("providerId")
	view, err := r.processes.SpawnStub(providerID)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusCreated, model.Envelope[model.RuntimeView]{
		Success: true,
		Code:    "runtime_spawned",
		Message: "",
		Data:    view,
		Trace: model.Trace{
			RuntimeID:  view.RuntimeID,
			ProviderID: view.ProviderID,
		},
	})
}

func (r *Router) registerRuntime(w http.ResponseWriter, req *http.Request) {
	var body model.RuntimeRegistrationRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err)
		return
	}

	data, trace, err := r.service.RegisterRuntime(body)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.RuntimeView]{
		Success: true,
		Code:    "runtime_registered",
		Message: "",
		Data:    data,
		Trace:   trace,
	})
}

func (r *Router) runtimeHeartbeat(w http.ResponseWriter, req *http.Request) {
	var body model.RuntimeHeartbeatRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err)
		return
	}

	data, trace, err := r.service.RecordHeartbeat(body)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.RuntimeView]{
		Success: true,
		Code:    "runtime_heartbeat_recorded",
		Message: "",
		Data:    data,
		Trace:   trace,
	})
}

func (r *Router) runtimeCompletion(w http.ResponseWriter, req *http.Request) {
	var body model.RuntimeCompletionRequest
	if err := decodeJSON(req, &body); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err)
		return
	}

	data, trace, err := r.service.RecordCompletion(body)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, model.Envelope[model.TaskStatusData]{
		Success: true,
		Code:    "runtime_completion_recorded",
		Message: "",
		Data:    data,
		Trace:   trace,
	})
}

func decodeJSON(req *http.Request, target any) error {
	if req.Body == nil {
		return nil
	}
	defer req.Body.Close()

	decoder := json.NewDecoder(req.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, code string, err error) {
	writeJSON(w, status, model.Envelope[map[string]any]{
		Success: false,
		Code:    code,
		Message: err.Error(),
		Error: &model.NormalizedError{
			Code:    code,
			Message: err.Error(),
		},
	})
}

func writeServiceError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, service.ErrInvalidRequest):
		writeError(w, http.StatusBadRequest, "invalid_request", err)
	case errors.Is(err, service.ErrNotFound):
		writeError(w, http.StatusNotFound, "not_found", err)
	default:
		writeError(w, http.StatusInternalServerError, "internal_error", err)
	}
}

func writeBrowserError(w http.ResponseWriter, err error) {
	var httpErr *browser.HTTPError
	if errors.As(err, &httpErr) {
		writeError(w, httpErr.StatusCode, httpErr.Code, errors.New(httpErr.Message))
		return
	}
	writeError(w, http.StatusBadGateway, "execution_failed", err)
}

func normalizeSpawnError(err error) *model.NormalizedError {
	if err == nil {
		return nil
	}
	if errors.Is(err, service.ErrInvalidRequest) {
		return &model.NormalizedError{
			Category:          "provider",
			Code:              "spawn_invalid_request",
			Message:           err.Error(),
			Retriable:         false,
			CooldownCandidate: false,
		}
	}

	return &model.NormalizedError{
		Category:          "startup",
		Code:              "spawn_failed",
		Message:           err.Error(),
		Retriable:         true,
		CooldownCandidate: true,
	}
}

func queryLimit(req *http.Request, fallback int) int {
	return queryLimitByKey(req, "limit", fallback)
}

func queryLimitByKey(req *http.Request, key string, fallback int) int {
	if req == nil || req.URL == nil {
		return fallback
	}
	raw := req.URL.Query().Get(key)
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}
