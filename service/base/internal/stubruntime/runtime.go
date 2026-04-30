package stubruntime

import (
	"bufio"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/ipc"
)

type executePayload struct {
	TaskID  string         `json:"task_id"`
	Request map[string]any `json:"request"`
}

func Run(args []string) error {
	fs := flag.NewFlagSet("stub-runtime", flag.ContinueOnError)
	providerID := fs.String("provider", "", "provider id")
	runtimeID := fs.String("runtime-id", "", "runtime id")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *providerID == "" || *runtimeID == "" {
		return errors.New("provider and runtime-id are required")
	}

	if err := sendReady(*providerID, *runtimeID); err != nil {
		return err
	}
	if err := sendHeartbeat(*providerID, *runtimeID, true, 0, false); err != nil {
		return err
	}

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		var env ipc.Envelope
		if err := json.Unmarshal(scanner.Bytes(), &env); err != nil {
			return err
		}
		switch env.Action {
		case "execute_task":
			var payload executePayload
			blob, _ := json.Marshal(env.Payload)
			_ = json.Unmarshal(blob, &payload)
			if payload.TaskID == "" {
				payload.TaskID = env.Trace.TaskID
			}
			if err := sendCompletion(*providerID, *runtimeID, payload.TaskID, payload.Request); err != nil {
				return err
			}
		case "collect_health":
			if err := sendHeartbeat(*providerID, *runtimeID, true, 0, false); err != nil {
				return err
			}
		case "shutdown_runtime":
			return nil
		}
	}
	return scanner.Err()
}

func sendReady(providerID, runtimeID string) error {
	return json.NewEncoder(os.Stdout).Encode(ipc.Envelope{
		ID:        fmt.Sprintf("evt-%d", time.Now().UnixNano()),
		Kind:      ipc.KindEvent,
		Action:    "runtime_ready",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Trace: ipc.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		},
		Payload: map[string]any{
			"runtime_id":  runtimeID,
			"provider_id": providerID,
			"pid":         os.Getpid(),
			"state":       "ready",
			"started_at":  time.Now().UTC().Format(time.RFC3339),
		},
	})
}

func sendHeartbeat(providerID, runtimeID string, healthy bool, recentFailures int, cooldownActive bool) error {
	return json.NewEncoder(os.Stdout).Encode(ipc.Envelope{
		ID:        fmt.Sprintf("hb-%d", time.Now().UnixNano()),
		Kind:      ipc.KindHeartbeat,
		Action:    "runtime_health",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Trace: ipc.Trace{
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		},
		Payload: map[string]any{
			"runtime_id":  runtimeID,
			"provider_id": providerID,
			"healthy":     healthy,
			"timestamp":   time.Now().UTC().Format(time.RFC3339),
			"signals": map[string]any{
				"recent_failures": recentFailures,
				"cooldown_active": cooldownActive,
			},
		},
	})
}

func sendCompletion(providerID, runtimeID, taskID string, request map[string]any) error {
	return json.NewEncoder(os.Stdout).Encode(ipc.Envelope{
		ID:        fmt.Sprintf("cmp-%d", time.Now().UnixNano()),
		Kind:      ipc.KindEvent,
		Action:    "task_completed",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Trace: ipc.Trace{
			TaskID:     taskID,
			RuntimeID:  runtimeID,
			ProviderID: providerID,
		},
		Payload: map[string]any{
			"runtime_id": runtimeID,
			"task_id":    taskID,
			"success":    true,
			"result": map[string]any{
				"provider_id": providerID,
				"runtime_id":  runtimeID,
				"echo":        request,
			},
			"error":       nil,
			"finished_at": time.Now().UTC().Format(time.RFC3339),
		},
	})
}
