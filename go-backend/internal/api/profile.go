
package api

import (
	"log"
	"net/http"

	"llm-healthy-assistant/go-backend/internal/auth"
	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/service"

	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"

	"github.com/gin-gonic/gin"
)

type profileSaveRequest struct {
	Kind    string `json:"kind" binding:"required"`
	Content string `json:"content" binding:"required"`
	Source  string `json:"source"`
}

type profileUpdateRequest struct {
	Content string `json:"content" binding:"required"`
}

var validProfileKinds = map[string]bool{
	"basic": true, "condition": true, "medication": true,
	"allergy": true, "goal": true, "exercise": true,
}

func memoryItemJSON(m *researchv1.MemoryItem) gin.H {
	return gin.H{
		"id":                   m.Id,
		"kind":                 m.Kind,
		"content":              m.Content,
		"source":               m.Source,
		"version":              m.Version,
		"pending_confirmation": m.PendingConfirmation,
		"created_at":           m.CreatedAt,
	}
}

func ProfileListHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := auth.GetUserID(c)
		resp, err := svc.GetActiveProfiles(c.Request.Context(), userID)
		if err != nil {
			log.Printf("[API] ProfileList error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取档案列表失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(resp.Items))
		for _, m := range resp.Items {
			items = append(items, memoryItemJSON(m))
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"items": items}})
	}
}

func ProfileSaveHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req profileSaveRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}

		if !validProfileKinds[req.Kind] {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "无效的档案类型: " + req.Kind},
			})
			return
		}

		saved, err := svc.SaveProfile(c.Request.Context(), service.SaveProfileRequest{
			UserID:  auth.GetUserID(c),
			Kind:    model.ProfileKind(req.Kind),
			Content: req.Content,
			Source:  req.Source,
		})
		if err != nil {
			log.Printf("[API] ProfileSave error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "保存档案失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": memoryItemJSON(saved)})
	}
}

func ProfileUpdateHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		entryID := c.Param("id")
		if entryID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "缺少 profile_id"},
			})
			return
		}

		var req profileUpdateRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}

		item, err := svc.UpdateProfile(c.Request.Context(), auth.GetUserID(c), entryID, req.Content)
		if err != nil {
			log.Printf("[API] ProfileUpdate error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "更新档案失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": memoryItemJSON(item)})
	}
}

func ProfileConfirmHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		entryID := c.Param("id")
		if entryID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "缺少 profile_id"},
			})
			return
		}

		item, err := svc.ConfirmProfile(c.Request.Context(), auth.GetUserID(c), entryID)
		if err != nil {
			log.Printf("[API] ProfileConfirm error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "确认失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": memoryItemJSON(item)})
	}
}

func ProfileDeleteHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		entryID := c.Param("id")
		if entryID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "缺少 profile_id"},
			})
			return
		}

		if err := svc.DeleteProfile(c.Request.Context(), auth.GetUserID(c), entryID); err != nil {
			log.Printf("[API] ProfileDelete error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "删除失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"id": entryID, "deleted": true}})
	}
}

func ProfileDeleteAllHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := auth.GetUserID(c)
		count, err := svc.DeleteAllProfiles(c.Request.Context(), userID)
		if err != nil {
			log.Printf("[API] ProfileDeleteAll error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "全量删除失败"},
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"deleted_count": count}})
	}
}

func ProfileAuditHandler(svc *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := auth.GetUserID(c)
		resp, err := svc.ListProfileAudit(c.Request.Context(), userID, 100)
		if err != nil {
			log.Printf("[API] ProfileAudit error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"code":  500,
				"error": gin.H{"error_code": errs.CodeInternal, "message": "获取审计记录失败"},
			})
			return
		}

		items := make([]gin.H, 0, len(resp.Items))
		for _, a := range resp.Items {
			items = append(items, gin.H{
				"id":         a.Id,
				"action":     a.Action,
				"target_id":  a.TargetId,
				"detail":     a.Detail,
				"created_at": a.CreatedAt,
			})
		}

		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{"items": items}})
	}
}
