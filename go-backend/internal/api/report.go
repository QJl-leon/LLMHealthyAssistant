
package api

import (
	"log"
	"net/http"
	"strconv"

	"llm-healthy-assistant/go-backend/internal/auth"
	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
)

func ReportListHandler(svc *service.ReportService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := auth.GetUserID(c)
		taskID := c.Query("task_id")

		limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
		if limit < 1 || limit > 100 {
			limit = 20
		}
		offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
		if offset < 0 {
			offset = 0
		}

		reports, err := svc.ListReports(c.Request.Context(), service.ListReportsRequest{
			UserID: userID,
			TaskID: taskID,
			Limit:  limit,
			Offset: offset,
		})
		if err != nil {
			log.Printf("[API] ReportList error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取报告列表失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(reports))
		for _, r := range reports {
			item := gin.H{
				"id":                r.ID,
				"task_id":           r.TaskID,
				"version":           r.Version,
				"knowledge_version": r.KnowledgeVersion,
				"status":            r.Status,
				"created_at":        r.CreatedAt,
			}

			if r.Content.Sections.Observation != "" {
				item["summary"] = truncateRunes(r.Content.Sections.Observation, 120)
			}
			items = append(items, item)
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"items":  items,
				"total":  len(items),
				"limit":  limit,
				"offset": offset,
			},
		})
	}
}

func ReportGetHandler(svc *service.ReportService) gin.HandlerFunc {
	return func(c *gin.Context) {
		reportID := c.Param("id")
		if reportID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "缺少 report_id"},
			})
			return
		}

		report, err := svc.GetReport(c.Request.Context(), reportID)
		if err != nil {
			log.Printf("[API] ReportGet error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取报告失败"},
			})
			return
		}

		citations := make([]gin.H, 0, len(report.Content.Citations))
		for _, cit := range report.Content.Citations {
			citations = append(citations, gin.H{
				"claim_id":    cit.ClaimID,
				"evidence_id": cit.EvidenceID,
				"source_name": cit.SourceName,
				"quote":       cit.Quote,
				"source_url":  cit.SourceURL,
			})
		}

		sections := gin.H{
			"observation":      report.Content.Sections.Observation,
			"facts":            report.Content.Sections.Facts,
			"inferences":       report.Content.Sections.Inferences,
			"conflicts":        report.Content.Sections.Conflicts,
			"unknowns":         report.Content.Sections.Unknowns,
			"related_to_you":   report.Content.Sections.RelatedToYou,
			"metric_reading":   report.Content.Sections.MetricReading,
			"metric_trend":     report.Content.Sections.MetricTrend,
			"exercise_advice":  report.Content.Sections.ExerciseAdvice,
			"lifestyle_advice": report.Content.Sections.LifestyleAdvice,
			"followup_advice":  report.Content.Sections.FollowupAdvice,
		}
		if report.Content.Metadata != nil {
			if inj := report.Content.Metadata["memory_injection"]; inj != "" {
				sections["memory_injection"] = inj
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
				"sections":          sections,
				"citations":         citations,
				"metrics":           report.Content.Metrics,
				"metric_trends":     report.Content.MetricTrends,
				"metadata":          report.Content.Metadata,
			},
		})
	}
}

func ReportVersionsHandler(svc *service.ReportService) gin.HandlerFunc {
	return func(c *gin.Context) {
		taskID := c.Param("taskId")
		if taskID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "缺少 task_id"},
			})
			return
		}

		reports, err := svc.ListVersions(c.Request.Context(), taskID)
		if err != nil {
			log.Printf("[API] ReportVersions error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取版本列表失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(reports))
		for _, r := range reports {
			items = append(items, gin.H{
				"id":                r.ID,
				"task_id":           r.TaskID,
				"version":           r.Version,
				"knowledge_version": r.KnowledgeVersion,
				"status":            r.Status,
				"created_at":        r.CreatedAt,
				"summary":           truncateRunes(r.Content.Sections.Observation, 120),
			})
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{"items": items, "total": len(items)},
		})
	}
}

func truncateRunes(s string, max int) string {
	rs := []rune(s)
	if len(rs) <= max {
		return s
	}
	return string(rs[:max]) + "…"
}
