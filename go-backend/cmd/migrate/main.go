
package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	_ "github.com/golang-migrate/migrate/v4/source/file"
	"github.com/joho/godotenv"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("用法: migrate [up|down|version]")
		os.Exit(1)
	}
	action := os.Args[1]

	dir, _ := os.Getwd()
	for range 5 {
		envPath := filepath.Join(dir, ".env")
		if _, err := os.Stat(envPath); err == nil {
			_ = godotenv.Load(envPath)
			break
		}
		dir = filepath.Dir(dir)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgresql://lha:lha_dev@localhost:5432/lha?sslmode=disable"
	}

	migrationsPath := "file://migrations"
	m, err := migrate.New(migrationsPath, dbURL)
	if err != nil {
		log.Fatalf("迁移初始化失败: %v", err)
	}
	defer m.Close()

	switch action {
	case "up":
		if err := m.Up(); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("迁移执行失败: %v", err)
		}
		fmt.Println("✅ 迁移已执行到最新版本")

	case "down":
		if err := m.Down(); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("回滚失败: %v", err)
		}
		fmt.Println("✅ 最近一次迁移已回滚")

	case "version":
		version, dirty, err := m.Version()
		if err != nil {
			log.Fatalf("获取版本失败: %v", err)
		}
		fmt.Printf("当前版本: %d (dirty=%v)\n", version, dirty)

	default:
		fmt.Println("未知操作:", action, "— 可用: up / down / version")
		os.Exit(1)
	}
}
