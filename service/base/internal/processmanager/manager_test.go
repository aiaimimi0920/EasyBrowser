package processmanager

import (
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

func TestResolveBrowserbaseRuntimeFindsScript(t *testing.T) {
	path := resolveBrowserbaseRuntime("")
	if path == "" {
		t.Fatal("expected browserbase runtime path to be discovered from source tree")
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected runtime path to exist: %v", err)
	}
}

func TestResolveChromeRuntimeFindsScript(t *testing.T) {
	path := resolveChromeRuntime("")
	if path == "" {
		t.Fatal("expected chrome runtime path to be discovered from source tree")
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected runtime path to exist: %v", err)
	}
}

func TestResolveCamoufoxRuntimeFindsScript(t *testing.T) {
	path := resolveCamoufoxRuntime("")
	if path == "" {
		t.Fatal("expected camoufox runtime path to be discovered from source tree")
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected runtime path to exist: %v", err)
	}
}

func TestResolveGeekezRuntimeFindsScript(t *testing.T) {
	path := resolveGeekezRuntime("")
	if path == "" {
		t.Fatal("expected geekez runtime path to be discovered from source tree")
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected runtime path to exist: %v", err)
	}
}

func TestSpawnBrowserbaseRequiresAPIKey(t *testing.T) {
	previous := os.Getenv("BROWSERBASE_API_KEY")
	t.Cleanup(func() {
		if previous == "" {
			_ = os.Unsetenv("BROWSERBASE_API_KEY")
			return
		}
		_ = os.Setenv("BROWSERBASE_API_KEY", previous)
	})
	_ = os.Unsetenv("BROWSERBASE_API_KEY")

	manager := New(service.New())
	_, err := manager.SpawnRuntime("browserbase")
	if !errors.Is(err, service.ErrInvalidRequest) {
		t.Fatalf("expected invalid request error, got %v", err)
	}
}

func TestReadyTimeoutForProviderUsesCamoufoxOverride(t *testing.T) {
	previous := os.Getenv("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS")
	t.Cleanup(func() {
		if previous == "" {
			_ = os.Unsetenv("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS")
			return
		}
		_ = os.Setenv("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS", previous)
	})
	_ = os.Setenv("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS", "65000")

	got := readyTimeoutForProvider("camoufox")
	if got.Milliseconds() != 65000 {
		t.Fatalf("expected camoufox ready timeout override 65000ms, got %dms", got.Milliseconds())
	}
}

func TestDecorateStartupErrorIncludesRecentStderr(t *testing.T) {
	manager := New(service.New())
	child := &childProcess{}
	manager.appendChildLog(child, "stage=build_launch_options")
	manager.appendChildLog(child, "startup failed stage=ws_endpoint_received error=boom")

	err := manager.decorateStartupError(child, "camoufox runtime", "did not become ready in time")
	if err == nil {
		t.Fatal("expected decorated error")
	}
	if !strings.Contains(err.Error(), "recent stderr:") {
		t.Fatalf("expected stderr summary in error, got %v", err)
	}
}

func TestRuntimeLaunchModeUsesProviderOverride(t *testing.T) {
	previousGlobal := os.Getenv("EASYBROWSER_RUNTIME_MODE")
	previousProvider := os.Getenv("EASYBROWSER_CHROME_RUNTIME_MODE")
	t.Cleanup(func() {
		if previousGlobal == "" {
			_ = os.Unsetenv("EASYBROWSER_RUNTIME_MODE")
		} else {
			_ = os.Setenv("EASYBROWSER_RUNTIME_MODE", previousGlobal)
		}
		if previousProvider == "" {
			_ = os.Unsetenv("EASYBROWSER_CHROME_RUNTIME_MODE")
		} else {
			_ = os.Setenv("EASYBROWSER_CHROME_RUNTIME_MODE", previousProvider)
		}
	})

	_ = os.Setenv("EASYBROWSER_RUNTIME_MODE", "local")
	_ = os.Setenv("EASYBROWSER_CHROME_RUNTIME_MODE", "docker")

	if got := runtimeLaunchMode("chrome"); got != "docker" {
		t.Fatalf("expected provider override docker, got %q", got)
	}
}

func TestLocalChromeRuntimeEnvMapsEasyBrowserOverrides(t *testing.T) {
	previousHeadless := os.Getenv("EASYBROWSER_CHROME_HEADLESS")
	previousUc := os.Getenv("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER")
	previousBinary := os.Getenv("EASYBROWSER_CHROME_BINARY_PATH")
	previousDriver := os.Getenv("EASYBROWSER_CHROMEDRIVER_PATH")
	t.Cleanup(func() {
		restoreEnvVar("EASYBROWSER_CHROME_HEADLESS", previousHeadless)
		restoreEnvVar("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER", previousUc)
		restoreEnvVar("EASYBROWSER_CHROME_BINARY_PATH", previousBinary)
		restoreEnvVar("EASYBROWSER_CHROMEDRIVER_PATH", previousDriver)
	})

	_ = os.Setenv("EASYBROWSER_CHROME_HEADLESS", "false")
	_ = os.Setenv("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER", "true")
	_ = os.Setenv("EASYBROWSER_CHROME_BINARY_PATH", "C:\\custom\\chrome.exe")
	_ = os.Setenv("EASYBROWSER_CHROMEDRIVER_PATH", "C:\\custom\\chromedriver.exe")

	env := localChromeRuntimeEnv([]string{"HEADLESS=1", "UNCHANGED=value"})
	envMap := envSliceToMap(env)

	if envMap["HEADLESS"] != "0" {
		t.Fatalf("expected HEADLESS=0 after easybrowser override, got %q", envMap["HEADLESS"])
	}
	if envMap["USE_UNDETECTED_CHROMEDRIVER"] != "1" {
		t.Fatalf("expected USE_UNDETECTED_CHROMEDRIVER=1, got %q", envMap["USE_UNDETECTED_CHROMEDRIVER"])
	}
	if envMap["BROWSER_BINARY_PATH"] != "C:\\custom\\chrome.exe" {
		t.Fatalf("expected BROWSER_BINARY_PATH override, got %q", envMap["BROWSER_BINARY_PATH"])
	}
	if envMap["CHROMEDRIVER_PATH"] != "C:\\custom\\chromedriver.exe" {
		t.Fatalf("expected CHROMEDRIVER_PATH override, got %q", envMap["CHROMEDRIVER_PATH"])
	}
	if envMap["PYTHONUNBUFFERED"] != "1" {
		t.Fatalf("expected PYTHONUNBUFFERED=1, got %q", envMap["PYTHONUNBUFFERED"])
	}
	if envMap["UNCHANGED"] != "value" {
		t.Fatalf("expected unrelated env to survive, got %q", envMap["UNCHANGED"])
	}
}

func TestRuntimePoolSettingsFromEnvUsesProviderOverrides(t *testing.T) {
	restore := captureEnv(t,
		"EASYBROWSER_RUNTIME_POOL_ENABLED",
		"EASYBROWSER_RUNTIME_POOL_RECONCILE_SECONDS",
		"EASYBROWSER_RUNTIME_POOL_IDLE_TIMEOUT_SECONDS",
		"EASYBROWSER_CHROME_MIN_WARM",
		"EASYBROWSER_CAMOUFOX_MIN_WARM",
	)
	defer restore()

	_ = os.Setenv("EASYBROWSER_RUNTIME_POOL_ENABLED", "true")
	_ = os.Setenv("EASYBROWSER_RUNTIME_POOL_RECONCILE_SECONDS", "7")
	_ = os.Setenv("EASYBROWSER_RUNTIME_POOL_IDLE_TIMEOUT_SECONDS", "180")
	_ = os.Setenv("EASYBROWSER_CHROME_MIN_WARM", "2")
	_ = os.Setenv("EASYBROWSER_CAMOUFOX_MIN_WARM", "1")

	settings := runtimePoolSettingsFromEnv()
	if !settings.enabled {
		t.Fatal("expected runtime pool to be enabled")
	}
	if settings.reconcileInterval != 7*time.Second {
		t.Fatalf("expected reconcile interval 7s, got %s", settings.reconcileInterval)
	}
	if settings.idleTimeout != 180*time.Second {
		t.Fatalf("expected idle timeout 180s, got %s", settings.idleTimeout)
	}
	if settings.minWarmByProviderID["chrome"] != 2 {
		t.Fatalf("expected chrome min warm 2, got %d", settings.minWarmByProviderID["chrome"])
	}
	if settings.minWarmByProviderID["camoufox"] != 1 {
		t.Fatalf("expected camoufox min warm 1, got %d", settings.minWarmByProviderID["camoufox"])
	}
}

func TestSnapshotProviderPoolStateCountsReadyIdleChildren(t *testing.T) {
	manager := &Manager{
		children: map[string]*childProcess{
			"rt-1": {runtimeID: "rt-1", providerID: "chrome", ready: true, busy: false, lastIdleAt: time.Now()},
			"rt-2": {runtimeID: "rt-2", providerID: "chrome", ready: true, busy: true},
			"rt-3": {runtimeID: "rt-3", providerID: "camoufox", ready: true, busy: false, stopping: true},
		},
	}

	snapshots := manager.snapshotProviderPoolState()
	chrome := snapshots["chrome"]
	if len(chrome.activeChildren) != 2 {
		t.Fatalf("expected 2 active chrome children, got %d", len(chrome.activeChildren))
	}
	if len(chrome.idleChildren) != 1 {
		t.Fatalf("expected 1 idle chrome child, got %d", len(chrome.idleChildren))
	}
	camoufox := snapshots["camoufox"]
	if len(camoufox.activeChildren) != 0 || len(camoufox.idleChildren) != 0 {
		t.Fatal("expected stopping child to be excluded from active and idle pool counts")
	}
}

func restoreEnvVar(key, previous string) {
	if previous == "" {
		_ = os.Unsetenv(key)
		return
	}
	_ = os.Setenv(key, previous)
}

func envSliceToMap(env []string) map[string]string {
	out := make(map[string]string, len(env))
	for _, entry := range env {
		parts := strings.SplitN(entry, "=", 2)
		if len(parts) != 2 {
			continue
		}
		out[parts[0]] = parts[1]
	}
	return out
}

func captureEnv(t *testing.T, keys ...string) func() {
	t.Helper()
	previous := make(map[string]string, len(keys))
	for _, key := range keys {
		previous[key] = os.Getenv(key)
	}
	return func() {
		for _, key := range keys {
			restoreEnvVar(key, previous[key])
		}
	}
}
