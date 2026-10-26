package main

import (
	"fmt"
	"log"
	"net/http"

	"llm-healthy-assistant/go-backend/internal/aiclient"
	"llm-healthy-assistant/go-backend/internal/api"
	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/config"
	"llm-healthy-assistant/go-backend/internal/db"
	"llm-healthy-assistant/go-backend/internal/observability"
	"llm-healthy-assistant/go-backend/internal/repository"
	"llm-healthy-assistant/go-backend/internal/service"
)

func main() {
	cfg := config.Load()

	pool, err := db.NewPool(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("❌ 数据库连接失败: %v", err)
	}
	defer pool.Close()
	if err := observability.Start(pool); err != nil {
		log.Fatalf("observability startup: %v", err)
	}
	log.Println("✅ 数据库连接成功")

	userRepo := repository.NewUserRepo(pool)
	taskRepo := repository.NewTaskRepo(pool)
	reportRepo := repository.NewReportRepo(pool)
	feedbackRepo := repository.NewFeedbackRepo(pool)

	grpcAddr := fmt.Sprintf("127.0.0.1:%s", cfg.GRPCServerAddr)
	aiClient, err := aiclient.New(grpcAddr)
	if err != nil {
		log.Fatalf("❌ 连接 Python AI 失败: %v", err)
	}
	defer aiClient.Close()
	log.Printf("✅ 已连接 Python AI gRPC: %s", grpcAddr)

	taskSvc := service.NewTaskService(taskRepo, userRepo)
	reportSvc := service.NewReportService(reportRepo)

	profileSvc := service.NewProfileService(aiClient)
	feedbackSvc := service.NewFeedbackService(feedbackRepo)
	authSvc := service.NewAuthService(userRepo, []byte(cfg.JWTSecret))

	uploadSvc := service.NewUploadService(repository.NewUploadRepo(pool), "data/uploads")
	router := api.SetupRouter(aiClient, taskSvc, profileSvc, reportSvc, feedbackSvc, authSvc, []byte(cfg.JWTSecret), cfg.RedisURL, uploadSvc)

	addr := fmt.Sprintf(":%s", cfg.ServerPort)
	log.Printf("🚀 Go 业务后端启动 http://localhost%s", addr)
	log.Printf("   AUTH_REQUIRED=%v JWT 已配置", auth.AuthRequired())
	log.Printf("   POST /api/v1/auth/login | /api/v1/auth/register | /oauth/token")
	log.Printf("   /healthz → http://localhost%s/healthz", addr)
	log.Printf("   POST /api/v1/tasks → 创建任务")
	log.Printf("   GET  /api/v1/tasks/:id/events → SSE 事件流")

	if err := http.ListenAndServe(addr, router); err != nil {
		log.Fatalf("服务启动失败: %v", err)
	}
}
