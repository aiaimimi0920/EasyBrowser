package service

import (
	"errors"
	"fmt"
	"math"
	"slices"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/provider"
)

var (
	ErrInvalidRequest = errors.New("invalid request")
	ErrNotFound       = errors.New("not found")
)

const (
	defaultFailureThreshold = 3
	defaultCooldownDuration = 5 * time.Minute
	defaultEventLimit       = 200
	defaultHeartbeatTimeout = 45 * time.Second
)

type taskRecord struct {
	RequestID string
	Data      model.TaskStatusData
}

type providerRecord struct {
	View          model.ProviderView
	Stats         model.ProviderStatsView
	cooldownUntil time.Time
	lastFailureAt time.Time
	lastSuccessAt time.Time
}

type runtimeRecord struct {
	View            model.RuntimeView
	Stats           model.RuntimeStatsView
	cooldownUntil   time.Time
	lastFailureAt   time.Time
	lastSuccessAt   time.Time
	lastHeartbeat   time.Time
	heartbeatMissed bool
}

type Service struct {
	mu               sync.RWMutex
	sequence         atomic.Uint64
	tasks            map[string]*taskRecord
	events           []model.OperationalEvent
	providers        map[string]*providerRecord
	runtimes         map[string]*runtimeRecord
	order            []string
	failureThreshold int
	cooldownDuration time.Duration
	eventLimit       int
	heartbeatTimeout time.Duration
}

type providerCandidate struct {
	id             string
	profileRank    int
	score          int
	breakdown      provider.StrategyScoreBreakdown
	readyRuntimes  int
	recentFailures int
	totalFailures  int
	orderIndex     int
}

type routeSelection struct {
	providerID      string
	strategyProfile string
	fallbackUsed    bool
	considered      []string
	rejected        []string
	reason          string
	diagnostics     *model.RouteDiagnosticsView
	candidates      []model.RouteCandidateView
}

func New() *Service {
	s := &Service{
		tasks:            make(map[string]*taskRecord),
		providers:        make(map[string]*providerRecord),
		runtimes:         make(map[string]*runtimeRecord),
		order:            []string{"chrome", "camoufox", "geekez", "browserbase"},
		failureThreshold: defaultFailureThreshold,
		cooldownDuration: defaultCooldownDuration,
		eventLimit:       defaultEventLimit,
		heartbeatTimeout: defaultHeartbeatTimeout,
	}

	s.providers["chrome"] = &providerRecord{
		View: model.ProviderView{
			ProviderID: "chrome",
			Kind:       "chrome",
			Enabled:    true,
			Healthy:    true,
			Capabilities: model.CapabilityFlags{
				SupportsDirectMode:      true,
				SupportsStrategyMode:    true,
				SupportsFreshRuntime:    true,
				SupportsRuntimeReuse:    true,
				SupportsLocalProcess:    true,
				SupportsRemoteExecution: false,
			},
			Limits: model.ProviderLimits{MaxRuntimes: 8, MaxParallelTasks: 8},
		},
		Stats: model.ProviderStatsView{
			ProviderID:  "chrome",
			ErrorCounts: map[string]int{},
		},
	}
	s.providers["camoufox"] = &providerRecord{
		View: model.ProviderView{
			ProviderID: "camoufox",
			Kind:       "camoufox",
			Enabled:    true,
			Healthy:    true,
			Capabilities: model.CapabilityFlags{
				SupportsDirectMode:      true,
				SupportsStrategyMode:    true,
				SupportsFreshRuntime:    true,
				SupportsRuntimeReuse:    true,
				SupportsLocalProcess:    true,
				SupportsRemoteExecution: false,
			},
			Limits: model.ProviderLimits{MaxRuntimes: 6, MaxParallelTasks: 6},
		},
		Stats: model.ProviderStatsView{
			ProviderID:  "camoufox",
			ErrorCounts: map[string]int{},
		},
	}
	s.providers["geekez"] = &providerRecord{
		View: model.ProviderView{
			ProviderID: "geekez",
			Kind:       "geekez",
			Enabled:    true,
			Healthy:    true,
			Capabilities: model.CapabilityFlags{
				SupportsDirectMode:      true,
				SupportsStrategyMode:    true,
				SupportsFreshRuntime:    true,
				SupportsRuntimeReuse:    true,
				SupportsLocalProcess:    true,
				SupportsRemoteExecution: false,
			},
			Limits: model.ProviderLimits{MaxRuntimes: 4, MaxParallelTasks: 4},
		},
		Stats: model.ProviderStatsView{
			ProviderID:  "geekez",
			ErrorCounts: map[string]int{},
		},
	}
	s.providers["browserbase"] = &providerRecord{
		View: model.ProviderView{
			ProviderID: "browserbase",
			Kind:       "browserbase",
			Enabled:    true,
			Healthy:    true,
			Capabilities: model.CapabilityFlags{
				SupportsDirectMode:      true,
				SupportsStrategyMode:    true,
				SupportsFreshRuntime:    true,
				SupportsRuntimeReuse:    true,
				SupportsLocalProcess:    false,
				SupportsRemoteExecution: true,
			},
			Limits: model.ProviderLimits{MaxRuntimes: 16, MaxParallelTasks: 16},
		},
		Stats: model.ProviderStatsView{
			ProviderID:  "browserbase",
			ErrorCounts: map[string]int{},
		},
	}

	for _, provider := range s.providers {
		s.syncProviderDerivedLocked(provider)
	}

	return s
}

func (s *Service) nextID(prefix string) string {
	value := s.sequence.Add(1)
	return fmt.Sprintf("%s-%06d", prefix, value)
}

func (s *Service) now() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func (s *Service) normalizeMode(mode string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(mode))
	switch normalized {
	case "", "strategy":
		return "strategy", nil
	case "direct", "specified":
		return "direct", nil
	default:
		return "", fmt.Errorf("%w: unsupported mode %q", ErrInvalidRequest, mode)
	}
}

func (s *Service) SubmitTask(req model.ExecuteRequest) (model.ExecuteAcceptedData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	mode, err := s.normalizeMode(req.Mode)
	if err != nil {
		return model.ExecuteAcceptedData{}, model.Trace{}, err
	}
	if req.Operation.Kind == "" {
		return model.ExecuteAcceptedData{}, model.Trace{}, fmt.Errorf("%w: operation.kind is required", ErrInvalidRequest)
	}
	if mode == "direct" && req.Target.Provider == "" && req.Target.RuntimeID == "" {
		return model.ExecuteAcceptedData{}, model.Trace{}, fmt.Errorf("%w: target.provider or target.runtime_id is required for direct/specified mode", ErrInvalidRequest)
	}
	action := provider.ActionNameFromRequest(req)
	resourceKind := provider.ResourceKindFromRequest(req)
	if mode == "strategy" && provider.IsGenericResourceAction(action) && resourceKind == "" {
		return model.ExecuteAcceptedData{}, model.Trace{}, fmt.Errorf("%w: resource_kind is required for strategy mode action %q", ErrInvalidRequest, action)
	}
	if mode == "direct" && resourceKind == "" {
		inferProvider := req.Target.Provider
		if inferProvider == "" && req.Target.RuntimeID != "" {
			if runtimeRecord, ok := s.runtimes[req.Target.RuntimeID]; ok {
				inferProvider = runtimeRecord.View.ProviderID
			}
		}
		resourceKind = provider.InferResourceKindForProvider(inferProvider)
	}

	s.refreshCooldownsLocked()

	taskID := s.nextID("task")
	requestID := req.RequestID
	if requestID == "" {
		requestID = s.nextID("req")
	}

	selection, err := s.selectProviderLocked(mode, action, resourceKind, req.Isolation.RuntimeReuse, req.Target)
	if err != nil {
		return model.ExecuteAcceptedData{}, model.Trace{}, err
	}

	trace := model.Trace{
		RequestID:  requestID,
		TaskID:     taskID,
		ProviderID: selection.providerID,
	}

	record := &taskRecord{
		RequestID: requestID,
		Data: model.TaskStatusData{
			TaskID: taskID,
			State:  "allocating",
			Mode:   mode,
			Route: model.RouteDecisionView{
				Mode:                mode,
				StrategyProfile:     selection.strategyProfile,
				SelectedProvider:    selection.providerID,
				StrategyReason:      selection.reason,
				FallbackUsed:        selection.fallbackUsed,
				ConsideredProviders: selection.considered,
				RejectedProviders:   selection.rejected,
				Diagnostics:         selection.diagnostics,
				Candidates:          selection.candidates,
			},
			Timing: model.TaskTiming{QueuedAt: s.now()},
		},
	}

	var allocation model.RuntimeAllocationView
	if mode == "direct" && req.Target.RuntimeID != "" {
		allocation = s.allocateSpecificRuntimeLocked(req.Target.RuntimeID, selection.providerID, taskID)
	} else {
		allocation = s.allocateRuntimeLocked(selection.providerID, taskID)
	}
	if allocation.Success {
		record.Data.State = "running"
		record.Data.Route.SelectedRuntimeID = allocation.Allocation.RuntimeID
		record.Data.Timing.StartedAt = s.now()
		trace.RuntimeID = allocation.Allocation.RuntimeID
	}

	s.tasks[taskID] = record
	if provider, ok := s.providers[selection.providerID]; ok {
		provider.Stats.TotalRequests++
		s.syncProviderDerivedLocked(provider)
	}
	s.appendEventLocked(
		"route_selected",
		"info",
		fmt.Sprintf("selected provider %s for action %s", selection.providerID, coalesceAction(action)),
		model.Trace{
			RequestID:  requestID,
			TaskID:     taskID,
			RuntimeID:  record.Data.Route.SelectedRuntimeID,
			ProviderID: selection.providerID,
		},
		map[string]any{
			"mode":             mode,
			"strategy_profile": selection.strategyProfile,
			"fallback_used":    selection.fallbackUsed,
			"action":           coalesceAction(action),
			"resource_kind":    coalesceResourceKind(resourceKind),
		},
	)
	if selection.fallbackUsed {
		s.appendEventLocked(
			"route_fallback",
			"warn",
			fmt.Sprintf("fallback selected provider %s", selection.providerID),
			model.Trace{
				RequestID:  requestID,
				TaskID:     taskID,
				RuntimeID:  record.Data.Route.SelectedRuntimeID,
				ProviderID: selection.providerID,
			},
			map[string]any{
				"strategy_profile": selection.strategyProfile,
				"action":           coalesceAction(action),
				"resource_kind":    coalesceResourceKind(resourceKind),
			},
		)
	}

	return model.ExecuteAcceptedData{
		TaskID: taskID,
		State:  record.Data.State,
		Route: model.ExecuteRouteView{
			Mode:             mode,
			StrategyProfile:  selection.strategyProfile,
			SelectedProvider: selection.providerID,
			RuntimeID:        record.Data.Route.SelectedRuntimeID,
			Diagnostics:      selection.diagnostics,
		},
	}, trace, nil
}

func (s *Service) selectProviderLocked(mode, action, resourceKind, runtimeReuse string, target model.TargetSpec) (routeSelection, error) {
	if mode == "direct" {
		providerID := target.Provider
		if target.RuntimeID != "" {
			runtimeRecord, ok := s.runtimes[target.RuntimeID]
			if !ok {
				return routeSelection{}, fmt.Errorf("%w: unknown runtime %q", ErrInvalidRequest, target.RuntimeID)
			}
			if providerID != "" && runtimeRecord.View.ProviderID != providerID {
				return routeSelection{}, fmt.Errorf("%w: runtime %q does not belong to provider %q", ErrInvalidRequest, target.RuntimeID, providerID)
			}
			providerID = runtimeRecord.View.ProviderID
		}

		providerRecord, ok := s.providers[providerID]
		if !ok {
			return routeSelection{}, fmt.Errorf("%w: unknown provider %q", ErrInvalidRequest, providerID)
		}
		if !provider.SupportsMode(providerRecord.View.Capabilities, mode) {
			return routeSelection{}, fmt.Errorf("%w: provider %q does not support mode %q", ErrInvalidRequest, providerID, mode)
		}
		if !providerRecord.View.Enabled {
			return routeSelection{}, fmt.Errorf("%w: provider %q disabled", ErrInvalidRequest, providerID)
		}
		if providerRecord.View.CooldownActive {
			return routeSelection{}, fmt.Errorf("%w: provider %q cooled until %s", ErrInvalidRequest, providerID, providerRecord.View.CooldownUntil)
		}
		if !provider.ProviderSupportsActionForResource(providerID, providerRecord.View.Capabilities, action, resourceKind) {
			return routeSelection{}, fmt.Errorf("%w: provider %q does not support action %q resource_kind=%q", ErrInvalidRequest, providerID, action, resourceKind)
		}
		diagnostics := buildRouteDiagnostics(action, resourceKind, runtimeReuse, "", 0, 0, provider.StrategyScoreBreakdown{}, 0, 0, 0)
		return routeSelection{
			providerID:   providerID,
			considered:   []string{providerID},
			reason:       directReason(action, resourceKind),
			fallbackUsed: false,
			diagnostics:  diagnostics,
			candidates: []model.RouteCandidateView{
				{
					ProviderID:      providerID,
					Eligible:        true,
					Selected:        true,
					SupportsAction:  true,
					SupportsMode:    true,
					ProviderEnabled: true,
				},
			},
		}, nil
	}

	strategyProfile := provider.NormalizeStrategyProfile(target.StrategyProfile)
	allowedSet := make(map[string]struct{})
	if len(target.AllowedProviders) > 0 {
		for _, providerID := range target.AllowedProviders {
			allowedSet[providerID] = struct{}{}
		}
	}

	considered := make([]string, 0, len(s.order))
	rejected := make([]string, 0)
	candidates := make([]providerCandidate, 0, len(s.order))
	candidateViews := make([]model.RouteCandidateView, 0, len(s.order))
	bestProfileRank := int(^uint(0) >> 1)

	for idx, providerID := range s.order {
		providerRecord, ok := s.providers[providerID]
		if !ok {
			continue
		}
		if len(allowedSet) > 0 {
			if _, allowed := allowedSet[providerID]; !allowed {
				continue
			}
		}
		considered = append(considered, providerID)
		supportsMode := provider.SupportsMode(providerRecord.View.Capabilities, mode)
		supportsAction := provider.ProviderSupportsActionForResource(providerID, providerRecord.View.Capabilities, action, resourceKind)
		readyRuntimes := s.readyRuntimeCountLocked(providerID)
		baseView := model.RouteCandidateView{
			ProviderID:      providerID,
			SupportsAction:  supportsAction,
			SupportsMode:    supportsMode,
			ProviderEnabled: providerRecord.View.Enabled,
			CooldownActive:  providerRecord.View.CooldownActive,
			ReadyRuntimes:   readyRuntimes,
			RecentFailures:  providerRecord.Stats.RecentFailures,
			TotalFailures:   providerRecord.Stats.TotalFailures,
		}
		if !supportsMode || !supportsAction {
			baseView.Eligible = false
			baseView.RejectionReason = rejectionReasonForCapabilities(supportsMode, supportsAction)
			candidateViews = append(candidateViews, baseView)
			rejected = append(rejected, providerID)
			continue
		}
		profileRank := provider.StrategyPriority(strategyProfile, providerID, action, resourceKind)
		baseView.ProfileRank = profileRank
		if profileRank < bestProfileRank {
			bestProfileRank = profileRank
		}
		if !providerRecord.View.Enabled || providerRecord.View.CooldownActive {
			baseView.Eligible = false
			baseView.RejectionReason = rejectionReasonForAvailability(providerRecord.View.Enabled, providerRecord.View.CooldownActive)
			candidateViews = append(candidateViews, baseView)
			rejected = append(rejected, providerID)
			continue
		}
		scoreResult := provider.StrategyScoreDetailed(provider.StrategyScoreInput{
			Profile:        strategyProfile,
			ProviderID:     providerID,
			Action:         action,
			ResourceKind:   resourceKind,
			RuntimeReuse:   runtimeReuse,
			ReadyRuntimes:  readyRuntimes,
			RecentFailures: providerRecord.Stats.RecentFailures,
			TotalFailures:  providerRecord.Stats.TotalFailures,
		})
		baseView.Eligible = true
		baseView.Score = scoreResult.Score
		baseView.Breakdown = mapRouteScoreBreakdown(scoreResult.Breakdown)
		candidateViews = append(candidateViews, baseView)

		candidates = append(candidates, providerCandidate{
			id:             providerID,
			profileRank:    profileRank,
			score:          scoreResult.Score,
			breakdown:      scoreResult.Breakdown,
			readyRuntimes:  readyRuntimes,
			recentFailures: providerRecord.Stats.RecentFailures,
			totalFailures:  providerRecord.Stats.TotalFailures,
			orderIndex:     idx,
		})
	}

	if len(candidates) == 0 {
		return routeSelection{}, fmt.Errorf("%w: no eligible provider for action %q resource_kind=%q profile=%q", ErrInvalidRequest, action, resourceKind, strategyProfile)
	}

	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].profileRank != candidates[j].profileRank {
			return candidates[i].profileRank < candidates[j].profileRank
		}
		if candidates[i].score != candidates[j].score {
			return candidates[i].score > candidates[j].score
		}
		if candidates[i].readyRuntimes != candidates[j].readyRuntimes {
			return candidates[i].readyRuntimes > candidates[j].readyRuntimes
		}
		if candidates[i].recentFailures != candidates[j].recentFailures {
			return candidates[i].recentFailures < candidates[j].recentFailures
		}
		if candidates[i].totalFailures != candidates[j].totalFailures {
			return candidates[i].totalFailures < candidates[j].totalFailures
		}
		return candidates[i].orderIndex < candidates[j].orderIndex
	})

	chosen := candidates[0]
	fallbackUsed := chosen.profileRank > bestProfileRank
	for i := range candidateViews {
		if candidateViews[i].ProviderID == chosen.id {
			candidateViews[i].Selected = true
		}
	}
	diagnostics := buildRouteDiagnostics(
		action,
		resourceKind,
		runtimeReuse,
		strategyProfile,
		chosen.profileRank,
		chosen.score,
		chosen.breakdown,
		chosen.readyRuntimes,
		chosen.recentFailures,
		chosen.totalFailures,
	)
	reason := fmt.Sprintf(
		"strategy selected provider=%s profile=%s action=%s class=%s resource_kind=%s runtime_reuse=%s fallback_used=%t profile_rank=%d score=%d ready_runtimes=%d recent_failures=%d total_failures=%d",
		chosen.id,
		strategyProfile,
		coalesceAction(action),
		provider.ClassifyAction(action),
		coalesceResourceKind(resourceKind),
		coalesceRuntimeReuse(runtimeReuse),
		fallbackUsed,
		chosen.profileRank,
		chosen.score,
		chosen.readyRuntimes,
		chosen.recentFailures,
		chosen.totalFailures,
	)
	return routeSelection{
		providerID:      chosen.id,
		strategyProfile: strategyProfile,
		fallbackUsed:    fallbackUsed,
		considered:      considered,
		rejected:        rejected,
		reason:          reason,
		diagnostics:     diagnostics,
		candidates:      candidateViews,
	}, nil
}

func (s *Service) readyRuntimeCountLocked(providerID string) int {
	count := 0
	for _, runtime := range s.runtimes {
		if runtime.View.ProviderID != providerID {
			continue
		}
		if runtime.View.State == "ready" && runtime.View.Healthy && !runtime.View.CooldownActive {
			count++
		}
	}
	return count
}

func (s *Service) allocateRuntimeLocked(providerID, taskID string) model.RuntimeAllocationView {
	var candidates []*runtimeRecord
	for _, runtime := range s.runtimes {
		if runtime.View.ProviderID != providerID || runtime.View.State != "ready" {
			continue
		}
		if runtime.View.CooldownActive || !runtime.View.Healthy {
			continue
		}
		candidates = append(candidates, runtime)
	}

	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].Stats.RecentFailures != candidates[j].Stats.RecentFailures {
			return candidates[i].Stats.RecentFailures < candidates[j].Stats.RecentFailures
		}
		return candidates[i].View.RuntimeID < candidates[j].View.RuntimeID
	})

	if len(candidates) > 0 {
		runtime := candidates[0]
		leaseID := s.nextID("lease")
		runtime.View.State = "busy"
		runtime.View.LeaseID = leaseID
		runtime.View.CurrentTaskID = taskID
		runtime.Stats.TotalLeases++
		s.syncRuntimeDerivedLocked(runtime)
		s.appendEventLocked("runtime_reused", "info", fmt.Sprintf("reused runtime %s for task %s", runtime.View.RuntimeID, taskID), model.Trace{
			TaskID:     taskID,
			RuntimeID:  runtime.View.RuntimeID,
			ProviderID: providerID,
		}, map[string]any{
			"lease_id": leaseID,
			"source":   "reused",
		})

		view := model.RuntimeAllocationView{Success: true}
		view.Allocation.RuntimeID = runtime.View.RuntimeID
		view.Allocation.ProviderID = providerID
		view.Allocation.Source = "reused"
		view.Allocation.LeaseID = leaseID
		return view
	}

	view := model.RuntimeAllocationView{}
	view.Reason.Code = "runtime_unavailable"
	view.Reason.Message = "no ready runtime available; awaiting allocation"
	return view
}

func (s *Service) allocateSpecificRuntimeLocked(runtimeID, providerID, taskID string) model.RuntimeAllocationView {
	runtime, ok := s.runtimes[runtimeID]
	if !ok {
		view := model.RuntimeAllocationView{}
		view.Reason.Code = "runtime_not_found"
		view.Reason.Message = fmt.Sprintf("runtime %s not found", runtimeID)
		return view
	}
	if runtime.View.ProviderID != providerID {
		view := model.RuntimeAllocationView{}
		view.Reason.Code = "runtime_provider_mismatch"
		view.Reason.Message = fmt.Sprintf("runtime %s does not belong to provider %s", runtimeID, providerID)
		return view
	}
	// Explicit runtime targeting is used by browser-session semantics. Keep dispatch pinned
	// to the caller-selected runtime instead of silently routing to a different child.
	if runtime.View.State == "busy" && runtime.View.CurrentTaskID != "" && runtime.View.CurrentTaskID != taskID {
		view := model.RuntimeAllocationView{}
		view.Reason.Code = "runtime_unavailable"
		view.Reason.Message = fmt.Sprintf("runtime %s is busy with task %s", runtimeID, runtime.View.CurrentTaskID)
		return view
	}

	leaseID := s.nextID("lease")
	runtime.View.State = "busy"
	runtime.View.LeaseID = leaseID
	runtime.View.CurrentTaskID = taskID
	runtime.Stats.TotalLeases++
	s.syncRuntimeDerivedLocked(runtime)
	s.appendEventLocked("runtime_reused", "info", fmt.Sprintf("assigned existing runtime %s for task %s", runtime.View.RuntimeID, taskID), model.Trace{
		TaskID:     taskID,
		RuntimeID:  runtime.View.RuntimeID,
		ProviderID: providerID,
	}, map[string]any{
		"lease_id": leaseID,
		"source":   "specified",
	})

	view := model.RuntimeAllocationView{Success: true}
	view.Allocation.RuntimeID = runtime.View.RuntimeID
	view.Allocation.ProviderID = providerID
	view.Allocation.Source = "specified"
	view.Allocation.LeaseID = leaseID
	return view
}

func (s *Service) GetTask(taskID string) (model.TaskStatusData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	record, ok := s.tasks[taskID]
	if !ok {
		return model.TaskStatusData{}, model.Trace{}, ErrNotFound
	}

	return record.Data, model.Trace{
		RequestID:  record.RequestID,
		TaskID:     record.Data.TaskID,
		RuntimeID:  record.Data.Route.SelectedRuntimeID,
		ProviderID: record.Data.Route.SelectedProvider,
	}, nil
}

func (s *Service) AssignRuntimeToTask(taskID, runtimeID string) (model.TaskStatusData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	task, ok := s.tasks[taskID]
	if !ok {
		return model.TaskStatusData{}, model.Trace{}, ErrNotFound
	}
	runtime, ok := s.runtimes[runtimeID]
	if !ok {
		return model.TaskStatusData{}, model.Trace{}, ErrNotFound
	}
	if runtime.View.State != "ready" {
		return model.TaskStatusData{}, model.Trace{}, fmt.Errorf("%w: runtime %q is not ready", ErrInvalidRequest, runtimeID)
	}
	if runtime.View.CooldownActive || !runtime.View.Healthy {
		return model.TaskStatusData{}, model.Trace{}, fmt.Errorf("%w: runtime %q is unavailable", ErrInvalidRequest, runtimeID)
	}
	if task.Data.Route.SelectedProvider != "" && task.Data.Route.SelectedProvider != runtime.View.ProviderID {
		return model.TaskStatusData{}, model.Trace{}, fmt.Errorf("%w: runtime provider mismatch", ErrInvalidRequest)
	}

	leaseID := s.nextID("lease")
	runtime.View.State = "busy"
	runtime.View.LeaseID = leaseID
	runtime.View.CurrentTaskID = taskID
	runtime.Stats.TotalLeases++
	s.syncRuntimeDerivedLocked(runtime)

	task.Data.State = "running"
	task.Data.Route.SelectedProvider = runtime.View.ProviderID
	task.Data.Route.SelectedRuntimeID = runtimeID
	if task.Data.Timing.StartedAt == "" {
		task.Data.Timing.StartedAt = s.now()
	}

	return task.Data, model.Trace{
		RequestID:  task.RequestID,
		TaskID:     taskID,
		RuntimeID:  runtimeID,
		ProviderID: runtime.View.ProviderID,
	}, nil
}

func (s *Service) CancelTask(taskID string, _ model.CancelRequest) (model.CancelData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.tasks[taskID]
	if !ok {
		return model.CancelData{}, model.Trace{}, ErrNotFound
	}

	cancelState := "requested"
	switch record.Data.State {
	case "succeeded", "failed", "timed_out", "cancelled":
		cancelState = "not_cancellable"
	default:
		record.Data.State = "cancelled"
		record.Data.Timing.FinishedAt = s.now()
		if runtimeID := record.Data.Route.SelectedRuntimeID; runtimeID != "" {
			s.releaseRuntimeLocked(runtimeID)
		}
		s.appendEventLocked("task_cancelled", "info", fmt.Sprintf("task %s cancelled", taskID), model.Trace{
			RequestID:  record.RequestID,
			TaskID:     record.Data.TaskID,
			RuntimeID:  record.Data.Route.SelectedRuntimeID,
			ProviderID: record.Data.Route.SelectedProvider,
		}, map[string]any{
			"action":        routeAction(record.Data.Route),
			"resource_kind": routeResourceKind(record.Data.Route),
			"cancel_state":  "cancelled",
		})
	}

	return model.CancelData{TaskID: taskID, CancelState: cancelState}, model.Trace{
		RequestID:  record.RequestID,
		TaskID:     record.Data.TaskID,
		RuntimeID:  record.Data.Route.SelectedRuntimeID,
		ProviderID: record.Data.Route.SelectedProvider,
	}, nil
}

func (s *Service) ListProviders() model.ProviderListData {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	providers := make([]model.ProviderView, 0, len(s.providers))
	for _, providerID := range s.order {
		if provider, ok := s.providers[providerID]; ok {
			providers = append(providers, provider.View)
		}
	}
	return model.ProviderListData{Providers: providers}
}

func (s *Service) ListRuntimes() model.RuntimeListData {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	runtimes := make([]model.RuntimeView, 0, len(s.runtimes))
	for _, runtime := range s.runtimes {
		runtimes = append(runtimes, runtime.View)
	}
	slices.SortFunc(runtimes, func(a, b model.RuntimeView) int {
		switch {
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		case a.RuntimeID < b.RuntimeID:
			return -1
		case a.RuntimeID > b.RuntimeID:
			return 1
		default:
			return 0
		}
	})
	return model.RuntimeListData{Runtimes: runtimes}
}

func (s *Service) GetRuntime(runtimeID string) (model.RuntimeView, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	runtime, ok := s.runtimes[runtimeID]
	if !ok {
		return model.RuntimeView{}, model.Trace{}, ErrNotFound
	}

	return runtime.View, model.Trace{
		RuntimeID:  runtime.View.RuntimeID,
		ProviderID: runtime.View.ProviderID,
		TaskID:     runtime.View.CurrentTaskID,
	}, nil
}

func (s *Service) ProviderStats() model.ProviderStatsData {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	stats := make([]model.ProviderStatsView, 0, len(s.providers))
	for _, providerID := range s.order {
		if provider, ok := s.providers[providerID]; ok {
			stats = append(stats, provider.Stats)
		}
	}
	return model.ProviderStatsData{Providers: stats}
}

func (s *Service) RuntimeStats() model.RuntimeStatsData {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshCooldownsLocked()

	stats := make([]model.RuntimeStatsView, 0, len(s.runtimes))
	for _, runtime := range s.runtimes {
		stats = append(stats, runtime.Stats)
	}
	slices.SortFunc(stats, func(a, b model.RuntimeStatsView) int {
		switch {
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		case a.RuntimeID < b.RuntimeID:
			return -1
		case a.RuntimeID > b.RuntimeID:
			return 1
		default:
			return 0
		}
	})
	return model.RuntimeStatsData{Runtimes: stats}
}

func (s *Service) RouteHistory(limit int) model.RouteHistoryData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.RouteHistoryData{Routes: s.collectRouteHistoryLocked(limit, false)}
}

func (s *Service) FallbackHistory(limit int) model.FallbackHistoryData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.FallbackHistoryData{Fallbacks: s.collectRouteHistoryLocked(limit, true)}
}

func (s *Service) RouteRejectionSummary() model.RouteRejectionSummaryData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.RouteRejectionSummaryData{Rejections: s.collectRouteRejectionSummaryLocked(0)}
}

func (s *Service) RouteInsights() model.RouteInsightsData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return s.collectRouteInsightsLocked()
}

func (s *Service) RouteWindowInsights() model.RouteWindowInsightsData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.RouteWindowInsightsData{Windows: s.collectRouteWindowInsightsLocked()}
}

func (s *Service) RouteWindowStats() model.RouteWindowStatsData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.RouteWindowStatsData{Windows: s.collectRouteWindowStatsLocked()}
}

func (s *Service) ProviderHealthSummary() model.ProviderHealthSummaryData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.ProviderHealthSummaryData{Providers: s.collectProviderHealthSummaryLocked()}
}

func (s *Service) RecentOperationalEvents(limit int) model.OperationalEventData {
	s.mu.Lock()
	defer s.mu.Unlock()

	return model.OperationalEventData{Events: s.collectOperationalEventsLocked(limit)}
}

func (s *Service) RecordOperationalEvent(kind, severity, message string, trace model.Trace, details map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.appendEventLocked(kind, severity, message, trace, details)
}

func (s *Service) RouteControlSummary(historyLimit, fallbackLimit, rejectionLimit, eventLimit int) model.RouteControlSummaryData {
	s.mu.Lock()
	defer s.mu.Unlock()

	recentEvents := s.collectRouteHistoryLocked(historyLimit, false)
	recentFallbacks := s.collectRouteHistoryLocked(fallbackLimit, true)
	rejections := s.collectRouteRejectionSummaryLocked(rejectionLimit)
	operationalEvents := s.collectOperationalEventsLocked(eventLimit)

	providerCounts := make(map[string]int)
	profileCounts := make(map[string]int)
	totalFallbacks := 0
	for _, task := range s.tasks {
		if task.Data.Route.SelectedProvider != "" {
			providerCounts[task.Data.Route.SelectedProvider]++
		}
		if task.Data.Route.StrategyProfile != "" {
			profileCounts[task.Data.Route.StrategyProfile]++
		}
		if task.Data.Route.FallbackUsed {
			totalFallbacks++
		}
	}

	providerSelections := make([]model.RouteSelectionSummaryEntry, 0, len(providerCounts))
	for providerID, count := range providerCounts {
		providerSelections = append(providerSelections, model.RouteSelectionSummaryEntry{
			ProviderID: providerID,
			Count:      count,
		})
	}
	slices.SortFunc(providerSelections, func(a, b model.RouteSelectionSummaryEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		default:
			return 0
		}
	})

	profileUsage := make([]model.RouteProfileUsageEntry, 0, len(profileCounts))
	for profile, count := range profileCounts {
		profileUsage = append(profileUsage, model.RouteProfileUsageEntry{
			StrategyProfile: profile,
			Count:           count,
		})
	}
	slices.SortFunc(profileUsage, func(a, b model.RouteProfileUsageEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.StrategyProfile < b.StrategyProfile:
			return -1
		case a.StrategyProfile > b.StrategyProfile:
			return 1
		default:
			return 0
		}
	})

	return model.RouteControlSummaryData{
		Totals: model.RouteSummaryTotals{
			TotalRoutes:    len(s.tasks),
			TotalFallbacks: totalFallbacks,
		},
		RecentEvents:            recentEvents,
		RecentFallbacks:         recentFallbacks,
		TopRejections:           rejections,
		ProviderSelections:      providerSelections,
		ProfileUsage:            profileUsage,
		ProviderHealth:          s.collectProviderHealthSummaryLocked(),
		RecentOperationalEvents: operationalEvents,
		WindowStats:             s.collectRouteWindowStatsLocked(),
	}
}

func (s *Service) RegisterRuntime(req model.RuntimeRegistrationRequest) (model.RuntimeView, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if req.RuntimeID == "" || req.ProviderID == "" {
		return model.RuntimeView{}, model.Trace{}, fmt.Errorf("%w: runtime_id and provider_id are required", ErrInvalidRequest)
	}
	if _, ok := s.providers[req.ProviderID]; !ok {
		return model.RuntimeView{}, model.Trace{}, fmt.Errorf("%w: unknown provider %q", ErrInvalidRequest, req.ProviderID)
	}

	state := req.State
	if state == "" {
		state = "ready"
	}

	record, exists := s.runtimes[req.RuntimeID]
	if !exists {
		record = &runtimeRecord{
			View: model.RuntimeView{
				RuntimeID:      req.RuntimeID,
				ProviderID:     req.ProviderID,
				CooldownActive: false,
				Healthy:        state != "failed",
			},
			Stats: model.RuntimeStatsView{
				RuntimeID:   req.RuntimeID,
				ProviderID:  req.ProviderID,
				ErrorCounts: map[string]int{},
			},
		}
		s.runtimes[req.RuntimeID] = record
	}

	record.View.ProviderID = req.ProviderID
	record.View.State = state
	record.View.PID = req.PID
	record.View.Healthy = state != "failed"
	if req.StartedAt != "" {
		record.View.LastHeartbeatAt = req.StartedAt
	} else {
		record.View.LastHeartbeatAt = s.now()
	}
	if heartbeatAt, ok := parseTimestamp(record.View.LastHeartbeatAt); ok {
		record.lastHeartbeat = heartbeatAt
	} else {
		record.lastHeartbeat = time.Now().UTC()
	}
	record.heartbeatMissed = false
	s.syncRuntimeDerivedLocked(record)

	if !exists {
		s.appendEventLocked("runtime_registered", "info", fmt.Sprintf("runtime %s registered", req.RuntimeID), model.Trace{
			RuntimeID:  req.RuntimeID,
			ProviderID: req.ProviderID,
		}, map[string]any{
			"pid":   req.PID,
			"state": state,
		})
	}
	if state == "ready" {
		s.appendEventLocked("runtime_ready", "info", fmt.Sprintf("runtime %s ready", req.RuntimeID), model.Trace{
			RuntimeID:  req.RuntimeID,
			ProviderID: req.ProviderID,
		}, map[string]any{
			"pid":   req.PID,
			"state": state,
		})
	}

	return record.View, model.Trace{
		RuntimeID:  req.RuntimeID,
		ProviderID: req.ProviderID,
	}, nil
}

func (s *Service) RecordHeartbeat(req model.RuntimeHeartbeatRequest) (model.RuntimeView, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.runtimes[req.RuntimeID]
	if !ok {
		return model.RuntimeView{}, model.Trace{}, ErrNotFound
	}

	previousHealthy := record.View.Healthy
	previousHeartbeatMissed := record.heartbeatMissed
	record.View.Healthy = req.Healthy
	record.View.CooldownActive = req.Signals.CooldownActive
	record.Stats.RecentFailures = req.Signals.RecentFailures
	if req.Timestamp != "" {
		record.View.LastHeartbeatAt = req.Timestamp
	} else {
		record.View.LastHeartbeatAt = s.now()
	}
	if heartbeatAt, ok := parseTimestamp(record.View.LastHeartbeatAt); ok {
		record.lastHeartbeat = heartbeatAt
	} else {
		record.lastHeartbeat = time.Now().UTC()
	}
	record.heartbeatMissed = false
	if req.Signals.CooldownActive && record.cooldownUntil.IsZero() {
		record.cooldownUntil = time.Now().Add(s.cooldownDuration)
	}
	s.syncRuntimeDerivedLocked(record)
	if previousHeartbeatMissed && req.Healthy {
		s.appendEventLocked("runtime_heartbeat_restored", "info", fmt.Sprintf("runtime %s heartbeat restored", req.RuntimeID), model.Trace{
			RuntimeID:  req.RuntimeID,
			ProviderID: req.ProviderID,
		}, map[string]any{
			"recent_failures": req.Signals.RecentFailures,
		})
	}
	if !req.Healthy && (previousHealthy || previousHeartbeatMissed) {
		s.appendEventLocked("runtime_health_degraded", "warn", fmt.Sprintf("runtime %s reported unhealthy heartbeat", req.RuntimeID), model.Trace{
			RuntimeID:  req.RuntimeID,
			ProviderID: req.ProviderID,
		}, map[string]any{
			"recent_failures": req.Signals.RecentFailures,
			"cooldown_active": req.Signals.CooldownActive,
		})
	}

	return record.View, model.Trace{
		RuntimeID:  req.RuntimeID,
		ProviderID: req.ProviderID,
	}, nil
}

func (s *Service) RecordCompletion(req model.RuntimeCompletionRequest) (model.TaskStatusData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.tasks[req.TaskID]
	if !ok {
		return model.TaskStatusData{}, model.Trace{}, ErrNotFound
	}

	record.Data.Result = provider.NormalizeExecutionResult(record.Data.Route.SelectedProvider, req.RuntimeID, req.Result)
	record.Data.Error = req.Error
	if req.Success {
		record.Data.State = "succeeded"
	} else {
		record.Data.State = "failed"
		if record.Data.Error == nil {
			record.Data.Error = &model.NormalizedError{
				Category:          "execution",
				Code:              "execution_failed",
				Message:           "execution failed",
				Retriable:         true,
				CooldownCandidate: true,
			}
		}
	}
	if req.FinishedAt != "" {
		record.Data.Timing.FinishedAt = req.FinishedAt
	} else {
		record.Data.Timing.FinishedAt = s.now()
	}

	if req.Success {
		s.recordSuccessLocked(record.Data.Route.SelectedProvider, req.RuntimeID)
		s.appendEventLocked("task_succeeded", "info", fmt.Sprintf("task %s succeeded", req.TaskID), model.Trace{
			RequestID:  record.RequestID,
			TaskID:     req.TaskID,
			RuntimeID:  req.RuntimeID,
			ProviderID: record.Data.Route.SelectedProvider,
		}, map[string]any{
			"action":        routeAction(record.Data.Route),
			"resource_kind": routeResourceKind(record.Data.Route),
		})
	} else {
		s.recordFailureLocked(record.Data.Route.SelectedProvider, req.RuntimeID, record.Data.Error)
		if record.Data.Error != nil {
			eventKind := "task_failed"
			severity := "warn"
			if record.Data.Error.Code == "dispatch_failed" {
				eventKind = "dispatch_failed"
				severity = "error"
			}
			s.appendEventLocked(
				eventKind,
				severity,
				record.Data.Error.Message,
				model.Trace{
					RequestID:  record.RequestID,
					TaskID:     req.TaskID,
					RuntimeID:  req.RuntimeID,
					ProviderID: record.Data.Route.SelectedProvider,
				},
				map[string]any{
					"error_category": record.Data.Error.Category,
					"error_code":     record.Data.Error.Code,
				},
			)
		}
	}
	s.releaseRuntimeLocked(req.RuntimeID)

	return record.Data, model.Trace{
		RequestID:  record.RequestID,
		TaskID:     req.TaskID,
		RuntimeID:  req.RuntimeID,
		ProviderID: record.Data.Route.SelectedProvider,
	}, nil
}

func (s *Service) SetProviderEnabled(providerID string, enabled bool, reason string) (model.ProviderView, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	provider, ok := s.providers[providerID]
	if !ok {
		return model.ProviderView{}, ErrNotFound
	}
	provider.View.Enabled = enabled
	if enabled {
		provider.View.DisabledReason = ""
	} else {
		provider.View.DisabledReason = reason
	}
	s.syncProviderDerivedLocked(provider)
	if enabled {
		s.appendEventLocked("provider_enabled", "info", fmt.Sprintf("provider %s enabled", providerID), model.Trace{ProviderID: providerID}, nil)
	} else {
		s.appendEventLocked("provider_disabled", "warn", fmt.Sprintf("provider %s disabled", providerID), model.Trace{ProviderID: providerID}, map[string]any{"reason": reason})
	}
	return provider.View, nil
}

func (s *Service) ResetProviderCooldown(providerID string) (model.ProviderView, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	provider, ok := s.providers[providerID]
	if !ok {
		return model.ProviderView{}, ErrNotFound
	}
	provider.cooldownUntil = time.Time{}
	provider.Stats.RecentFailures = 0
	s.syncProviderDerivedLocked(provider)
	s.appendEventLocked("provider_cooldown_reset", "info", fmt.Sprintf("provider %s cooldown reset", providerID), model.Trace{ProviderID: providerID}, nil)
	return provider.View, nil
}

func (s *Service) releaseRuntimeLocked(runtimeID string) {
	runtime, ok := s.runtimes[runtimeID]
	if !ok {
		return
	}
	runtime.View.CurrentTaskID = ""
	runtime.View.LeaseID = ""
	if runtime.View.State != "failed" && runtime.View.State != "cooled" {
		runtime.View.State = "ready"
	}
	s.syncRuntimeDerivedLocked(runtime)
}

func (s *Service) MarkRuntimeStopped(runtimeID string, abnormal bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	runtime, ok := s.runtimes[runtimeID]
	if !ok {
		return
	}

	activeTaskID := runtime.View.CurrentTaskID
	runtime.View.Healthy = false
	runtime.View.CurrentTaskID = ""
	runtime.View.LeaseID = ""
	if abnormal {
		errView := &model.NormalizedError{
			Category:          "abnormal_exit",
			Code:              "child_abnormal_exit",
			Message:           "runtime exited unexpectedly",
			Retriable:         true,
			CooldownCandidate: true,
		}
		if activeTaskID != "" {
			if task, exists := s.tasks[activeTaskID]; exists {
				switch task.Data.State {
				case "succeeded", "failed", "timed_out", "cancelled":
				default:
					task.Data.State = "failed"
					task.Data.Error = errView
					task.Data.Timing.FinishedAt = s.now()
				}
			}
		}
		s.recordFailureLocked(runtime.View.ProviderID, runtimeID, errView)
		runtime.View.State = "failed"
		runtime.Stats.AbnormalExitCount++
		s.syncRuntimeDerivedLocked(runtime)
		s.appendEventLocked("runtime_abnormal_exit", "error", "runtime exited unexpectedly", model.Trace{
			TaskID:     activeTaskID,
			RuntimeID:  runtimeID,
			ProviderID: runtime.View.ProviderID,
		}, nil)
		return
	}

	runtime.View.State = "stopped"
	s.syncRuntimeDerivedLocked(runtime)
	s.appendEventLocked("runtime_shutdown", "info", "runtime stopped cleanly", model.Trace{
		TaskID:     activeTaskID,
		RuntimeID:  runtimeID,
		ProviderID: runtime.View.ProviderID,
	}, nil)
}

func (s *Service) recordSuccessLocked(providerID, runtimeID string) {
	now := time.Now()

	if provider, ok := s.providers[providerID]; ok {
		provider.Stats.TotalSuccesses++
		provider.Stats.RecentFailures = 0
		provider.lastSuccessAt = now
		provider.View.LastError = ""
		s.syncProviderDerivedLocked(provider)
	}

	if runtimeID == "" {
		return
	}
	if runtime, ok := s.runtimes[runtimeID]; ok {
		runtime.Stats.RecentFailures = 0
		runtime.lastSuccessAt = now
		runtime.View.LastError = ""
		if runtime.View.State != "failed" {
			runtime.View.State = "ready"
			runtime.View.Healthy = true
		}
		s.syncRuntimeDerivedLocked(runtime)
	}
}

func (s *Service) recordFailureLocked(providerID, runtimeID string, errView *model.NormalizedError) {
	if errView == nil {
		errView = &model.NormalizedError{
			Category:          "unknown",
			Code:              "unknown_error",
			Message:           "unknown error",
			CooldownCandidate: true,
		}
	}
	now := time.Now()
	category := strings.TrimSpace(errView.Category)
	if category == "" {
		category = "unknown"
	}

	if provider, ok := s.providers[providerID]; ok {
		provider.View.FailureCount++
		provider.View.LastError = errView.Message
		provider.lastFailureAt = now
		provider.Stats.TotalFailures++
		provider.Stats.RecentFailures++
		ensureMap(&provider.Stats.ErrorCounts)
		provider.Stats.ErrorCounts[category]++
		provider.Stats.LastError = errView.Message
		s.applyCooldownToProviderLocked(provider, errView)
		s.syncProviderDerivedLocked(provider)
	}

	if runtimeID == "" {
		return
	}
	if runtime, ok := s.runtimes[runtimeID]; ok {
		runtime.View.FailureCount++
		runtime.View.LastError = errView.Message
		runtime.lastFailureAt = now
		runtime.Stats.RecentFailures++
		ensureMap(&runtime.Stats.ErrorCounts)
		runtime.Stats.ErrorCounts[category]++
		runtime.Stats.LastError = errView.Message
		if shouldInvalidateRuntimeForError(errView) {
			s.applyCooldownToRuntimeLocked(runtime, errView)
			runtime.View.State = "failed"
			runtime.View.Healthy = false
		}
		s.syncRuntimeDerivedLocked(runtime)
	}
}

func shouldInvalidateRuntimeForError(errView *model.NormalizedError) bool {
	if errView == nil {
		return true
	}
	category := strings.TrimSpace(strings.ToLower(errView.Category))
	code := strings.TrimSpace(strings.ToLower(errView.Code))
	switch category {
	case "abnormal_exit", "startup", "transport":
		return true
	case "blocked", "flow_error", "auth_error", "otp_timeout", "proxy_error":
		return false
	}
	switch code {
	case "dispatch_failed", "child_abnormal_exit", "spawn_failed", "ready_timeout", "transport_error", "devtools_transport_error":
		return true
	case "action_failed", "action_blocked", "callback", "otp_error", "network":
		return false
	}
	return errView.CooldownCandidate
}

func (s *Service) applyCooldownToProviderLocked(provider *providerRecord, errView *model.NormalizedError) {
	if provider.Stats.RecentFailures < s.failureThreshold {
		return
	}
	if !errView.CooldownCandidate {
		return
	}
	wasActive := !provider.cooldownUntil.IsZero() && time.Now().Before(provider.cooldownUntil)
	provider.cooldownUntil = time.Now().Add(s.cooldownDuration)
	provider.Stats.CooldownCount++
	if !wasActive {
		s.appendEventLocked("provider_cooled", "warn", fmt.Sprintf("provider %s entered cooldown", provider.View.ProviderID), model.Trace{
			ProviderID: provider.View.ProviderID,
		}, map[string]any{
			"error_code": errView.Code,
			"category":   errView.Category,
		})
	}
}

func (s *Service) applyCooldownToRuntimeLocked(runtime *runtimeRecord, errView *model.NormalizedError) {
	if runtime.Stats.RecentFailures < s.failureThreshold && errView.Category != "abnormal_exit" {
		return
	}
	if !errView.CooldownCandidate {
		return
	}
	wasActive := !runtime.cooldownUntil.IsZero() && time.Now().Before(runtime.cooldownUntil)
	runtime.cooldownUntil = time.Now().Add(s.cooldownDuration)
	runtime.View.State = "cooled"
	if !wasActive {
		s.appendEventLocked("runtime_cooled", "warn", fmt.Sprintf("runtime %s entered cooldown", runtime.View.RuntimeID), model.Trace{
			RuntimeID:  runtime.View.RuntimeID,
			ProviderID: runtime.View.ProviderID,
		}, map[string]any{
			"error_code": errView.Code,
			"category":   errView.Category,
		})
	}
}

func (s *Service) refreshCooldownsLocked() {
	now := time.Now()
	for _, provider := range s.providers {
		if !provider.cooldownUntil.IsZero() && !now.Before(provider.cooldownUntil) {
			provider.cooldownUntil = time.Time{}
			provider.Stats.RecentFailures = 0
		}
		s.syncProviderDerivedLocked(provider)
	}
	for _, runtime := range s.runtimes {
		if !runtime.lastHeartbeat.IsZero() && !runtime.heartbeatMissed {
			if (runtime.View.State == "ready" || runtime.View.State == "busy") && now.Sub(runtime.lastHeartbeat) > s.heartbeatTimeout {
				runtime.heartbeatMissed = true
				runtime.View.Healthy = false
				s.appendEventLocked("runtime_heartbeat_missed", "warn", fmt.Sprintf("runtime %s heartbeat overdue", runtime.View.RuntimeID), model.Trace{
					RuntimeID:  runtime.View.RuntimeID,
					ProviderID: runtime.View.ProviderID,
					TaskID:     runtime.View.CurrentTaskID,
				}, map[string]any{
					"last_heartbeat_at": runtime.View.LastHeartbeatAt,
					"overdue_ms":        now.Sub(runtime.lastHeartbeat).Milliseconds(),
				})
			}
		}
		if !runtime.cooldownUntil.IsZero() && !now.Before(runtime.cooldownUntil) {
			runtime.cooldownUntil = time.Time{}
			runtime.Stats.RecentFailures = 0
			if runtime.View.State == "cooled" && runtime.View.Healthy {
				runtime.View.State = "ready"
			}
		}
		s.syncRuntimeDerivedLocked(runtime)
	}
}

func (s *Service) syncProviderDerivedLocked(provider *providerRecord) {
	provider.View.CooldownActive = !provider.cooldownUntil.IsZero() && time.Now().Before(provider.cooldownUntil)
	if provider.View.CooldownActive {
		provider.View.CooldownUntil = provider.cooldownUntil.UTC().Format(time.RFC3339)
		provider.Stats.CooldownUntil = provider.View.CooldownUntil
	} else {
		provider.View.CooldownUntil = ""
		provider.Stats.CooldownUntil = ""
	}

	if !provider.lastFailureAt.IsZero() {
		t := provider.lastFailureAt.UTC().Format(time.RFC3339)
		provider.View.LastFailureAt = t
		provider.Stats.LastFailureAt = t
	}
	if !provider.lastSuccessAt.IsZero() {
		t := provider.lastSuccessAt.UTC().Format(time.RFC3339)
		provider.View.LastSuccessAt = t
		provider.Stats.LastSuccessAt = t
	}

	provider.Stats.LastError = provider.View.LastError
	provider.View.StatsSummary.TotalRequests = provider.Stats.TotalRequests
	provider.View.StatsSummary.TotalFailures = provider.Stats.TotalFailures
	provider.View.StatsSummary.RecentFailures = provider.Stats.RecentFailures
	provider.View.StatsSummary.CooldownUntil = provider.View.CooldownUntil
	provider.View.StatsSummary.LastError = provider.View.LastError
	provider.View.Healthy = provider.View.Enabled && !provider.View.CooldownActive
}

func (s *Service) syncRuntimeDerivedLocked(runtime *runtimeRecord) {
	runtime.View.CooldownActive = !runtime.cooldownUntil.IsZero() && time.Now().Before(runtime.cooldownUntil)
	if runtime.View.CooldownActive {
		runtime.View.CooldownUntil = runtime.cooldownUntil.UTC().Format(time.RFC3339)
		runtime.Stats.CooldownUntil = runtime.View.CooldownUntil
		if runtime.View.State != "busy" {
			runtime.View.State = "cooled"
		}
	} else {
		runtime.View.CooldownUntil = ""
		runtime.Stats.CooldownUntil = ""
	}

	if !runtime.lastFailureAt.IsZero() {
		t := runtime.lastFailureAt.UTC().Format(time.RFC3339)
		runtime.View.LastFailureAt = t
		runtime.Stats.LastFailureAt = t
	}
	if !runtime.lastSuccessAt.IsZero() {
		t := runtime.lastSuccessAt.UTC().Format(time.RFC3339)
		runtime.View.LastSuccessAt = t
		runtime.Stats.LastSuccessAt = t
	}

	runtime.Stats.LastError = runtime.View.LastError
}

func ensureMap(target *map[string]int) {
	if *target == nil {
		*target = make(map[string]int)
	}
}

func directReason(action, resourceKind string) string {
	action = coalesceAction(action)
	return fmt.Sprintf("direct/specified provider requested for action=%s class=%s resource_kind=%s", action, provider.ClassifyAction(action), coalesceResourceKind(resourceKind))
}

func coalesceAction(action string) string {
	if strings.TrimSpace(action) == "" {
		return "generic"
	}
	return action
}

func coalesceResourceKind(kind string) string {
	if strings.TrimSpace(kind) == "" {
		return "auto"
	}
	return kind
}

func coalesceRuntimeReuse(value string) string {
	if strings.TrimSpace(value) == "" {
		return "default"
	}
	return value
}

func routeAction(route model.RouteDecisionView) string {
	if route.Diagnostics != nil && strings.TrimSpace(route.Diagnostics.Action) != "" {
		return route.Diagnostics.Action
	}
	return "generic"
}

func routeResourceKind(route model.RouteDecisionView) string {
	if route.Diagnostics != nil && strings.TrimSpace(route.Diagnostics.ResourceKind) != "" {
		return route.Diagnostics.ResourceKind
	}
	return "auto"
}

func buildRouteDiagnostics(action, resourceKind, runtimeReuse, profile string, profileRank, score int, breakdown provider.StrategyScoreBreakdown, readyRuntimes, recentFailures, totalFailures int) *model.RouteDiagnosticsView {
	return &model.RouteDiagnosticsView{
		Action:         coalesceAction(action),
		ActionClass:    string(provider.ClassifyAction(action)),
		ResourceKind:   coalesceResourceKind(resourceKind),
		RuntimeReuse:   coalesceRuntimeReuse(runtimeReuse),
		Profile:        profile,
		ProfileRank:    profileRank,
		Score:          score,
		ReadyRuntimes:  readyRuntimes,
		RecentFailures: recentFailures,
		TotalFailures:  totalFailures,
		Breakdown:      mapRouteScoreBreakdown(breakdown),
	}
}

func mapRouteScoreBreakdown(breakdown provider.StrategyScoreBreakdown) *model.RouteScoreBreakdownView {
	if breakdown == (provider.StrategyScoreBreakdown{}) {
		return nil
	}
	return &model.RouteScoreBreakdownView{
		BaseScore:            breakdown.BaseScore,
		ProfileBonus:         breakdown.ProfileBonus,
		ReuseBonus:           breakdown.ReuseBonus,
		ReadyRuntimeBonus:    breakdown.ReadyRuntimeBonus,
		RecentFailurePenalty: breakdown.RecentFailurePenalty,
		TotalFailurePenalty:  breakdown.TotalFailurePenalty,
	}
}

func (s *Service) collectRouteHistoryLocked(limit int, fallbackOnly bool) []model.RouteHistoryEntry {
	entries := make([]model.RouteHistoryEntry, 0, len(s.tasks))
	for _, task := range s.tasks {
		if fallbackOnly && !task.Data.Route.FallbackUsed {
			continue
		}
		entries = append(entries, model.RouteHistoryEntry{
			TaskID:              task.Data.TaskID,
			RequestID:           task.RequestID,
			State:               task.Data.State,
			Mode:                task.Data.Mode,
			StrategyProfile:     task.Data.Route.StrategyProfile,
			SelectedProvider:    task.Data.Route.SelectedProvider,
			SelectedRuntimeID:   task.Data.Route.SelectedRuntimeID,
			FallbackUsed:        task.Data.Route.FallbackUsed,
			StrategyReason:      task.Data.Route.StrategyReason,
			ConsideredProviders: append([]string(nil), task.Data.Route.ConsideredProviders...),
			RejectedProviders:   append([]string(nil), task.Data.Route.RejectedProviders...),
			Diagnostics:         task.Data.Route.Diagnostics,
			Candidates:          append([]model.RouteCandidateView(nil), task.Data.Route.Candidates...),
			QueuedAt:            task.Data.Timing.QueuedAt,
			StartedAt:           task.Data.Timing.StartedAt,
			FinishedAt:          task.Data.Timing.FinishedAt,
			Error:               task.Data.Error,
		})
	}

	slices.SortFunc(entries, func(a, b model.RouteHistoryEntry) int {
		switch {
		case a.QueuedAt > b.QueuedAt:
			return -1
		case a.QueuedAt < b.QueuedAt:
			return 1
		case a.TaskID > b.TaskID:
			return -1
		case a.TaskID < b.TaskID:
			return 1
		default:
			return 0
		}
	})

	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries
}

func (s *Service) collectRouteRejectionSummaryLocked(limit int) []model.RouteRejectionSummaryEntry {
	type summaryKey struct {
		ProviderID string
		Reason     string
	}

	counts := make(map[summaryKey]int)
	for _, task := range s.tasks {
		for _, candidate := range task.Data.Route.Candidates {
			if candidate.Eligible || strings.TrimSpace(candidate.RejectionReason) == "" {
				continue
			}
			key := summaryKey{
				ProviderID: candidate.ProviderID,
				Reason:     candidate.RejectionReason,
			}
			counts[key]++
		}
	}

	entries := make([]model.RouteRejectionSummaryEntry, 0, len(counts))
	for key, count := range counts {
		entries = append(entries, model.RouteRejectionSummaryEntry{
			ProviderID:      key.ProviderID,
			RejectionReason: key.Reason,
			Count:           count,
		})
	}

	slices.SortFunc(entries, func(a, b model.RouteRejectionSummaryEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		case a.RejectionReason < b.RejectionReason:
			return -1
		case a.RejectionReason > b.RejectionReason:
			return 1
		default:
			return 0
		}
	})

	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries
}

func (s *Service) collectRouteInsightsLocked() model.RouteInsightsData {
	return s.collectRouteInsightsSinceLocked(nil)
}

func (s *Service) collectRouteInsightsSinceLocked(since *time.Time) model.RouteInsightsData {
	providerInsights := make(map[string]*model.RouteProviderInsight)
	profileInsights := make(map[string]*model.RouteProfileInsight)

	ensureProviderInsight := func(providerID string) *model.RouteProviderInsight {
		insight, ok := providerInsights[providerID]
		if !ok {
			insight = &model.RouteProviderInsight{
				ProviderID:      providerID,
				RejectionCounts: map[string]int{},
				EventCounts:     map[string]int{},
			}
			providerInsights[providerID] = insight
		}
		return insight
	}

	ensureProfileInsight := func(profile string) *model.RouteProfileInsight {
		insight, ok := profileInsights[profile]
		if !ok {
			insight = &model.RouteProfileInsight{
				StrategyProfile:    profile,
				ProviderSelections: map[string]int{},
			}
			profileInsights[profile] = insight
		}
		return insight
	}

	for _, task := range s.tasks {
		if since != nil {
			queuedAt, ok := parseTimestamp(task.Data.Timing.QueuedAt)
			if !ok || queuedAt.Before(*since) {
				continue
			}
		}

		if providerID := strings.TrimSpace(task.Data.Route.SelectedProvider); providerID != "" {
			insight := ensureProviderInsight(providerID)
			insight.SelectedCount++
			if task.Data.Route.FallbackUsed {
				insight.FallbackSelectedCount++
			}
			switch task.Data.State {
			case "succeeded":
				insight.SucceededCount++
			case "failed":
				insight.FailedCount++
			}
			if task.Data.Timing.QueuedAt > insight.LastSelectedAt {
				insight.LastSelectedAt = task.Data.Timing.QueuedAt
			}
		}

		for _, candidate := range task.Data.Route.Candidates {
			if candidate.Eligible || strings.TrimSpace(candidate.RejectionReason) == "" {
				continue
			}
			insight := ensureProviderInsight(candidate.ProviderID)
			insight.RejectionCounts[candidate.RejectionReason]++
		}

		if profile := strings.TrimSpace(task.Data.Route.StrategyProfile); profile != "" {
			insight := ensureProfileInsight(profile)
			insight.TotalRoutes++
			if task.Data.Route.FallbackUsed {
				insight.FallbackRoutes++
			}
			switch task.Data.State {
			case "succeeded":
				insight.SucceededCount++
			case "failed":
				insight.FailedCount++
			}
			if providerID := strings.TrimSpace(task.Data.Route.SelectedProvider); providerID != "" {
				insight.ProviderSelections[providerID]++
			}
		}
	}

	for _, event := range s.events {
		if since != nil {
			occurredAt, ok := parseTimestamp(event.OccurredAt)
			if !ok || occurredAt.Before(*since) {
				continue
			}
		}
		if providerID := strings.TrimSpace(event.ProviderID); providerID != "" {
			insight := ensureProviderInsight(providerID)
			insight.EventCounts[event.Kind]++
		}
	}

	providers := make([]model.RouteProviderInsight, 0, len(providerInsights))
	for _, insight := range providerInsights {
		providers = append(providers, *insight)
	}
	slices.SortFunc(providers, func(a, b model.RouteProviderInsight) int {
		switch {
		case a.SelectedCount > b.SelectedCount:
			return -1
		case a.SelectedCount < b.SelectedCount:
			return 1
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		default:
			return 0
		}
	})

	profiles := make([]model.RouteProfileInsight, 0, len(profileInsights))
	for _, insight := range profileInsights {
		profiles = append(profiles, *insight)
	}
	slices.SortFunc(profiles, func(a, b model.RouteProfileInsight) int {
		switch {
		case a.TotalRoutes > b.TotalRoutes:
			return -1
		case a.TotalRoutes < b.TotalRoutes:
			return 1
		case a.StrategyProfile < b.StrategyProfile:
			return -1
		case a.StrategyProfile > b.StrategyProfile:
			return 1
		default:
			return 0
		}
	})

	return model.RouteInsightsData{
		Providers: providers,
		Profiles:  profiles,
	}
}

func (s *Service) collectRouteWindowInsightsLocked() []model.RouteInsightsWindow {
	type windowDef struct {
		name     string
		duration time.Duration
	}

	defs := []windowDef{
		{name: "10m", duration: 10 * time.Minute},
		{name: "1h", duration: 1 * time.Hour},
		{name: "24h", duration: 24 * time.Hour},
	}

	now := time.Now().UTC()
	results := make([]model.RouteInsightsWindow, 0, len(defs))
	for _, def := range defs {
		since := now.Add(-def.duration)
		insights := s.collectRouteInsightsSinceLocked(&since)
		results = append(results, model.RouteInsightsWindow{
			Window:    def.name,
			Since:     since.Format(time.RFC3339),
			Providers: insights.Providers,
			Profiles:  insights.Profiles,
		})
	}

	return results
}

func (s *Service) collectRouteWindowStatsLocked() []model.RouteWindowSummary {
	type windowDef struct {
		name     string
		duration time.Duration
	}

	defs := []windowDef{
		{name: "10m", duration: 10 * time.Minute},
		{name: "1h", duration: 1 * time.Hour},
		{name: "24h", duration: 24 * time.Hour},
	}

	now := time.Now().UTC()
	results := make([]model.RouteWindowSummary, 0, len(defs))

	for _, def := range defs {
		since := now.Add(-def.duration)

		providerCounts := make(map[string]int)
		profileCounts := make(map[string]int)
		rejectionCounts := make(map[string]int)
		eventCounts := make(map[string]int)

		summary := model.RouteWindowSummary{
			Window: def.name,
			Since:  since.Format(time.RFC3339),
		}

		for _, task := range s.tasks {
			queuedAt, ok := parseTimestamp(task.Data.Timing.QueuedAt)
			if !ok || queuedAt.Before(since) {
				continue
			}

			summary.TotalRoutes++
			if task.Data.Route.FallbackUsed {
				summary.TotalFallbacks++
			}
			if task.Data.State == "failed" {
				summary.TotalFailures++
			}
			if providerID := strings.TrimSpace(task.Data.Route.SelectedProvider); providerID != "" {
				providerCounts[providerID]++
			}
			if profile := strings.TrimSpace(task.Data.Route.StrategyProfile); profile != "" {
				profileCounts[profile]++
			}
			for _, candidate := range task.Data.Route.Candidates {
				if candidate.Eligible || strings.TrimSpace(candidate.RejectionReason) == "" {
					continue
				}
				key := candidate.ProviderID + "|" + candidate.RejectionReason
				rejectionCounts[key]++
			}
		}

		for _, event := range s.events {
			occurredAt, ok := parseTimestamp(event.OccurredAt)
			if !ok || occurredAt.Before(since) {
				continue
			}
			eventCounts[event.Kind]++
		}

		summary.ProviderSelections = mapProviderSelectionCounts(providerCounts)
		summary.ProfileUsage = mapProfileUsageCounts(profileCounts)
		summary.Rejections = mapRejectionCounts(rejectionCounts)
		if len(eventCounts) > 0 {
			summary.EventCounts = eventCounts
		}

		results = append(results, summary)
	}

	return results
}

func (s *Service) collectProviderHealthSummaryLocked() []model.ProviderHealthSummaryEntry {
	type windowDef struct {
		name     string
		duration time.Duration
	}

	type providerWindowAccumulator struct {
		TaskSucceededCount     int
		TaskFailedCount        int
		TaskCancelledCount     int
		SpawnStartedCount      int
		StartupFailedCount     int
		ReadyTimeoutCount      int
		HeartbeatMissedCount   int
		HeartbeatRestoredCount int
		HealthDegradedCount    int
	}

	type providerAccumulator struct {
		entry   model.ProviderHealthSummaryEntry
		windows map[string]*providerWindowAccumulator
	}

	windowDefs := []windowDef{
		{name: "10m", duration: 10 * time.Minute},
		{name: "1h", duration: 1 * time.Hour},
		{name: "24h", duration: 24 * time.Hour},
	}

	now := time.Now().UTC()
	accumulators := make(map[string]*providerAccumulator, len(s.order))
	for _, providerID := range s.order {
		providerRecord, ok := s.providers[providerID]
		if !ok {
			continue
		}
		acc := &providerAccumulator{
			entry: model.ProviderHealthSummaryEntry{
				ProviderID:     providerID,
				Enabled:        providerRecord.View.Enabled,
				Healthy:        providerRecord.View.Healthy,
				CooldownActive: providerRecord.View.CooldownActive,
				FailureCount:   providerRecord.View.FailureCount,
				LastError:      providerRecord.View.LastError,
				LastFailureAt:  providerRecord.View.LastFailureAt,
				LastSuccessAt:  providerRecord.View.LastSuccessAt,
			},
			windows: make(map[string]*providerWindowAccumulator, len(windowDefs)),
		}
		for _, def := range windowDefs {
			acc.windows[def.name] = &providerWindowAccumulator{}
		}
		accumulators[providerID] = acc
	}

	taskTimestamp := func(task *taskRecord) (time.Time, bool) {
		if finishedAt, ok := parseTimestamp(task.Data.Timing.FinishedAt); ok {
			return finishedAt, true
		}
		return parseTimestamp(task.Data.Timing.QueuedAt)
	}

	for _, task := range s.tasks {
		providerID := strings.TrimSpace(task.Data.Route.SelectedProvider)
		if providerID == "" {
			continue
		}
		acc, ok := accumulators[providerID]
		if !ok {
			continue
		}

		switch task.Data.State {
		case "succeeded":
			acc.entry.TotalTaskSucceededCount++
		case "failed":
			acc.entry.TotalTaskFailedCount++
		case "cancelled":
			acc.entry.TotalTaskCancelledCount++
		}

		timestamp, ok := taskTimestamp(task)
		if !ok {
			continue
		}
		for _, def := range windowDefs {
			if timestamp.Before(now.Add(-def.duration)) {
				continue
			}
			window := acc.windows[def.name]
			switch task.Data.State {
			case "succeeded":
				window.TaskSucceededCount++
			case "failed":
				window.TaskFailedCount++
			case "cancelled":
				window.TaskCancelledCount++
			}
		}
	}

	incrementEventCounter := func(window *providerWindowAccumulator, kind string) {
		switch kind {
		case "runtime_spawn_started":
			window.SpawnStartedCount++
		case "runtime_startup_failed":
			window.StartupFailedCount++
		case "runtime_ready_timeout":
			window.ReadyTimeoutCount++
		case "runtime_heartbeat_missed":
			window.HeartbeatMissedCount++
		case "runtime_heartbeat_restored":
			window.HeartbeatRestoredCount++
		case "runtime_health_degraded":
			window.HealthDegradedCount++
		}
	}

	for _, event := range s.events {
		providerID := strings.TrimSpace(event.ProviderID)
		if providerID == "" {
			continue
		}
		acc, ok := accumulators[providerID]
		if !ok {
			continue
		}

		switch event.Kind {
		case "runtime_spawn_started":
			acc.entry.TotalSpawnStartedCount++
		case "runtime_startup_failed":
			acc.entry.TotalStartupFailedCount++
		case "runtime_ready_timeout":
			acc.entry.TotalReadyTimeoutCount++
		case "runtime_heartbeat_missed":
			acc.entry.TotalHeartbeatMissedCount++
		case "runtime_heartbeat_restored":
			acc.entry.TotalHeartbeatRestoredCount++
		case "runtime_health_degraded":
			acc.entry.TotalHealthDegradedCount++
		}

		occurredAt, ok := parseTimestamp(event.OccurredAt)
		if !ok {
			continue
		}
		for _, def := range windowDefs {
			if occurredAt.Before(now.Add(-def.duration)) {
				continue
			}
			incrementEventCounter(acc.windows[def.name], event.Kind)
		}
	}

	entries := make([]model.ProviderHealthSummaryEntry, 0, len(accumulators))
	for _, providerID := range s.order {
		acc, ok := accumulators[providerID]
		if !ok {
			continue
		}
		windows := make([]model.ProviderHealthWindowSummary, 0, len(windowDefs))
		for _, def := range windowDefs {
			windowAcc := acc.windows[def.name]
			since := now.Add(-def.duration)
			completions := windowAcc.TaskSucceededCount + windowAcc.TaskFailedCount
			windows = append(windows, model.ProviderHealthWindowSummary{
				Window:                 def.name,
				Since:                  since.Format(time.RFC3339),
				TaskSucceededCount:     windowAcc.TaskSucceededCount,
				TaskFailedCount:        windowAcc.TaskFailedCount,
				TaskCancelledCount:     windowAcc.TaskCancelledCount,
				SpawnStartedCount:      windowAcc.SpawnStartedCount,
				StartupFailedCount:     windowAcc.StartupFailedCount,
				ReadyTimeoutCount:      windowAcc.ReadyTimeoutCount,
				HeartbeatMissedCount:   windowAcc.HeartbeatMissedCount,
				HeartbeatRestoredCount: windowAcc.HeartbeatRestoredCount,
				HealthDegradedCount:    windowAcc.HealthDegradedCount,
				SuccessRate:            ratio(windowAcc.TaskSucceededCount, completions),
				FailureRate:            ratio(windowAcc.TaskFailedCount, completions),
			})
		}
		acc.entry.Windows = windows
		entries = append(entries, acc.entry)
	}

	slices.SortFunc(entries, func(a, b model.ProviderHealthSummaryEntry) int {
		switch {
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		default:
			return 0
		}
	})

	return entries
}

func (s *Service) collectOperationalEventsLocked(limit int) []model.OperationalEvent {
	if len(s.events) == 0 {
		return nil
	}
	if limit <= 0 || limit > len(s.events) {
		limit = len(s.events)
	}

	out := make([]model.OperationalEvent, 0, limit)
	for i := len(s.events) - 1; i >= 0 && len(out) < limit; i-- {
		out = append(out, s.events[i])
	}
	return out
}

func (s *Service) appendEventLocked(kind, severity, message string, trace model.Trace, details map[string]any) {
	event := model.OperationalEvent{
		EventID:    s.nextID("evt"),
		Kind:       kind,
		Severity:   severity,
		ProviderID: trace.ProviderID,
		RuntimeID:  trace.RuntimeID,
		TaskID:     trace.TaskID,
		RequestID:  trace.RequestID,
		OccurredAt: s.now(),
		Message:    message,
	}
	if len(details) > 0 {
		event.Details = details
	}
	s.events = append(s.events, event)
	if s.eventLimit > 0 && len(s.events) > s.eventLimit {
		s.events = s.events[len(s.events)-s.eventLimit:]
	}
}

func parseTimestamp(value string) (time.Time, bool) {
	if strings.TrimSpace(value) == "" {
		return time.Time{}, false
	}
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return time.Time{}, false
	}
	return parsed.UTC(), true
}

func mapProviderSelectionCounts(counts map[string]int) []model.RouteSelectionSummaryEntry {
	out := make([]model.RouteSelectionSummaryEntry, 0, len(counts))
	for providerID, count := range counts {
		out = append(out, model.RouteSelectionSummaryEntry{
			ProviderID: providerID,
			Count:      count,
		})
	}
	slices.SortFunc(out, func(a, b model.RouteSelectionSummaryEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		default:
			return 0
		}
	})
	return out
}

func mapProfileUsageCounts(counts map[string]int) []model.RouteProfileUsageEntry {
	out := make([]model.RouteProfileUsageEntry, 0, len(counts))
	for profile, count := range counts {
		out = append(out, model.RouteProfileUsageEntry{
			StrategyProfile: profile,
			Count:           count,
		})
	}
	slices.SortFunc(out, func(a, b model.RouteProfileUsageEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.StrategyProfile < b.StrategyProfile:
			return -1
		case a.StrategyProfile > b.StrategyProfile:
			return 1
		default:
			return 0
		}
	})
	return out
}

func mapRejectionCounts(counts map[string]int) []model.RouteRejectionSummaryEntry {
	out := make([]model.RouteRejectionSummaryEntry, 0, len(counts))
	for key, count := range counts {
		parts := strings.SplitN(key, "|", 2)
		if len(parts) != 2 {
			continue
		}
		out = append(out, model.RouteRejectionSummaryEntry{
			ProviderID:      parts[0],
			RejectionReason: parts[1],
			Count:           count,
		})
	}
	slices.SortFunc(out, func(a, b model.RouteRejectionSummaryEntry) int {
		switch {
		case a.Count > b.Count:
			return -1
		case a.Count < b.Count:
			return 1
		case a.ProviderID < b.ProviderID:
			return -1
		case a.ProviderID > b.ProviderID:
			return 1
		case a.RejectionReason < b.RejectionReason:
			return -1
		case a.RejectionReason > b.RejectionReason:
			return 1
		default:
			return 0
		}
	})
	return out
}

func ratio(numerator, denominator int) float64 {
	if denominator <= 0 {
		return 0
	}
	return math.Round((float64(numerator)/float64(denominator))*10000) / 10000
}

func rejectionReasonForCapabilities(supportsMode, supportsAction bool) string {
	switch {
	case !supportsMode && !supportsAction:
		return "unsupported_mode_and_action"
	case !supportsMode:
		return "unsupported_mode"
	case !supportsAction:
		return "unsupported_action"
	default:
		return ""
	}
}

func rejectionReasonForAvailability(enabled, cooldownActive bool) string {
	switch {
	case !enabled && cooldownActive:
		return "disabled_and_cooled"
	case !enabled:
		return "disabled"
	case cooldownActive:
		return "cooldown_active"
	default:
		return ""
	}
}
