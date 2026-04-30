package main

import (
	"log"
	"os"

	"github.com/aiaimimi0920/EasyBrowser/internal/app"
	"github.com/aiaimimi0920/EasyBrowser/internal/stubruntime"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "stub-runtime" {
		if err := stubruntime.Run(os.Args[2:]); err != nil {
			log.Fatal(err)
		}
		return
	}

	cfg := app.DefaultConfig()
	a := app.New(cfg)

	log.Printf("easybrowser listening on %s", cfg.Listen)
	if err := a.Run(); err != nil {
		log.Fatal(err)
	}
}
