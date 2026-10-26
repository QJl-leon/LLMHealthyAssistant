package api

import (
	"bytes"
	"context"
	"errors"
	"net"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"google.golang.org/grpc"
	"llm-healthy-assistant/go-backend/internal/aiclient"
	pb "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"
	"llm-healthy-assistant/go-backend/internal/auth"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/repository"
	"llm-healthy-assistant/go-backend/internal/service"
)

type memoryUploadRepo struct {
	files map[string]repository.UploadedFile
	fail  bool
}

func (r *memoryUploadRepo) Create(_ context.Context, f repository.UploadedFile) error {
	if r.fail {
		return errors.New("database unavailable")
	}
	r.files[f.Key] = f
	return nil
}
func (r *memoryUploadRepo) GetOwned(_ context.Context, key, tenant, user string) (*repository.UploadedFile, error) {
	if r.fail {
		return nil, errors.New("database unavailable")
	}
	f, ok := r.files[key]
	if !ok || f.TenantID != tenant || f.UserID != user {
		return nil, nil
	}
	return &f, nil
}

type ownershipTasks struct {
	task    model.Task
	creates int
}

func (r *ownershipTasks) CreateOrGet(_ context.Context, t *model.Task) (*model.Task, error) {
	r.creates++
	return t, nil
}
func (r *ownershipTasks) GetByID(_ context.Context, tenant, id string) (*model.Task, error) {
	if id != r.task.ID || tenant != r.task.TenantID {
		return nil, nil
	}
	return &r.task, nil
}
func (r *ownershipTasks) UpdateStatus(context.Context, string, string) error { return nil }
func (r *ownershipTasks) ListByUser(context.Context, string, string, int, int) ([]model.Task, error) {
	return nil, nil
}

type uploadAI struct {
	pb.UnimplementedResearchServiceServer
	submitted, resumed atomic.Int64
}

func (s *uploadAI) SubmitTask(_ context.Context, r *pb.SubmitTaskRequest) (*pb.SubmitTaskResponse, error) {
	s.submitted.Add(1)
	return &pb.SubmitTaskResponse{TaskId: r.TaskId, Status: "intake"}, nil
}
func (s *uploadAI) ResumeTask(_ context.Context, r *pb.ResumeTaskRequest) (*pb.ResumeTaskResponse, error) {
	s.resumed.Add(1)
	return &pb.ResumeTaskResponse{TaskId: r.TaskId, Status: "intake"}, nil
}

func TestUploadOwnershipBoundaries(t *testing.T) {
	t.Setenv("AUTH_REQUIRED", "true")
	dir := t.TempDir()
	secret := []byte("ownership-test-secret")
	key := "11111111-1111-4111-8111-111111111111.png"
	otherKey := "22222222-2222-4222-8222-222222222222.png"
	missingKey := "33333333-3333-4333-8333-333333333333.png"
	linkKey := "44444444-4444-4444-8444-444444444444.png"
	repo := &memoryUploadRepo{files: map[string]repository.UploadedFile{}}
	for _, k := range []string{key, otherKey, missingKey, linkKey} {
		user := "A"
		if k == otherKey {
			user = "B"
		}
		repo.files[k] = repository.UploadedFile{Key: k, UserID: user, TenantID: "T", MIME: "image/png", Size: 7}
	}
	for _, k := range []string{key, otherKey, "55555555-5555-4555-8555-555555555555.png"} {
		if err := os.WriteFile(filepath.Join(dir, k), []byte("fixture"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	privatePath := filepath.Join(t.TempDir(), "private")
	if err := os.WriteFile(privatePath, []byte("private secret"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(privatePath, filepath.Join(dir, linkKey)); err != nil {
		t.Fatal(err)
	}
	svc := service.NewUploadService(repo, dir)
	tasks := &ownershipTasks{task: model.Task{ID: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", TenantID: "T", UserID: "A"}}
	ai := &uploadAI{}
	server := grpc.NewServer()
	pb.RegisterResearchServiceServer(server, ai)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	go server.Serve(listener)
	t.Cleanup(server.Stop)
	client, err := aiclient.New(listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { client.Close() })
	router := SetupRouter(client, service.NewTaskService(tasks, nil), nil, nil, nil, nil, secret, "invalid-test-url", svc)
	token := func(user, tenant string) string {
		v, err := auth.NewUserToken(secret, user, tenant, "user", time.Hour)
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	call := func(method, path, body, user, tenant string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, path, bytes.NewBufferString(body))
		req.Header.Set("Content-Type", "application/json")
		if user != "" {
			req.Header.Set("Authorization", "Bearer "+token(user, tenant))
		}
		response := httptest.NewRecorder()
		router.ServeHTTP(response, req)
		return response
	}
	for _, tc := range []struct {
		name, key, user, tenant string
		status                  int
	}{
		{"owner", key, "A", "T", 200}, {"anonymous", key, "", "", 401},
		{"same-tenant", key, "B", "T", 404}, {"cross-tenant", key, "A", "T2", 404},
		{"missing-identity-tenant", key, "A", "", 401}, {"missing-file", missingKey, "A", "T", 404},
		{"unknown-record", "55555555-5555-4555-8555-555555555555.png", "A", "T", 404},
		{"symlink", linkKey, "A", "T", 404}, {"invalid-name", "secret.txt", "A", "T", 404},
	} {
		t.Run("read/"+tc.name, func(t *testing.T) {
			r := call("GET", "/uploads/"+tc.key, "", tc.user, tc.tenant)
			if r.Code != tc.status {
				t.Fatalf("%d: %s", r.Code, r.Body)
			}
			if tc.status == 200 && r.Header().Get("Cache-Control") != "private, no-store" {
				t.Fatal("cache header missing")
			}
		})
	}
	for _, tc := range []struct {
		name, body, user, tenant string
		status                   int
	}{
		{"own", `{"client_task_id":"own","image_keys":["` + key + `"]}`, "A", "T", 200},
		{"foreign", `{"client_task_id":"foreign","image_keys":["` + key + `"]}`, "B", "T", 404},
		{"mixed", `{"client_task_id":"mixed","images":[{"key":"` + key + `"},{"key":"` + otherKey + `"}]}`, "A", "T", 404},
		{"cross-tenant", `{"client_task_id":"cross","image_keys":["` + key + `"]}`, "A", "T2", 404},
		{"traversal", `{"client_task_id":"path","image_keys":["../private.png"]}`, "A", "T", 404},
	} {
		t.Run("create/"+tc.name, func(t *testing.T) {
			before, dbBefore := ai.submitted.Load(), tasks.creates
			r := call("POST", "/api/v1/tasks", tc.body, tc.user, tc.tenant)
			if r.Code != tc.status {
				t.Fatalf("%d: %s", r.Code, r.Body)
			}
			if tc.status != 200 && (before != ai.submitted.Load() || dbBefore != tasks.creates) {
				t.Fatal("denied request created/submitted task")
			}
		})
	}
	for _, tc := range []struct {
		name, body, user, tenant string
		status                   int
	}{
		{"own-image", `{"action":"add_images","new_image_keys":["` + key + `"]}`, "A", "T", 200},
		{"foreign-image", `{"action":"add_images","new_image_keys":["` + otherKey + `"]}`, "A", "T", 404},
		{"foreign-task", `{"action":"add_images","new_image_keys":["` + otherKey + `"]}`, "B", "T", 404},
		{"cross-tenant-task", `{"action":"confirm_publish"}`, "A", "T2", 404},
		{"empty-images", `{"action":"add_images"}`, "A", "T", 400},
	} {
		t.Run("resume/"+tc.name, func(t *testing.T) {
			before := ai.resumed.Load()
			r := call("POST", "/api/v1/tasks/"+tasks.task.ID+"/resume", tc.body, tc.user, tc.tenant)
			if r.Code != tc.status {
				t.Fatalf("%d: %s", r.Code, r.Body)
			}
			if tc.status != 200 && before != ai.resumed.Load() {
				t.Fatal("denied request resumed task")
			}
		})
	}
	t.Run("database-failure", func(t *testing.T) {
		repo.fail = true
		defer func() { repo.fail = false }()
		r := call("GET", "/uploads/"+key, "", "A", "T")
		if r.Code != 500 {
			t.Fatalf("status=%d", r.Code)
		}
	})
}
