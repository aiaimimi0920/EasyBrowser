package provider

import (
	"testing"

	"github.com/aiaimimi0920/EasyBrowser/internal/model"
)

func TestIsHighLevelBrowserAction(t *testing.T) {
	if !IsHighLevelBrowserAction("repair_full") {
		t.Fatal("expected repair_full to be treated as a high-level browser action")
	}
	if !IsHighLevelBrowserAction("register_auth") {
		t.Fatal("expected register_auth to be treated as a high-level browser action")
	}
	if IsHighLevelBrowserAction("click") {
		t.Fatal("did not expect click to be treated as a high-level browser action")
	}
}

func TestProviderSupportsActionForResourceRejectsHighLevelActionsForProviders(t *testing.T) {
	capabilities := model.CapabilityFlags{SupportsLocalProcess: true}

	if ProviderSupportsActionForResource("chrome", capabilities, "repair_full", "page") {
		t.Fatal("did not expect chrome provider runtime to advertise support for high-level repair_full orchestration")
	}
	if ProviderSupportsActionForResource("camoufox", capabilities, "repair_full", "page") {
		t.Fatal("did not expect camoufox provider runtime to advertise support for high-level repair_full")
	}
	if ProviderSupportsActionForResource("geekez", capabilities, "register_full", "page") {
		t.Fatal("did not expect geekez provider runtime to advertise support for high-level register_full")
	}
	if !ProviderSupportsActionForResource("geekez", capabilities, "click", "page") {
		t.Fatal("expected geekez provider runtime to keep supporting low-level click actions")
	}
}
