
package config

import (
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/joho/godotenv"
)

type Config struct {

	ServerPort string

	DatabaseURL string

	RedisURL string

	MilvusHost string

	MilvusPort string

	MinioEndpoint string

	MinioAccessKey string

	MinioSecretKey string

	GRPCServerAddr string

	JWTSecret string
}

func Load() *Config {

	loadDotenv()

	return &Config{
		ServerPort:     envOr("GO_SERVER_PORT", "8080"),
		DatabaseURL:    envOr("DATABASE_URL", "postgresql://lha:lha_dev@localhost:5432/lha?sslmode=disable"),
		RedisURL:       envOr("REDIS_URL", "redis://localhost:6379/0"),
		MilvusHost:     envOr("MILVUS_HOST", "localhost"),
		MilvusPort:     envOr("MILVUS_PORT", "19530"),
		MinioEndpoint:  envOr("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey: envOr("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey: envOr("MINIO_SECRET_KEY", "minioadmin_dev"),
		GRPCServerAddr: envOr("GRPC_SERVER_PORT", "50057"),
		JWTSecret:      envOr("JWT_SECRET", "lha-dev-secret-change-in-production"),
	}
}

func loadDotenv() {
	dir, _ := os.Getwd()
	for range 5 {
		envPath := filepath.Join(dir, ".env")
		if _, err := os.Stat(envPath); err == nil {
			if err := godotenv.Load(envPath); err == nil {
				log.Println("[config] loaded .env from", envPath)
			}
			return
		}
		dir = filepath.Dir(dir)
	}
}

func envOr(key, fallback string) string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return fallback
	}
	return v
}
