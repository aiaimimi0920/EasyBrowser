package processmanager

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/ipc"
	"github.com/aiaimimi0920/EasyBrowser/internal/model"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

type Manager struct {
	service            *service.Service
	execPath           string
	chromeRuntime      string
	camoufoxRuntime    string
	geekezRuntime      string
	browserbaseRuntime string
	seq                atomic.Uint64

	mu       sync.RWMutex
	children map[string]*childProcess
}

type childProcess struct {
	runtimeID  string
	providerID string
	cmd        *exec.Cmd
	stdin      io.WriteCloser
	writeMu    sync.Mutex
	logMu      sync.Mutex
	stderrTail []string
	readyCh    chan struct{}
	exitCh     chan error
}

func New(svc *service.Service) *Manager {
	execPath, err := os.Executable()
	if err != nil {
		execPath = ""
	}
	chromeRuntime := resolveChromeRuntime(execPath)
	camoufoxRuntime := resolveCamoufoxRuntime(execPath)
	geekezRuntime := resolveGeekezRuntime(execPath)
	browserbaseRuntime := resolveBrowserbaseRuntime(execPath)
	return &Manager{
		service:            svc,
		execPath:           execPath,
		chromeRuntime:      chromeRuntime,
		camoufoxRuntime:    camoufoxRuntime,
		geekezRuntime:      geekezRuntime,
		browserbaseRuntime: browserbaseRuntime,
		children:           make(map[string]*childProcess),
	}
}

func (m *Manager) nextRuntimeID(providerID string) string {
	n := m.seq.Add(1)
	return fmt.Sprintf("rt-%s-%06d", providerID, n)
}

func (m *Manager) SpawnRuntime(providerID string) (model.RuntimeView, error) {
	if providerID == "" {
		return model.RuntimeView{}, fmt.Errorf("%w: provider id is required", service.ErrInvalidRequest)
	}

	switch providerID {
	case "chrome":
		return m.spawnChromeRuntime(providerID)
	case "camoufox":
		return m.spawnCamoufoxRuntime(providerID)
	case "geekez":
		return m.spawnGeekezRuntime(providerID)
	case "browserbase":
		return m.spawnBrowserbaseRuntime(providerID)
	}

	return m.SpawnStub(providerID)
}

func (m *Manager) SpawnStub(providerID string) (model.RuntimeView, error) {
	if providerID == "" {
		return model.RuntimeView{}, fmt.Errorf("%w: provider id is required", service.ErrInvalidRequest)
	}
	if m.execPath == "" {
		return model.RuntimeView{}, errors.New("process manager executable path unavailable")
	}

	runtimeID := m.nextRuntimeID(providerID)
	cmd := exec.Command(m.execPath, "stub-runtime", "--provider", providerID, "--runtime-id", runtimeID)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}

	child := &childProcess{
		runtimeID:  runtimeID,
		providerID: providerID,
		cmd:        cmd,
		stdin:      stdin,
		readyCh:    make(chan struct{}),
		exitCh:     make(chan error, 1),
	}

	m.recordOperationalEvent("runtime_spawn_started", "info", fmt.Sprintf("starting stub runtime for provider %s", providerID), model.Trace{
		RuntimeID:  runtimeID,
		ProviderID: providerID,
	}, map[string]any{
		"provider_id":  providerID,
		"runtime_id":   runtimeID,
		"runtime_kind": "stub",
	})

	m.mu.Lock()
	m.children[runtimeID] = child
	m.mu.Unlock()

	if err := cmd.Start(); err != nil {
		m.mu.Lock()
		delete(m.children, runtimeID)
		m.mu.Unlock()
		m.recordOperationalEvent("runtime_startup_failed", "error", err.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": "stub",
		})
		return model.RuntimeView{}, err
	}

	go m.readStdout(child, stdout)
	go m.readStderr(child, stderr)
	go m.waitChild(child)

	select {
	case <-child.readyCh:
	case err := <-child.exitCh:
		if err != nil {
			decorated := m.decorateStartupError(child, "stub runtime", fmt.Sprintf("exited before ready: %v", err))
			m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
				RuntimeID:  runtimeID,
				ProviderID: providerID,
			}, map[string]any{
				"provider_id":  providerID,
				"runtime_id":   runtimeID,
				"runtime_kind": "stub",
			})
			return model.RuntimeView{}, decorated
		}
		decorated := m.decorateStartupError(child, "stub runtime", "exited before ready")
		m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": "stub",
		})
		return model.RuntimeView{}, decorated
	case <-time.After(5 * time.Second):
		m.killChild(child)
		decorated := m.decorateStartupError(child, "stub runtime", "did not become ready in 5s")
		m.recordOperationalEvent("runtime_ready_timeout", "warn", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": "stub",
			"timeout_ms":   5000,
		})
		m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": "stub",
			"reason":       "ready_timeout",
		})
		return model.RuntimeView{}, decorated
	}

	view, _, err := m.service.RecordHeartbeat(model.RuntimeHeartbeatRequest{
		RuntimeID:  runtimeID,
		ProviderID: providerID,
		Healthy:    true,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
	})
	if err != nil {
		view, _, err = m.service.RegisterRuntime(model.RuntimeRegistrationRequest{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
			State:      "ready",
			StartedAt:  time.Now().UTC().Format(time.RFC3339),
		})
		if err != nil {
			return model.RuntimeView{}, err
		}
	}
	return view, nil
}

func (m *Manager) spawnChromeRuntime(providerID string) (model.RuntimeView, error) {
	if runtimeLaunchMode(providerID) == "docker" {
		return m.spawnDockerRuntime(providerID)
	}
	if m.chromeRuntime == "" {
		return model.RuntimeView{}, errors.New("chrome runtime script not found")
	}
	pythonPath, err := resolveChromePython()
	if err != nil {
		return model.RuntimeView{}, err
	}

	runtimeID := m.nextRuntimeID(providerID)
	cmd := exec.Command(pythonPath, m.chromeRuntime, "--provider", providerID, "--runtime-id", runtimeID)
	cmd.Env = localChromeRuntimeEnv(os.Environ())
	return m.startChildCommand(providerID, runtimeID, cmd, readyTimeoutForProvider(providerID), "chrome runtime")
}

func (m *Manager) spawnCamoufoxRuntime(providerID string) (model.RuntimeView, error) {
	if runtimeLaunchMode(providerID) == "docker" {
		return m.spawnDockerRuntime(providerID)
	}
	if m.camoufoxRuntime == "" {
		return model.RuntimeView{}, errors.New("camoufox runtime script not found")
	}

	pythonPath, err := resolveCamoufoxPython()
	if err != nil {
		return model.RuntimeView{}, err
	}

	runtimeID := m.nextRuntimeID(providerID)
	cmd := exec.Command(pythonPath, m.camoufoxRuntime, "--provider", providerID, "--runtime-id", runtimeID)
	return m.startChildCommand(providerID, runtimeID, cmd, readyTimeoutForProvider(providerID), "camoufox runtime")
}

func (m *Manager) spawnGeekezRuntime(providerID string) (model.RuntimeView, error) {
	if runtimeLaunchMode(providerID) == "docker" {
		return m.spawnDockerRuntime(providerID)
	}
	if m.geekezRuntime == "" {
		return model.RuntimeView{}, errors.New("geekez runtime script not found")
	}

	pythonPath, err := resolveGeekezPython()
	if err != nil {
		return model.RuntimeView{}, err
	}

	runtimeID := m.nextRuntimeID(providerID)
	cmd := exec.Command(pythonPath, m.geekezRuntime, "--provider", providerID, "--runtime-id", runtimeID)
	return m.startChildCommand(providerID, runtimeID, cmd, readyTimeoutForProvider(providerID), "geekez runtime")
}

func (m *Manager) spawnBrowserbaseRuntime(providerID string) (model.RuntimeView, error) {
	if strings.TrimSpace(os.Getenv("BROWSERBASE_API_KEY")) == "" {
		return model.RuntimeView{}, fmt.Errorf("%w: BROWSERBASE_API_KEY is required for browserbase provider", service.ErrInvalidRequest)
	}
	if m.browserbaseRuntime == "" {
		return model.RuntimeView{}, errors.New("browserbase runtime script not found")
	}
	nodePath, err := exec.LookPath("node")
	if err != nil {
		return model.RuntimeView{}, fmt.Errorf("node executable not found: %w", err)
	}

	runtimeID := m.nextRuntimeID(providerID)
	cmd := exec.Command(nodePath, m.browserbaseRuntime, "--provider", providerID, "--runtime-id", runtimeID)
	return m.startChildCommand(providerID, runtimeID, cmd, 8*time.Second, "browserbase runtime")
}

func (m *Manager) spawnDockerRuntime(providerID string) (model.RuntimeView, error) {
	runtimeID := m.nextRuntimeID(providerID)
	cmd, label, err := m.dockerCommandForProvider(providerID, runtimeID)
	if err != nil {
		return model.RuntimeView{}, err
	}
	return m.startChildCommand(providerID, runtimeID, cmd, readyTimeoutForProvider(providerID), label)
}

func (m *Manager) dockerCommandForProvider(providerID, runtimeID string) (*exec.Cmd, string, error) {
	dockerPath, err := exec.LookPath("docker")
	if err != nil {
		return nil, "", fmt.Errorf("docker executable not found: %w", err)
	}

	image := dockerImageForProvider(providerID)
	if image == "" {
		return nil, "", fmt.Errorf("docker image is not configured for provider %s", providerID)
	}

	args := []string{
		"run",
		"--rm",
		"-i",
		"--init",
		"--shm-size=2g",
		"--name", dockerContainerName(runtimeID),
	}

	if network := strings.TrimSpace(os.Getenv("EASYBROWSER_DOCKER_NETWORK")); network != "" {
		args = append(args, "--network", network)
	} else {
		args = append(args, "--network", "Easy")
	}

	appendDockerEnv := func(key, value string) {
		if strings.TrimSpace(key) == "" || value == "" {
			return
		}
		args = append(args, "-e", fmt.Sprintf("%s=%s", key, value))
	}

	appendDockerEnv("PYTHONUNBUFFERED", "1")
	appendDockerEnv("EASYBROWSER_CHILD_PROVIDER", providerID)
	appendDockerEnv("EASYBROWSER_CHILD_RUNTIME_ID", runtimeID)

	switch providerID {
	case "chrome":
		appendDockerEnv("HEADLESS", coalesceEnv("EASYBROWSER_CHROME_HEADLESS", "HEADLESS", "1"))
		appendDockerEnv("USE_UNDETECTED_CHROMEDRIVER", coalesceEnv("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER", "USE_UNDETECTED_CHROMEDRIVER", "0"))
		appendDockerEnv("MAILBOX_SERVICE_BASE_URL", coalesceEnv("MAILBOX_SERVICE_BASE_URL", "http://easy-email-service:8080"))
		appendDockerEnv("MAILBOX_SERVICE_API_KEY", coalesceEnv("MAILBOX_SERVICE_API_KEY", "J7L+RCwLIBEcMZHzz0rXjm4oyR9rymq9"))
		appendDockerEnv("BROWSER_BINARY_PATH", coalesceEnv("EASYBROWSER_CHROME_BINARY_PATH", "/usr/bin/chromium"))
		appendDockerEnv("CHROMEDRIVER_PATH", coalesceEnv("EASYBROWSER_CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
		args = append(args, image, "python", "/opt/browserservice/repos/chrome/src/chrome_runtime/runtime_entry.py", "--provider", providerID, "--runtime-id", runtimeID)
		return exec.Command(dockerPath, args...), "chrome runtime (docker)", nil
	case "camoufox":
		appendDockerEnv("EASYBROWSER_CAMOUFOX_HEADLESS", coalesceEnv("EASYBROWSER_CAMOUFOX_HEADLESS", "true"))
		args = append(args, image, "python", "/opt/easybrowser/providers/camoufox/runtime.py", "--provider", providerID, "--runtime-id", runtimeID)
		return exec.Command(dockerPath, args...), "camoufox runtime (docker)", nil
	case "geekez":
		appendDockerEnv("EASYBROWSER_GEEKEZ_API_PORT", coalesceEnv("EASYBROWSER_GEEKEZ_API_PORT", "52000"))
		appendDockerEnv("EASYBROWSER_GEEKEZ_REMOTE_DEBUG_MIN_PORT", coalesceEnv("EASYBROWSER_GEEKEZ_REMOTE_DEBUG_MIN_PORT", "53000"))
		appendDockerEnv("EASYBROWSER_GEEKEZ_REMOTE_DEBUG_MAX_PORT", coalesceEnv("EASYBROWSER_GEEKEZ_REMOTE_DEBUG_MAX_PORT", "53999"))
		appendDockerEnv("EASYBROWSER_GEEKEZ_APP_ROOT", "/opt/geekez-browser")
		appendDockerEnv("XDG_CONFIG_HOME", "/tmp/geekez-config")
		appendDockerEnv("HOME", "/tmp/geekez-home")
		args = append(args, image, "python", "/opt/easybrowser/providers/geekez/runtime.py", "--provider", providerID, "--runtime-id", runtimeID)
		return exec.Command(dockerPath, args...), "geekez runtime (docker)", nil
	default:
		return nil, "", fmt.Errorf("docker mode is unsupported for provider %s", providerID)
	}
}

func (m *Manager) startChildCommand(providerID, runtimeID string, cmd *exec.Cmd, readyTimeout time.Duration, label string) (model.RuntimeView, error) {
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return model.RuntimeView{}, err
	}

	child := &childProcess{
		runtimeID:  runtimeID,
		providerID: providerID,
		cmd:        cmd,
		stdin:      stdin,
		stderrTail: make([]string, 0, 12),
		readyCh:    make(chan struct{}),
		exitCh:     make(chan error, 1),
	}

	m.recordOperationalEvent("runtime_spawn_started", "info", fmt.Sprintf("starting %s", label), model.Trace{
		RuntimeID:  runtimeID,
		ProviderID: providerID,
	}, map[string]any{
		"provider_id":  providerID,
		"runtime_id":   runtimeID,
		"runtime_kind": label,
	})

	m.mu.Lock()
	m.children[runtimeID] = child
	m.mu.Unlock()

	if err := cmd.Start(); err != nil {
		m.mu.Lock()
		delete(m.children, runtimeID)
		m.mu.Unlock()
		m.recordOperationalEvent("runtime_startup_failed", "error", err.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": label,
		})
		return model.RuntimeView{}, err
	}

	go m.readStdout(child, stdout)
	go m.readStderr(child, stderr)
	go m.waitChild(child)

	select {
	case <-child.readyCh:
	case err := <-child.exitCh:
		if err != nil {
			decorated := m.decorateStartupError(child, label, fmt.Sprintf("exited before ready: %v", err))
			m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
				RuntimeID:  runtimeID,
				ProviderID: providerID,
			}, map[string]any{
				"provider_id":  providerID,
				"runtime_id":   runtimeID,
				"runtime_kind": label,
			})
			return model.RuntimeView{}, decorated
		}
		decorated := m.decorateStartupError(child, label, "exited before ready")
		m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": label,
		})
		return model.RuntimeView{}, decorated
	case <-time.After(readyTimeout):
		m.killChild(child)
		decorated := m.decorateStartupError(child, label, fmt.Sprintf("did not become ready in %s", readyTimeout))
		m.recordOperationalEvent("runtime_ready_timeout", "warn", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": label,
			"timeout_ms":   readyTimeout.Milliseconds(),
		})
		m.recordOperationalEvent("runtime_startup_failed", "error", decorated.Error(), model.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		}, map[string]any{
			"provider_id":  providerID,
			"runtime_id":   runtimeID,
			"runtime_kind": label,
			"reason":       "ready_timeout",
		})
		return model.RuntimeView{}, decorated
	}

	view, _, err := m.service.GetRuntime(runtimeID)
	if err != nil {
		return model.RuntimeView{}, err
	}
	return view, nil
}

func (m *Manager) recordOperationalEvent(kind, severity, message string, trace model.Trace, details map[string]any) {
	if m == nil || m.service == nil {
		return
	}
	m.service.RecordOperationalEvent(kind, severity, message, trace, details)
}

func (m *Manager) DispatchTask(taskID, runtimeID string, req model.ExecuteRequest) error {
	m.mu.RLock()
	child, ok := m.children[runtimeID]
	m.mu.RUnlock()
	if !ok {
		return service.ErrNotFound
	}

	payload := map[string]any{
		"task_id": taskID,
		"request": req,
	}
	return m.sendEnvelope(child, ipc.Envelope{
		ID:        fmt.Sprintf("msg-%d", time.Now().UnixNano()),
		Kind:      ipc.KindRequest,
		Action:    "execute_task",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Trace: ipc.Trace{
			TaskID:     taskID,
			RuntimeID:  runtimeID,
			ProviderID: child.providerID,
		},
		Payload: payload,
	})
}

func (m *Manager) ShutdownRuntime(runtimeID string) error {
	m.mu.RLock()
	child, ok := m.children[runtimeID]
	m.mu.RUnlock()
	if !ok {
		return service.ErrNotFound
	}
	return m.sendEnvelope(child, ipc.Envelope{
		ID:        fmt.Sprintf("msg-%d", time.Now().UnixNano()),
		Kind:      ipc.KindRequest,
		Action:    "shutdown_runtime",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Trace: ipc.Trace{
			RuntimeID:  runtimeID,
			ProviderID: child.providerID,
		},
		Payload: map[string]any{
			"runtime_id": runtimeID,
		},
	})
}

func (m *Manager) sendEnvelope(child *childProcess, env ipc.Envelope) error {
	child.writeMu.Lock()
	defer child.writeMu.Unlock()
	return json.NewEncoder(child.stdin).Encode(env)
}

func (m *Manager) readStdout(child *childProcess, reader io.Reader) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		var env ipc.Envelope
		if err := json.Unmarshal(scanner.Bytes(), &env); err != nil {
			log.Printf("easybrowser: failed to decode child envelope from %s: %v", child.runtimeID, err)
			continue
		}
		m.handleEnvelope(child, env)
	}
}

func (m *Manager) readStderr(child *childProcess, reader io.Reader) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 0, 16*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		m.appendChildLog(child, line)
		log.Printf("easybrowser child[%s] stderr: %s", child.runtimeID, line)
	}
}

func (m *Manager) waitChild(child *childProcess) {
	err := child.cmd.Wait()
	if err != nil {
		log.Printf("easybrowser child[%s] exited with error: %v", child.runtimeID, err)
		m.service.MarkRuntimeStopped(child.runtimeID, true)
	} else {
		m.service.MarkRuntimeStopped(child.runtimeID, false)
	}
	child.exitCh <- err
	close(child.exitCh)

	m.mu.Lock()
	delete(m.children, child.runtimeID)
	m.mu.Unlock()
}

func (m *Manager) handleEnvelope(child *childProcess, env ipc.Envelope) {
	switch env.Action {
	case "runtime_ready":
		payload := decodeRegistration(env.Payload)
		payload.RuntimeID = fallbackString(payload.RuntimeID, child.runtimeID)
		payload.ProviderID = fallbackString(payload.ProviderID, child.providerID)
		if _, _, err := m.service.RegisterRuntime(payload); err != nil {
			log.Printf("easybrowser: failed to register runtime %s: %v", child.runtimeID, err)
		}
		select {
		case <-child.readyCh:
		default:
			close(child.readyCh)
		}
	case "runtime_health":
		payload := decodeHeartbeat(env.Payload)
		payload.RuntimeID = fallbackString(payload.RuntimeID, child.runtimeID)
		payload.ProviderID = fallbackString(payload.ProviderID, child.providerID)
		if _, _, err := m.service.RecordHeartbeat(payload); err != nil && !errors.Is(err, service.ErrNotFound) {
			log.Printf("easybrowser: failed to record heartbeat for %s: %v", child.runtimeID, err)
		}
	case "task_completed":
		payload := decodeCompletion(env.Payload)
		payload.RuntimeID = fallbackString(payload.RuntimeID, child.runtimeID)
		if _, _, err := m.service.RecordCompletion(payload); err != nil {
			log.Printf("easybrowser: failed to record completion for %s: %v", child.runtimeID, err)
		}
	}
}

func decodeRegistration(payload map[string]any) model.RuntimeRegistrationRequest {
	var out model.RuntimeRegistrationRequest
	blob, _ := json.Marshal(payload)
	_ = json.Unmarshal(blob, &out)
	return out
}

func decodeHeartbeat(payload map[string]any) model.RuntimeHeartbeatRequest {
	var out model.RuntimeHeartbeatRequest
	blob, _ := json.Marshal(payload)
	_ = json.Unmarshal(blob, &out)
	return out
}

func decodeCompletion(payload map[string]any) model.RuntimeCompletionRequest {
	var out model.RuntimeCompletionRequest
	blob, _ := json.Marshal(payload)
	_ = json.Unmarshal(blob, &out)
	return out
}

func fallbackString(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}

func resolveBrowserbaseRuntime(execPath string) string {
	return resolveNodeRuntime(execPath, filepath.Join("providers", "browserbase", "runtime.js"))
}

func resolveChromeRuntime(execPath string) string {
	return resolvePythonRuntime(execPath, filepath.Join("..", "..", "runtimes", "chrome", "src", "browser_runtime", "runtime_entry.py"))
}

func localChromeRuntimeEnv(base []string) []string {
	env := append([]string{}, base...)
	env = upsertEnv(env, "PYTHONUNBUFFERED", "1")

	if value := strings.TrimSpace(os.Getenv("EASYBROWSER_CHROME_HEADLESS")); value != "" {
		env = upsertEnv(env, "HEADLESS", normalizeZeroOneBooleanEnv(value))
	}
	if value := strings.TrimSpace(os.Getenv("EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER")); value != "" {
		env = upsertEnv(env, "USE_UNDETECTED_CHROMEDRIVER", normalizeZeroOneBooleanEnv(value))
	}
	if value := strings.TrimSpace(os.Getenv("EASYBROWSER_CHROME_BINARY_PATH")); value != "" {
		env = upsertEnv(env, "BROWSER_BINARY_PATH", value)
	}
	if value := strings.TrimSpace(os.Getenv("EASYBROWSER_CHROMEDRIVER_PATH")); value != "" {
		env = upsertEnv(env, "CHROMEDRIVER_PATH", value)
	}
	if value := strings.TrimSpace(os.Getenv("MAILBOX_SERVICE_BASE_URL")); value != "" {
		env = upsertEnv(env, "MAILBOX_SERVICE_BASE_URL", value)
	}
	if value := strings.TrimSpace(os.Getenv("MAILBOX_SERVICE_API_KEY")); value != "" {
		env = upsertEnv(env, "MAILBOX_SERVICE_API_KEY", value)
	}

	return env
}

func upsertEnv(env []string, key, value string) []string {
	if strings.TrimSpace(key) == "" {
		return env
	}
	prefix := key + "="
	for idx, entry := range env {
		if strings.HasPrefix(strings.ToUpper(entry), strings.ToUpper(prefix)) {
			env[idx] = prefix + value
			return env
		}
	}
	return append(env, prefix+value)
}

func normalizeZeroOneBooleanEnv(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "", "0", "false", "no", "off":
		return "0"
	default:
		return "1"
	}
}

func resolveCamoufoxRuntime(execPath string) string {
	return resolveNodeRuntime(execPath, filepath.Join("providers", "camoufox", "runtime.py"))
}

func resolveGeekezRuntime(execPath string) string {
	return resolveNodeRuntime(execPath, filepath.Join("providers", "geekez", "runtime.py"))
}

func resolveNodeRuntime(execPath, relativePath string) string {
	candidates := []string{}
	if cwd, err := os.Getwd(); err == nil {
		for _, base := range searchRoots(cwd) {
			candidates = append(candidates, filepath.Join(base, relativePath))
		}
	}
	if execPath != "" {
		for _, base := range searchRoots(filepath.Dir(execPath)) {
			candidates = append(candidates, filepath.Join(base, relativePath))
		}
	}

	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate
		}
	}
	return ""
}

func resolvePythonRuntime(execPath, relativePath string) string {
	candidates := []string{}
	if cwd, err := os.Getwd(); err == nil {
		for _, base := range searchRoots(cwd) {
			candidates = append(candidates, filepath.Join(base, relativePath))
		}
	}
	if execPath != "" {
		for _, base := range searchRoots(filepath.Dir(execPath)) {
			candidates = append(candidates, filepath.Join(base, relativePath))
		}
	}
	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate
		}
	}
	return ""
}

func resolveChromePython() (string, error) {
	if custom := strings.TrimSpace(os.Getenv("EASYBROWSER_CHROME_PYTHON")); custom != "" {
		if _, err := os.Stat(custom); err == nil {
			return custom, nil
		}
	}
	if path, err := exec.LookPath("python"); err == nil {
		return path, nil
	}
	if path, err := exec.LookPath("python3"); err == nil {
		return path, nil
	}
	return "", errors.New("python executable not found for chrome runtime")
}

func resolveCamoufoxPython() (string, error) {
	if custom := strings.TrimSpace(os.Getenv("EASYBROWSER_CAMOUFOX_PYTHON")); custom != "" {
		if _, err := os.Stat(custom); err == nil {
			return custom, nil
		}
	}
	if path, err := exec.LookPath("python"); err == nil {
		return path, nil
	}
	if path, err := exec.LookPath("python3"); err == nil {
		return path, nil
	}
	return "", errors.New("python executable not found for camoufox runtime")
}

func resolveGeekezPython() (string, error) {
	if custom := strings.TrimSpace(os.Getenv("EASYBROWSER_GEEKEZ_PYTHON")); custom != "" {
		if _, err := os.Stat(custom); err == nil {
			return custom, nil
		}
	}
	if path, err := exec.LookPath("python"); err == nil {
		return path, nil
	}
	if path, err := exec.LookPath("python3"); err == nil {
		return path, nil
	}
	return "", errors.New("python executable not found for geekez runtime")
}

func readyTimeoutForProvider(providerID string) time.Duration {
	switch providerID {
	case "camoufox":
		return durationFromEnvMs("EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS", 75*time.Second)
	case "geekez":
		return durationFromEnvMs("EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS", 90*time.Second)
	case "chrome":
		return durationFromEnvMs("EASYBROWSER_CHROME_READY_TIMEOUT_MS", 8*time.Second)
	case "browserbase":
		return durationFromEnvMs("EASYBROWSER_BROWSERBASE_READY_TIMEOUT_MS", 8*time.Second)
	default:
		return 10 * time.Second
	}
}

func durationFromEnvMs(key string, fallback time.Duration) time.Duration {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	millis, err := time.ParseDuration(value + "ms")
	if err != nil || millis <= 0 {
		return fallback
	}
	return millis
}

func runtimeLaunchMode(providerID string) string {
	key := "EASYBROWSER_" + strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(providerID), "-", "_")) + "_RUNTIME_MODE"
	if value := strings.ToLower(strings.TrimSpace(os.Getenv(key))); value == "docker" || value == "local" {
		return value
	}
	if value := strings.ToLower(strings.TrimSpace(os.Getenv("EASYBROWSER_RUNTIME_MODE"))); value == "docker" || value == "local" {
		return value
	}
	return "local"
}

func dockerImageForProvider(providerID string) string {
	switch providerID {
	case "chrome":
		return coalesceEnv("EASYBROWSER_CHROME_DOCKER_IMAGE", "easybrowser/chrome-runtime:local")
	case "camoufox":
		return coalesceEnv("EASYBROWSER_CAMOUFOX_DOCKER_IMAGE", "easybrowser/camoufox-runtime:local")
	case "geekez":
		return coalesceEnv("EASYBROWSER_GEEKEZ_DOCKER_IMAGE", "easybrowser/geekez-runtime:local")
	default:
		return ""
	}
}

func dockerContainerName(runtimeID string) string {
	normalized := strings.NewReplacer("_", "-", ":", "-", "/", "-", "\\", "-").Replace(strings.TrimSpace(runtimeID))
	normalized = strings.ToLower(normalized)
	if normalized == "" {
		normalized = fmt.Sprintf("rt-%d", time.Now().UnixNano())
	}
	return "easybrowser-" + normalized
}

func coalesceEnv(keysAndFallback ...string) string {
	for _, key := range keysAndFallback {
		if strings.TrimSpace(key) == "" {
			continue
		}
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}
	if len(keysAndFallback) > 0 {
		return strings.TrimSpace(keysAndFallback[len(keysAndFallback)-1])
	}
	return ""
}

func (m *Manager) appendChildLog(child *childProcess, line string) {
	if child == nil {
		return
	}
	child.logMu.Lock()
	defer child.logMu.Unlock()
	child.stderrTail = append(child.stderrTail, line)
	if len(child.stderrTail) > 12 {
		child.stderrTail = child.stderrTail[len(child.stderrTail)-12:]
	}
}

func (m *Manager) childLogSummary(child *childProcess) string {
	if child == nil {
		return ""
	}
	child.logMu.Lock()
	defer child.logMu.Unlock()
	if len(child.stderrTail) == 0 {
		return ""
	}
	return strings.Join(child.stderrTail, " | ")
}

func (m *Manager) decorateStartupError(child *childProcess, label, reason string) error {
	summary := strings.TrimSpace(m.childLogSummary(child))
	if summary == "" {
		return fmt.Errorf("%s %s", label, reason)
	}
	return fmt.Errorf("%s %s; recent stderr: %s", label, reason, summary)
}

func (m *Manager) killChild(child *childProcess) {
	if child == nil || child.cmd == nil || child.cmd.Process == nil {
		return
	}
	_ = child.stdin.Close()
	_ = child.cmd.Process.Kill()
}

func searchRoots(start string) []string {
	if start == "" {
		return nil
	}

	seen := map[string]struct{}{}
	roots := make([]string, 0, 5)
	current := start
	for i := 0; i < 5; i++ {
		cleaned := filepath.Clean(current)
		if _, ok := seen[cleaned]; ok {
			break
		}
		seen[cleaned] = struct{}{}
		roots = append(roots, cleaned)

		parent := filepath.Dir(cleaned)
		if parent == cleaned {
			break
		}
		current = parent
	}
	return roots
}
