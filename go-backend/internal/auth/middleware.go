
package auth

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

type ctxKey string

const (
	keyTenantID ctxKey = "tenant_id"
	keyUserID   ctxKey = "user_id"
	keyRole     ctxKey = "role"
	keyScopes   ctxKey = "scopes"
	keyAuthed   ctxKey = "authenticated"
)

func AuthRequired() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("AUTH_REQUIRED")))
	return v == "1" || v == "true" || v == "yes"
}

func TenantUser(jwtSecret []byte) gin.HandlerFunc {
	return func(c *gin.Context) {
		tenantID := ""
		userID := ""
		role := ""
		var scopes []string
		authed := false

		token := extractBearer(c)
		if token == "" {
			token = c.Query("access_token")
		}

		if token != "" && len(jwtSecret) > 0 {
			claims, err := VerifyJWT(jwtSecret, token)
			if err == nil {
				tenantID = claims.TenantID
				userID = claims.Subject
				role = claims.Role
				scopes = claims.Scopes
				authed = true
			} else if AuthRequired() {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
					"code":  401,
					"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "无效或过期的令牌"},
				})
				return
			}
		}

		if !authed && !AuthRequired() {
			if userID == "" {
				userID = c.GetHeader("X-User-Id")
			}
			if tenantID == "" {
				tenantID = c.GetHeader("X-Tenant-Id")
			}
			if tenantID == "" {
				tenantID = "00000000-0000-0000-0000-000000000001"
			}
			if userID == "" {
				userID = "00000000-0000-0000-0000-000000000001"
			}
			if role == "" {
				role = "user"
			}
		}

		if AuthRequired() && !authed {

			tenantID = ""
			userID = ""
		}

		if role == "" && authed {
			role = "user"
		}

		ctx := context.WithValue(c.Request.Context(), keyTenantID, tenantID)
		ctx = context.WithValue(ctx, keyUserID, userID)
		ctx = context.WithValue(ctx, keyRole, role)
		ctx = context.WithValue(ctx, keyScopes, scopes)
		ctx = context.WithValue(ctx, keyAuthed, authed)
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func extractBearer(c *gin.Context) string {
	authHeader := c.GetHeader("Authorization")
	if strings.HasPrefix(authHeader, "Bearer ") {
		return strings.TrimPrefix(authHeader, "Bearer ")
	}
	return ""
}

func RequireAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		if AuthRequired() {
			if !IsAuthenticated(c) || GetUserID(c) == "" {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
					"code":  401,
					"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "需要登录"},
				})
				return
			}
		} else if GetUserID(c) == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"code":  401,
				"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "需要认证"},
			})
			return
		}
		c.Next()
	}
}

func RequireRole(minRole string) gin.HandlerFunc {
	rank := map[string]int{"user": 1, "operator": 2, "admin": 3}
	return func(c *gin.Context) {
		if AuthRequired() && !IsAuthenticated(c) {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"code":  401,
				"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "需要登录"},
			})
			return
		}
		have := rank[GetRole(c)]
		need := rank[minRole]
		if have == 0 {
			have = 1
		}
		if need == 0 {
			need = 1
		}
		if have < need {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"code":  403,
				"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "权限不足，需要角色 " + minRole},
			})
			return
		}
		c.Next()
	}
}

func RequireScope(scope string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if HasScope(c, scope) {
			c.Next()
			return
		}

		if GetRole(c) == "admin" {
			c.Next()
			return
		}
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
			"code":  403,
			"error": gin.H{"error_code": "PERMISSION_DENIED", "message": "缺少 scope: " + scope},
		})
	}
}

func GetTenantID(c *gin.Context) string {
	v, _ := c.Request.Context().Value(keyTenantID).(string)
	return v
}

func GetUserID(c *gin.Context) string {
	v, _ := c.Request.Context().Value(keyUserID).(string)
	return v
}

func GetRole(c *gin.Context) string {
	v, _ := c.Request.Context().Value(keyRole).(string)
	return v
}

func GetScopes(c *gin.Context) []string {
	v, _ := c.Request.Context().Value(keyScopes).([]string)
	return v
}

func IsAuthenticated(c *gin.Context) bool {
	v, _ := c.Request.Context().Value(keyAuthed).(bool)
	return v
}

func HasScope(c *gin.Context, scope string) bool {
	for _, s := range GetScopes(c) {
		if s == scope || s == "*" {
			return true
		}
	}
	return false
}
