package api

import (
	"bytes"
	"encoding/json"
	"image"
	"image/png"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/repository"
	"llm-healthy-assistant/go-backend/internal/service"
)

func TestUploadAuthentication(t *testing.T) {
	t.Setenv("AUTH_REQUIRED", "true")
	dir := t.TempDir()
	repo := &memoryUploadRepo{files: make(map[string]repository.UploadedFile)}
	svc := service.NewUploadService(repo, dir)
	secret := []byte("upload-auth-regression-secret")
	token, err := auth.NewUserToken(secret, "test-user", "test-tenant", "user", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	expired, err := auth.SignJWT(secret, auth.JWTClaims{Subject: "test-user", Expires: time.Now().Add(-time.Hour).Unix()})
	if err != nil {
		t.Fatal(err)
	}
	router := SetupRouter(nil, nil, nil, nil, nil, nil, secret, "invalid-test-url", svc)
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", "synthetic.png")
	if err != nil {
		t.Fatal(err)
	}
	if err := png.Encode(part, image.NewRGBA(image.Rect(0, 0, 2, 2))); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteField("user_id", "victim"); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteField("tenant_id", "other-tenant"); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, token string }{
		{"anonymous", ""}, {"invalid", "invalid-token"}, {"expired", expired},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/api/v1/uploads", bytes.NewReader(body.Bytes()))
			req.Header.Set("Content-Type", writer.FormDataContentType())
			// Caller-controlled identity headers must not bypass authentication.
			req.Header.Set("X-User-Id", "test-user")
			req.Header.Set("X-Tenant-Id", "test-tenant")
			if tc.token != "" {
				req.Header.Set("Authorization", "Bearer "+tc.token)
			}
			response := httptest.NewRecorder()
			router.ServeHTTP(response, req)
			if response.Code != http.StatusUnauthorized {
				t.Fatalf("status=%d, want 401", response.Code)
			}
			entries, err := os.ReadDir(dir)
			if err != nil {
				t.Fatal(err)
			}
			if len(entries) != 0 {
				t.Fatal("unauthenticated upload wrote files")
			}
		})
	}
	t.Run("authenticated", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/uploads", bytes.NewReader(body.Bytes()))
		req.Header.Set("Content-Type", writer.FormDataContentType())
		req.Header.Set("Authorization", "Bearer "+token)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, req)
		if response.Code != http.StatusOK {
			t.Fatalf("status=%d: %s", response.Code, response.Body)
		}
		var result struct {
			Code int `json:"code"`
			Data struct {
				Key string `json:"image_key"`
			} `json:"data"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		if result.Code != 0 || result.Data.Key == "" {
			t.Fatalf("invalid upload result: %s", response.Body)
		}
		record, ok := repo.files[result.Data.Key]
		if !ok || record.UserID != "test-user" || record.TenantID != "test-tenant" {
			t.Fatal("ownership must come from authenticated context")
		}
		saved, err := os.ReadFile(filepath.Join(dir, result.Data.Key))
		if err != nil {
			t.Fatal(err)
		}
		if _, err := png.Decode(bytes.NewReader(saved)); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("anonymous-body-not-read", func(t *testing.T) {
		body := &readTracker{}
		req := httptest.NewRequest(http.MethodPost, "/api/v1/uploads", body)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, req)
		if response.Code != http.StatusUnauthorized || body.read {
			t.Fatalf("status=%d body_read=%v", response.Code, body.read)
		}
	})
}

type readTracker struct{ read bool }

func (r *readTracker) Read(p []byte) (int, error) { r.read = true; return 0, io.EOF }
