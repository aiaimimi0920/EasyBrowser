package provider

import (
	"fmt"
	"strings"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
)

type ActionClass string

const (
	ActionClassGeneric  ActionClass = "generic"
	ActionClassProvider ActionClass = "provider"
	ActionClassPage     ActionClass = "page"
	ActionClassSession  ActionClass = "session"
)

func ActionNameFromRequest(request model.ExecuteRequest) string {
	if request.Operation.Payload != nil {
		if action, ok := request.Operation.Payload["action"]; ok {
			if normalized := CanonicalActionName(valueToString(action)); normalized != "" {
				return normalized
			}
		}
	}

	kind := strings.ToLower(strings.TrimSpace(request.Operation.Kind))
	if kind == "" || kind == "task" {
		return ""
	}
	return CanonicalActionName(kind)
}

func ClassifyAction(action string) ActionClass {
	switch CanonicalActionName(action) {
	case "":
		return ActionClassGeneric
	case "health", "get_version":
		return ActionClassProvider
	case "open_resource", "list_resources", "get_resource", "close_resource":
		return ActionClassGeneric
	case "open_page", "list_pages", "list_targets", "activate_target", "close_target", "navigate", "click", "input_text", "submit", "wait_for", "read_value", "evaluate_script":
		return ActionClassPage
	case "list_sessions", "create_session", "get_session", "update_session", "request_release", "api_request":
		return ActionClassSession
	default:
		return ActionClassGeneric
	}
}

func IsHighLevelBrowserAction(action string) bool {
	switch CanonicalActionName(action) {
	case "register_auth", "register_profile", "register_finalize", "register_oauth_auth", "register_oauth_finalize", "register_full", "repair_login", "repair_finalize", "repair_full":
		return true
	default:
		return false
	}
}

func ProviderSupportsAction(providerID string, capabilities model.CapabilityFlags, action string) bool {
	return ProviderSupportsActionForResource(providerID, capabilities, action, "")
}

func ProviderSupportsActionForResource(providerID string, capabilities model.CapabilityFlags, action, resourceKind string) bool {
	action = CanonicalActionName(action)
	resourceKind = CanonicalResourceKind(resourceKind)
	switch providerID {
	case "chrome":
		switch action {
		case "", "health", "get_version", "open_page", "list_pages", "list_targets", "activate_target", "close_target":
			return capabilities.SupportsLocalProcess
		case "open_resource", "list_resources", "get_resource", "close_resource":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		case "navigate":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		case "click", "input_text", "submit", "wait_for", "read_value", "evaluate_script":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		default:
			return false
		}
	case "camoufox", "geekez":
		switch action {
		case "", "health", "get_version", "open_page", "list_pages", "list_targets", "activate_target", "close_target":
			return capabilities.SupportsLocalProcess
		case "open_resource", "list_resources", "get_resource", "close_resource":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		case "navigate":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		case "click", "input_text", "submit", "wait_for", "read_value", "evaluate_script":
			return capabilities.SupportsLocalProcess && (resourceKind == "" || resourceKind == "page")
		default:
			return false
		}
	case "browserbase":
		switch action {
		case "", "health", "list_sessions", "create_session", "get_session", "update_session", "request_release", "api_request":
			return capabilities.SupportsRemoteExecution
		case "open_resource", "list_resources", "get_resource", "close_resource":
			return capabilities.SupportsRemoteExecution && (resourceKind == "" || resourceKind == "session")
		default:
			return false
		}
	default:
		return action == ""
	}
}

func CanonicalResourceKind(kind string) string {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "", "resource":
		return ""
	case "page", "tab":
		return "page"
	case "session":
		return "session"
	case "provider":
		return "provider"
	default:
		return strings.ToLower(strings.TrimSpace(kind))
	}
}

func ResourceKindFromRequest(request model.ExecuteRequest) string {
	if request.Operation.Payload != nil {
		if kind, ok := request.Operation.Payload["resource_kind"]; ok {
			return CanonicalResourceKind(valueToString(kind))
		}
		if kind, ok := request.Operation.Payload["resourceKind"]; ok {
			return CanonicalResourceKind(valueToString(kind))
		}
	}

	switch ClassifyAction(ActionNameFromRequest(request)) {
	case ActionClassPage:
		return "page"
	case ActionClassSession:
		return "session"
	case ActionClassProvider:
		return "provider"
	default:
		return ""
	}
}

func IsGenericResourceAction(action string) bool {
	switch CanonicalActionName(action) {
	case "open_resource", "list_resources", "get_resource", "close_resource":
		return true
	default:
		return false
	}
}

func InferResourceKindForProvider(providerID string) string {
	switch strings.ToLower(strings.TrimSpace(providerID)) {
	case "chrome", "camoufox", "geekez":
		return "page"
	case "browserbase":
		return "session"
	default:
		return ""
	}
}

func SupportsMode(capabilities model.CapabilityFlags, mode string) bool {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "strategy", "":
		return capabilities.SupportsStrategyMode
	case "direct":
		return capabilities.SupportsDirectMode
	default:
		return false
	}
}

func valueToString(value any) string {
	if value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return fmt.Sprint(typed)
	}
}
