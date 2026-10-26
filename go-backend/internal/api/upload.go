package api

import (
	"errors"
	"log"
	"net/http"

	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/service"
	"llm-healthy-assistant/go-backend/internal/upload"

	errs "llm-healthy-assistant/go-backend/internal/errors"

	"github.com/gin-gonic/gin"
)

const uploadDir = "data/uploads"

func uploadIdentity(c *gin.Context) bool {
	if !auth.IsAuthenticated(c) || auth.GetUserID(c) == "" || auth.GetTenantID(c) == "" {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"code": 401, "error": gin.H{"error_code": "PERMISSION_DENIED", "message": "需要登录"}})
		return false
	}
	return true
}

func UploadHandler(svc *service.UploadService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !uploadIdentity(c) {
			return
		}

		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, upload.DefaultOptions().MaxBytes+1<<20)
		if err := c.Request.ParseMultipartForm(upload.DefaultOptions().MaxBytes); err != nil {
			if isMaxBytesErr(err) {
				c.JSON(http.StatusRequestEntityTooLarge, gin.H{
					"code":  413,
					"error": gin.H{"error_code": errs.CodeBadRequest, "message": "图片过大"},
				})
			} else {
				c.JSON(http.StatusBadRequest, gin.H{
					"code":  400,
					"error": gin.H{"error_code": errs.CodeBadRequest, "message": "请选择图片文件"},
				})
			}
			return
		}

		defer c.Request.MultipartForm.RemoveAll()

		if !svc.AllowIP(c.ClientIP()) {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"code":  429,
				"error": gin.H{"error_code": errs.CodeRateLimited, "message": "上传过于频繁，请稍后重试"},
			})
			return
		}

		file, header, err := c.Request.FormFile("file")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code":  400,
				"error": gin.H{"error_code": errs.CodeBadRequest, "message": "请选择图片文件"},
			})
			return
		}
		defer file.Close()

		saved, err := svc.Save(c.Request.Context(), auth.GetTenantID(c), auth.GetUserID(c), file, header.Filename)
		if err != nil {
			status, code, msg := mapUploadError(err)
			c.JSON(status, gin.H{
				"code":  code,
				"error": gin.H{"error_code": code, "message": msg},
			})
			return
		}

		log.Printf("[Upload] 图片已保存: %s (%d bytes) %s/%s %dx%d pos=%s",
			saved.Name, saved.Size, saved.Mime, saved.Ext,
			saved.Width, saved.Height, c.PostForm("position"))

		c.JSON(http.StatusOK, gin.H{
			"code": 0,
			"data": gin.H{
				"image_key": saved.Name,
				"url":       "/uploads/" + saved.Name,
				"size":      saved.Size,
				"mime":      saved.Mime,
				"width":     saved.Width,
				"height":    saved.Height,
				"position":  c.PostForm("position"),
			},
		})
	}

}

func mapUploadError(err error) (int, string, string) {
	switch {
	case errors.Is(err, upload.ErrUnsupportedFormat):
		return http.StatusBadRequest, errs.CodeBadRequest, "仅支持 JPG / PNG / WebP / GIF 图片"
	case errors.Is(err, upload.ErrTooLarge):
		return http.StatusRequestEntityTooLarge, errs.CodeBadRequest, "图片过大，请压缩后重传"
	case errors.Is(err, upload.ErrPixelsTooLarge):
		return http.StatusBadRequest, errs.CodeBadRequest, "图片分辨率过高，请压缩后重传"
	case errors.Is(err, upload.ErrEmptyFile):
		return http.StatusBadRequest, errs.CodeBadRequest, "空文件，请重新选择图片"
	case errors.Is(err, upload.ErrRateLimited):
		return http.StatusTooManyRequests, errs.CodeRateLimited, "上传过于频繁，请稍后重试"
	case errors.Is(err, upload.ErrBusy):
		return http.StatusServiceUnavailable, errs.CodeUpstreamUnavailable, "服务器繁忙，请稍后重试"
	default:
		log.Printf("[Upload] 保存失败: %v", err)
		return http.StatusInternalServerError, errs.CodeInternal, "文件保存失败"
	}
}

// uploadFailure deliberately hides whether another user's image exists.
func uploadFailure(c *gin.Context, err error) {
	if errors.Is(err, service.ErrUploadNotFound) {
		c.AbortWithStatusJSON(404, gin.H{"code": 404, "error": gin.H{"message": "图片不存在"}})
	} else {
		log.Printf("[Upload] ownership lookup failed: %v", err)
		c.AbortWithStatusJSON(500, gin.H{"code": 500, "error": gin.H{"message": "图片访问失败"}})
	}
}

func ServeUploads(svc *service.UploadService) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Cache-Control", "private, no-store")
		c.Header("X-Content-Type-Options", "nosniff")
		if !uploadIdentity(c) {
			return
		}
		file, record, err := svc.OpenOwned(c.Request.Context(), c.Param("filename"), auth.GetTenantID(c), auth.GetUserID(c))
		if err != nil {
			uploadFailure(c, err)
			return
		}
		defer file.Close()
		info, err := file.Stat()
		if err != nil {
			uploadFailure(c, service.ErrUploadNotFound)
			return
		}
		c.Header("Content-Type", record.MIME)
		http.ServeContent(c.Writer, c.Request, file.Name(), info.ModTime(), file)
	}
}

func isMaxBytesErr(err error) bool {
	var mbe *http.MaxBytesError
	return errors.As(err, &mbe)
}
