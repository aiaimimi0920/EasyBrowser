package browser

import (
	"errors"
	"testing"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

func newTestBrowserAPI() *API {
	api := New(service.New(), nil)
	api.sessions["sess-test"] = &SessionRecord{
		SessionID:    "sess-test",
		RuntimeID:    "rt-test",
		ProviderID:   "chrome",
		ResourceID:   "page-test",
		ResourceKind: "page",
		CreatedAt:    time.Now().UTC(),
		ExpiresAt:    time.Now().UTC().Add(time.Minute),
	}
	return api
}

func TestStepSessionRejectsHighLevelStepType(t *testing.T) {
	api := newTestBrowserAPI()

	_, err := api.StepSession("sess-test", model.BrowserSessionStepRequest{
		StepType: "repair_full",
	})
	if err == nil {
		t.Fatal("expected deprecated high-level step error")
	}
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected HTTPError, got %T", err)
	}
	if httpErr.Code != "deprecated_high_level_step_type" {
		t.Fatalf("unexpected error code %q", httpErr.Code)
	}
}

func TestExecuteSessionFlowRejectsInvalidFlowType(t *testing.T) {
	api := newTestBrowserAPI()

	_, err := api.ExecuteSessionFlow("sess-test", model.BrowserSessionFlowRequest{
		FlowType: "unknown",
		Steps: []model.BrowserSessionFlowStep{
			{StepType: "register_auth"},
		},
	})
	if err == nil {
		t.Fatal("expected invalid flow type error")
	}
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected HTTPError, got %T", err)
	}
	if httpErr.Code != "invalid_request" {
		t.Fatalf("unexpected error code %q", httpErr.Code)
	}
}

func TestExecuteSessionFlowRejectsInvalidStepForFlowType(t *testing.T) {
	api := newTestBrowserAPI()

	_, err := api.ExecuteSessionFlow("sess-test", model.BrowserSessionFlowRequest{
		FlowType: "repair",
		Steps: []model.BrowserSessionFlowStep{
			{StepType: "register_auth"},
		},
	})
	if err == nil {
		t.Fatal("expected invalid flow definition error")
	}
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected HTTPError, got %T", err)
	}
	if httpErr.Code != "invalid_flow_definition" {
		t.Fatalf("unexpected error code %q", httpErr.Code)
	}
}

func TestExecuteSessionFlowAcceptsLoginFlow(t *testing.T) {
	api := newTestBrowserAPI()

	accepted, err := api.ExecuteSessionFlow("sess-test", model.BrowserSessionFlowRequest{
		FlowType: "login",
		Steps: []model.BrowserSessionFlowStep{
			{StepType: "openai_web_login"},
		},
	})
	if err != nil {
		t.Fatalf("expected login flow to be accepted, got %v", err)
	}
	if accepted.TaskID == "" {
		t.Fatal("expected accepted flow task id")
	}
}

func TestShouldEscalateAuthSubmit(t *testing.T) {
	err := &model.NormalizedError{Code: "email_submit_not_found"}
	if shouldEscalateAuthSubmit(err, 1, "email_submit_not_found") {
		t.Fatal("did not expect escalation on first surface hit")
	}
	if !shouldEscalateAuthSubmit(err, 2, "email_submit_not_found") {
		t.Fatal("expected escalation after repeated email surface when primary submit was not found")
	}
	if shouldEscalateAuthSubmit(&model.NormalizedError{Code: "email_input_not_found"}, 3, "email_submit_not_found") {
		t.Fatal("did not expect escalation for unrelated error code")
	}
}

func TestShouldBootstrapDirectAuth(t *testing.T) {
	if shouldBootstrapDirectAuth("https://platform.openai.com/login", 1, true, false) {
		t.Fatal("did not expect bootstrap before repeated blank surface hits")
	}
	if shouldBootstrapDirectAuth("https://platform.openai.com/login", 2, false, false) {
		t.Fatal("did not expect bootstrap before reloaded indeterminate surface")
	}
	if !shouldBootstrapDirectAuth("https://platform.openai.com/login", 2, true, false) {
		t.Fatal("expected direct auth bootstrap after repeated blank platform login surface")
	}
	if shouldBootstrapDirectAuth("https://auth.openai.com/log-in", 2, true, false) {
		t.Fatal("did not expect bootstrap when already on direct auth host")
	}
	if shouldBootstrapDirectAuth("https://platform.openai.com/login", 3, true, true) {
		t.Fatal("did not expect bootstrap more than once")
	}
}

func TestIsRegisterAccountReadySurface(t *testing.T) {
	if !isRegisterAccountReadySurface(map[string]any{
		"url": "https://platform.openai.com/",
	}) {
		t.Fatal("expected platform home to count as account-ready")
	}
	if !isRegisterAccountReadySurface(map[string]any{
		"url": "https://chatgpt.com/",
	}) {
		t.Fatal("expected chatgpt home to count as account-ready")
	}
	if isRegisterAccountReadySurface(map[string]any{
		"url":         "https://platform.openai.com/login",
		"email_stage": true,
	}) {
		t.Fatal("did not expect login surface to count as account-ready")
	}
	if isRegisterAccountReadySurface(map[string]any{
		"url":       "https://auth.openai.com/email-verification",
		"otp_stage": true,
	}) {
		t.Fatal("did not expect otp stage to count as account-ready")
	}
}

func TestIsConsentSurface(t *testing.T) {
	if !isConsentSurface(map[string]any{
		"url": "https://auth.openai.com/oauth/consent",
	}) {
		t.Fatal("expected consent url to count as consent surface")
	}
	if !isConsentSurface(map[string]any{
		"consent_stage": true,
	}) {
		t.Fatal("expected explicit consent_stage to count as consent surface")
	}
	if isConsentSurface(map[string]any{
		"url":      "http://localhost:1455/auth/callback?code=1",
		"callback": true,
	}) {
		t.Fatal("did not expect callback surface to count as consent surface")
	}
}

func TestMergedProviderResponsePromotesTopLevelFields(t *testing.T) {
	merged := mergedProviderResponse(map[string]any{
		"provider_response": map[string]any{
			"id":  "browser-session-1",
			"url": "https://auth.openai.com/email-verification",
		},
		"callback_url": "http://localhost:1455/auth/callback?code=abc",
		"mailbox_ref":  "mailcreate:demo",
		"mode":         "otp",
		"runner":       "selenium",
	})
	if merged["callback_url"] != "http://localhost:1455/auth/callback?code=abc" {
		t.Fatalf("expected callback_url promoted, got %#v", merged["callback_url"])
	}
	if merged["mailbox_ref"] != "mailcreate:demo" {
		t.Fatalf("expected mailbox_ref promoted, got %#v", merged["mailbox_ref"])
	}
	if merged["url"] != "https://auth.openai.com/email-verification" {
		t.Fatalf("expected provider response url preserved, got %#v", merged["url"])
	}
}
