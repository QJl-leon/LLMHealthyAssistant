package api

import (
	"llm-healthy-assistant/go-backend/internal/aiclient"
	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/observability"
	"llm-healthy-assistant/go-backend/internal/service"
	"llm-healthy-assistant/go-backend/internal/sse"

	"github.com/gin-gonic/gin"
)

func SetupRouter(
	aiClient *aiclient.Client,
	taskSvc *service.TaskService,
	profileSvc *service.ProfileService,
	reportSvc *service.ReportService,
	feedbackSvc *service.FeedbackService,
	authSvc *service.AuthService,
	jwtSecret []byte,
	redisURL string,
	uploadSvc *service.UploadService,
) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())

	r.Use(observability.Middleware())
	r.Use(auth.TenantUser(jwtSecret))

	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Trace-Id,X-Tenant-Id,X-User-Id")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	r.GET("/healthz", HealthHandler)

	if authSvc != nil {
		r.POST("/api/v1/auth/register", AuthRegisterHandler(authSvc))
		r.POST("/api/v1/auth/login", AuthLoginHandler(authSvc))
		r.GET("/api/v1/auth/me", AuthMeHandler(authSvc))
		r.POST("/oauth/token", OAuthTokenHandler(authSvc))
	}

	fwd := sse.NewForwarder(aiClient, sse.NewFailoverStore(redisURL, 256))

	r.GET("/uploads/:filename", auth.RequireAuth(), ServeUploads(uploadSvc))

	if reportSvc != nil {
		r.POST("/internal/reports", InternalReportCreateHandler(reportSvc, taskSvc))
		r.POST("/internal/tasks/:id/status", InternalTaskStatusHandler(taskSvc))
	}

	v1 := r.Group("/api/v1")

	if auth.AuthRequired() {
		v1.Use(auth.RequireAuth())
	}
	{
		v1.POST("/uploads", UploadHandler(uploadSvc))
		v1.POST("/tasks", TaskCreateHandler(aiClient, taskSvc, uploadSvc))
		v1.GET("/tasks", TaskListHandler(taskSvc))
		v1.GET("/tasks/:id/events", fwd.GinStreamHandler)
		v1.POST("/tasks/:id/resume", TaskResumeHandler(aiClient, taskSvc, uploadSvc))
		v1.GET("/tasks/:id/cost", TaskCostHandler(aiClient))
		v1.POST("/chat", ChatHandler(aiClient))

		if reportSvc != nil {
			v1.GET("/reports/task/:taskId/versions", ReportVersionsHandler(reportSvc))
			v1.GET("/reports", ReportListHandler(reportSvc))
			v1.GET("/reports/:id", ReportGetHandler(reportSvc))
		}

		if profileSvc != nil {

			v1.GET("/profile", ProfileListHandler(profileSvc))
			v1.POST("/profile", ProfileSaveHandler(profileSvc))
			v1.PUT("/profile/:id", ProfileUpdateHandler(profileSvc))
			v1.POST("/profile/:id/confirm", ProfileConfirmHandler(profileSvc))
			v1.DELETE("/profile/:id", ProfileDeleteHandler(profileSvc))
			v1.DELETE("/profile", ProfileDeleteAllHandler(profileSvc))
			v1.GET("/profile/audit", ProfileAuditHandler(profileSvc))
		}

		if feedbackSvc != nil {
			v1.POST("/feedback", FeedbackCreateHandler(feedbackSvc))
		}

		v1.GET("/admin/whoami", auth.RequireRole("operator"), func(c *gin.Context) {
			c.JSON(200, gin.H{
				"code": 0,
				"data": gin.H{
					"user_id": auth.GetUserID(c),
					"role":    auth.GetRole(c),
					"scopes":  auth.GetScopes(c),
				},
			})
		})
	}

	return r
}
