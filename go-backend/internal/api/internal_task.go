package api

import (
	"log"
	"net/http"
	"os"

	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
)

func InternalTaskStatusHandler(taskSvc *service.TaskService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if token := os.Getenv("INTERNAL_API_TOKEN"); token != "" {
			if c.GetHeader("X-Internal-Token") != token {
				c.JSON(http.StatusUnauthorized, gin.H{
					"code": 401, "error": gin.H{"error_code": errs.CodePermissionDenied},
				})
				return
			}
		}
		taskID := c.Param("id")
		var req struct {
			Status string `json:"status" binding:"required"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "error": gin.H{"error_code": errs.CodeBadRequest}})
			return
		}

		allowed := map[string]bool{
			"published": true, "refused": true, "persist_failed": true,
			"cancelled": true, "failed": true,
		}
		if !allowed[req.Status] {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "error": gin.H{"error_code": errs.CodeBadRequest, "message": "非法状态"}})
			return
		}
		if taskSvc == nil {
			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": req.Status}})
			return
		}
		if err := taskSvc.UpdateTaskStatus(c.Request.Context(), taskID, req.Status); err != nil {
			log.Printf("[API] InternalTaskStatus error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "error": gin.H{"error_code": errs.CodeInternal}})
			return
		}
		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": req.Status}})
	}
}

var _ = model.Task{}
