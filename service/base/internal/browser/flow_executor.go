package browser

import (
	"fmt"
	"strings"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

const (
	defaultFlowTimeout     = 7 * time.Minute
	defaultPrimitiveTimout = 45 * time.Second
	challengeGracePeriod   = 35 * time.Second
)

var mediumFlowStepsByType = map[string]map[string]struct{}{
	"login": {
		"openai_web_login": {},
	},
	"register": {
		"register_auth":           {},
		"register_profile":        {},
		"register_finalize":       {},
		"register_oauth_auth":     {},
		"register_oauth_finalize": {},
	},
	"repair": {
		"repair_login":    {},
		"repair_finalize": {},
	},
}

type flowExecutionState struct {
	Artifacts         map[string]any
	MediumStepResults map[string]any
	PrimitiveTrace    []map[string]any
	RegisterAuthState map[string]any
	RegisterProfile   map[string]any
	RegisterOAuth     map[string]any
	RepairLoginState  map[string]any
	LastSurface       map[string]any
}

type flowStepOutcome struct {
	Artifacts map[string]any
	Summary   map[string]any
	Err       *model.NormalizedError
}

func (b *API) ExecuteSessionFlow(sessionID string, req model.BrowserSessionFlowRequest) (model.ExecuteAcceptedData, error) {
	record, err := b.getSession(sessionID)
	if err != nil {
		return model.ExecuteAcceptedData{}, err
	}
	flowType := strings.ToLower(strings.TrimSpace(req.FlowType))
	if flowType == "" {
		return model.ExecuteAcceptedData{}, &HTTPError{
			StatusCode: 400,
			Code:       "invalid_request",
			Message:    "flow_type is required",
			Stage:      "flow",
		}
	}
	allowed, ok := mediumFlowStepsByType[flowType]
	if !ok {
		return model.ExecuteAcceptedData{}, &HTTPError{
			StatusCode: 400,
			Code:       "invalid_request",
			Message:    fmt.Sprintf("unsupported flow_type %q", flowType),
			Stage:      "flow",
		}
	}
	if len(req.Steps) == 0 {
		return model.ExecuteAcceptedData{}, &HTTPError{
			StatusCode: 400,
			Code:       "invalid_request",
			Message:    "flow steps are required",
			Stage:      "flow",
		}
	}
	for _, step := range req.Steps {
		stepType := strings.ToLower(strings.TrimSpace(step.StepType))
		if _, ok := allowed[stepType]; !ok {
			return model.ExecuteAcceptedData{}, &HTTPError{
				StatusCode: 400,
				Code:       "invalid_flow_definition",
				Message:    fmt.Sprintf("step type %q is not allowed for flow_type %q", step.StepType, flowType),
				Stage:      "flow",
			}
		}
	}

	accepted, trace, err := b.service.CreateFlowTask(service.FlowTaskSpec{
		RequestID:    req.RequestID,
		Mode:         "direct",
		ProviderID:   record.ProviderID,
		RuntimeID:    record.RuntimeID,
		Action:       flowType + "_flow",
		ResourceKind: record.ResourceKind,
		Message:      fmt.Sprintf("browser %s flow accepted", flowType),
	})
	if err != nil {
		return model.ExecuteAcceptedData{}, err
	}

	timeout := defaultFlowTimeout
	if req.TimeoutMS > 0 {
		timeout = resolveExecutionTimeout(req.TimeoutMS, defaultFlowTimeout)
	}
	go b.runSessionFlow(trace, record.SessionID, flowType, req.Steps, timeout)
	return accepted, nil
}

func (b *API) runSessionFlow(trace model.Trace, sessionID, flowType string, steps []model.BrowserSessionFlowStep, timeout time.Duration) {
	record, err := b.getSession(sessionID)
	if err != nil {
		_, _, _ = b.service.CompleteFlowTask(trace.TaskID, nil, &model.NormalizedError{
			Category: "not_found",
			Code:     "unknown_session",
			Message:  err.Error(),
		})
		return
	}

	state := &flowExecutionState{
		Artifacts:         map[string]any{},
		MediumStepResults: map[string]any{},
		PrimitiveTrace:    []map[string]any{},
	}
	deadline := time.Now().Add(timeout)

	for index, step := range steps {
		if time.Now().After(deadline) {
			_, _, _ = b.service.CompleteFlowTask(trace.TaskID, map[string]any{
				"flow_type":           flowType,
				"medium_step_results": state.MediumStepResults,
				"primitive_trace":     state.PrimitiveTrace,
				"artifacts":           state.Artifacts,
			}, &model.NormalizedError{
				Category:  "timeout",
				Code:      "flow_timeout",
				Message:   fmt.Sprintf("%s flow timed out", flowType),
				Retriable: true,
			})
			return
		}

		stepID := asString(step.Metadata["id"])
		if stepID == "" {
			stepID = asString(step.Metadata["step_id"])
		}
		if stepID == "" {
			stepID = fmt.Sprintf("%s-step-%d", flowType, index+1)
		}
		stepType := strings.ToLower(strings.TrimSpace(step.StepType))
		b.service.RecordFlowEvent("flow_step_started", "info", fmt.Sprintf("flow step %s started", stepID), trace, map[string]any{
			"step_id":   stepID,
			"step_type": stepType,
		})
		outcome := b.runFlowStep(record, trace, stepID, stepType, step.Input, state, deadline)
		summary := map[string]any{
			"step_id":   stepID,
			"step_type": stepType,
			"status":    "ok",
		}
		if len(outcome.Summary) > 0 {
			for key, value := range outcome.Summary {
				summary[key] = value
			}
		}
		if len(outcome.Artifacts) > 0 {
			for key, value := range outcome.Artifacts {
				state.Artifacts[key] = value
			}
			summary["artifacts"] = outcome.Artifacts
		}
		if outcome.Err != nil {
			summary["status"] = "failed"
			summary["error"] = map[string]any{
				"category":  outcome.Err.Category,
				"code":      outcome.Err.Code,
				"message":   outcome.Err.Message,
				"retriable": outcome.Err.Retriable,
			}
			state.MediumStepResults[stepID] = summary
			b.service.RecordFlowEvent("flow_step_failed", "warn", outcome.Err.Message, trace, map[string]any{
				"step_id":        stepID,
				"step_type":      stepType,
				"error_category": outcome.Err.Category,
				"error_code":     outcome.Err.Code,
			})
			_, _, _ = b.service.CompleteFlowTask(trace.TaskID, map[string]any{
				"flow_type":           flowType,
				"medium_step_results": state.MediumStepResults,
				"primitive_trace":     state.PrimitiveTrace,
				"artifacts":           state.Artifacts,
			}, outcome.Err)
			return
		}

		state.MediumStepResults[stepID] = summary
		b.service.RecordFlowEvent("flow_step_completed", "info", fmt.Sprintf("flow step %s completed", stepID), trace, map[string]any{
			"step_id":   stepID,
			"step_type": stepType,
		})
	}

	_, _, _ = b.service.CompleteFlowTask(trace.TaskID, map[string]any{
		"flow_type":           flowType,
		"medium_step_results": state.MediumStepResults,
		"primitive_trace":     state.PrimitiveTrace,
		"artifacts":           state.Artifacts,
	}, nil)
}

func (b *API) runFlowStep(record *SessionRecord, trace model.Trace, stepID, stepType string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	switch stepType {
	case "register_auth":
		return b.runRegisterAuthFlowStep(record, trace, stepID, input, state, deadline)
	case "register_profile":
		return b.runRegisterProfileFlowStep(record, trace, stepID, input, state, deadline)
	case "register_finalize":
		return b.runRegisterFinalizeFlowStep(record, trace, stepID, input, state, deadline)
	case "register_oauth_auth":
		return b.runRegisterOAuthAuthFlowStep(record, trace, stepID, input, state, deadline)
	case "register_oauth_finalize":
		return b.runRegisterOAuthFinalizeFlowStep(record, trace, stepID, input, state, deadline)
	case "repair_login":
		return b.runRepairLoginFlowStep(record, trace, stepID, input, state, deadline)
	case "repair_finalize":
		return b.runRepairFinalizeFlowStep(record, trace, stepID, input, state, deadline)
	case "openai_web_login":
		return b.runOpenAIWebLoginFlowStep(record, trace, stepID, input, state, deadline)
	default:
		return flowStepOutcome{
			Err: &model.NormalizedError{
				Category: "invalid_request",
				Code:     "invalid_flow_definition",
				Message:  fmt.Sprintf("unsupported medium step %q", stepType),
			},
		}
	}
}

func (b *API) runRegisterAuthFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	startURL := coalesce(asString(input["startup_url"]), "https://platform.openai.com/login")
	email := asString(input["email"])
	password := asString(input["password"])
	emailSurfaceHits := 0
	passwordSurfaceHits := 0
	indeterminateSurfaceHits := 0
	reloadedIndeterminateSurface := false
	challengeResetUsed := false
	if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
		return outcome
	}
	for round := 0; round < 24 && time.Now().Before(deadline); round++ {
		surface, err := b.inspectSurface(record, trace, stepID, state)
		if err != nil {
			return flowStepOutcome{Err: err}
		}
		surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
		if err != nil {
			if err.Code == "blocked_challenge_page" && !challengeResetUsed {
				if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
					return outcome
				}
				challengeResetUsed = true
				time.Sleep(1500 * time.Millisecond)
				continue
			}
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
				Err:       err,
			}
		}
		currentURL := asString(surface["url"])
		if isIndeterminateAuthSurface(surface) && isAuthSurfaceURL(currentURL) {
			indeterminateSurfaceHits++
			if indeterminateSurfaceHits >= 3 && !reloadedIndeterminateSurface {
				if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
					return outcome
				}
				reloadedIndeterminateSurface = true
				indeterminateSurfaceHits = 0
				time.Sleep(1500 * time.Millisecond)
				continue
			}
			time.Sleep(1200 * time.Millisecond)
			continue
		}
		indeterminateSurfaceHits = 0
		if terminal := classifyTerminalSurface(surface); terminal != nil {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
				Err:       terminal,
			}
		}
		if boolValue(surface["broken_surface"]) {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
				Err: &model.NormalizedError{
					Category:  "flow_error",
					Code:      "broken_auth_surface",
					Message:   "register_auth reached a broken auth surface",
					Retriable: true,
				},
			}
		}
		if boolValue(surface["callback"]) {
			state.RegisterAuthState = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
			}
		}
		if boolValue(surface["password_stage"]) && boolValue(surface["otp_login_option"]) && strings.Contains(currentURL, "/log-in/password") {
			if err := b.clickAuthLandingAction(record, trace, stepID, []string{
				"log in with a one-time code",
				"login with a one-time code",
				"one-time code",
				"email me a code",
			}, nil, state); err != nil {
				return flowStepOutcome{Err: err}
			}
			time.Sleep(1500 * time.Millisecond)
			continue
		}
		if boolValue(surface["email_stage"]) && email != "" {
			emailSurfaceHits++
			if err := b.fillAndSubmitEmail(record, trace, stepID, email, state); err != nil {
				if shouldEscalateAuthSubmit(err, emailSurfaceHits, "email_submit_not_found") {
					if err := b.forceSubmitForm(record, trace, stepID, "", []string{
						"input[name='email']",
						"input[type='email']",
						"input[autocomplete='email']",
					}, "email form submit fallback failed", "email_submit_fallback_failed", state); err != nil {
						return flowStepOutcome{Err: err}
					}
				} else {
					return flowStepOutcome{Err: err}
				}
			}
			continue
		}
		if boolValue(surface["password_stage"]) && password != "" {
			passwordSurfaceHits++
			if err := b.fillAndSubmitPassword(record, trace, stepID, password, state); err != nil {
				if shouldTreatPasswordFlowErrorAsTransient(err, currentURL) {
					time.Sleep(1500 * time.Millisecond)
					continue
				}
				if shouldEscalateAuthSubmit(err, passwordSurfaceHits, "password_submit_not_found") {
					if err := b.forceSubmitForm(record, trace, stepID, passwordActionContains(currentURL), []string{
						"input[name='password']",
						"input[type='password']",
						"input[autocomplete='current-password']",
						"input[autocomplete='new-password']",
					}, "password form submit fallback failed", "password_submit_fallback_failed", state); err != nil {
						return flowStepOutcome{Err: err}
					}
				} else {
					return flowStepOutcome{Err: err}
				}
			} else if passwordSurfaceHits >= 2 && passwordActionContains(currentURL) != "" {
				if err := b.forceSubmitForm(record, trace, stepID, passwordActionContains(currentURL), []string{
					"input[name='password']",
					"input[type='password']",
					"input[autocomplete='current-password']",
					"input[autocomplete='new-password']",
				}, "password form submit recovery failed", "password_submit_recovery_failed", state); err != nil {
					return flowStepOutcome{Err: err}
				}
			}
			continue
		}
		if boolValue(surface["session_ended"]) && boolValue(surface["login_cta"]) && !boolValue(surface["signup_cta"]) && strings.Contains(currentURL, "auth.openai.com/log-in-or-create-account") {
			if outcome := b.navigateFlowStep(record, trace, stepID, "https://platform.openai.com/login", state); outcome.Err != nil {
				return outcome
			}
			time.Sleep(1500 * time.Millisecond)
			continue
		}
		if boolValue(surface["auth_landing"]) || boolValue(surface["signup_cta"]) {
			if err := b.clickAuthLandingAction(record, trace, stepID, []string{
				"create account",
				"create free account",
				"create your account",
				"sign up",
				"continue",
				"continue with email",
				"use email",
				"work email",
				"email",
			}, []string{
				"signup",
				"sign-up",
				"create-account",
				"register",
				"screen_hint=signup",
			}, state); err != nil {
				return flowStepOutcome{Err: err}
			}
			time.Sleep(1500 * time.Millisecond)
			continue
		}
		if boolValue(surface["profile_stage"]) || boolValue(surface["about_you"]) {
			state.RegisterAuthState = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
			}
		}
		if boolValue(surface["otp_stage"]) {
			state.RegisterAuthState = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
			}
		}
		time.Sleep(1200 * time.Millisecond)
	}
	return flowStepOutcome{
		Err: &model.NormalizedError{
			Category:  "flow_error",
			Code:      "auth_surface_unresolved",
			Message:   "register_auth did not reach a known surface",
			Retriable: true,
		},
	}
}

func (b *API) runRegisterProfileFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	fullName := coalesce(asString(input["full_name"]), strings.TrimSpace(asString(input["first_name"])+" "+asString(input["last_name"])))
	birthdate := asString(input["birthdate"])
	surface, err := b.inspectSurface(record, trace, stepID, state)
	if err != nil {
		return flowStepOutcome{Err: err}
	}
	surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
	if err != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
	}
	if terminal := classifyTerminalSurface(surface); terminal != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
	}
	if boolValue(surface["callback"]) {
		state.RegisterProfile = surface
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary: map[string]any{
				"surface": surface,
				"state":   "skipped_callback_already_reached",
			},
		}
	}
	if isRegisterAccountReadySurface(surface) {
		state.RegisterProfile = surface
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary: map[string]any{
				"surface": surface,
				"state":   "skipped_account_already_ready",
			},
		}
	}
	if !(boolValue(surface["profile_stage"]) || boolValue(surface["about_you"])) {
		return flowStepOutcome{
			Summary: map[string]any{"surface": surface},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "profile_stage_not_ready",
				Message:   "register_profile requires about-you surface",
				Retriable: true,
			},
		}
	}
	if err := b.fillAboutYou(record, trace, stepID, fullName, birthdate, state); err != nil {
		return flowStepOutcome{Err: err}
	}
	for round := 0; round < 12 && time.Now().Before(deadline); round++ {
		surface, err = b.inspectSurface(record, trace, stepID, state)
		if err != nil {
			return flowStepOutcome{Err: err}
		}
		surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
		if err != nil {
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
		}
		if terminal := classifyTerminalSurface(surface); terminal != nil {
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
		}
		if !boolValue(surface["profile_stage"]) && !boolValue(surface["about_you"]) {
			state.RegisterProfile = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
			}
		}
		time.Sleep(1200 * time.Millisecond)
	}
	return flowStepOutcome{
		Artifacts: collectSurfaceArtifacts(surface),
		Summary:   map[string]any{"surface": surface},
		Err: &model.NormalizedError{
			Category:  "flow_error",
			Code:      "profile_submit_timeout",
			Message:   "register_profile did not leave about-you surface",
			Retriable: true,
		},
	}
}

func (b *API) runRegisterFinalizeFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	otpCode := asString(input["otp_code"])
	surface, err := b.inspectSurface(record, trace, stepID, state)
	if err != nil {
		return flowStepOutcome{Err: err}
	}
	surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
	if err != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
	}
	if terminal := classifyTerminalSurface(surface); terminal != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
	}
	if boolValue(surface["otp_stage"]) {
		if otpCode == "" {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
				Err: &model.NormalizedError{
					Category:  "flow_error",
					Code:      "otp_code_required",
					Message:   "register_finalize requires otp_code when the auth surface is at email verification",
					Retriable: true,
				},
			}
		}
		if err := b.fillAndSubmitOtp(record, trace, stepID, otpCode, state); err != nil {
			return flowStepOutcome{Err: err}
		}
		for round := 0; round < 18 && time.Now().Before(deadline); round++ {
			time.Sleep(1200 * time.Millisecond)
			surface, err = b.inspectSurface(record, trace, stepID, state)
			if err != nil {
				return flowStepOutcome{Err: err}
			}
			surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
			if err != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
			}
			if terminal := classifyTerminalSurface(surface); terminal != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
			}
			if boolValue(surface["callback"]) {
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "callback_reached",
					},
				}
			}
			if boolValue(surface["profile_stage"]) || boolValue(surface["about_you"]) {
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "profile_pending",
					},
				}
			}
			if isRegisterAccountReadySurface(surface) {
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "account_ready",
					},
				}
			}
		}
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary:   map[string]any{"surface": surface},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "otp_submit_timeout",
				Message:   "register_finalize submitted otp but did not advance to profile or callback",
				Retriable: true,
			},
		}
	}
	if boolValue(surface["profile_stage"]) || boolValue(surface["about_you"]) {
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary: map[string]any{
				"surface": surface,
				"state":   "profile_pending",
			},
		}
	}
	if isRegisterAccountReadySurface(surface) {
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary: map[string]any{
				"surface": surface,
				"state":   "account_ready",
			},
		}
	}
	if !boolValue(surface["callback"]) {
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary:   map[string]any{"surface": surface},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "register_finalize_surface_unresolved",
				Message:   "register_finalize requires profile, callback, or account-ready surface",
				Retriable: true,
			},
		}
	}
	return flowStepOutcome{
		Artifacts: collectSurfaceArtifacts(surface),
		Summary:   map[string]any{"surface": surface},
	}
}

func (b *API) runRegisterOAuthAuthFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	startURL := coalesce(asString(input["authorize_url"]), asString(input["startup_url"]))
	if startURL == "" {
		return flowStepOutcome{
			Err: &model.NormalizedError{
				Category: "invalid_request",
				Code:     "missing_authorize_url",
				Message:  "register_oauth_auth requires authorize_url",
			},
		}
	}
	email := asString(input["email"])
	password := asString(input["password"])
	emailSurfaceHits := 0
	passwordSurfaceHits := 0
	indeterminateSurfaceHits := 0
	reloadedIndeterminateSurface := false
	challengeResetUsed := false

	if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
		return outcome
	}
	for round := 0; round < 24 && time.Now().Before(deadline); round++ {
		surface, err := b.inspectSurface(record, trace, stepID, state)
		if err != nil {
			return flowStepOutcome{Err: err}
		}
		surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
		if err != nil {
			if err.Code == "blocked_challenge_page" && !challengeResetUsed {
				if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
					return outcome
				}
				challengeResetUsed = true
				time.Sleep(1500 * time.Millisecond)
				continue
			}
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
		}
		currentURL := asString(surface["url"])
		if isIndeterminateAuthSurface(surface) && isAuthSurfaceURL(currentURL) {
			indeterminateSurfaceHits++
			if indeterminateSurfaceHits >= 3 && !reloadedIndeterminateSurface {
				if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
					return outcome
				}
				reloadedIndeterminateSurface = true
				indeterminateSurfaceHits = 0
				time.Sleep(1500 * time.Millisecond)
				continue
			}
			time.Sleep(1200 * time.Millisecond)
			continue
		}
		indeterminateSurfaceHits = 0
		if terminal := classifyTerminalSurface(surface); terminal != nil {
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
		}
		if boolValue(surface["broken_surface"]) {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary:   map[string]any{"surface": surface},
				Err: &model.NormalizedError{
					Category:  "flow_error",
					Code:      "broken_oauth_surface",
					Message:   "register_oauth_auth reached a broken auth surface",
					Retriable: true,
				},
			}
		}
		if boolValue(surface["callback"]) {
			state.RegisterOAuth = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "callback_reached",
				},
			}
		}
		if isConsentSurface(surface) {
			state.RegisterOAuth = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "consent_pending",
				},
			}
		}
		if boolValue(surface["otp_stage"]) {
			state.RegisterOAuth = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
			}
		}
		if boolValue(surface["password_stage"]) && boolValue(surface["otp_login_option"]) && strings.Contains(currentURL, "/log-in/password") {
			if err := b.clickAuthLandingAction(record, trace, stepID, []string{
				"log in with a one-time code",
				"login with a one-time code",
				"one-time code",
				"email me a code",
			}, nil, state); err != nil {
				return flowStepOutcome{Err: err}
			}
			time.Sleep(1500 * time.Millisecond)
			continue
		}
		if boolValue(surface["email_stage"]) && email != "" {
			emailSurfaceHits++
			if err := b.fillAndSubmitEmail(record, trace, stepID, email, state); err != nil {
				if shouldEscalateAuthSubmit(err, emailSurfaceHits, "email_submit_not_found") {
					if err := b.forceSubmitForm(record, trace, stepID, "", []string{
						"input[name='email']",
						"input[type='email']",
						"input[autocomplete='email']",
					}, "oauth email form submit fallback failed", "oauth_email_submit_fallback_failed", state); err != nil {
						return flowStepOutcome{Err: err}
					}
				} else {
					return flowStepOutcome{Err: err}
				}
			}
			continue
		}
		if boolValue(surface["password_stage"]) && password != "" {
			passwordSurfaceHits++
			if err := b.fillAndSubmitPassword(record, trace, stepID, password, state); err != nil {
				if shouldTreatPasswordFlowErrorAsTransient(err, currentURL) {
					time.Sleep(1500 * time.Millisecond)
					continue
				}
				if shouldEscalateAuthSubmit(err, passwordSurfaceHits, "password_submit_not_found") {
					if err := b.forceSubmitForm(record, trace, stepID, passwordActionContains(currentURL), []string{
						"input[name='password']",
						"input[type='password']",
						"input[autocomplete='current-password']",
						"input[autocomplete='new-password']",
					}, "oauth password form submit fallback failed", "oauth_password_submit_fallback_failed", state); err != nil {
						return flowStepOutcome{Err: err}
					}
				} else {
					return flowStepOutcome{Err: err}
				}
			} else if passwordSurfaceHits >= 2 && passwordActionContains(currentURL) != "" {
				if err := b.forceSubmitForm(record, trace, stepID, passwordActionContains(currentURL), []string{
					"input[name='password']",
					"input[type='password']",
					"input[autocomplete='current-password']",
					"input[autocomplete='new-password']",
				}, "oauth password form submit recovery failed", "oauth_password_submit_recovery_failed", state); err != nil {
					return flowStepOutcome{Err: err}
				}
			}
			continue
		}
		if boolValue(surface["auth_landing"]) || boolValue(surface["login_cta"]) || boolValue(surface["signup_cta"]) {
			if err := b.clickAuthLandingAction(record, trace, stepID, []string{
				"log in",
				"login",
				"continue",
				"continue with email",
				"email",
			}, []string{
				"login",
				"log-in",
				"signin",
				"sign-in",
			}, state); err != nil {
				return flowStepOutcome{Err: err}
			}
			time.Sleep(1500 * time.Millisecond)
			continue
		}
		time.Sleep(1200 * time.Millisecond)
	}
	return flowStepOutcome{
		Err: &model.NormalizedError{
			Category:  "flow_error",
			Code:      "oauth_surface_unresolved",
			Message:   "register_oauth_auth did not reach a known surface",
			Retriable: true,
		},
	}
}

func (b *API) runRegisterOAuthFinalizeFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	otpCode := asString(input["otp_code"])
	surface, err := b.inspectSurface(record, trace, stepID, state)
	if err != nil {
		return flowStepOutcome{Err: err}
	}
	surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
	if err != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
	}
	if terminal := classifyTerminalSurface(surface); terminal != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
	}
	if boolValue(surface["otp_stage"]) {
		if otpCode == "" {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
				Err: &model.NormalizedError{
					Category:  "flow_error",
					Code:      "otp_code_required",
					Message:   "register_oauth_finalize requires otp_code when the auth surface is at email verification",
					Retriable: true,
				},
			}
		}
		if err := b.fillAndSubmitOtp(record, trace, stepID, otpCode, state); err != nil {
			return flowStepOutcome{Err: err}
		}
		for round := 0; round < 18 && time.Now().Before(deadline); round++ {
			time.Sleep(1200 * time.Millisecond)
			surface, err = b.inspectSurface(record, trace, stepID, state)
			if err != nil {
				return flowStepOutcome{Err: err}
			}
			surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
			if err != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
			}
			if terminal := classifyTerminalSurface(surface); terminal != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
			}
			if boolValue(surface["callback"]) {
				state.RegisterOAuth = surface
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "callback_reached",
					},
				}
			}
			if isConsentSurface(surface) {
				break
			}
		}
	}
	if isConsentSurface(surface) {
		if err := b.clickAuthLandingAction(record, trace, stepID, []string{
			"continue",
			"allow",
			"accept",
			"authorize",
			"approve",
		}, []string{
			"/consent",
		}, state); err != nil {
			return flowStepOutcome{Err: err}
		}
		for round := 0; round < 18 && time.Now().Before(deadline); round++ {
			time.Sleep(1200 * time.Millisecond)
			surface, err = b.inspectSurface(record, trace, stepID, state)
			if err != nil {
				return flowStepOutcome{Err: err}
			}
			surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
			if err != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
			}
			if terminal := classifyTerminalSurface(surface); terminal != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
			}
			if boolValue(surface["callback"]) {
				state.RegisterOAuth = surface
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "callback_reached",
					},
				}
			}
		}
	}
	if boolValue(surface["callback"]) {
		state.RegisterOAuth = surface
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary: map[string]any{
				"surface": surface,
				"state":   "callback_reached",
			},
		}
	}
	return flowStepOutcome{
		Artifacts: collectSurfaceArtifacts(surface),
		Summary:   map[string]any{"surface": surface},
		Err: &model.NormalizedError{
			Category:  "flow_error",
			Code:      "oauth_callback_not_reached",
			Message:   "register_oauth_finalize requires callback surface",
			Retriable: true,
		},
	}
}

func (b *API) runRepairLoginFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	authInput := asMap(input["auth"])
	auth := map[string]any{}
	for key, value := range authInput {
		auth[key] = value
	}
	email := coalesce(asString(input["email"]), asString(auth["email"]))
	password := coalesce(asString(input["password"]), asString(auth["password"]))
	mailboxRef := coalesce(asString(input["mailbox_ref"]), asString(auth["mailbox_ref"]))
	if email != "" {
		auth["email"] = email
	}
	if password != "" {
		auth["password"] = password
	}
	if mailboxRef != "" {
		auth["mailbox_ref"] = mailboxRef
	}

	startURL := asString(input["startup_url"])
	if startURL != "" {
		if outcome := b.navigateFlowStep(record, trace, stepID, startURL, state); outcome.Err != nil {
			return outcome
		}
	}

	remaining := time.Until(deadline)
	if remaining <= 0 {
		return flowStepOutcome{
			Err: &model.NormalizedError{
				Category:  "timeout",
				Code:      "repair_login_timeout",
				Message:   "repair_login timed out before runtime execution",
				Retriable: true,
			},
		}
	}

	runtimeInput := map[string]any{
		"auth": auth,
	}
	if captchaProvider := coalesce(asString(input["captcha_provider"]), record.CaptchaProvider, "turnstile-solver-camoufox"); captchaProvider != "" {
		runtimeInput["captcha_provider"] = captchaProvider
	}
	if browserBackend := asString(input["browser_backend"]); browserBackend != "" {
		runtimeInput["browser_backend"] = browserBackend
	}

	status, err := b.executePrimitiveStep(
		record,
		trace,
		stepID,
		"repair_login",
		nil,
		runtimeInput,
		int(remaining.Milliseconds()),
		state,
	)
	if err != nil {
		return flowStepOutcome{Err: err}
	}

	result := mergedProviderResponse(status.Result)
	repairState := nestedMap(result, "state")
	callbackURL := coalesce(lookupString(result, "callback_url"), lookupString(repairState, "callback_url"))
	if callbackURL == "" {
		return flowStepOutcome{
			Summary: map[string]any{
				"result": result,
			},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "repair_callback_missing",
				Message:   "repair_login completed without callback_url",
				Retriable: true,
			},
		}
	}

	resolvedEmail := coalesce(lookupString(result, "email"), lookupString(repairState, "email"), email)
	resolvedMailboxRef := coalesce(lookupString(result, "mailbox_ref"), lookupString(repairState, "mailbox_ref"), mailboxRef)
	mode := coalesce(lookupString(result, "mode"), lookupString(repairState, "mode"))
	runner := coalesce(lookupString(result, "runner"), lookupString(repairState, "runner"))
	currentURL := coalesce(
		lookupString(nestedMap(status.Result, "resource"), "url"),
		lookupString(repairState, "current_url"),
		startURL,
	)

	state.RepairLoginState = result
	artifacts := map[string]any{}
	if currentURL != "" {
		artifacts["url"] = currentURL
	}
	if callbackURL != "" {
		artifacts["callback_url"] = callbackURL
	}
	if resolvedEmail != "" {
		artifacts["email"] = resolvedEmail
	}
	if resolvedMailboxRef != "" {
		artifacts["mailbox_ref"] = resolvedMailboxRef
	}
	if mode != "" {
		artifacts["mode"] = mode
	}
	if runner != "" {
		artifacts["runner"] = runner
	}
	return flowStepOutcome{
		Artifacts: artifacts,
		Summary: map[string]any{
			"state":        "callback_reached",
			"callback_url": callbackURL,
			"mode":         mode,
			"runner":       runner,
		},
	}
}

func (b *API) runOpenAIWebLoginFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	authInput := asMap(input["auth"])
	auth := map[string]any{}
	for key, value := range authInput {
		auth[key] = value
	}
	email := coalesce(asString(input["email"]), asString(auth["email"]))
	password := coalesce(asString(input["password"]), asString(auth["password"]))
	mailboxRef := coalesce(asString(input["mailbox_ref"]), asString(auth["mailbox_ref"]))
	if email != "" {
		auth["email"] = email
	}
	if password != "" {
		auth["password"] = password
	}
	if mailboxRef != "" {
		auth["mailbox_ref"] = mailboxRef
	}

	startURL := coalesce(asString(input["startup_url"]), "https://auth.openai.com/log-in-or-create-account")
	remaining := time.Until(deadline)
	if remaining <= 0 {
		return flowStepOutcome{
			Err: &model.NormalizedError{
				Category:  "timeout",
				Code:      "openai_web_login_timeout",
				Message:   "openai_web_login timed out before runtime execution",
				Retriable: true,
			},
		}
	}

	runtimeInput := map[string]any{
		"auth":        auth,
		"startup_url": startURL,
	}
	if captchaProvider := coalesce(asString(input["captcha_provider"]), record.CaptchaProvider, "turnstile-solver-camoufox"); captchaProvider != "" {
		runtimeInput["captcha_provider"] = captchaProvider
	}
	if browserBackend := asString(input["browser_backend"]); browserBackend != "" {
		runtimeInput["browser_backend"] = browserBackend
	}

	status, err := b.executePrimitiveStep(
		record,
		trace,
		stepID,
		"openai_web_login",
		nil,
		runtimeInput,
		int(remaining.Milliseconds()),
		state,
	)
	if err != nil {
		return flowStepOutcome{Err: err}
	}

	result := mergedProviderResponse(status.Result)
	loginState := nestedMap(result, "state")
	targetURL := coalesce(
		lookupString(result, "target_url"),
		lookupString(loginState, "target_url"),
		lookupString(nestedMap(status.Result, "resource"), "url"),
		lookupString(loginState, "current_url"),
	)
	if targetURL == "" {
		return flowStepOutcome{
			Summary: map[string]any{
				"result": result,
			},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "openai_web_login_target_missing",
				Message:   "openai_web_login completed without target_url",
				Retriable: true,
			},
		}
	}

	resolvedEmail := coalesce(lookupString(result, "email"), lookupString(loginState, "email"), email)
	resolvedMailboxRef := coalesce(lookupString(result, "mailbox_ref"), lookupString(loginState, "mailbox_ref"), mailboxRef)
	mode := coalesce(lookupString(result, "mode"), lookupString(loginState, "mode"))
	runner := coalesce(lookupString(result, "runner"), lookupString(loginState, "runner"))

	artifacts := map[string]any{
		"url": targetURL,
	}
	if targetURL != "" {
		artifacts["target_url"] = targetURL
	}
	if resolvedEmail != "" {
		artifacts["email"] = resolvedEmail
	}
	if resolvedMailboxRef != "" {
		artifacts["mailbox_ref"] = resolvedMailboxRef
	}
	if mode != "" {
		artifacts["mode"] = mode
	}
	if runner != "" {
		artifacts["runner"] = runner
	}
	return flowStepOutcome{
		Artifacts: artifacts,
		Summary: map[string]any{
			"state":      "logged_in",
			"target_url": targetURL,
			"mode":       mode,
			"runner":     runner,
		},
	}
}

func (b *API) waitForRepairOtpTransition(record *SessionRecord, trace model.Trace, stepID string, state *flowExecutionState, deadline time.Time) (flowStepOutcome, bool) {
	for round := 0; round < 7 && time.Now().Before(deadline); round++ {
		time.Sleep(1200 * time.Millisecond)
		surface, err := b.inspectSurface(record, trace, stepID, state)
		if err != nil {
			return flowStepOutcome{Err: err}, true
		}
		surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
		if err != nil {
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}, true
		}
		if terminal := classifyTerminalSurface(surface); terminal != nil {
			return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}, true
		}
		if boolValue(surface["callback"]) || boolValue(surface["otp_stage"]) {
			state.RepairLoginState = surface
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
			}, true
		}
	}
	return flowStepOutcome{}, false
}

func (b *API) runRepairFinalizeFlowStep(record *SessionRecord, trace model.Trace, stepID string, input map[string]any, state *flowExecutionState, deadline time.Time) flowStepOutcome {
	otpCode := asString(input["otp_code"])
	surface, err := b.inspectSurface(record, trace, stepID, state)
	if err != nil {
		return flowStepOutcome{Err: err}
	}
	surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
	if err != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
	}
	if terminal := classifyTerminalSurface(surface); terminal != nil {
		return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
	}
	if boolValue(surface["otp_stage"]) {
		if otpCode == "" {
			return flowStepOutcome{
				Artifacts: collectSurfaceArtifacts(surface),
				Summary: map[string]any{
					"surface": surface,
					"state":   "otp_pending",
				},
				Err: &model.NormalizedError{
					Category:  "flow_error",
					Code:      "otp_code_required",
					Message:   "repair_finalize requires otp_code when the auth surface is at email verification",
					Retriable: true,
				},
			}
		}
		if err := b.fillAndSubmitOtp(record, trace, stepID, otpCode, state); err != nil {
			return flowStepOutcome{Err: err}
		}
		for round := 0; round < 6 && time.Now().Before(deadline); round++ {
			time.Sleep(1200 * time.Millisecond)
			surface, err = b.inspectSurface(record, trace, stepID, state)
			if err != nil {
				return flowStepOutcome{Err: err}
			}
			surface, err = b.recoverChallengeSurface(record, trace, stepID, surface, state, deadline)
			if err != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: err}
			}
			if terminal := classifyTerminalSurface(surface); terminal != nil {
				return flowStepOutcome{Artifacts: collectSurfaceArtifacts(surface), Summary: map[string]any{"surface": surface}, Err: terminal}
			}
			if boolValue(surface["callback"]) {
				return flowStepOutcome{
					Artifacts: collectSurfaceArtifacts(surface),
					Summary: map[string]any{
						"surface": surface,
						"state":   "callback_reached",
					},
				}
			}
		}
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary:   map[string]any{"surface": surface},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "otp_submit_timeout",
				Message:   "repair_finalize submitted otp but did not advance to callback",
				Retriable: true,
			},
		}
	}
	if !boolValue(surface["callback"]) {
		return flowStepOutcome{
			Artifacts: collectSurfaceArtifacts(surface),
			Summary:   map[string]any{"surface": surface},
			Err: &model.NormalizedError{
				Category:  "flow_error",
				Code:      "callback_not_reached",
				Message:   "repair_finalize requires callback surface",
				Retriable: true,
			},
		}
	}
	return flowStepOutcome{
		Artifacts: collectSurfaceArtifacts(surface),
		Summary:   map[string]any{"surface": surface},
	}
}

func (b *API) navigateFlowStep(record *SessionRecord, trace model.Trace, stepID, url string, state *flowExecutionState) flowStepOutcome {
	_, err := b.executePrimitiveStep(record, trace, stepID, "navigate", map[string]any{"url": url}, nil, 60000, state)
	if err != nil {
		return flowStepOutcome{Err: err}
	}
	return flowStepOutcome{}
}

func (b *API) inspectSurface(record *SessionRecord, trace model.Trace, stepID string, state *flowExecutionState) (map[string]any, *model.NormalizedError) {
	status, err := b.executePrimitiveStep(record, trace, stepID, "evaluate_script", nil, map[string]any{
		"script": jsInspectBrowserSurface,
		"arg":    map[string]any{},
	}, 20000, state)
	if err != nil {
		return nil, err
	}
	value := primitiveResultValue(status)
	surface := asMap(value)
	state.LastSurface = surface
	return surface, nil
}

func (b *API) recoverChallengeSurface(record *SessionRecord, trace model.Trace, stepID string, surface map[string]any, state *flowExecutionState, deadline time.Time) (map[string]any, *model.NormalizedError) {
	if !boolValue(surface["challenge"]) {
		return surface, nil
	}
	recoveryDeadline := time.Now().Add(challengeGracePeriod)
	if deadline.Before(recoveryDeadline) {
		recoveryDeadline = deadline
	}
	lastSurface := surface
	for time.Now().Before(recoveryDeadline) {
		time.Sleep(1500 * time.Millisecond)
		nextSurface, err := b.inspectSurface(record, trace, stepID, state)
		if err != nil {
			return lastSurface, err
		}
		lastSurface = nextSurface
		if !boolValue(nextSurface["challenge"]) {
			return nextSurface, nil
		}
	}
	return lastSurface, &model.NormalizedError{
		Category:  "business_terminal_error",
		Code:      "blocked_challenge_page",
		Message:   "blocked challenge page",
		Retriable: true,
	}
}

func isAuthSurfaceURL(url string) bool {
	lower := strings.ToLower(strings.TrimSpace(url))
	return strings.Contains(lower, "platform.openai.com/login") || strings.Contains(lower, "auth.openai.com")
}

func isIndeterminateAuthSurface(surface map[string]any) bool {
	if len(surface) == 0 {
		return true
	}
	if boolValue(surface["email_stage"]) || boolValue(surface["password_stage"]) || boolValue(surface["otp_stage"]) || boolValue(surface["profile_stage"]) || boolValue(surface["about_you"]) || boolValue(surface["callback"]) || boolValue(surface["auth_landing"]) || boolValue(surface["challenge"]) || boolValue(surface["broken_surface"]) || boolValue(surface["phone_wall"]) || boolValue(surface["unsupported_email"]) || boolValue(surface["account_deactivated"]) {
		return false
	}
	if len(asSlice(surface["button_texts"])) > 0 {
		return false
	}
	if asString(surface["text_excerpt"]) != "" {
		return false
	}
	return true
}

func (b *API) fillAndSubmitEmail(record *SessionRecord, trace model.Trace, stepID, email string, state *flowExecutionState) *model.NormalizedError {
	selectors := []string{
		"input[name='email']",
		"input[type='email']",
		"input[autocomplete='email']",
	}
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsNativeAuthFillEmail, map[string]any{
		"value":  email,
		"submit": true,
	}, 20000, state)
	if err == nil && boolValue(value["ok"]) {
		return nil
	}
	if err := b.nativeInputTextFirstMatching(record, trace, stepID, selectors, email, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsFillFirstMatchingInput, map[string]any{
			"selectors": selectors,
			"value":     email,
		}, 20000, state)
		if scriptErr != nil {
			return scriptErr
		}
		if err := ensureScriptOK("email_input_not_found", "email input not found on auth surface", value, false); err != nil {
			return err
		}
	}
	if err := b.nativeSubmitFirst(record, trace, stepID, []string{
		"button[type='submit']",
		"input[type='submit']",
		"form button[type='submit']",
	}, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsClickFirstMatchingButton, map[string]any{
			"selectors": []string{
				"button[type='submit']",
				"form button",
			},
			"text_variants": []string{"continue", "next", "create", "sign up", "login", "log in"},
		}, 15000, state)
		if scriptErr != nil {
			return scriptErr
		}
		return ensureScriptOK("email_submit_not_found", "email submit action not found on auth surface", value, true)
	}
	return nil
}

func (b *API) fillAndSubmitPassword(record *SessionRecord, trace model.Trace, stepID, password string, state *flowExecutionState) *model.NormalizedError {
	selectors := []string{
		"input[name='password']",
		"input[type='password']",
		"input[autocomplete='current-password']",
		"input[autocomplete='new-password']",
	}
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsNativeAuthFillPassword, map[string]any{
		"value":  password,
		"submit": true,
	}, 20000, state)
	if err == nil && boolValue(value["ok"]) {
		return nil
	}
	if err := b.nativeInputTextFirstMatching(record, trace, stepID, selectors, password, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsFillFirstMatchingInput, map[string]any{
			"selectors": selectors,
			"value":     password,
		}, 20000, state)
		if scriptErr != nil {
			return scriptErr
		}
		if err := ensureScriptOK("password_input_not_found", "password input not found on auth surface", value, false); err != nil {
			return err
		}
	}
	if err := b.nativeSubmitFirst(record, trace, stepID, []string{
		"button[type='submit']",
		"input[type='submit']",
		"form button[type='submit']",
	}, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsClickFirstMatchingButton, map[string]any{
			"selectors": []string{
				"button[type='submit']",
				"form button",
			},
			"text_variants": []string{"continue", "next", "verify", "log in", "login"},
		}, 15000, state)
		if scriptErr != nil {
			return scriptErr
		}
		return ensureScriptOK("password_submit_not_found", "password submit action not found on auth surface", value, true)
	}
	return nil
}

func (b *API) fillAndSubmitOtp(record *SessionRecord, trace model.Trace, stepID, otpCode string, state *flowExecutionState) *model.NormalizedError {
	selectors := []string{
		"input[name='code']",
		"input[name='otp']",
		"input[inputmode='numeric']",
		"input[autocomplete='one-time-code']",
		"input[name='verifyCode']",
		"input[type='text']",
	}
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsNativeSubmitCode, map[string]any{
		"value":  otpCode,
		"submit": true,
	}, 20000, state)
	if err == nil && boolValue(value["ok"]) {
		return nil
	}
	if err := b.nativeInputTextFirstMatching(record, trace, stepID, selectors, otpCode, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsFillFirstMatchingInput, map[string]any{
			"selectors": selectors,
			"value":     otpCode,
		}, 20000, state)
		if scriptErr != nil {
			return scriptErr
		}
		if err := ensureScriptOK("otp_input_not_found", "otp input not found on auth surface", value, false); err != nil {
			return err
		}
	}
	if err := b.nativeSubmitFirst(record, trace, stepID, []string{
		"button[type='submit']",
		"input[type='submit']",
		"form button[type='submit']",
	}, state); err != nil {
		value, scriptErr := b.executeScriptPrimitive(record, trace, stepID, jsClickFirstMatchingButton, map[string]any{
			"selectors": []string{
				"button[type='submit']",
				"form button",
			},
			"text_variants": []string{"continue", "next", "verify"},
		}, 15000, state)
		if scriptErr != nil {
			return scriptErr
		}
		if err := ensureScriptOK("otp_submit_not_found", "otp submit action not found on auth surface", value, true); err != nil {
			if fallbackErr := b.forceSubmitForm(record, trace, stepID, "/email-verification", selectors, "otp form submit fallback failed", "otp_submit_fallback_failed", state); fallbackErr != nil {
				return fallbackErr
			}
		}
	}
	return nil
}

func (b *API) nativeInputTextFirstMatching(record *SessionRecord, trace model.Trace, stepID string, selectors []string, value string, state *flowExecutionState) *model.NormalizedError {
	var lastErr *model.NormalizedError
	for _, selector := range selectors {
		if selector == "" {
			continue
		}
		_, err := b.executePrimitiveStep(record, trace, stepID, "input_text", map[string]any{"selector": selector}, map[string]any{"value": value}, 15000, state)
		if err == nil {
			return nil
		}
		lastErr = err
	}
	return lastErr
}

func (b *API) nativeSubmitFirst(record *SessionRecord, trace model.Trace, stepID string, selectors []string, state *flowExecutionState) *model.NormalizedError {
	var lastErr *model.NormalizedError
	for _, selector := range selectors {
		if selector == "" {
			continue
		}
		_, err := b.executePrimitiveStep(record, trace, stepID, "click", map[string]any{"selector": selector}, nil, 15000, state)
		if err == nil {
			return nil
		}
		lastErr = err
	}
	_, err := b.executePrimitiveStep(record, trace, stepID, "submit", nil, nil, 15000, state)
	if err == nil {
		return nil
	}
	if lastErr != nil {
		return lastErr
	}
	return err
}

func (b *API) fillAboutYou(record *SessionRecord, trace model.Trace, stepID, fullName, birthdate string, state *flowExecutionState) *model.NormalizedError {
	age := ageValueFromBirthdate(birthdate)
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsFillAboutYouForm, map[string]any{
		"full_name": fullName,
		"birthdate": birthdate,
		"age":       age,
	}, 25000, state)
	if err != nil {
		return err
	}
	if err := ensureScriptOK("about_you_input_not_found", "about-you form inputs not found", value, false); err != nil {
		return err
	}
	value, err = b.executeScriptPrimitive(record, trace, stepID, jsClickFirstMatchingButton, map[string]any{
		"selectors": []string{
			"button[type='submit']",
			"form button",
		},
		"text_variants": []string{"continue", "next", "submit"},
	}, 15000, state)
	if err != nil {
		return err
	}
	if err := ensureScriptOK("about_you_submit_not_found", "about-you submit action not found", value, true); err != nil {
		value, fallbackErr := b.executeScriptPrimitive(record, trace, stepID, jsForceSubmitAboutYouForm, map[string]any{
			"full_name": fullName,
			"birthdate": birthdate,
			"age":       age,
		}, 20000, state)
		if fallbackErr != nil {
			return fallbackErr
		}
		return ensureScriptOK("about_you_submit_fallback_failed", "about-you submit fallback failed", value, true)
	}
	return nil
}

func (b *API) clickAuthLandingAction(record *SessionRecord, trace model.Trace, stepID string, texts []string, hrefs []string, state *flowExecutionState) *model.NormalizedError {
	return b.clickAuthLandingActionFiltered(record, trace, stepID, texts, hrefs, nil, state)
}

func (b *API) clickAuthLandingActionFiltered(record *SessionRecord, trace model.Trace, stepID string, texts []string, hrefs []string, forbiddenHrefs []string, state *flowExecutionState) *model.NormalizedError {
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsClickFirstMatchingButton, map[string]any{
		"selectors": []string{
			"button",
			"a[role='button']",
			"a",
			"input[type='submit']",
			"input[type='button']",
		},
		"text_variants":        texts,
		"href_variants":        hrefs,
		"forbid_href_variants": forbiddenHrefs,
	}, 15000, state)
	if err != nil {
		return err
	}
	return ensureScriptOK("auth_landing_cta_not_found", "auth landing action not found", value, true)
}

func (b *API) executeScriptPrimitive(record *SessionRecord, trace model.Trace, stepID, script string, arg map[string]any, timeoutMS int, state *flowExecutionState) (map[string]any, *model.NormalizedError) {
	status, err := b.executePrimitiveStep(record, trace, stepID, "evaluate_script", nil, map[string]any{
		"script": script,
		"arg":    arg,
	}, timeoutMS, state)
	if err != nil {
		return nil, err
	}
	return asMap(primitiveResultValue(status)), nil
}

func (b *API) forceSubmitForm(record *SessionRecord, trace model.Trace, stepID, actionContains string, selectors []string, message, code string, state *flowExecutionState) *model.NormalizedError {
	value, err := b.executeScriptPrimitive(record, trace, stepID, jsForceSubmitForm, map[string]any{
		"action_contains": actionContains,
		"selectors":       selectors,
	}, 15000, state)
	if err != nil {
		return err
	}
	return ensureScriptOK(code, message, value, true)
}

func ensureScriptOK(code, message string, value map[string]any, retriable bool) *model.NormalizedError {
	if boolValue(value["ok"]) {
		return nil
	}
	raw := map[string]any{}
	if len(value) > 0 {
		raw["script_result"] = value
	}
	return &model.NormalizedError{
		Category:  "flow_error",
		Code:      code,
		Message:   message,
		Retriable: retriable,
		Raw:       raw,
	}
}

func (b *API) executePrimitiveStep(record *SessionRecord, trace model.Trace, stepID, action string, target, input map[string]any, timeoutMS int, state *flowExecutionState) (model.TaskStatusData, *model.NormalizedError) {
	b.service.RecordFlowEvent("primitive_step_started", "info", fmt.Sprintf("primitive %s started", action), trace, map[string]any{
		"step_id": stepID,
		"action":  action,
	})
	payload := map[string]any{
		"action":        action,
		"resource_kind": record.ResourceKind,
		"resource_id":   record.ResourceID,
		"target":        target,
		"input":         input,
	}
	if action == "navigate" {
		if url := asString(target["url"]); url != "" {
			payload["url"] = url
		}
	}
	if action == "wait_for" && timeoutMS > 0 {
		payload["timeout_s"] = float64(timeoutMS) / 1000.0
	}
	status, err := b.executeOnSession(record, model.ExecuteRequest{
		Mode: "direct",
		Target: model.TargetSpec{
			RuntimeID: record.RuntimeID,
		},
		Operation: model.OperationSpec{
			Kind:    action,
			Payload: payload,
		},
		Metadata: model.MetadataSpec{
			Caller: "easybrowser-flow",
			Tags:   []string{"browser_session_flow", stepID, action},
		},
		Timeout: model.TimeoutSpec{
			TotalMS: timeoutMS,
		},
	}, resolveExecutionTimeout(timeoutMS, defaultPrimitiveTimout))
	primitiveEntry := map[string]any{
		"step_id": stepID,
		"action":  action,
	}
	if status.TaskID != "" {
		primitiveEntry["task_id"] = status.TaskID
	}
	if err != nil {
		normalized := normalizeFlowError(action, err)
		primitiveEntry["status"] = "failed"
		primitiveEntry["error"] = map[string]any{
			"category": normalized.Category,
			"code":     normalized.Code,
			"message":  normalized.Message,
		}
		state.PrimitiveTrace = append(state.PrimitiveTrace, primitiveEntry)
		b.service.RecordFlowEvent("primitive_step_failed", "warn", normalized.Message, trace, map[string]any{
			"step_id":        stepID,
			"action":         action,
			"error_category": normalized.Category,
			"error_code":     normalized.Code,
		})
		return model.TaskStatusData{}, normalized
	}
	record.refreshFromTask(status)
	primitiveEntry["status"] = status.State
	primitiveEntry["result"] = status.Result
	state.PrimitiveTrace = append(state.PrimitiveTrace, primitiveEntry)
	b.service.RecordFlowEvent("primitive_step_completed", "info", fmt.Sprintf("primitive %s completed", action), trace, map[string]any{
		"step_id": stepID,
		"action":  action,
		"task_id": status.TaskID,
	})
	return status, nil
}

func normalizeFlowError(action string, err error) *model.NormalizedError {
	if err == nil {
		return nil
	}
	if httpErr, ok := err.(*HTTPError); ok {
		category := "primitive_flow_error"
		if httpErr.StatusCode >= 500 {
			category = "primitive_transport_error"
		}
		return &model.NormalizedError{
			Category:  category,
			Code:      coalesce(httpErr.Code, "primitive_failed"),
			Message:   fmt.Sprintf("%s: %s", action, httpErr.Message),
			Retriable: httpErr.StatusCode >= 500,
			Raw: map[string]any{
				"http_status": httpErr.StatusCode,
				"stage":       httpErr.Stage,
			},
		}
	}
	return &model.NormalizedError{
		Category:  "primitive_transport_error",
		Code:      "primitive_failed",
		Message:   fmt.Sprintf("%s: %v", action, err),
		Retriable: true,
	}
}

func classifyTerminalSurface(surface map[string]any) *model.NormalizedError {
	switch {
	case boolValue(surface["account_deactivated"]):
		return &model.NormalizedError{Category: "business_terminal_error", Code: "account_deactivated", Message: "account_deactivated"}
	case boolValue(surface["unsupported_email"]):
		return &model.NormalizedError{Category: "business_terminal_error", Code: "unsupported_email", Message: "unsupported_email"}
	case boolValue(surface["phone_wall"]):
		return &model.NormalizedError{Category: "business_terminal_error", Code: "phone_wall", Message: "phone wall encountered"}
	case boolValue(surface["challenge"]):
		return &model.NormalizedError{Category: "business_terminal_error", Code: "blocked_challenge_page", Message: "blocked challenge page", Retriable: true}
	default:
		return nil
	}
}

func collectSurfaceArtifacts(surface map[string]any) map[string]any {
	if len(surface) == 0 {
		return nil
	}
	out := map[string]any{}
	for _, key := range []string{"url", "title", "callback_url"} {
		if value := asString(surface[key]); value != "" {
			out[key] = value
		}
	}
	for _, key := range []string{"phone_wall", "unsupported_email", "account_deactivated", "otp_stage", "otp_login_option", "email_stage", "password_stage", "profile_stage", "about_you", "callback", "auth_landing", "session_ended", "login_cta", "signup_cta", "broken_surface", "text_excerpt", "button_texts"} {
		if _, ok := surface[key]; ok {
			out[key] = surface[key]
		}
	}
	return out
}

func primitiveResultValue(status model.TaskStatusData) any {
	if status.Result == nil {
		return nil
	}
	if value, ok := status.Result["value"]; ok {
		return value
	}
	if providerResponse, ok := status.Result["provider_response"].(map[string]any); ok {
		if value, ok := providerResponse["value"]; ok {
			return value
		}
	}
	if response, ok := status.Result["response"].(map[string]any); ok {
		if value, ok := response["value"]; ok {
			return value
		}
	}
	return nil
}

func mergedProviderResponse(result map[string]any) map[string]any {
	if len(result) == 0 {
		return nil
	}
	providerResponse := nestedMap(result, "provider_response")
	if len(providerResponse) == 0 {
		return result
	}
	merged := map[string]any{}
	for key, value := range providerResponse {
		merged[key] = value
	}
	for key, value := range result {
		if key == "provider_response" {
			continue
		}
		if _, exists := merged[key]; !exists {
			merged[key] = value
		}
	}
	return merged
}

func asMap(value any) map[string]any {
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return map[string]any{}
}

func asSlice(value any) []any {
	switch typed := value.(type) {
	case []any:
		return typed
	case []string:
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			out = append(out, item)
		}
		return out
	default:
		return nil
	}
}

func asString(value any) string {
	if value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return strings.TrimSpace(fmt.Sprint(value))
	}
}

func boolValue(value any) bool {
	if typed, ok := value.(bool); ok {
		return typed
	}
	if asString(value) == "true" {
		return true
	}
	return false
}

func shouldEscalateAuthSubmit(err *model.NormalizedError, surfaceHits int, primaryCode string) bool {
	if err == nil || surfaceHits <= 1 {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(err.Code), primaryCode)
}

func shouldBootstrapDirectAuth(currentURL string, surfaceHits int, reloadedIndeterminateSurface bool, directAuthBootstrapUsed bool) bool {
	if directAuthBootstrapUsed || !reloadedIndeterminateSurface || surfaceHits < 2 {
		return false
	}
	lowerURL := strings.ToLower(strings.TrimSpace(currentURL))
	return strings.Contains(lowerURL, "platform.openai.com/login")
}

func shouldTreatPasswordFlowErrorAsTransient(err *model.NormalizedError, currentURL string) bool {
	if err == nil {
		return false
	}
	lowerURL := strings.ToLower(strings.TrimSpace(currentURL))
	if !strings.Contains(lowerURL, "/password") {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(err.Code)) {
	case "password_input_not_found", "password_submit_recovery_failed", "password_submit_fallback_failed":
		return true
	default:
		return false
	}
}

func passwordActionContains(currentURL string) string {
	lowerURL := strings.ToLower(strings.TrimSpace(currentURL))
	switch {
	case strings.Contains(lowerURL, "/create-account/password"):
		return "/create-account/password"
	case strings.Contains(lowerURL, "/log-in/password"):
		return "/log-in/password"
	case strings.Contains(lowerURL, "/password"):
		return "/password"
	default:
		return ""
	}
}

func isRegisterAccountReadySurface(surface map[string]any) bool {
	currentURL := strings.ToLower(strings.TrimSpace(asString(surface["url"])))
	if currentURL == "" {
		return false
	}
	if boolValue(surface["callback"]) || boolValue(surface["otp_stage"]) || boolValue(surface["profile_stage"]) || boolValue(surface["about_you"]) || boolValue(surface["email_stage"]) || boolValue(surface["password_stage"]) {
		return false
	}
	if strings.Contains(currentURL, "platform.openai.com") && !strings.Contains(currentURL, "/login") && !strings.Contains(currentURL, "/about-you") && !strings.Contains(currentURL, "/auth/callback") {
		return true
	}
	if strings.Contains(currentURL, "chatgpt.com") && !strings.Contains(currentURL, "/auth/") {
		return true
	}
	return false
}

func isConsentSurface(surface map[string]any) bool {
	if boolValue(surface["callback"]) {
		return false
	}
	currentURL := strings.ToLower(strings.TrimSpace(asString(surface["url"])))
	if strings.Contains(currentURL, "/consent") {
		return true
	}
	return boolValue(surface["consent_stage"])
}

func ageValueFromBirthdate(birthdate string) string {
	parts := strings.Split(strings.TrimSpace(birthdate), "-")
	if len(parts) != 3 {
		return ""
	}
	year, month, day := 0, 0, 0
	if _, err := fmt.Sscanf(birthdate, "%d-%d-%d", &year, &month, &day); err != nil || year <= 0 {
		return ""
	}
	now := time.Now().UTC()
	age := now.Year() - year
	if int(now.Month()) < month || (int(now.Month()) == month && now.Day() < day) {
		age--
	}
	if age < 18 {
		age = 18
	}
	if age > 99 {
		age = 99
	}
	return fmt.Sprintf("%d", age)
}

const jsInspectBrowserSurface = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const anyVisible = (selectors) => {
    for (const selector of selectors || []) {
      try {
        const el = document.querySelector(selector);
        if (visible(el)) return true;
      } catch (e) {}
    }
    return false;
  };
  const text = String(document.body?.innerText || '').slice(0, 24000);
  const lower = text.toLowerCase();
  const href = String(location.href || '');
  const title = String(document.title || '');
  const callback = href.includes('/auth/callback') || href.includes('chatgpt.com/api/auth/callback/openai') || href.includes('localhost:1455/auth/callback');
  const buttonText = Array.from(document.querySelectorAll('button, a[role="button"], a, input[type="submit"], input[type="button"]'))
    .filter(visible)
    .map((node) => String(node.innerText || node.textContent || node.getAttribute?.('aria-label') || node.getAttribute?.('title') || node.value || '').trim().toLowerCase())
    .filter(Boolean)
    .slice(0, 24);
  const hasButtonText = (needle) => buttonText.some((txt) => txt.includes(String(needle || '').toLowerCase()));
  const sessionEnded = lower.includes('your session has ended');
  const authLanding = sessionEnded || lower.includes('continue by logging in') || lower.includes('create account') || lower.includes('sign up') || lower.includes('continue with email') || lower.includes('use chatgpt.com without an account');
  const brokenSurface = lower.includes('route error') || lower.includes('invalid content type') || lower.includes('this page isn’t working') || lower.includes("this page isn't working") || lower.includes("didn't send any data") || lower.includes('didn’t send any data');
  const challenge = lower.includes('verify you are human') || lower.includes('security verification') || lower.includes('attention required') || lower.includes('just a moment') || title.toLowerCase().includes('just a moment') || href.includes('__cf_chl') || href.includes('/cdn-cgi/challenge-platform');
  return {
    url: href,
    title,
    callback,
    callback_url: callback ? href : '',
    email_stage: anyVisible(["input[name='email']", "input[type='email']", "input[autocomplete='email']"]),
    password_stage: anyVisible(["input[name='password']", "input[type='password']", "input[autocomplete='current-password']", "input[autocomplete='new-password']"]),
    otp_stage: anyVisible(["input[name='code']", "input[name='otp']", "input[inputmode='numeric']", "input[autocomplete='one-time-code']", "input[name='verifyCode']"]),
    profile_stage: href.includes('/about-you') || anyVisible(["form[action='/about-you']", "input[name='name']", "input[autocomplete='name']"]),
    about_you: href.includes('/about-you') || lower.includes('about you'),
    auth_landing: authLanding,
    session_ended: sessionEnded,
    login_cta: hasButtonText('log in') || hasButtonText('login'),
    signup_cta: hasButtonText('create account') || hasButtonText('create free account') || hasButtonText('sign up') || hasButtonText('continue with email'),
    otp_login_option: lower.includes('log in with a one-time code') || lower.includes('login with a one-time code') || lower.includes('email me a code') || buttonText.some((txt) => txt.includes('one-time code')),
    consent_stage: href.includes('/consent'),
    phone_wall: lower.includes('add-phone') || lower.includes('phone number required') || lower.includes('verify your phone') || lower.includes('phone number'),
    unsupported_email: lower.includes('unsupported_email') || lower.includes('unsupported email') || lower.includes('email is unsupported'),
    account_deactivated: lower.includes('account_deactivated'),
    challenge,
    broken_surface: brokenSurface,
    text_excerpt: text.slice(0, 600),
    button_texts: buttonText
  };
}`

const jsFillFirstMatchingInput = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const selectors = Array.isArray(arg?.selectors) ? arg.selectors : [];
  const value = String(arg?.value ?? '');
  for (const selector of selectors) {
    let el = null;
    try { el = document.querySelector(selector); } catch (e) { el = null; }
    if (!visible(el)) continue;
    try { el.scrollIntoView({ block: 'center' }); } catch (e) {}
    try { el.focus(); } catch (e) {}
    try {
      const proto = (el.tagName || '').toLowerCase() === 'textarea'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (typeof setter === 'function') setter.call(el, value);
      else el.value = value;
    } catch (e) {
      try { el.value = value; } catch (_) {}
    }
    try { el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value })); } catch (e) {
      try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
    }
    try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
    try { el.dispatchEvent(new Event('blur', { bubbles: true })); } catch (e) {}
    try { el.blur(); } catch (e) {}
    return { ok: true, selector, value: String(el.value || '') };
  }
  return { ok: false };
}`

const jsNativeAuthFillEmail = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const textOf = (el) => String(el?.innerText || el?.textContent || '').trim();
  const expectedEmail = String(arg?.value || '');
  const shouldSubmit = !!arg?.submit;
  const selectors = [
    "input[type='email']",
    "input[name*='email']",
    "input[id*='email']",
    "input[autocomplete='email']",
    "input[autocomplete='username']",
    "input[placeholder*='email' i]"
  ];
  let input = null;
  for (const selector of selectors) {
    let node = null;
    try { node = document.querySelector(selector); } catch (e) { node = null; }
    if (visible(node)) {
      input = node;
      break;
    }
  }
  if (!input) return { ok: false, stage: 'missing-email', url: String(location.href || '') };
  const proto = (input.tagName || '').toLowerCase() === 'textarea'
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  try { input.focus(); } catch (e) {}
  if (typeof nativeSetter === 'function') nativeSetter.call(input, expectedEmail);
  else input.value = expectedEmail;
  try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
  try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  try { input.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
  try { input.blur(); } catch (e) {}
  let action = 'filled';
  let buttonText = '';
  if (shouldSubmit) {
    const candidateSelectors = [
      "button[type='submit'][name='intent'][value='email']",
      "button[name='intent'][value='email']",
      "button[type='submit']:not([disabled])",
      "button:not([disabled])",
      "[role='button']"
    ];
    let button = null;
    for (const selector of candidateSelectors) {
      let nodes = [];
      try { nodes = Array.from(document.querySelectorAll(selector)); } catch (e) { nodes = []; }
      for (const node of nodes) {
        if (!visible(node)) continue;
        const txt = textOf(node);
        if (!txt || !/continue|create account|sign up|next|password/i.test(txt)) continue;
        button = node;
        buttonText = txt.slice(0, 120);
        break;
      }
      if (button) break;
    }
    if (button) {
      try { button.click(); action = 'click_button'; } catch (e) {}
    }
    if (action === 'filled') {
      try {
        const form = input.closest('form');
        if (form && typeof form.requestSubmit === 'function') {
          form.requestSubmit();
          action = 'request_submit';
        } else if (form) {
          form.submit();
          action = 'form_submit';
        }
      } catch (e) {}
    }
    if (action === 'filled') {
      try {
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
        input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
        action = 'dispatch_enter';
      } catch (e) {}
    }
  }
  return { ok: true, stage: 'email', action, buttonText, url: String(location.href || '') };
}`

const jsNativeAuthFillPassword = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const textOf = (el) => String(el?.innerText || el?.textContent || '').trim();
  const expectedPassword = String(arg?.value || '');
  const shouldSubmit = !!arg?.submit;
  const selectors = [
    "input[type='password']",
    "input[name*='password']",
    "input[id*='password']",
    "input[autocomplete='current-password']",
    "input[autocomplete='new-password']",
    "input[aria-label*='password' i]"
  ];
  let input = null;
  for (const selector of selectors) {
    let node = null;
    try { node = document.querySelector(selector); } catch (e) { node = null; }
    if (visible(node)) {
      input = node;
      break;
    }
  }
  if (!input) return { ok: false, stage: 'missing-password', url: String(location.href || '') };
  const proto = (input.tagName || '').toLowerCase() === 'textarea'
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  try { input.focus(); } catch (e) {}
  if (typeof nativeSetter === 'function') nativeSetter.call(input, expectedPassword);
  else input.value = expectedPassword;
  try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
  try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  try { input.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
  try { input.blur(); } catch (e) {}
  let action = 'filled';
  let buttonText = '';
  if (shouldSubmit) {
    const candidateSelectors = [
      "button[type='submit']:not([disabled])",
      "button:not([disabled])",
      "[role='button']"
    ];
    let button = null;
    for (const selector of candidateSelectors) {
      let nodes = [];
      try { nodes = Array.from(document.querySelectorAll(selector)); } catch (e) { nodes = []; }
      for (const node of nodes) {
        if (!visible(node)) continue;
        const txt = textOf(node);
        if (!txt) continue;
        if (/show password|edit/i.test(txt)) continue;
        if (!/continue|create account|sign up|log in|login|next|verify|finish creating account/i.test(txt)) continue;
        button = node;
        buttonText = txt.slice(0, 120);
        break;
      }
      if (button) break;
    }
    if (button) {
      try { button.click(); action = 'click_button'; } catch (e) {}
    }
    if (action === 'filled') {
      try {
        const form = input.closest('form');
        if (form && typeof form.requestSubmit === 'function') {
          form.requestSubmit();
          action = 'request_submit';
        } else if (form) {
          form.submit();
          action = 'form_submit';
        }
      } catch (e) {}
    }
    if (action === 'filled') {
      try {
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
        input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
        action = 'dispatch_enter';
      } catch (e) {}
    }
  }
  return { ok: true, stage: 'password', action, buttonText, url: String(location.href || '') };
}`

const jsNativeSubmitCode = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const expectedCode = String(arg?.value || '');
  const shouldSubmit = !!arg?.submit;
  const singleSelectors = [
    "input[autocomplete='one-time-code']",
    "input[inputmode='numeric'][maxlength='6']",
    "input[name*='code' i]",
    "input[id*='code' i]",
    "input[aria-label*='code' i]",
    "input[placeholder*='code' i]"
  ];
  const segmentedSelectors = [
    "div[role='group'] input[inputmode='numeric'][maxlength='1']"
  ];
  let single = null;
  for (const selector of singleSelectors) {
    let node = null;
    try { node = document.querySelector(selector); } catch (e) { node = null; }
    if (visible(node)) {
      single = node;
      break;
    }
  }
  let segmented = [];
  for (const selector of segmentedSelectors) {
    try {
      segmented = Array.from(document.querySelectorAll(selector)).filter((node) => visible(node));
    } catch (e) {
      segmented = [];
    }
    if (segmented.length >= 6) break;
  }
  if (!single && segmented.length < 6) {
    return { ok: false, stage: 'missing-code', url: String(location.href || '') };
  }
  let action = 'filled';
  if (single) {
    const proto = (single.tagName || '').toLowerCase() === 'textarea'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    try { single.focus(); } catch (e) {}
    if (typeof nativeSetter === 'function') nativeSetter.call(single, expectedCode);
    else single.value = expectedCode;
    try { single.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
    try { single.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
    try { single.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
    try { single.blur(); } catch (e) {}
    if (shouldSubmit) {
      try {
        const buttons = Array.from(document.querySelectorAll("button[type='submit'],input[type='submit'],button,[role='button']"));
        const submitButton = buttons.find((node) => {
          if (!visible(node)) return false;
          const txt = String(node.innerText || node.textContent || node.value || '').trim();
          return /continue|verify|next/i.test(txt);
        });
        if (submitButton) {
          submitButton.click();
          action = 'click_button';
        }
      } catch (e) {}
      try {
        if (action === 'filled') {
          const form = single.closest('form');
          if (form && typeof form.requestSubmit === 'function') {
            form.requestSubmit();
            action = 'request_submit';
          } else if (form) {
            form.submit();
            action = 'form_submit';
          }
        }
      } catch (e) {}
      if (action === 'filled') {
        try {
          single.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
          single.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
          single.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
          action = 'dispatch_enter';
        } catch (e) {}
      }
    }
    return { ok: true, stage: 'code', mode: 'single', action, url: String(location.href || '') };
  }
  const digits = String(expectedCode || '').replace(/\D+/g, '').slice(0, 6).split('');
  segmented.slice(0, digits.length).forEach((node, idx) => {
    const digit = digits[idx] || '';
    const proto = (node.tagName || '').toLowerCase() === 'textarea'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    try { node.focus(); } catch (e) {}
    if (typeof nativeSetter === 'function') nativeSetter.call(node, digit);
    else node.value = digit;
    try { node.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
    try { node.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  });
  if (shouldSubmit) {
    try {
      const last = segmented[Math.min(segmented.length - 1, Math.max(0, digits.length - 1))];
      last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
      last.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
      last.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
      action = 'dispatch_enter';
    } catch (e) {}
  }
  return { ok: true, stage: 'code', mode: 'segmented', action, url: String(location.href || '') };
}`

const jsClickFirstMatchingButton = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const selectors = Array.isArray(arg?.selectors) ? arg.selectors : [];
  const texts = (Array.isArray(arg?.text_variants) ? arg.text_variants : []).map((x) => String(x || '').toLowerCase());
  const hrefs = (Array.isArray(arg?.href_variants) ? arg.href_variants : []).map((x) => String(x || '').toLowerCase());
  const forbidHrefs = (Array.isArray(arg?.forbid_href_variants) ? arg.forbid_href_variants : []).map((x) => String(x || '').toLowerCase());
  const nodeText = (node) => String(node?.innerText || node?.textContent || node?.getAttribute?.('aria-label') || node?.getAttribute?.('title') || node?.value || '').trim().toLowerCase();
  const nodeHref = (node) => String(node?.getAttribute?.('href') || '').trim().toLowerCase();
  const matches = (node) => {
    const txt = nodeText(node);
    const href = nodeHref(node);
    if (forbidHrefs.length && forbidHrefs.some((needle) => href.includes(needle))) return { ok: false, txt, href };
    if (texts.length && texts.some((needle) => txt.includes(needle))) return { ok: true, txt, href };
    if (hrefs.length && hrefs.some((needle) => href.includes(needle))) return { ok: true, txt, href };
    return { ok: texts.length === 0 && hrefs.length === 0, txt, href };
  };
  for (const selector of selectors) {
    let nodes = [];
    try { nodes = Array.from(document.querySelectorAll(selector)); } catch (e) { nodes = []; }
    for (const node of nodes) {
      if (!visible(node)) continue;
      const match = matches(node);
      if (!match.ok) continue;
      const txt = match.txt;
      const href = match.href;
      try { node.scrollIntoView({ block: 'center' }); } catch (e) {}
      node.click();
      return { ok: true, selector, text: txt, href };
    }
  }
  const generic = Array.from(document.querySelectorAll('button, a[role="button"], input[type="submit"]'));
  for (const node of generic) {
    if (!visible(node)) continue;
    const match = matches(node);
    if (!match.ok) continue;
    const txt = match.txt;
    const href = match.href;
    try { node.scrollIntoView({ block: 'center' }); } catch (e) {}
    node.click();
    return { ok: true, selector: '<generic>', text: txt, href };
  }
  return { ok: false, button_texts: Array.from(document.querySelectorAll('button, a[role=\"button\"], a, input[type=\"submit\"], input[type=\"button\"]')).filter(visible).map((node) => nodeText(node)).filter(Boolean).slice(0, 24) };
}`

const jsFillAboutYouForm = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled && (el.offsetParent !== null || st.position === 'fixed'));
  };
  const fullName = String(arg?.full_name ?? '');
  const birthdate = String(arg?.birthdate ?? '');
  const age = String(arg?.age ?? '');
  const setValue = (selector, value) => {
    let el = null;
    try { el = document.querySelector(selector); } catch (e) { el = null; }
    if (!visible(el)) return false;
    el.focus();
    if ('value' in el) el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const nameDone = setValue("input[name='name']", fullName) || setValue("input[autocomplete='name']", fullName);
  if (age) {
    setValue("input[name='age']", age) || setValue("input[inputmode='numeric']", age);
  }
  if (birthdate) {
    setValue("input[name='birthday']", birthdate);
    setValue("input[name='birthdate']", birthdate);
    const hidden = document.querySelector("input[type='hidden'][name='birthday']");
    if (hidden && 'value' in hidden) {
      hidden.value = birthdate;
      hidden.dispatchEvent(new Event('input', { bubbles: true }));
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
  return { ok: nameDone, birthdate, age };
}`

const jsForceSubmitAboutYouForm = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled);
  };
  const fullName = String(arg?.full_name || '');
  const birthdate = String(arg?.birthdate || '');
  const age = String(arg?.age || '');
  const form = document.querySelector("form[action='/about-you']") || document.querySelector('form');
  if (!form) return { ok: false, reason: 'form_not_found' };
  const setValue = (selector, value) => {
    let el = null;
    try { el = form.querySelector(selector); } catch (e) { el = null; }
    if (!visible(el)) return false;
    try { el.focus(); } catch (e) {}
    try {
      const proto = (el.tagName || '').toLowerCase() === 'textarea'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (typeof setter === 'function') setter.call(el, value);
      else el.value = value;
    } catch (e) {
      try { el.value = value; } catch (_) {}
    }
    try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
    try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
    return true;
  };
  setValue("input[name='name']", fullName) || setValue("input[autocomplete='name']", fullName) || setValue("input[type='text']", fullName);
  if (age) {
    setValue("input[name='age']", age) || setValue("input[inputmode='numeric']", age);
  }
  const match = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(birthdate || '');
  if (match) {
    try {
      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'birthday';
      hidden.value = birthdate;
      form.appendChild(hidden);
    } catch (e) {}
  }
  const submit = form.querySelector("button[type='submit'],input[type='submit'],button");
  if (submit && visible(submit)) {
    try { submit.click(); } catch (e) {}
    return { ok: true, mode: 'click' };
  }
  try {
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
    return { ok: true, mode: 'submit' };
  } catch (e) {
    return { ok: false, reason: String(e || '') };
  }
}`

const jsForceSubmitForm = `(arg) => {
  const visible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && !el.disabled);
  };
  const actionContains = String(arg?.action_contains || '').toLowerCase();
  const selectors = Array.isArray(arg?.selectors) ? arg.selectors : [];
  const forms = Array.from(document.querySelectorAll('form'));
  let form = null;
  if (actionContains) {
    form = forms.find((candidate) => String(candidate.getAttribute('action') || '').toLowerCase().includes(actionContains)) || null;
  }
  if (!form) {
    for (const selector of selectors) {
      let el = null;
      try { el = document.querySelector(selector); } catch (e) { el = null; }
      if (el && typeof el.closest === 'function') {
        form = el.closest('form');
        if (form) break;
      }
    }
  }
  if (!form) form = document.querySelector('form');
  if (!form) return { ok: false, reason: 'form_not_found' };
  const submit = form.querySelector('button[type="submit"],input[type="submit"]');
  if (submit && visible(submit)) {
    try {
      submit.click();
      return {
        ok: true,
        mode: 'click',
        text: String(submit.innerText || submit.textContent || submit.value || '').trim().toLowerCase(),
      };
    } catch (e) {}
  }
  try {
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
    return { ok: true, mode: 'submit' };
  } catch (e) {
    return { ok: false, reason: String(e || '') };
  }
}`
