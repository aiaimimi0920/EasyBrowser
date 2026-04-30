package config

import "os"

type Config struct {
	Listen string
}

func Default() Config {
	listen := os.Getenv("EASYBROWSER_LISTEN")
	if listen == "" {
		listen = "127.0.0.1:18080"
	}

	return Config{
		Listen: listen,
	}
}
