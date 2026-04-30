package processmanager

import (
	"errors"
	"os"
	"strings"
	"testing"

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
