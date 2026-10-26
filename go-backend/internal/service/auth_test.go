package service_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/db"
	"llm-healthy-assistant/go-backend/internal/repository"
	"llm-healthy-assistant/go-backend/internal/service"
)

func TestAuthRegisterLogin(t *testing.T) {
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		url = "postgresql://lha:lha_dev@localhost:5432/lha?sslmode=disable"
	}
	pool, err := db.NewPool(url)
	if err != nil {
		t.Skip("no database:", err)
	}
	defer pool.Close()

	secret := []byte("lha-dev-secret-change-in-production")
	svc := service.NewAuthService(repository.NewUserRepo(pool), secret)
	email := fmt.Sprintf("test_%d@lha.local", os.Getpid())

	res, err := svc.Register(context.Background(), service.RegisterRequest{
		Email: email, Password: "demo1234", Nickname: "Tester",
	})
	if err != nil {
		t.Fatal(err)
	}
	claims, err := auth.VerifyJWT(secret, res.AccessToken)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Role != "user" || claims.Subject == "" {
		t.Fatalf("bad claims: %+v", claims)
	}

	res2, err := svc.Login(context.Background(), service.LoginRequest{
		Email: email, Password: "demo1234",
	})
	if err != nil {
		t.Fatal(err)
	}
	if res2.User.Email != email {
		t.Fatalf("email mismatch %s", res2.User.Email)
	}

	res3, err := svc.TokenClientCredentials("lha-mcp", string(secret), []string{"mcp:read"})
	if err != nil {
		t.Fatal(err)
	}
	c3, err := auth.VerifyJWT(secret, res3.AccessToken)
	if err != nil {
		t.Fatal(err)
	}
	if c3.Role != "operator" {
		t.Fatalf("want operator got %s", c3.Role)
	}
}
