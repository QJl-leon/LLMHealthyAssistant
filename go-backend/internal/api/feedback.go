
package api

import (
	"log"
	"net/http"

	"llm-healthy-assistant/go-backend/internal/auth"
	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
)

type feedbackCreateRequest struct {
	ReportID  string `json:"report_id" binding:"required"`
	ClaimID   string `json:"claim_id"`
	IssueType string `json:"issue_type" binding:"required"`
	Detail    string `json:"detail"`
}

func FeedbackCreateHandler(svc *service.FeedbackService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := auth.GetUserID(c)

		var req feedbackCreateRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "参数不完整: " + err.Error()},
			})
			return
		}

		issueType := model.FeedbackIssueType(req.IssueType)
		switch issueType {
		case model.FeedbackWrongCitation, model.FeedbackUnsupported,
			model.FeedbackOutdated, model.FeedbackOther:

		default:
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "无效的 issue_type，可选值: wrong_citation | unsupported | outdated | other"},
			})
			return
		}

		fb, err := svc.SubmitFeedback(c.Request.Context(), service.SubmitFeedbackRequest{
			UserID:    userID,
			ReportID:  req.ReportID,
			ClaimID:   req.ClaimID,
			IssueType: issueType,
			Detail:    req.Detail,
		})
		if err != nil {
			log.Printf("[API] FeedbackCreate error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "提交反馈失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"id":         fb.ID,
				"report_id":  fb.ReportID,
				"claim_id":   fb.ClaimID,
				"issue_type": fb.IssueType,
				"detail":     fb.Detail,
				"created_at": fb.CreatedAt,
			},
		})
	}
}
