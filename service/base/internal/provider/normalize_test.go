package provider

import "testing"

func TestCanonicalActionName(t *testing.T) {
	cases := map[string]string{
		"open_url":        "open_page",
		"new_page":        "open_page",
		"create_tab":      "open_page",
		"close_page":      "close_target",
		"activate_tab":    "activate_target",
		"close_session":   "request_release",
		"release_session": "request_release",
	}

	for input, expected := range cases {
		if got := CanonicalActionName(input); got != expected {
			t.Fatalf("canonical action mismatch for %q: got %q want %q", input, got, expected)
		}
	}
}

func TestNormalizeBrowserbaseSessionResult(t *testing.T) {
	result := NormalizeExecutionResult("browserbase", "rt-browserbase-1", map[string]any{
		"action": "create_session",
		"response": map[string]any{
			"id":                "sess-1",
			"status":            "RUNNING",
			"projectId":         "proj-1",
			"region":            "us-west-2",
			"keepAlive":         false,
			"connectUrl":        "secret-connect",
			"signingKey":        "secret-signing",
			"seleniumRemoteUrl": "secret-selenium",
		},
	})

	if result["resource_kind"] != "session" {
		t.Fatalf("expected session resource kind, got %#v", result["resource_kind"])
	}
	resource, ok := result["resource"].(map[string]any)
	if !ok {
		t.Fatalf("expected resource map, got %#v", result["resource"])
	}
	if resource["id"] != "sess-1" {
		t.Fatalf("expected session id sess-1, got %#v", resource["id"])
	}
	providerResponse := result["provider_response"].(map[string]any)
	if providerResponse["connectUrl"] != "[REDACTED]" {
		t.Fatalf("expected connectUrl redacted, got %#v", providerResponse["connectUrl"])
	}
}

func TestNormalizeChromeOpenPageResult(t *testing.T) {
	result := NormalizeExecutionResult("chrome", "rt-chrome-1", map[string]any{
		"action":     "open_url",
		"target_id":  "page-123",
		"debug_port": 9222,
		"response": map[string]any{
			"id":                   "page-123",
			"title":                "Example Domain",
			"url":                  "https://example.com/",
			"type":                 "page",
			"webSocketDebuggerUrl": "ws://secret",
		},
	})

	if result["action"] != "open_page" {
		t.Fatalf("expected canonical action open_page, got %#v", result["action"])
	}
	resource := result["resource"].(map[string]any)
	if resource["kind"] != "page" {
		t.Fatalf("expected page kind, got %#v", resource["kind"])
	}
	if resource["id"] != "page-123" {
		t.Fatalf("expected page id, got %#v", resource["id"])
	}
	providerResponse := result["provider_response"].(map[string]any)
	if providerResponse["webSocketDebuggerUrl"] != "[REDACTED]" {
		t.Fatalf("expected websocket url redacted, got %#v", providerResponse["webSocketDebuggerUrl"])
	}
}

func TestNormalizeGeekezOpenPageResult(t *testing.T) {
	result := NormalizeExecutionResult("geekez", "rt-geekez-1", map[string]any{
		"action":    "open_resource",
		"target_id": "page-789",
		"response": map[string]any{
			"id":                   "page-789",
			"title":                "GeekEZ Example",
			"url":                  "https://example.com/",
			"type":                 "page",
			"webSocketDebuggerUrl": "ws://secret-geekez",
		},
	})

	resource := result["resource"].(map[string]any)
	if resource["kind"] != "page" {
		t.Fatalf("expected page kind, got %#v", resource["kind"])
	}
	providerResponse := result["provider_response"].(map[string]any)
	if providerResponse["webSocketDebuggerUrl"] != "[REDACTED]" {
		t.Fatalf("expected websocket url redacted, got %#v", providerResponse["webSocketDebuggerUrl"])
	}
}

func TestNormalizeChromeOpenResourcePreservesAttachContract(t *testing.T) {
	result := NormalizeExecutionResult("chrome", "rt-chrome-2", map[string]any{
		"action":      "open_resource",
		"resource_id": "browser-session-123",
		"attach": map[string]any{
			"scope":        "page",
			"transport":    "cdp",
			"endpoint":     "http://127.0.0.1:9222",
			"browser_name": "chromium",
			"resource_id":  "browser-session-123",
			"page_url":     "https://suno.com/create",
		},
		"response": map[string]any{
			"id":    "browser-session-123",
			"title": "Suno | AI Music Generator",
			"url":   "https://suno.com/create",
		},
	})

	attach, ok := result["attach"].(map[string]any)
	if !ok {
		t.Fatalf("expected attach contract map, got %#v", result["attach"])
	}
	if attach["transport"] != "cdp" {
		t.Fatalf("expected attach transport cdp, got %#v", attach["transport"])
	}
	if attach["endpoint"] != "http://127.0.0.1:9222" {
		t.Fatalf("expected attach endpoint preserved, got %#v", attach["endpoint"])
	}
}
