package service

import (
	"context"
	"fmt"
	"strings"
	"time"

	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/repository"

	"github.com/google/uuid"
)

type AuthService struct {
	users     repository.UserRepository
	jwtSecret []byte
}

func NewAuthService(users repository.UserRepository, jwtSecret []byte) *AuthService {
	return &AuthService{users: users, jwtSecret: jwtSecret}
}

const defaultTenant = "00000000-0000-0000-0000-000000000001"

type RegisterRequest struct {
	Email    string
	Password string
	Nickname string
	TenantID string
}

type LoginRequest struct {
	Email    string
	Password string
	TenantID string
}

type AuthResult struct {
	AccessToken string      `json:"access_token"`
	TokenType   string      `json:"token_type"`
	ExpiresIn   int64       `json:"expires_in"`
	User        *model.User `json:"user"`
}

func (s *AuthService) Register(ctx context.Context, req RegisterRequest) (*AuthResult, error) {
	email := strings.TrimSpace(strings.ToLower(req.Email))
	if email == "" || !strings.Contains(email, "@") {
		return nil, fmt.Errorf("邮箱无效")
	}
	tenantID := req.TenantID
	if tenantID == "" {
		tenantID = defaultTenant
	}
	existing, err := s.users.GetByEmail(ctx, tenantID, email)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, fmt.Errorf("邮箱已注册")
	}
	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		return nil, err
	}
	nick := strings.TrimSpace(req.Nickname)
	if nick == "" {
		nick = strings.Split(email, "@")[0]
	}
	user := &model.User{
		ID:           uuid.New().String(),
		TenantID:     tenantID,
		Nickname:     nick,
		Email:        email,
		PasswordHash: hash,
		Role:         model.RoleUser,
		CreatedAt:    time.Now(),
	}
	if err := s.users.CreateAccount(ctx, user); err != nil {
		return nil, err
	}
	return s.issue(user)
}

func (s *AuthService) Login(ctx context.Context, req LoginRequest) (*AuthResult, error) {
	email := strings.TrimSpace(strings.ToLower(req.Email))
	tenantID := req.TenantID
	if tenantID == "" {
		tenantID = defaultTenant
	}
	user, err := s.users.GetByEmail(ctx, tenantID, email)
	if err != nil {
		return nil, err
	}
	if user == nil || !auth.CheckPassword(user.PasswordHash, req.Password) {
		return nil, fmt.Errorf("邮箱或密码错误")
	}
	return s.issue(user)
}

func (s *AuthService) Me(ctx context.Context, userID string) (*model.User, error) {
	return s.users.GetByID(ctx, userID)
}

func (s *AuthService) TokenByPassword(ctx context.Context, email, password, tenantID string, scopes []string) (*AuthResult, error) {
	res, err := s.Login(ctx, LoginRequest{Email: email, Password: password, TenantID: tenantID})
	if err != nil {
		return nil, err
	}

	token, err := auth.NewUserToken(s.jwtSecret, res.User.ID, res.User.TenantID, res.User.Role, 24*time.Hour, scopes...)
	if err != nil {
		return nil, err
	}
	res.AccessToken = token
	return res, nil
}

func (s *AuthService) TokenClientCredentials(clientID, clientSecret string, scopes []string) (*AuthResult, error) {

	expectedSecret := string(s.jwtSecret)
	if clientID == "" || clientSecret == "" || clientSecret != expectedSecret {
		return nil, fmt.Errorf("invalid_client")
	}
	role := model.RoleOperator
	userID := "00000000-0000-0000-0000-0000000000aa"
	tenantID := defaultTenant
	if len(scopes) == 0 {
		scopes = []string{"mcp:read", "a2a:health_consult"}
	}
	token, err := auth.NewUserToken(s.jwtSecret, userID, tenantID, role, 12*time.Hour, scopes...)
	if err != nil {
		return nil, err
	}
	return &AuthResult{
		AccessToken: token,
		TokenType:   "Bearer",
		ExpiresIn:   int64((12 * time.Hour).Seconds()),
		User: &model.User{
			ID:       userID,
			TenantID: tenantID,
			Nickname: clientID,
			Role:     role,
		},
	}, nil
}

func (s *AuthService) issue(user *model.User) (*AuthResult, error) {
	scopes := []string{"api:user"}
	switch user.Role {
	case model.RoleAdmin:
		scopes = append(scopes, "api:admin", "mcp:read", "a2a:health_consult", "*")
	case model.RoleOperator:
		scopes = append(scopes, "api:operator", "mcp:read", "a2a:health_consult")
	}
	token, err := auth.NewUserToken(s.jwtSecret, user.ID, user.TenantID, user.Role, 24*time.Hour, scopes...)
	if err != nil {
		return nil, err
	}

	safe := *user
	safe.PasswordHash = ""
	return &AuthResult{
		AccessToken: token,
		TokenType:   "Bearer",
		ExpiresIn:   int64((24 * time.Hour).Seconds()),
		User:        &safe,
	}, nil
}
