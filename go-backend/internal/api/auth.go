package api

import (
	"net/http"
	"strings"

	"llm-healthy-assistant/go-backend/internal/auth"
	errs "llm-healthy-assistant/go-backend/internal/errors"
	"llm-healthy-assistant/go-backend/internal/service"

	"github.com/gin-gonic/gin"
)

func AuthRegisterHandler(svc *service.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req struct {
			Email    string `json:"email" binding:"required"`
			Password string `json:"password" binding:"required"`
			Nickname string `json:"nickname"`
			TenantID string `json:"tenant_id"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code": 400, "error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}
		res, err := svc.Register(c.Request.Context(), service.RegisterRequest{
			Email: req.Email, Password: req.Password, Nickname: req.Nickname, TenantID: req.TenantID,
		})
		if err != nil {
			code := http.StatusBadRequest
			if strings.Contains(err.Error(), "已注册") {
				code = http.StatusConflict
			}
			c.JSON(code, gin.H{
				"code": code, "error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{"code": 0, "data": res})
	}
}

func AuthLoginHandler(svc *service.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req struct {
			Email    string `json:"email" binding:"required"`
			Password string `json:"password" binding:"required"`
			TenantID string `json:"tenant_id"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"code": 400, "error": gin.H{"error_code": errs.CodeBadRequest, "message": err.Error()},
			})
			return
		}
		res, err := svc.Login(c.Request.Context(), service.LoginRequest{
			Email: req.Email, Password: req.Password, TenantID: req.TenantID,
		})
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code": 401, "error": gin.H{"error_code": "PERMISSION_DENIED", "message": err.Error()},
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{"code": 0, "data": res})
	}
}

func AuthMeHandler(svc *service.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		uid := auth.GetUserID(c)
		if uid == "" || (auth.AuthRequired() && !auth.IsAuthenticated(c)) {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code": 401, "error": gin.H{"error_code": "PERMISSION_DENIED", "message": "需要登录"},
			})
			return
		}
		user, err := svc.Me(c.Request.Context(), uid)
		if err != nil || user == nil {

			c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{
				"id": uid, "tenant_id": auth.GetTenantID(c),
				"nickname": "guest", "role": auth.GetRole(c),
				"authenticated": auth.IsAuthenticated(c),
			}})
			return
		}
		user.PasswordHash = ""
		c.JSON(http.StatusOK, gin.H{"code": 0, "data": gin.H{
			"id": user.ID, "tenant_id": user.TenantID, "nickname": user.Nickname,
			"email": user.Email, "role": user.Role, "authenticated": auth.IsAuthenticated(c),
			"scopes": auth.GetScopes(c),
		}})
	}
}

func OAuthTokenHandler(svc *service.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		grant := c.PostForm("grant_type")
		if grant == "" {
			var body struct {
				GrantType    string `json:"grant_type"`
				Username     string `json:"username"`
				Password     string `json:"password"`
				ClientID     string `json:"client_id"`
				ClientSecret string `json:"client_secret"`
				Scope        string `json:"scope"`
				TenantID     string `json:"tenant_id"`
			}
			_ = c.ShouldBindJSON(&body)
			grant = body.GrantType
			if grant == "password" {
				scopes := splitScopes(body.Scope)
				res, err := svc.TokenByPassword(c.Request.Context(), body.Username, body.Password, body.TenantID, scopes)
				writeOAuthToken(c, res, err)
				return
			}
			if grant == "client_credentials" {
				res, err := svc.TokenClientCredentials(body.ClientID, body.ClientSecret, splitScopes(body.Scope))
				writeOAuthToken(c, res, err)
				return
			}
		} else if grant == "password" {
			scopes := splitScopes(c.PostForm("scope"))
			res, err := svc.TokenByPassword(
				c.Request.Context(),
				c.PostForm("username"),
				c.PostForm("password"),
				c.PostForm("tenant_id"),
				scopes,
			)
			writeOAuthToken(c, res, err)
			return
		} else if grant == "client_credentials" {
			res, err := svc.TokenClientCredentials(
				c.PostForm("client_id"),
				c.PostForm("client_secret"),
				splitScopes(c.PostForm("scope")),
			)
			writeOAuthToken(c, res, err)
			return
		}

		c.JSON(http.StatusBadRequest, gin.H{
			"error":             "unsupported_grant_type",
			"error_description": "支持 password 与 client_credentials",
		})
	}
}

func splitScopes(s string) []string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	parts := strings.Fields(s)
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func writeOAuthToken(c *gin.Context, res *service.AuthResult, err error) {
	if err != nil {
		status := http.StatusUnauthorized
		code := "invalid_grant"
		if strings.Contains(err.Error(), "invalid_client") {
			code = "invalid_client"
		}
		c.JSON(status, gin.H{"error": code, "error_description": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"access_token": res.AccessToken,
		"token_type":   res.TokenType,
		"expires_in":   res.ExpiresIn,
		"scope":        strings.Join(authScopeFromUser(res), " "),
	})
}

func authScopeFromUser(res *service.AuthResult) []string {
	if res == nil || res.User == nil {
		return nil
	}
	switch res.User.Role {
	case "admin":
		return []string{"api:user", "api:admin", "mcp:read", "a2a:health_consult"}
	case "operator":
		return []string{"api:user", "api:operator", "mcp:read", "a2a:health_consult"}
	default:
		return []string{"api:user"}
	}
}
