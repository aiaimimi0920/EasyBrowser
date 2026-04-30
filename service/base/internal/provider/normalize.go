package provider

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

func CanonicalActionName(action string) string {
	switch strings.ToLower(strings.TrimSpace(action)) {
	case "", "task":
		return ""
	case "version":
		return "get_version"
	case "open_resource", "list_resources", "get_resource", "close_resource":
		return strings.ToLower(strings.TrimSpace(action))
	case "open_url", "new_page", "create_tab":
		return "open_page"
	case "navigate_page", "navigate_resource":
		return "navigate"
	case "close_page", "close_tab":
		return "close_target"
	case "activate_page", "activate_tab":
		return "activate_target"
	case "list_tabs":
		return "list_pages"
	case "close_session", "release_session":
		return "request_release"
	default:
		return strings.ToLower(strings.TrimSpace(action))
	}
}

func NormalizeExecutionResult(providerID, runtimeID string, raw map[string]any) map[string]any {
	if raw == nil {
		return nil
	}

	action := CanonicalActionName(stringValue(raw["action"]))
	response := sanitizeProviderValue(providerID, raw["response"])
	resourceKind := CanonicalResourceKind(stringValue(raw["resource_kind"]))
	if resourceKind == "" {
		resourceKind = inferResourceKind(providerID, response)
	}

	out := map[string]any{
		"provider_id": providerID,
		"runtime_id":  coalesce(stringValue(raw["runtime_id"]), runtimeID),
	}
	if action != "" {
		out["action"] = action
	}
	if attach := normalizeAttach(raw["attach"]); attach != nil {
		out["attach"] = attach
	}

	metadata := collectMetadata(providerID, raw, response)
	if len(metadata) > 0 {
		out["metadata"] = metadata
	}
	if response != nil {
		out["provider_response"] = response
	}

	switch action {
	case "get_version", "health":
		out["resource_kind"] = "provider"
		out["resource"] = normalizeProviderResource(providerID, response, metadata)
	case "list_resources":
		out["resource_kind"] = coalesceResourceKindForResult(resourceKind)
		if resourceKind == "session" {
			resources := normalizeSessionList(response)
			out["resources"] = resources
			out["count"] = len(resources)
		} else {
			resources := normalizePageList(response, runtimeID)
			out["resources"] = resources
			out["count"] = len(resources)
		}
	case "get_resource":
		out["resource_kind"] = coalesceResourceKindForResult(resourceKind)
		if resourceKind == "session" {
			resource := normalizeSessionResource(response, coalesce(stringValue(raw["session_id"]), stringValue(raw["resource_id"])))
			if resource != nil {
				out["resource"] = resource
				if id := stringValue(resource["id"]); id != "" {
					out["resource_id"] = id
				}
			}
		} else {
			resource := normalizePageResource(response, coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"])), "open")
			if resource != nil {
				out["resource"] = resource
				if id := stringValue(resource["id"]); id != "" {
					out["resource_id"] = id
				}
			}
		}
	case "open_resource":
		out["resource_kind"] = coalesceResourceKindForResult(resourceKind)
		if resourceKind == "session" {
			resource := normalizeSessionResource(response, coalesce(stringValue(raw["session_id"]), stringValue(raw["resource_id"])))
			if resource != nil {
				out["resource"] = resource
				if id := stringValue(resource["id"]); id != "" {
					out["resource_id"] = id
				}
			}
		} else {
			resource := normalizePageResource(response, coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"])), "open")
			if resource != nil {
				out["resource"] = resource
				if id := stringValue(resource["id"]); id != "" {
					out["resource_id"] = id
				}
			}
		}
	case "close_resource":
		out["resource_kind"] = coalesceResourceKindForResult(resourceKind)
		if resourceKind == "session" {
			resource := normalizeSessionResource(response, coalesce(stringValue(raw["session_id"]), stringValue(raw["resource_id"])))
			if resource != nil {
				out["resource"] = resource
				if id := stringValue(resource["id"]); id != "" {
					out["resource_id"] = id
				}
			}
		} else {
			resourceID := coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"]))
			if responseMap, ok := response.(map[string]any); ok {
				resourceID = coalesce(resourceID, lookupString(responseMap, "id"))
			}
			out["resource"] = map[string]any{
				"id":     resourceID,
				"kind":   "page",
				"status": "closed",
			}
			if resourceID != "" {
				out["resource_id"] = resourceID
			}
		}
	case "list_pages", "list_targets":
		out["resource_kind"] = "page"
		resources := normalizePageList(response, runtimeID)
		out["resources"] = resources
		out["count"] = len(resources)
	case "open_page":
		out["resource_kind"] = "page"
		resource := normalizePageResource(response, coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"])), "open")
		if resource != nil {
			out["resource"] = resource
			if id := stringValue(resource["id"]); id != "" {
				out["resource_id"] = id
			}
		}
	case "close_target":
		out["resource_kind"] = "page"
		resourceID := coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"]))
		if responseMap, ok := response.(map[string]any); ok {
			resourceID = coalesce(resourceID, lookupString(responseMap, "id"))
		}
		resource := map[string]any{
			"id":     resourceID,
			"kind":   "page",
			"status": "closed",
		}
		out["resource"] = resource
		if resourceID != "" {
			out["resource_id"] = resourceID
		}
	case "activate_target":
		out["resource_kind"] = "page"
		resource := normalizePageResource(response, coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"])), "active")
		if resource != nil {
			out["resource"] = resource
			if id := stringValue(resource["id"]); id != "" {
				out["resource_id"] = id
			}
		}
	case "navigate", "click", "input_text", "submit", "wait_for", "read_value", "evaluate_script":
		out["resource_kind"] = "page"
		resource := normalizePageResource(response, coalesce(stringValue(raw["target_id"]), stringValue(raw["resource_id"])), "open")
		if resource != nil {
			out["resource"] = resource
			if id := stringValue(resource["id"]); id != "" {
				out["resource_id"] = id
			}
		}
		if responseMap, ok := response.(map[string]any); ok {
			if value, ok := responseMap["value"]; ok {
				out["value"] = value
			}
			if detail, ok := responseMap["detail"]; ok {
				out["detail"] = detail
			}
		}
		for _, key := range []string{"state", "email", "mode", "runner", "callback_url", "mailbox_ref", "auth_file_path", "wait_update_file_path"} {
			if value, ok := raw[key]; ok && value != nil && value != "" {
				out[key] = sanitizeProviderValue(providerID, value)
			}
		}
		for _, key := range []string{"auth", "stage1", "stage2"} {
			if value, ok := raw[key]; ok && value != nil {
				out[key] = sanitizeProviderValue(providerID, value)
			}
		}
	case "list_sessions":
		out["resource_kind"] = "session"
		resources := normalizeSessionList(response)
		out["resources"] = resources
		out["count"] = len(resources)
	case "create_session", "get_session", "request_release", "update_session":
		out["resource_kind"] = "session"
		resource := normalizeSessionResource(response, coalesce(stringValue(raw["session_id"]), stringValue(raw["resource_id"])))
		if resource != nil {
			out["resource"] = resource
			if id := stringValue(resource["id"]); id != "" {
				out["resource_id"] = id
			}
		}
	default:
		kind := inferResourceKind(providerID, response)
		if kind != "" {
			out["resource_kind"] = kind
		}
	}

	return out
}

func collectMetadata(providerID string, raw map[string]any, response any) map[string]any {
	metadata := map[string]any{}

	for _, key := range []string{"browser_kind", "browser_path", "debug_port", "browser_version", "provider", "os", "headless", "ws_endpoint"} {
		if value, ok := raw[key]; ok && value != nil && value != "" {
			metadata[key] = value
		}
	}

	if responseMap, ok := response.(map[string]any); ok {
		switch providerID {
		case "browserbase":
			copyIfPresent(responseMap, metadata, "projectId", "project_id")
			copyIfPresent(responseMap, metadata, "region", "region")
			copyIfPresent(responseMap, metadata, "keepAlive", "keep_alive")
		case "chrome", "camoufox", "geekez":
			copyIfPresent(responseMap, metadata, "Browser", "browser")
			copyIfPresent(responseMap, metadata, "Provider", "provider")
			copyIfPresent(responseMap, metadata, "Headless", "headless")
			copyIfPresent(responseMap, metadata, "OS", "os")
		}
	}

	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func normalizeAttach(value any) map[string]any {
	item, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	out := map[string]any{}
	copyIfPresent(item, out, "transport", "transport")
	copyIfPresent(item, out, "scope", "scope")
	copyIfPresent(item, out, "endpoint", "endpoint")
	copyIfPresent(item, out, "browser_name", "browser_name")
	copyIfPresent(item, out, "target_id", "target_id")
	copyIfPresent(item, out, "resource_id", "resource_id")
	copyIfPresent(item, out, "page_url", "page_url")
	if len(out) == 0 {
		return nil
	}
	return out
}

func normalizeProviderResource(providerID string, response any, metadata map[string]any) map[string]any {
	resource := map[string]any{
		"id":     providerID,
		"kind":   "provider",
		"status": "ready",
	}
	if metadata != nil {
		resource["attributes"] = metadata
	}
	if responseMap, ok := response.(map[string]any); ok {
		if version := coalesce(lookupString(responseMap, "Browser"), lookupString(responseMap, "browser")); version != "" {
			resource["version"] = version
		}
	}
	return resource
}

func normalizePageList(response any, runtimeID string) []map[string]any {
	items, ok := response.([]any)
	if !ok {
		return nil
	}
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		resource := normalizePageResource(item, "", "open")
		if resource == nil {
			continue
		}
		if runtimeID != "" {
			resource["runtime_id"] = runtimeID
		}
		out = append(out, resource)
	}
	return out
}

func normalizePageResource(response any, fallbackID, status string) map[string]any {
	item, ok := response.(map[string]any)
	if !ok {
		return nil
	}
	id := coalesce(lookupString(item, "id"), fallbackID)
	resource := map[string]any{
		"id":     id,
		"kind":   "page",
		"status": status,
	}
	if title := lookupString(item, "title"); title != "" {
		resource["title"] = title
	}
	if url := lookupString(item, "url"); url != "" {
		resource["url"] = url
	}
	attributes := map[string]any{}
	copyIfPresent(item, attributes, "type", "type")
	if len(attributes) > 0 {
		resource["attributes"] = attributes
	}
	return resource
}

func normalizeSessionList(response any) []map[string]any {
	items, ok := response.([]any)
	if !ok {
		return nil
	}
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		resource := normalizeSessionResource(item, "")
		if resource == nil {
			continue
		}
		out = append(out, resource)
	}
	return out
}

func normalizeSessionResource(response any, fallbackID string) map[string]any {
	item, ok := response.(map[string]any)
	if !ok {
		return nil
	}
	id := coalesce(lookupString(item, "id"), fallbackID)
	resource := map[string]any{
		"id":     id,
		"kind":   "session",
		"status": lookupString(item, "status"),
	}

	attributes := map[string]any{}
	copyIfPresent(item, attributes, "projectId", "project_id")
	copyIfPresent(item, attributes, "region", "region")
	copyIfPresent(item, attributes, "keepAlive", "keep_alive")
	copyIfPresent(item, attributes, "createdAt", "created_at")
	copyIfPresent(item, attributes, "updatedAt", "updated_at")
	copyIfPresent(item, attributes, "startedAt", "started_at")
	copyIfPresent(item, attributes, "endedAt", "ended_at")
	copyIfPresent(item, attributes, "expiresAt", "expires_at")
	copyIfPresent(item, attributes, "proxyBytes", "proxy_bytes")
	copyIfPresent(item, attributes, "userMetadata", "user_metadata")
	if len(attributes) > 0 {
		resource["attributes"] = attributes
	}
	return resource
}

func inferResourceKind(providerID string, response any) string {
	if providerID == "browserbase" {
		return "session"
	}
	if _, ok := response.([]any); ok {
		return "page"
	}
	if responseMap, ok := response.(map[string]any); ok {
		if _, exists := responseMap["url"]; exists {
			return "page"
		}
	}
	return ""
}

func coalesceResourceKindForResult(kind string) string {
	if strings.TrimSpace(kind) == "" {
		return "resource"
	}
	return kind
}

func sanitizeProviderValue(providerID string, value any) any {
	data, err := json.Marshal(value)
	if err != nil {
		return value
	}
	var clone any
	if err := json.Unmarshal(data, &clone); err != nil {
		return value
	}
	sanitizeInPlace(providerID, &clone)
	return clone
}

func sanitizeInPlace(providerID string, node *any) {
	switch typed := (*node).(type) {
	case map[string]any:
		for key, value := range typed {
			if shouldRedact(providerID, key) {
				typed[key] = "[REDACTED]"
				continue
			}
			child := value
			sanitizeInPlace(providerID, &child)
			typed[key] = child
		}
	case []any:
		for i, value := range typed {
			child := value
			sanitizeInPlace(providerID, &child)
			typed[i] = child
		}
	}
}

func shouldRedact(providerID, key string) bool {
	normalized := strings.ToLower(strings.TrimSpace(key))
	switch providerID {
	case "browserbase":
		return normalized == "connecturl" || normalized == "signingkey" || normalized == "seleniumremoteurl" || normalized == "debuggerurl" || normalized == "debuggerfullscreenurl" || normalized == "downloadurl"
	case "chrome", "geekez":
		return normalized == "websocketdebuggerurl" || normalized == "devtoolsfrontendurl"
	default:
		return false
	}
}

func copyIfPresent(src, dst map[string]any, srcKey, dstKey string) {
	if value, ok := src[srcKey]; ok && value != nil && value != "" {
		dst[dstKey] = value
	}
}

func lookupString(src map[string]any, key string) string {
	return stringValue(src[key])
}

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	case json.Number:
		return typed.String()
	case float64:
		if typed == float64(int64(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case float32:
		if typed == float32(int64(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(float64(typed), 'f', -1, 32)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case int32:
		return strconv.FormatInt(int64(typed), 10)
	case bool:
		return strconv.FormatBool(typed)
	default:
		return ""
	}
}

func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
