package app

import (
	"net/http"
	"time"

	"github.com/aiaimimi0920/EasyBrowser/internal/config"
	"github.com/aiaimimi0920/EasyBrowser/internal/httpapi"
	"github.com/aiaimimi0920/EasyBrowser/internal/processmanager"
	"github.com/aiaimimi0920/EasyBrowser/internal/service"
)

type App struct {
	cfg       config.Config
	service   *service.Service
	processes *processmanager.Manager
	server    *http.Server
}

func DefaultConfig() config.Config {
	return config.Default()
}

func New(cfg config.Config) *App {
	svc := service.New()
	manager := processmanager.New(svc)
	handler := httpapi.NewRouter(svc, manager)

	server := &http.Server{
		Addr:              cfg.Listen,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}

	return &App{
		cfg:       cfg,
		service:   svc,
		processes: manager,
		server:    server,
	}
}

func (a *App) Run() error {
	if a.processes != nil {
		defer a.processes.Close()
	}
	return a.server.ListenAndServe()
}
