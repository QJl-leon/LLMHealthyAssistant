package api

import (
	"llm-healthy-assistant/go-backend/internal/observability"
	"log"
	"net/http"
	"os"
	"time"

	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
)

type internalReportRequest struct {
	TaskID           string            `json:"task_id" binding:"required"`
	KnowledgeVersion string            `json:"knowledge_version"`
	Status           string            `json:"status"`
	Sections         map[string]string `json:"sections"`
	Citations        []struct {
		ClaimID    string `json:"claim_id"`
		EvidenceID string `json:"evidence_id"`
		SourceName string `json:"source_name"`
		Quote      string `json:"quote"`
		SourceURL  string `json:"source_url"`
	} `json:"citations"`
	Metadata map[string]string `json:"metadata"`

	Metrics []model.MetricItem `json:"metrics"`

	MetricTrends []model.MetricTrend `json:"metric_trends"`
}

func InternalReportCreateHandler(reportSvc *service.ReportService, taskSvc *service.TaskService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if token := os.Getenv("INTERNAL_API_TOKEN"); token != "" {
			if c.GetHeader("X-Internal-Token") != token {
				c.JSON(http.StatusUnauthorized, gin.H{
					"code":  401,
					"error": gin.H{"error_code": errs.CodePermissionDenied, "message": "invalid internal token"},
				})
				return
			}
		}

		var req internalReportRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}

		status := req.Status
		if status == "" {
			status = "published"
		}
		kv := req.KnowledgeVersion
		if kv == "" {
			kv = "unknown"
		}

		sections := req.Sections
		if sections == nil {
			sections = map[string]string{}
		}

		content := model.ReportContent{
			Sections: model.ReportSection{
				Observation:     firstNonEmpty(sections, "observation", "🔍 观察"),
				Facts:           firstNonEmpty(sections, "facts", "📋 事实"),
				Inferences:      firstNonEmpty(sections, "inferences", "🧠 推断"),
				Conflicts:       firstNonEmpty(sections, "conflicts", "⚡ 冲突"),
				Unknowns:        firstNonEmpty(sections, "unknowns", "❓ 未知"),
				RelatedToYou:    firstNonEmpty(sections, "related_to_you", "👤 与你相关"),
				MetricReading:   firstNonEmpty(sections, "metric_reading", "📊 指标解读"),
				MetricTrend:     firstNonEmpty(sections, "metric_trend", "📈 指标趋势"),
				ExerciseAdvice:  firstNonEmpty(sections, "exercise_advice", "🏃 运动建议"),
				LifestyleAdvice: firstNonEmpty(sections, "lifestyle_advice", "🌿 生活方式建议"),
				FollowupAdvice:  firstNonEmpty(sections, "followup_advice", "📅 随访建议"),
			},
			Metrics:      req.Metrics,
			MetricTrends: req.MetricTrends,
			Metadata:     req.Metadata,
		}

		if content.Metadata == nil {
			content.Metadata = map[string]string{}
		}
		if inj := firstNonEmpty(sections, "memory_injection", "🧠 记忆注入"); inj != "" {
			content.Metadata["memory_injection"] = inj
		}
		for _, cit := range req.Citations {
			content.Citations = append(content.Citations, model.ReportCitation{
				ClaimID:    cit.ClaimID,
				EvidenceID: cit.EvidenceID,
				SourceName: cit.SourceName,
				Quote:      cit.Quote,
				SourceURL:  cit.SourceURL,
			})
		}

		saveStarted := time.Now()
		report, err := reportSvc.CreateReport(c.Request.Context(), service.CreateReportRequest{
			TaskID:           req.TaskID,
			KnowledgeVersion: kv,
			Content:          content,
			Status:           status,
		})
		if err != nil {
			observability.ReportWrite(req.TaskID, "", time.Since(saveStarted), err)
			log.Printf("[API] InternalReportCreate error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "落库失败: " + err.Error()},
			})
			return
		}

		observability.ReportWrite(req.TaskID, report.ID, time.Since(saveStarted), nil)

		if taskSvc != nil && (status == "published" || status == "refused") {
			if err := taskSvc.UpdateTaskStatus(c.Request.Context(), req.TaskID, status); err != nil {
				log.Printf("[API] update task status after report: %v", err)
			}
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"id":                report.ID,
				"task_id":           report.TaskID,
				"version":           report.Version,
				"knowledge_version": report.KnowledgeVersion,
				"status":            report.Status,
				"created_at":        report.CreatedAt,
			},
		})
	}
}

func firstNonEmpty(m map[string]string, keys ...string) string {
	for _, k := range keys {
		if v := m[k]; v != "" {
			return v
		}
	}
	return ""
}
