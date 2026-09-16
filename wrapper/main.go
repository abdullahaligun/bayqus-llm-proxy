package main

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func isProxyAlive(addr string) bool {
	conn, err := net.DialTimeout("tcp", addr, 250*time.Millisecond)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}

func logInfo(msg string) {
	appData := os.Getenv("APPDATA")
	if appData == "" {
		return
	}
	logPath := filepath.Join(appData, "Claude", "claude-code", "wrapper.log")
	f, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	_, _ = fmt.Fprintf(f, "[%s] %s\n", timestamp, msg)
}

func main() {
	exePath, err := os.Executable()
	if err != nil {
		os.Exit(1)
	}
	dir := filepath.Dir(exePath)
	realExe := filepath.Join(dir, "claude_real.exe")

	if _, err := os.Stat(realExe); err != nil {
		logInfo(fmt.Sprintf("ERROR: claude_real.exe not found in %s", dir))
		os.Exit(1)
	}

	proxyAddr := "127.0.0.1:5199"
	alive := isProxyAlive(proxyAddr)

	var newEnv []string
	for _, e := range os.Environ() {
		upper := strings.ToUpper(e)
		if strings.HasPrefix(upper, "ANTHROPIC_BASE_URL=") {
			continue
		}
		newEnv = append(newEnv, e)
	}

	if alive {
		newEnv = append(newEnv,
			"ANTHROPIC_BASE_URL=http://"+proxyAddr,
			"_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1",
		)
		logInfo(fmt.Sprintf("Running with proxy (http://%s), args: %v", proxyAddr, os.Args[1:]))
	} else {
		newEnv = append(newEnv, "ANTHROPIC_BASE_URL=https://api.anthropic.com")
		logInfo(fmt.Sprintf("Proxy not running, direct fallback, args: %v", os.Args[1:]))
	}

	cmd := exec.Command(realExe, os.Args[1:]...)
	cmd.Env = newEnv
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		os.Exit(1)
	}
	os.Exit(0)
}
