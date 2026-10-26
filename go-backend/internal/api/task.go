package api

import (
	"context"
	"log"
	"net/http"

	"llm-healthy-assistant/go-backend/internal/aiclient"
	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"
	"llm-healthy-assistant/go-backend/internal/auth"
	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/observability"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type createTaskRequest struct {
	ClientTaskID string `json:"client_task_id" binding:"required"`

	ImageKeys []string `json:"image_keys"`

	Images []imageRef `json:"images"`

	ReportDate string `json:"report_date"`

	Institution string `json:"institution"`
}

type imageRef struct {
	Key      string `json:"key" binding:"required"`
	Position string `json:"position"`
}

func normalizeImages(images []imageRef, keys []string) []imageRef {
	if len(images) > 0 {
		out := make([]imageRef, 0, len(images))
		for _, img := range images {
			if img.Key == "" {
				continue
			}
			pos := img.Position
			if pos == "" {
				pos = "exam_report"
			}
			out = append(out, imageRef{Key: img.Key, Position: pos})
		}
		return out
	}
	out := make([]imageRef, 0, len(keys))
	for _, key := range keys {
		if key == "" {
			continue
		}
		out = append(out, imageRef{Key: key, Position: "exam_report"})
	}
	return out
}

func imageKeysOf(images []imageRef) []string {
	keys := make([]string, 0, len(images))
	for _, img := range images {
		keys = append(keys, img.Key)
	}
	return keys
}

func TaskCreateHandler(client *aiclient.Client, taskSvc *service.TaskService, uploads *service.UploadService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req createTaskRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code": 400,
				"error": gin.H{
					"error_code": errs.CodeBadRequest,
					"message":    err.Error(),
				},
			})
			return
		}

		tenantID := auth.GetTenantID(c)
		userID := auth.GetUserID(c)
		imagesIn := normalizeImages(req.Images, req.ImageKeys)
		if len(imagesIn) == 0 {
			c.JSON(http.StatusBadRequest, gin.H{
				"code": 400,
				"error": gin.H{
					"error_code": errs.CodeBadRequest,
					"message":    "至少需要上传一张体检报告图片",
				},
			})
			return
		}

		if !uploadIdentity(c) {
			return
		}
		if err := uploads.CheckOwned(c.Request.Context(), imageKeysOf(imagesIn), tenantID, userID); err != nil {
			uploadFailure(c, err)
			return
		}

		created, err := taskSvc.Create(c.Request.Context(), service.CreateTaskRequest{
			TenantID:     tenantID,
			UserID:       userID,
			ClientTaskID: req.ClientTaskID,
			ImageKeys:    imageKeysOf(imagesIn),
		})
		if err != nil {
			log.Printf("[API] TaskService.Create error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code": 500,
				"error": gin.H{
					"error_code": errs.CodeInternal,
					"message":    "任务落库失败: " + err.Error(),
				},
			})
			return
		}

		observability.Event("task_submission", map[string]any{"task_id": created.TaskID, "trace_id": created.TraceID, "request_trace_id": c.GetString("observation_trace"), "run_id": c.GetHeader("X-Run-Id"), "client_task_id": req.ClientTaskID, "is_new": created.IsNew})

		if !created.IsNew {
			c.JSON(http.StatusOK, gin.H{
				"code": 0,
				"data": gin.H{
					"task_id":  created.TaskID,
					"status":   created.Status,
					"trace_id": created.TraceID,
					"is_new":   false,
				},
			})
			return
		}

		var images []*researchv1.ImageAsset
		for _, img := range imagesIn {
			images = append(images, &researchv1.ImageAsset{
				Key:          img.Key,
				Position:     img.Position,
				PresignedUrl: "/uploads/" + img.Key,
			})
		}

		resp, err := client.SubmitTask(c.Request.Context(), &researchv1.SubmitTaskRequest{
			TaskId:       created.TaskID,
			TenantId:     tenantID,
			UserId:       userID,
			ClientTaskId: req.ClientTaskID,
			Images:       images,
			ReportDate:   req.ReportDate,
			Institution:  req.Institution,
		})
		if err != nil {
			log.Printf("[API] SubmitTask gRPC error: %v", err)
			_ = taskSvc.UpdateTaskStatus(context.Background(), created.TaskID, "failed")
			c.JSON(http.StatusInternalServerError, gin.H{
				"code": 500,
				"error": gin.H{
					"error_code": errs.CodeUpstreamUnavailable,
					"message":    err.Error(),
					"retryable":  errs.IsRetryable(errs.CodeUpstreamUnavailable),
				},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"task_id":  resp.TaskId,
				"status":   resp.Status,
				"trace_id": created.TraceID,
				"is_new":   true,
			},
		})
	}
}

type resumeTaskRequest struct {
	Action       string     `json:"action" binding:"required"`
	NewImageKeys []string   `json:"new_image_keys"`
	NewImages    []imageRef `json:"new_images"`
	Decisions    []struct {
		CandidateID string `json:"candidate_id"`
		Accepted    bool   `json:"accepted"`
	} `json:"decisions"`
}

func TaskResumeHandler(client *aiclient.Client, taskSvc *service.TaskService, uploads *service.UploadService) gin.HandlerFunc {
	return func(c *gin.Context) {
		taskID := c.Param("id")
		if taskID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "missing task_id"},
			})
			return
		}

		if !uploadIdentity(c) {
			return
		}
		if _, err := uuid.Parse(taskID); err != nil {
			c.AbortWithStatusJSON(404, gin.H{"code": 404, "error": gin.H{"message": "任务不存在"}})
			return
		}
		task, err := taskSvc.GetTask(c.Request.Context(), auth.GetTenantID(c), taskID)
		if err != nil {
			c.AbortWithStatusJSON(500, gin.H{"code": 500, "error": gin.H{"message": "任务访问失败"}})
			return
		}
		if task == nil || task.UserID != auth.GetUserID(c) || task.TenantID != auth.GetTenantID(c) {
			c.AbortWithStatusJSON(404, gin.H{"code": 404, "error": gin.H{"message": "任务不存在"}})
			return
		}

		var req resumeTaskRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}

		traceID := c.GetHeader("X-Trace-Id")
		if traceID == "" {
			traceID = taskID
		}

		ctx := context.Background()

		switch req.Action {
		case "add_images":

			imgs := normalizeImages(req.NewImages, req.NewImageKeys)
			if len(imgs) == 0 {
				c.AbortWithStatusJSON(400, gin.H{"code": 400, "error": gin.H{"message": "至少需要上传一张图片"}})
				return
			}
			if err := uploads.CheckOwned(c.Request.Context(), imageKeysOf(imgs), auth.GetTenantID(c), auth.GetUserID(c)); err != nil {
				uploadFailure(c, err)
				return
			}
			var images []*researchv1.ImageAsset
			for _, img := range imgs {
				images = append(images, &researchv1.ImageAsset{
					Key:          img.Key,
					Position:     img.Position,
					PresignedUrl: "/uploads/" + img.Key,
				})
			}
			resp, err := client.ResumeTask(ctx, &researchv1.ResumeTaskRequest{
				TaskId:    taskID,
				TraceId:   traceID,
				Action:    "add_images",
				NewImages: images,
			})
			if err != nil {
				log.Printf("[API] ResumeTask(add_images) gRPC error: %v", err)
				c.JSON(http.StatusInternalServerError, gin.H{
					"code":  500,
					"error": gin.H{"error_code": errs.CodeUpstreamUnavailable, "message": err.Error()},
				})
				return
			}
			log.Printf("[API] ResumeTask(add_images) task=%s status=%s images=%d", taskID, resp.Status, len(images))
			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": resp.Status}})

		case "confirm_memory":

			var lastStatus string
			for _, d := range req.Decisions {
				resp, err := client.ResumeTask(ctx, &researchv1.ResumeTaskRequest{
					TaskId:      taskID,
					TraceId:     traceID,
					Action:      "confirm_memory",
					CandidateId: d.CandidateID,
					Confirmed:   d.Accepted,
				})
				if err != nil {
					log.Printf("[API] ResumeTask(confirm_memory) gRPC error: %v", err)
					c.JSON(http.StatusInternalServerError, gin.H{
						"code":  500,
						"error": gin.H{"error_code": errs.CodeUpstreamUnavailable, "message": err.Error()},
					})
					return
				}
				lastStatus = resp.Status
				log.Printf("[API] ResumeTask(confirm_memory) candidate=%s accepted=%v status=%s",
					d.CandidateID, d.Accepted, resp.Status)
			}
			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": lastStatus}})

		case "confirm_publish":

			resp, err := client.ResumeTask(ctx, &researchv1.ResumeTaskRequest{
				TaskId:    taskID,
				TraceId:   traceID,
				Action:    "confirm_publish",
				Confirmed: true,
			})
			if err != nil {
				log.Printf("[API] ResumeTask(confirm_publish) gRPC error: %v", err)
				c.JSON(http.StatusInternalServerError, gin.H{
					"code":  500,
					"error": gin.H{"error_code": errs.CodeUpstreamUnavailable, "message": err.Error()},
				})
				return
			}
			log.Printf("[API] ResumeTask(confirm_publish) task=%s status=%s", taskID, resp.Status)
			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": resp.Status}})

		case "cancel_publish":

			resp, err := client.ResumeTask(ctx, &researchv1.ResumeTaskRequest{
				TaskId:    taskID,
				TraceId:   traceID,
				Action:    "cancel_publish",
				Confirmed: false,
			})
			if err != nil {
				log.Printf("[API] ResumeTask(cancel_publish) gRPC error: %v", err)
				c.JSON(http.StatusInternalServerError, gin.H{
					"code":  500,
					"error": gin.H{"error_code": errs.CodeUpstreamUnavailable, "message": err.Error()},
				})
				return
			}
			log.Printf("[API] ResumeTask(cancel_publish) task=%s status=%s", taskID, resp.Status)
			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"task_id": taskID, "status": resp.Status}})

		default:
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "unknown action: " + req.Action},
			})
		}
	}
}

func TaskCostHandler(client *aiclient.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		taskID := c.Param("id")
		if taskID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "missing task_id"},
			})
			return
		}

		resp, err := client.GetTaskCost(c.Request.Context(), taskID, auth.GetUserID(c))
		if err != nil {
			log.Printf("[API] TaskCost error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "查询任务成本失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(resp.Items))
		for _, it := range resp.Items {
			items = append(items, gin.H{
				"call_type":         it.CallType,
				"model":             it.Model,
				"calls":             it.Calls,
				"tokens":            it.Tokens,
				"prompt_tokens":     it.PromptTokens,
				"completion_tokens": it.CompletionTokens,
				"avg_latency_ms":    it.AvgLatencyMs,
			})
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"task_id":      resp.TaskId,
				"total_tokens": resp.TotalTokens,
				"call_count":   resp.CallCount,
				"items":        items,
			},
		})
	}
}

func TaskListHandler(taskSvc *service.TaskService) gin.HandlerFunc {
	return func(c *gin.Context) {
		tenantID := auth.GetTenantID(c)
		userID := auth.GetUserID(c)

		tasks, err := taskSvc.ListUserTasks(c.Request.Context(), tenantID, userID, 50, 0)
		if err != nil {
			log.Printf("[API] TaskList error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取任务列表失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(tasks))
		for _, t := range tasks {
			items = append(items, gin.H{
				"id":             t.ID,
				"client_task_id": t.ClientTaskID,
				"status":         t.Status,
				"image_count":    len(t.ImageKeys),
				"created_at":     t.CreatedAt,
			})
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{"items": items, "total": len(items)},
		})
	}
}

type chatHistoryItem struct {
	Role    string `json:"role" binding:"required,oneof=user assistant"`
	Content string `json:"content" binding:"required"`
}

type chatRequest struct {
	Query   string            `json:"query" binding:"required"`
	History []chatHistoryItem `json:"history"`
}

func ChatHandler(client *aiclient.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req chatRequest
		if err := c.ShouldBindJSON(&req); err != nil || req.Query == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "query 不能为空"},
			})
			return
		}

		userID := auth.GetUserID(c)

		history := make([]*researchv1.ChatHistoryItem, 0, len(req.History))
		for _, h := range req.History {
			if (h.Role == "user" || h.Role == "assistant") && h.Content != "" {
				history = append(history, &researchv1.ChatHistoryItem{
					Role:    h.Role,
					Content: h.Content,
				})
			}
		}
		if n := len(history); n > 8 {
			history = history[n-8:]
		}

		resp, err := client.Chat(c.Request.Context(), &researchv1.ChatRequest{
			UserId:  userID,
			Query:   req.Query,
			TraceId: userID,
			History: history,
		})
		if err != nil {
			log.Printf("[API] Chat error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeUpstreamUnavailable, "message": "对话服务暂不可用"},
			})
			return
		}

		evidence := make([]gin.H, 0, len(resp.Evidence))
		for _, ev := range resp.Evidence {
			evidence = append(evidence, gin.H{
				"evidence_id":  ev.EvidenceId,
				"source_name":  ev.SourceName,
				"source_level": ev.SourceLevel,
				"quote":        ev.Quote,
				"source_url":   ev.SourceUrl,
			})
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"refused":  resp.Refused,
				"answer":   resp.Answer,
				"evidence": evidence,
			},
		})
	}
}
