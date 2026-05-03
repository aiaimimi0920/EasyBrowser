package service

import (
	"testing"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
)

func TestSubmitTaskDirectModeRequiresProvider(t *testing.T) {
	svc := New()

	_, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Operation: model.OperationSpec{
			Kind: "task",
		},
	})
	if err == nil {
		t.Fatal("expected validation error for missing direct provider")
	}
}

func TestSubmitTaskStrategyModeAcceptsRequest(t *testing.T) {
	svc := New()

	data, trace, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.TaskID == "" {
		t.Fatal("expected task id")
	}
	if trace.TaskID == "" {
		t.Fatal("expected trace task id")
	}
	if data.Route.SelectedProvider == "" {
		t.Fatal("expected selected provider")
	}
}

func TestSubmitTaskSpecifiedModeAliasAccepted(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "specified",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.Mode != "direct" {
		t.Fatalf("expected canonical mode direct, got %q", data.Route.Mode)
	}
}

func TestStrategySkipsCooledProvider(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-test",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	for i := 0; i < 3; i++ {
		accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
			Mode: "direct",
			Target: model.TargetSpec{
				Provider: "chrome",
			},
			Operation: model.OperationSpec{Kind: "task"},
		})
		if err != nil {
			t.Fatalf("submit task %d: %v", i, err)
		}
		_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
			RuntimeID: accepted.Route.RuntimeID,
			TaskID:    accepted.TaskID,
			Success:   false,
			Error: &model.NormalizedError{
				Category:          "execution",
				Code:              "forced_failure",
				Message:           "forced failure",
				CooldownCandidate: true,
			},
		})
		if err != nil {
			t.Fatalf("record completion %d: %v", i, err)
		}
	}

	strategyTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode:      "strategy",
		Operation: model.OperationSpec{Kind: "task"},
	})
	if err != nil {
		t.Fatalf("strategy submit: %v", err)
	}
	if strategyTask.Route.SelectedProvider != "camoufox" {
		t.Fatalf("expected cooled chrome to be skipped, got provider %q", strategyTask.Route.SelectedProvider)
	}
}

func TestMarkRuntimeStoppedFailsActiveTask(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-active",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{Kind: "task"},
	})
	if err != nil {
		t.Fatalf("submit task: %v", err)
	}
	if accepted.Route.RuntimeID == "" {
		t.Fatal("expected runtime assignment")
	}

	svc.MarkRuntimeStopped(accepted.Route.RuntimeID, true)

	task, _, err := svc.GetTask(accepted.TaskID)
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if task.State != "failed" {
		t.Fatalf("expected task to fail after abnormal runtime stop, got %q", task.State)
	}
	if task.Error == nil || task.Error.Category != "abnormal_exit" {
		t.Fatalf("expected abnormal_exit error, got %#v", task.Error)
	}
}

func TestListRuntimesSeparatesActiveAndHistoricalViews(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-active",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register active runtime: %v", err)
	}
	_, _, err = svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-stopped",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register stopped runtime: %v", err)
	}
	_, _, err = svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-cooled",
		ProviderID: "camoufox",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register cooled runtime: %v", err)
	}

	svc.MarkRuntimeStopped("rt-stopped", false)
	svc.mu.Lock()
	if runtime, ok := svc.runtimes["rt-cooled"]; ok {
		runtime.View.State = "cooled"
		runtime.View.Healthy = false
		svc.syncRuntimeDerivedLocked(runtime)
	}
	svc.mu.Unlock()

	data := svc.ListRuntimes()
	if len(data.Runtimes) != 1 {
		t.Fatalf("expected only active runtimes in runtimes list, got %d", len(data.Runtimes))
	}
	if len(data.ActiveRuntimes) != 1 || data.ActiveRuntimes[0].RuntimeID != "rt-active" {
		t.Fatalf("expected active runtime list to contain rt-active, got %#v", data.ActiveRuntimes)
	}
	if len(data.HistoricalRuntimes) != 2 {
		t.Fatalf("expected 2 historical runtimes, got %d", len(data.HistoricalRuntimes))
	}
	if data.HistoricalRuntimes[0].RuntimeID != "rt-cooled" && data.HistoricalRuntimes[1].RuntimeID != "rt-cooled" {
		t.Fatalf("expected cooled runtime to appear in history, got %#v", data.HistoricalRuntimes)
	}
}

func TestDirectTargetRuntimeAllowsPinnedReuseAfterPrimitiveFlowFailure(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-session-001",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	first, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			RuntimeID: "rt-session-001",
		},
		Operation: model.OperationSpec{
			Kind: "read_value",
			Payload: map[string]any{
				"action":        "read_value",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit first task: %v", err)
	}
	if first.Route.RuntimeID != "rt-session-001" {
		t.Fatalf("expected first task to pin rt-session-001, got %q", first.Route.RuntimeID)
	}

	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: "rt-session-001",
		TaskID:    first.TaskID,
		Success:   false,
		Error: &model.NormalizedError{
			Category:          "flow_error",
			Code:              "action_failed",
			Message:           "email input not found",
			CooldownCandidate: true,
		},
	})
	if err != nil {
		t.Fatalf("record flow failure completion: %v", err)
	}

	view, _, err := svc.GetRuntime("rt-session-001")
	if err != nil {
		t.Fatalf("get runtime after failure: %v", err)
	}
	if view.State != "ready" {
		t.Fatalf("expected flow failure to preserve ready runtime, got %q", view.State)
	}
	if !view.Healthy {
		t.Fatal("expected flow failure to preserve healthy runtime")
	}

	second, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			RuntimeID: "rt-session-001",
		},
		Operation: model.OperationSpec{
			Kind: "get_resource",
			Payload: map[string]any{
				"action":        "get_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit second task: %v", err)
	}
	if second.Route.RuntimeID != "rt-session-001" {
		t.Fatalf("expected second task to reuse rt-session-001, got %q", second.Route.RuntimeID)
	}
}

func TestDirectTargetRuntimeCanLeasePinnedRuntimeEvenIfMarkedFailed(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-session-002",
		ProviderID: "chrome",
		State:      "failed",
	})
	if err != nil {
		t.Fatalf("register failed runtime: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			RuntimeID: "rt-session-002",
		},
		Operation: model.OperationSpec{
			Kind: "get_resource",
			Payload: map[string]any{
				"action":        "get_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit task against pinned failed runtime: %v", err)
	}
	if accepted.State != "running" {
		t.Fatalf("expected running state, got %q", accepted.State)
	}
	if accepted.Route.RuntimeID != "rt-session-002" {
		t.Fatalf("expected pinned runtime rt-session-002, got %q", accepted.Route.RuntimeID)
	}
}

func TestStrategySelectsBrowserbaseForSessionActions(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "list_sessions",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "browserbase" {
		t.Fatalf("expected browserbase for session action, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategySelectsLocalProviderForPageActions(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "open_page",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider == "browserbase" {
		t.Fatalf("expected local provider for page action, got %q", data.Route.SelectedProvider)
	}
}

func TestDirectRejectsIncompatibleProviderAction(t *testing.T) {
	svc := New()

	_, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "browserbase",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "open_page",
			},
		},
	})
	if err == nil {
		t.Fatal("expected incompatible provider/action validation error")
	}
}

func TestStrategySelectsBrowserbaseForGenericSessionResourceAction(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "list_resources",
				"resource_kind": "session",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "browserbase" {
		t.Fatalf("expected browserbase for generic session resource action, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategySelectsLocalProviderForGenericPageResourceAction(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider == "browserbase" {
		t.Fatalf("expected local provider for generic page resource action, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyGenericResourceActionRequiresResourceKind(t *testing.T) {
	svc := New()

	_, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "list_resources",
			},
		},
	})
	if err == nil {
		t.Fatal("expected resource_kind validation error")
	}
}

func TestStrategyProfileStealthFirstPrefersCamoufox(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.StrategyProfile != "stealth-first" {
		t.Fatalf("expected canonical strategy profile stealth-first, got %q", data.Route.StrategyProfile)
	}
	if data.Route.SelectedProvider != "camoufox" {
		t.Fatalf("expected camoufox for stealth-first page strategy, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyProfileChromeFirstPrefersChrome(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "chrome" {
		t.Fatalf("expected chrome for chrome-first page strategy, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyProfileRemoteFirstPrefersBrowserbaseForHealth(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "remote-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "health",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "browserbase" {
		t.Fatalf("expected browserbase for remote-first provider action, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyProfileLocalFirstAvoidsBrowserbaseForHealth(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "local-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action": "health",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider == "browserbase" {
		t.Fatalf("expected local provider for local-first provider action, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyProfileFallbackWhenPreferredProviderCooled(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-camoufox-test",
		ProviderID: "camoufox",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	for i := 0; i < 3; i++ {
		accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
			Mode: "direct",
			Target: model.TargetSpec{
				Provider: "camoufox",
			},
			Operation: model.OperationSpec{Kind: "task"},
		})
		if err != nil {
			t.Fatalf("submit task %d: %v", i, err)
		}
		_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
			RuntimeID: accepted.Route.RuntimeID,
			TaskID:    accepted.TaskID,
			Success:   false,
			Error: &model.NormalizedError{
				Category:          "execution",
				Code:              "forced_failure",
				Message:           "forced failure",
				CooldownCandidate: true,
			},
		})
		if err != nil {
			t.Fatalf("record completion %d: %v", i, err)
		}
	}

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "geekez" {
		t.Fatalf("expected fallback to geekez when camoufox cooled, got %q", data.Route.SelectedProvider)
	}

	task, _, err := svc.GetTask(data.TaskID)
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if !task.Route.FallbackUsed {
		t.Fatal("expected fallback_used=true when preferred stealth provider cooled")
	}
	if task.Route.StrategyProfile != "stealth-first" {
		t.Fatalf("expected canonical profile stealth-first, got %q", task.Route.StrategyProfile)
	}
	if task.Route.Diagnostics == nil {
		t.Fatal("expected structured route diagnostics")
	}
	if task.Route.Diagnostics.Score == 0 {
		t.Fatal("expected non-zero score in route diagnostics")
	}
	if task.Route.Diagnostics.Breakdown == nil {
		t.Fatal("expected score breakdown in route diagnostics")
	}
	if len(task.Route.Candidates) == 0 {
		t.Fatal("expected route candidates to be populated")
	}
	foundSelected := false
	foundRejectedCamoufox := false
	for _, candidate := range task.Route.Candidates {
		if candidate.Selected && candidate.ProviderID == "geekez" {
			foundSelected = true
		}
		if candidate.ProviderID == "camoufox" && candidate.RejectionReason != "" {
			foundRejectedCamoufox = true
		}
	}
	if !foundSelected {
		t.Fatal("expected selected candidate entry for geekez")
	}
	if !foundRejectedCamoufox {
		t.Fatal("expected rejected candidate entry for camoufox")
	}
}

func TestStrategyProfileLatencyFirstPrefersReadyRuntime(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-ready-latency",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	_, _, err = svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-fail-latency",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{Kind: "task"},
	})
	if err != nil {
		t.Fatalf("submit task: %v", err)
	}
	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: accepted.Route.RuntimeID,
		TaskID:    accepted.TaskID,
		Success:   false,
		Error: &model.NormalizedError{
			Category:          "execution",
			Code:              "forced_failure",
			Message:           "forced failure",
			CooldownCandidate: false,
		},
	})
	if err != nil {
		t.Fatalf("record completion: %v", err)
	}

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "latency-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
		Isolation: model.IsolationSpec{
			RuntimeReuse: "prefer_reuse",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "chrome" {
		t.Fatalf("expected chrome for latency-first due to ready runtime, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyProfileStabilityFirstAvoidsFailureHeavyProvider(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-ready-stability",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	_, _, err = svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-camoufox-ready-stability",
		ProviderID: "camoufox",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	_, _, err = svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-fail-stability",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{Kind: "task"},
	})
	if err != nil {
		t.Fatalf("submit task: %v", err)
	}
	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: accepted.Route.RuntimeID,
		TaskID:    accepted.TaskID,
		Success:   false,
		Error: &model.NormalizedError{
			Category:          "execution",
			Code:              "forced_failure",
			Message:           "forced failure",
			CooldownCandidate: false,
		},
	})
	if err != nil {
		t.Fatalf("record completion: %v", err)
	}

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stability-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
		Isolation: model.IsolationSpec{
			RuntimeReuse: "prefer_reuse",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "camoufox" {
		t.Fatalf("expected camoufox for stability-first due to lower failure history, got %q", data.Route.SelectedProvider)
	}
}

func TestStrategyRequireReuseRejectsProvidersWithoutReadyRuntimeWhenPreferred(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-chrome-reuse-only",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "balanced",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
		Isolation: model.IsolationSpec{
			RuntimeReuse: "require_reuse",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.SelectedProvider != "chrome" {
		t.Fatalf("expected chrome when require_reuse only has chrome ready runtime, got %q", data.Route.SelectedProvider)
	}
	if data.Route.Diagnostics == nil || data.Route.Diagnostics.RuntimeReuse != "require_reuse" {
		t.Fatalf("expected route diagnostics to record runtime reuse, got %#v", data.Route.Diagnostics)
	}
}

func TestDirectRouteIncludesStructuredDiagnostics(t *testing.T) {
	svc := New()

	data, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
		Isolation: model.IsolationSpec{
			RuntimeReuse: "prefer_reuse",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if data.Route.Diagnostics == nil {
		t.Fatal("expected execute route diagnostics for direct mode")
	}
	if data.Route.Diagnostics.Action != "open_resource" {
		t.Fatalf("expected open_resource action, got %#v", data.Route.Diagnostics)
	}
	if data.Route.Diagnostics.RuntimeReuse != "prefer_reuse" {
		t.Fatalf("expected runtime reuse prefer_reuse, got %#v", data.Route.Diagnostics)
	}
	if data.Route.Diagnostics.Breakdown != nil {
		t.Fatalf("expected no score breakdown for direct diagnostics, got %#v", data.Route.Diagnostics.Breakdown)
	}
}

func TestRouteHistoryAndFallbackHistory(t *testing.T) {
	svc := New()

	normal, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit normal task: %v", err)
	}

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}
	fallback, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit fallback task: %v", err)
	}

	history := svc.RouteHistory(10)
	if len(history.Routes) < 2 {
		t.Fatalf("expected at least two route history entries, got %d", len(history.Routes))
	}
	if history.Routes[0].TaskID != fallback.TaskID {
		t.Fatalf("expected most recent history entry to be fallback task %q, got %q", fallback.TaskID, history.Routes[0].TaskID)
	}

	fallbacks := svc.FallbackHistory(10)
	if len(fallbacks.Fallbacks) != 1 {
		t.Fatalf("expected one fallback history entry, got %d", len(fallbacks.Fallbacks))
	}
	if fallbacks.Fallbacks[0].TaskID != fallback.TaskID {
		t.Fatalf("expected fallback task id %q, got %q", fallback.TaskID, fallbacks.Fallbacks[0].TaskID)
	}
	if fallbacks.Fallbacks[0].FallbackUsed != true {
		t.Fatal("expected fallback_used=true in fallback history")
	}

	limited := svc.RouteHistory(1)
	if len(limited.Routes) != 1 {
		t.Fatalf("expected route history limit=1 to return one entry, got %d", len(limited.Routes))
	}
	if limited.Routes[0].TaskID != fallback.TaskID {
		t.Fatalf("expected limited route history to contain latest task %q, got %q", fallback.TaskID, limited.Routes[0].TaskID)
	}

	_ = normal
}

func TestRouteRejectionSummaryAggregatesCounts(t *testing.T) {
	svc := New()

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}

	for i := 0; i < 2; i++ {
		_, _, err := svc.SubmitTask(model.ExecuteRequest{
			Mode: "strategy",
			Target: model.TargetSpec{
				StrategyProfile: "stealth-first",
			},
			Operation: model.OperationSpec{
				Kind: "task",
				Payload: map[string]any{
					"action":        "open_resource",
					"resource_kind": "page",
				},
			},
		})
		if err != nil {
			t.Fatalf("submit task %d: %v", i, err)
		}
	}

	summary := svc.RouteRejectionSummary()
	if len(summary.Rejections) == 0 {
		t.Fatal("expected rejection summary entries")
	}

	foundCamoufoxDisabled := false
	foundBrowserbaseUnsupported := false
	for _, entry := range summary.Rejections {
		if entry.ProviderID == "camoufox" && entry.RejectionReason == "disabled" && entry.Count == 2 {
			foundCamoufoxDisabled = true
		}
		if entry.ProviderID == "browserbase" && entry.RejectionReason == "unsupported_action" && entry.Count == 2 {
			foundBrowserbaseUnsupported = true
		}
	}
	if !foundCamoufoxDisabled {
		t.Fatal("expected aggregated disabled rejection for camoufox")
	}
	if !foundBrowserbaseUnsupported {
		t.Fatal("expected aggregated unsupported_action rejection for browserbase")
	}
}

func TestRouteControlSummaryAggregatesDashboardData(t *testing.T) {
	svc := New()

	_, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit normal task: %v", err)
	}

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}
	fallbackTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit fallback task: %v", err)
	}

	summary := svc.RouteControlSummary(10, 10, 10, 10)
	if summary.Totals.TotalRoutes != 2 {
		t.Fatalf("expected total_routes=2, got %d", summary.Totals.TotalRoutes)
	}
	if summary.Totals.TotalFallbacks != 1 {
		t.Fatalf("expected total_fallbacks=1, got %d", summary.Totals.TotalFallbacks)
	}
	if len(summary.RecentEvents) != 2 {
		t.Fatalf("expected two recent events, got %d", len(summary.RecentEvents))
	}
	if len(summary.RecentFallbacks) != 1 {
		t.Fatalf("expected one recent fallback, got %d", len(summary.RecentFallbacks))
	}
	if summary.RecentFallbacks[0].TaskID != fallbackTask.TaskID {
		t.Fatalf("expected fallback task %q, got %q", fallbackTask.TaskID, summary.RecentFallbacks[0].TaskID)
	}
	if len(summary.TopRejections) == 0 {
		t.Fatal("expected top rejections in summary")
	}
	if len(summary.ProviderSelections) == 0 {
		t.Fatal("expected provider selections in summary")
	}
	if len(summary.ProfileUsage) == 0 {
		t.Fatal("expected profile usage in summary")
	}

	foundChromeSelections := false
	foundStealthProfile := false
	for _, entry := range summary.ProviderSelections {
		if entry.ProviderID == "chrome" && entry.Count >= 1 {
			foundChromeSelections = true
		}
	}
	for _, entry := range summary.ProfileUsage {
		if entry.StrategyProfile == "stealth-first" && entry.Count == 1 {
			foundStealthProfile = true
		}
	}
	if !foundChromeSelections {
		t.Fatal("expected chrome in provider selections summary")
	}
	if !foundStealthProfile {
		t.Fatal("expected stealth-first in profile usage summary")
	}
	if len(summary.RecentOperationalEvents) == 0 {
		t.Fatal("expected recent operational events in summary")
	}
}

func TestRecentOperationalEventsCaptureAdminAndFailureSignals(t *testing.T) {
	svc := New()

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}
	if _, err := svc.ResetProviderCooldown("chrome"); err != nil {
		t.Fatalf("reset chrome cooldown: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit task: %v", err)
	}

	if accepted.Route.RuntimeID != "" {
		svc.MarkRuntimeStopped(accepted.Route.RuntimeID, true)
	} else {
		_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
			RuntimeID: "",
			TaskID:    accepted.TaskID,
			Success:   false,
			Error: &model.NormalizedError{
				Category:          "transport",
				Code:              "dispatch_failed",
				Message:           "dispatch failed",
				CooldownCandidate: true,
			},
		})
		if err != nil {
			t.Fatalf("record completion: %v", err)
		}
	}

	events := svc.RecentOperationalEvents(20)
	if len(events.Events) == 0 {
		t.Fatal("expected operational events")
	}

	foundDisabled := false
	foundCooldownReset := false
	foundFallback := false
	foundSelected := false
	foundFailureSignal := false
	for _, event := range events.Events {
		switch event.Kind {
		case "provider_disabled":
			foundDisabled = true
		case "provider_cooldown_reset":
			foundCooldownReset = true
		case "route_fallback":
			foundFallback = true
		case "route_selected":
			foundSelected = true
		case "runtime_abnormal_exit", "dispatch_failed":
			foundFailureSignal = true
		}
	}
	if !foundDisabled {
		t.Fatal("expected provider_disabled event")
	}
	if !foundCooldownReset {
		t.Fatal("expected provider_cooldown_reset event")
	}
	if !foundFallback {
		t.Fatal("expected route_fallback event")
	}
	if !foundSelected {
		t.Fatal("expected route_selected event")
	}
	if !foundFailureSignal {
		t.Fatal("expected abnormal exit or dispatch failure event")
	}
}

func TestRecentOperationalEventsCaptureRuntimeLifecycleSignals(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-lifecycle-001",
		ProviderID: "chrome",
		State:      "ready",
		PID:        4242,
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	accepted, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit task: %v", err)
	}
	if accepted.Route.RuntimeID == "" {
		t.Fatal("expected reused runtime assignment")
	}

	svc.MarkRuntimeStopped(accepted.Route.RuntimeID, false)

	events := svc.RecentOperationalEvents(20)
	if len(events.Events) == 0 {
		t.Fatal("expected operational events")
	}

	foundRegistered := false
	foundReady := false
	foundReused := false
	foundShutdown := false
	for _, event := range events.Events {
		switch event.Kind {
		case "runtime_registered":
			foundRegistered = true
		case "runtime_ready":
			foundReady = true
		case "runtime_reused":
			foundReused = true
		case "runtime_shutdown":
			foundShutdown = true
		}
	}
	if !foundRegistered {
		t.Fatal("expected runtime_registered event")
	}
	if !foundReady {
		t.Fatal("expected runtime_ready event")
	}
	if !foundReused {
		t.Fatal("expected runtime_reused event")
	}
	if !foundShutdown {
		t.Fatal("expected runtime_shutdown event")
	}
}

func TestRecentOperationalEventsCaptureTaskSuccessAndCancel(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-task-events-001",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	successTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit success task: %v", err)
	}
	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: successTask.Route.RuntimeID,
		TaskID:    successTask.TaskID,
		Success:   true,
		Result: map[string]any{
			"action": "open_resource",
		},
	})
	if err != nil {
		t.Fatalf("complete success task: %v", err)
	}

	cancelTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit cancel task: %v", err)
	}
	_, _, err = svc.CancelTask(cancelTask.TaskID, model.CancelRequest{
		Reason:      "test_cancel",
		RequestedBy: "unit_test",
	})
	if err != nil {
		t.Fatalf("cancel task: %v", err)
	}

	events := svc.RecentOperationalEvents(20)
	foundSucceeded := false
	foundCancelled := false
	for _, event := range events.Events {
		switch event.Kind {
		case "task_succeeded":
			foundSucceeded = true
		case "task_cancelled":
			foundCancelled = true
		}
	}
	if !foundSucceeded {
		t.Fatal("expected task_succeeded event")
	}
	if !foundCancelled {
		t.Fatal("expected task_cancelled event")
	}
}

func TestRuntimeHeartbeatMissedAndHealthDegradedEvents(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-health-001",
		ProviderID: "camoufox",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	svc.mu.Lock()
	svc.runtimes["rt-health-001"].lastHeartbeat = time.Now().UTC().Add(-(svc.heartbeatTimeout + 5*time.Second))
	svc.runtimes["rt-health-001"].View.LastHeartbeatAt = svc.runtimes["rt-health-001"].lastHeartbeat.Format(time.RFC3339)
	svc.refreshCooldownsLocked()
	svc.mu.Unlock()

	_, _, err = svc.RecordHeartbeat(model.RuntimeHeartbeatRequest{
		RuntimeID:  "rt-health-001",
		ProviderID: "camoufox",
		Healthy:    false,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		Signals: model.HeartbeatSignals{
			RecentFailures: 1,
		},
	})
	if err != nil {
		t.Fatalf("record degraded heartbeat: %v", err)
	}

	events := svc.RecentOperationalEvents(20)
	foundHeartbeatMissed := false
	foundHealthDegraded := false
	for _, event := range events.Events {
		switch event.Kind {
		case "runtime_heartbeat_missed":
			foundHeartbeatMissed = true
		case "runtime_health_degraded":
			foundHealthDegraded = true
		}
	}
	if !foundHeartbeatMissed {
		t.Fatal("expected runtime_heartbeat_missed event")
	}
	if !foundHealthDegraded {
		t.Fatal("expected runtime_health_degraded event")
	}
}

func TestRouteInsightsAggregatesProviderAndProfileStats(t *testing.T) {
	svc := New()

	_, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit chrome-first task: %v", err)
	}

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}

	_, _, err = svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit stealth-first task: %v", err)
	}

	insights := svc.RouteInsights()
	if len(insights.Providers) == 0 {
		t.Fatal("expected provider insights")
	}
	if len(insights.Profiles) == 0 {
		t.Fatal("expected profile insights")
	}

	foundChrome := false
	foundCamoufox := false
	foundGeekez := false
	for _, insight := range insights.Providers {
		switch insight.ProviderID {
		case "chrome":
			foundChrome = true
			if insight.SelectedCount != 1 {
				t.Fatalf("expected chrome selected exactly once, got %d", insight.SelectedCount)
			}
			if insight.FallbackSelectedCount != 0 {
				t.Fatalf("expected chrome fallback selections to remain 0, got %d", insight.FallbackSelectedCount)
			}
		case "camoufox":
			foundCamoufox = true
			if insight.RejectionCounts["disabled"] < 1 {
				t.Fatalf("expected camoufox disabled rejection count, got %#v", insight.RejectionCounts)
			}
		case "geekez":
			foundGeekez = true
			if insight.SelectedCount != 1 {
				t.Fatalf("expected geekez selected exactly once, got %d", insight.SelectedCount)
			}
			if insight.FallbackSelectedCount < 1 {
				t.Fatalf("expected geekez fallback selections, got %d", insight.FallbackSelectedCount)
			}
		}
	}
	if !foundChrome {
		t.Fatal("expected chrome provider insight")
	}
	if !foundCamoufox {
		t.Fatal("expected camoufox provider insight")
	}
	if !foundGeekez {
		t.Fatal("expected geekez provider insight")
	}

	foundStealthProfile := false
	for _, insight := range insights.Profiles {
		if insight.StrategyProfile == "stealth-first" {
			foundStealthProfile = true
			if insight.TotalRoutes != 1 {
				t.Fatalf("expected stealth-first total routes 1, got %d", insight.TotalRoutes)
			}
			if insight.FallbackRoutes != 1 {
				t.Fatalf("expected stealth-first fallback routes 1, got %d", insight.FallbackRoutes)
			}
			if insight.ProviderSelections["geekez"] != 1 {
				t.Fatalf("expected stealth-first provider selection geekez=1, got %#v", insight.ProviderSelections)
			}
		}
	}
	if !foundStealthProfile {
		t.Fatal("expected stealth-first profile insight")
	}
}

func TestRouteWindowStatsRespectTaskTimestamps(t *testing.T) {
	svc := New()

	oldTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit old task: %v", err)
	}

	oldTime := time.Now().UTC().Add(-2 * time.Hour).Format(time.RFC3339)
	svc.tasks[oldTask.TaskID].Data.Timing.QueuedAt = oldTime
	svc.tasks[oldTask.TaskID].Data.Timing.StartedAt = oldTime
	svc.tasks[oldTask.TaskID].Data.Timing.FinishedAt = oldTime

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}
	_, _, err = svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit recent task: %v", err)
	}

	stats := svc.RouteWindowStats()
	if len(stats.Windows) != 3 {
		t.Fatalf("expected 3 route windows, got %d", len(stats.Windows))
	}

	windowMap := make(map[string]model.RouteWindowSummary)
	for _, window := range stats.Windows {
		windowMap[window.Window] = window
	}

	if windowMap["10m"].TotalRoutes != 1 {
		t.Fatalf("expected 10m total_routes=1, got %d", windowMap["10m"].TotalRoutes)
	}
	if windowMap["1h"].TotalRoutes != 1 {
		t.Fatalf("expected 1h total_routes=1, got %d", windowMap["1h"].TotalRoutes)
	}
	if windowMap["24h"].TotalRoutes != 2 {
		t.Fatalf("expected 24h total_routes=2, got %d", windowMap["24h"].TotalRoutes)
	}
	if windowMap["10m"].TotalFallbacks != 1 {
		t.Fatalf("expected 10m total_fallbacks=1, got %d", windowMap["10m"].TotalFallbacks)
	}
	foundRecentDisabled := false
	for _, rejection := range windowMap["10m"].Rejections {
		if rejection.ProviderID == "camoufox" && rejection.RejectionReason == "disabled" {
			foundRecentDisabled = true
		}
	}
	if !foundRecentDisabled {
		t.Fatal("expected disabled rejection in 10m window")
	}
}

func TestProviderHealthSummaryAggregatesProviderSignals(t *testing.T) {
	svc := New()

	_, _, err := svc.RegisterRuntime(model.RuntimeRegistrationRequest{
		RuntimeID:  "rt-health-summary-001",
		ProviderID: "chrome",
		State:      "ready",
	})
	if err != nil {
		t.Fatalf("register runtime: %v", err)
	}

	successTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit success task: %v", err)
	}
	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: successTask.Route.RuntimeID,
		TaskID:    successTask.TaskID,
		Success:   true,
		Result: map[string]any{
			"action": "open_resource",
		},
	})
	if err != nil {
		t.Fatalf("record success completion: %v", err)
	}

	failTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit fail task: %v", err)
	}
	_, _, err = svc.RecordCompletion(model.RuntimeCompletionRequest{
		RuntimeID: failTask.Route.RuntimeID,
		TaskID:    failTask.TaskID,
		Success:   false,
		Error: &model.NormalizedError{
			Category:          "transport",
			Code:              "dispatch_failed",
			Message:           "dispatch failed",
			CooldownCandidate: true,
		},
	})
	if err != nil {
		t.Fatalf("record failed completion: %v", err)
	}

	cancelTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			Provider: "chrome",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit cancel task: %v", err)
	}
	_, _, err = svc.CancelTask(cancelTask.TaskID, model.CancelRequest{
		Reason:      "test_cancel",
		RequestedBy: "unit_test",
	})
	if err != nil {
		t.Fatalf("cancel task: %v", err)
	}

	svc.RecordOperationalEvent("runtime_spawn_started", "info", "spawn chrome", model.Trace{ProviderID: "chrome", RuntimeID: "rt-health-summary-001"}, nil)
	svc.RecordOperationalEvent("runtime_ready_timeout", "warn", "chrome ready timeout", model.Trace{ProviderID: "chrome", RuntimeID: "rt-health-summary-001"}, nil)
	svc.RecordOperationalEvent("runtime_startup_failed", "error", "chrome startup failed", model.Trace{ProviderID: "chrome", RuntimeID: "rt-health-summary-001"}, nil)
	svc.RecordOperationalEvent("runtime_heartbeat_missed", "warn", "heartbeat missed", model.Trace{ProviderID: "chrome", RuntimeID: "rt-health-summary-001"}, nil)
	svc.RecordOperationalEvent("runtime_health_degraded", "warn", "health degraded", model.Trace{ProviderID: "chrome", RuntimeID: "rt-health-summary-001"}, nil)

	summary := svc.ProviderHealthSummary()
	if len(summary.Providers) == 0 {
		t.Fatal("expected provider health summary entries")
	}

	var chrome *model.ProviderHealthSummaryEntry
	for i := range summary.Providers {
		if summary.Providers[i].ProviderID == "chrome" {
			chrome = &summary.Providers[i]
			break
		}
	}
	if chrome == nil {
		t.Fatal("expected chrome provider health summary")
	}
	if chrome.TotalTaskSucceededCount < 1 {
		t.Fatalf("expected chrome success count, got %+v", chrome)
	}
	if chrome.TotalTaskFailedCount < 1 {
		t.Fatalf("expected chrome failed count, got %+v", chrome)
	}
	if chrome.TotalTaskCancelledCount < 1 {
		t.Fatalf("expected chrome cancelled count, got %+v", chrome)
	}
	if chrome.TotalSpawnStartedCount < 1 {
		t.Fatalf("expected chrome spawn started count, got %+v", chrome)
	}
	if chrome.TotalReadyTimeoutCount < 1 {
		t.Fatalf("expected chrome ready timeout count, got %+v", chrome)
	}
	if chrome.TotalStartupFailedCount < 1 {
		t.Fatalf("expected chrome startup failed count, got %+v", chrome)
	}
	if chrome.TotalHeartbeatMissedCount < 1 {
		t.Fatalf("expected chrome heartbeat missed count, got %+v", chrome)
	}
	if chrome.TotalHealthDegradedCount < 1 {
		t.Fatalf("expected chrome health degraded count, got %+v", chrome)
	}
	if len(chrome.Windows) != 3 {
		t.Fatalf("expected three provider health windows, got %d", len(chrome.Windows))
	}
	if chrome.Windows[0].SuccessRate <= 0 {
		t.Fatalf("expected positive recent success rate, got %+v", chrome.Windows[0])
	}

	control := svc.RouteControlSummary(10, 10, 10, 10)
	if len(control.ProviderHealth) == 0 {
		t.Fatal("expected provider health summary embedded in control summary")
	}
}

func TestRouteWindowInsightsRespectTaskAndEventTimestamps(t *testing.T) {
	svc := New()

	oldTask, _, err := svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "chrome-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit old task: %v", err)
	}

	oldTime := time.Now().UTC().Add(-2 * time.Hour).Format(time.RFC3339)
	svc.tasks[oldTask.TaskID].Data.Timing.QueuedAt = oldTime
	svc.tasks[oldTask.TaskID].Data.Timing.StartedAt = oldTime
	svc.tasks[oldTask.TaskID].Data.Timing.FinishedAt = oldTime
	if len(svc.events) > 0 {
		svc.events[len(svc.events)-1].OccurredAt = oldTime
	}

	if _, err := svc.SetProviderEnabled("camoufox", false, "admin_disabled"); err != nil {
		t.Fatalf("disable camoufox: %v", err)
	}

	_, _, err = svc.SubmitTask(model.ExecuteRequest{
		Mode: "strategy",
		Target: model.TargetSpec{
			StrategyProfile: "stealth-first",
		},
		Operation: model.OperationSpec{
			Kind: "task",
			Payload: map[string]any{
				"action":        "open_resource",
				"resource_kind": "page",
			},
		},
	})
	if err != nil {
		t.Fatalf("submit recent task: %v", err)
	}

	insights := svc.RouteWindowInsights()
	if len(insights.Windows) != 3 {
		t.Fatalf("expected 3 window insights, got %d", len(insights.Windows))
	}

	windowMap := make(map[string]model.RouteInsightsWindow)
	for _, window := range insights.Windows {
		windowMap[window.Window] = window
	}

	providerCount := func(window model.RouteInsightsWindow, providerID string) int {
		for _, insight := range window.Providers {
			if insight.ProviderID == providerID {
				return insight.SelectedCount
			}
		}
		return 0
	}
	profileCount := func(window model.RouteInsightsWindow, profile string) int {
		for _, insight := range window.Profiles {
			if insight.StrategyProfile == profile {
				return insight.TotalRoutes
			}
		}
		return 0
	}
	findProviderInsight := func(window model.RouteInsightsWindow, providerID string) *model.RouteProviderInsight {
		for _, insight := range window.Providers {
			if insight.ProviderID == providerID {
				copy := insight
				return &copy
			}
		}
		return nil
	}

	if got := providerCount(windowMap["10m"], "geekez"); got != 1 {
		t.Fatalf("expected 10m geekez selected_count=1, got %d", got)
	}
	if got := providerCount(windowMap["24h"], "chrome"); got != 1 {
		t.Fatalf("expected 24h chrome selected_count=1, got %d", got)
	}
	if got := providerCount(windowMap["24h"], "geekez"); got != 1 {
		t.Fatalf("expected 24h geekez selected_count=1, got %d", got)
	}
	if got := profileCount(windowMap["10m"], "stealth-first"); got != 1 {
		t.Fatalf("expected 10m stealth-first total_routes=1, got %d", got)
	}
	if got := profileCount(windowMap["24h"], "chrome-first"); got != 1 {
		t.Fatalf("expected 24h chrome-first total_routes=1, got %d", got)
	}

	camoufox10m := findProviderInsight(windowMap["10m"], "camoufox")
	if camoufox10m == nil {
		t.Fatal("expected camoufox provider insight in 10m window")
	}
	if camoufox10m.RejectionCounts["disabled"] < 1 {
		t.Fatalf("expected disabled rejection in 10m camoufox insight, got %#v", camoufox10m.RejectionCounts)
	}
	if camoufox10m.EventCounts["provider_disabled"] < 1 {
		t.Fatalf("expected provider_disabled event in 10m camoufox insight, got %#v", camoufox10m.EventCounts)
	}

	geekez10m := findProviderInsight(windowMap["10m"], "geekez")
	if geekez10m == nil {
		t.Fatal("expected geekez provider insight in 10m window")
	}
	if geekez10m.EventCounts["route_selected"] < 1 {
		t.Fatalf("expected route_selected event in 10m geekez insight, got %#v", geekez10m.EventCounts)
	}
}
