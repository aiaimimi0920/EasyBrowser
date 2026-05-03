//go:build windows

package processmanager

import (
	"fmt"
	"os/exec"
)

func prepareChildCommand(cmd *exec.Cmd) {
	if cmd == nil {
		return
	}
}

func terminateChildProcessTree(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = exec.Command("taskkill", "/PID", fmt.Sprintf("%d", cmd.Process.Pid), "/T", "/F").Run()
}
