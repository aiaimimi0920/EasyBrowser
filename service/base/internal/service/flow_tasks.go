package service

import (
	"fmt"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/provider"
)

type FlowTaskSpec struct {
	RequestID    string
	Mode         string
	ProviderID   string
	RuntimeID    string
	Action       string
	ResourceKind string
	Message      string
}

func (s *Service) CreateFlowTask(spec FlowTaskSpec) (model.ExecuteAcceptedData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	mode, err := s.normalizeMode(spec.Mode)
	if err != nil {
		return model.ExecuteAcceptedData{}, model.Trace{}, err
	}

	taskID := s.nextID("task")
	requestID := spec.RequestID
	if requestID == "" {
		requestID = s.nextID("req")
	}

	route := model.RouteDecisionView{
		Mode:              mode,
		SelectedProvider:  spec.ProviderID,
		SelectedRuntimeID: spec.RuntimeID,
		StrategyReason:    firstNonEmpty(spec.Message, "browser session flow execution"),
		Diagnostics:       buildRouteDiagnostics(spec.Action, spec.ResourceKind, "", "", 0, 0, provider.StrategyScoreBreakdown{}, 0, 0, 0),
	}
	record := &taskRecord{
		RequestID: requestID,
		Data: model.TaskStatusData{
			TaskID: taskID,
			State:  "running",
			Mode:   mode,
			Route:  route,
			Timing: model.TaskTiming{
				QueuedAt:  s.now(),
				StartedAt: s.now(),
			},
		},
	}
	s.tasks[taskID] = record
	s.appendEventLocked(
		"flow_task_started",
		"info",
		firstNonEmpty(spec.Message, fmt.Sprintf("flow task %s started", taskID)),
		model.Trace{
			RequestID:  requestID,
			TaskID:     taskID,
			RuntimeID:  spec.RuntimeID,
			ProviderID: spec.ProviderID,
		},
		map[string]any{
			"action":        coalesceAction(spec.Action),
			"resource_kind": coalesceResourceKind(spec.ResourceKind),
		},
	)

	return model.ExecuteAcceptedData{
			TaskID: taskID,
			State:  record.Data.State,
			Route: model.ExecuteRouteView{
				Mode:             mode,
				SelectedProvider: spec.ProviderID,
				RuntimeID:        spec.RuntimeID,
				Diagnostics:      route.Diagnostics,
			},
		},
		model.Trace{
			RequestID:  requestID,
			TaskID:     taskID,
			RuntimeID:  spec.RuntimeID,
			ProviderID: spec.ProviderID,
		},
		nil
}

func (s *Service) CompleteFlowTask(taskID string, result map[string]any, err *model.NormalizedError) (model.TaskStatusData, model.Trace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.tasks[taskID]
	if !ok {
		return model.TaskStatusData{}, model.Trace{}, ErrNotFound
	}

	record.Data.Result = result
	record.Data.Error = err
	if err == nil {
		record.Data.State = "succeeded"
	} else {
		record.Data.State = "failed"
	}
	record.Data.Timing.FinishedAt = s.now()

	trace := model.Trace{
		RequestID:  record.RequestID,
		TaskID:     record.Data.TaskID,
		RuntimeID:  record.Data.Route.SelectedRuntimeID,
		ProviderID: record.Data.Route.SelectedProvider,
	}
	if err == nil {
		s.appendEventLocked(
			"flow_task_succeeded",
			"info",
			fmt.Sprintf("flow task %s succeeded", taskID),
			trace,
			map[string]any{
				"action":        routeAction(record.Data.Route),
				"resource_kind": routeResourceKind(record.Data.Route),
			},
		)
	} else {
		s.appendEventLocked(
			"flow_task_failed",
			"warn",
			err.Message,
			trace,
			map[string]any{
				"action":         routeAction(record.Data.Route),
				"resource_kind":  routeResourceKind(record.Data.Route),
				"error_category": err.Category,
				"error_code":     err.Code,
			},
		)
	}
	return record.Data, trace, nil
}

func (s *Service) RecordFlowEvent(kind, severity, message string, trace model.Trace, details map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.appendEventLocked(kind, severity, message, trace, details)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
