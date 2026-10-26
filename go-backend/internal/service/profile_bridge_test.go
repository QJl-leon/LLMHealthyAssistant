
package service

import (
	"context"
	"net"
	"testing"

	"llm-healthy-assistant/go-backend/internal/aiclient"
	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"
	"llm-healthy-assistant/go-backend/internal/model"

	"google.golang.org/grpc"
	"google.golang.org/grpc/test/bufconn"
)

type fakeMemoryServer struct {
	researchv1.UnimplementedMemoryServiceServer

	lastCreate    *researchv1.CreateMemoryRequest
	lastUpdate    *researchv1.UpdateMemoryRequest
	lastDelete    *researchv1.DeleteMemoryRequest
	lastConfirm   *researchv1.ConfirmMemoryRequest
	lastAuditUser string

	items []*researchv1.MemoryItem
}

func (f *fakeMemoryServer) ListMemory(_ context.Context, req *researchv1.ListMemoryRequest) (*researchv1.ListMemoryResponse, error) {
	return &researchv1.ListMemoryResponse{Items: f.items}, nil
}

func (f *fakeMemoryServer) CreateMemory(_ context.Context, req *researchv1.CreateMemoryRequest) (*researchv1.MemoryItem, error) {
	f.lastCreate = req
	return &researchv1.MemoryItem{
		Id: "mem-1", Kind: req.Kind, Content: req.Content,
		Source: req.Source, Version: 1,
	}, nil
}

func (f *fakeMemoryServer) UpdateMemory(_ context.Context, req *researchv1.UpdateMemoryRequest) (*researchv1.MemoryItem, error) {
	f.lastUpdate = req
	return &researchv1.MemoryItem{
		Id: req.EntryId, Content: req.NewContent, Version: 2,
	}, nil
}

func (f *fakeMemoryServer) DeleteMemory(_ context.Context, req *researchv1.DeleteMemoryRequest) (*researchv1.DeleteMemoryResponse, error) {
	f.lastDelete = req
	return &researchv1.DeleteMemoryResponse{Ok: true, DeletedCount: 1}, nil
}

func (f *fakeMemoryServer) DeleteAllMemory(_ context.Context, req *researchv1.DeleteAllMemoryRequest) (*researchv1.DeleteMemoryResponse, error) {
	return &researchv1.DeleteMemoryResponse{Ok: true, DeletedCount: 3}, nil
}

func (f *fakeMemoryServer) ConfirmMemory(_ context.Context, req *researchv1.ConfirmMemoryRequest) (*researchv1.MemoryItem, error) {
	f.lastConfirm = req
	return &researchv1.MemoryItem{
		Id: req.EntryId, Confidence: 1.0, PendingConfirmation: false,
	}, nil
}

func (f *fakeMemoryServer) ListMemoryAudit(_ context.Context, req *researchv1.ListMemoryAuditRequest) (*researchv1.ListMemoryAuditResponse, error) {
	f.lastAuditUser = req.UserId
	return &researchv1.ListMemoryAuditResponse{
		Items: []*researchv1.MemoryAuditItem{
			{Id: "a1", UserId: req.UserId, Action: "write", Detail: "condition=高血压"},
		},
	}, nil
}

func newBridgeTestClient(t *testing.T, fake *fakeMemoryServer) *aiclient.Client {
	t.Helper()
	lis := bufconn.Listen(1024 * 1024)
	srv := grpc.NewServer()
	researchv1.RegisterMemoryServiceServer(srv, fake)
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(func() { srv.Stop(); _ = lis.Close() })

	conn, err := grpc.DialContext(
		context.Background(), "bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithInsecure(),
	)
	if err != nil {
		t.Fatalf("bufconn dial: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	return aiclient.NewForConn(conn)
}

func TestProfileService_Bridge(t *testing.T) {
	fake := &fakeMemoryServer{
		items: []*researchv1.MemoryItem{
			{Id: "m1", Kind: "condition", Content: "高血压 3 年", Version: 1},
		},
	}
	client := newBridgeTestClient(t, fake)
	svc := NewProfileService(client)
	ctx := context.Background()

	saved, err := svc.SaveProfile(ctx, SaveProfileRequest{
		UserID: "u1", Kind: model.ProfileCondition, Content: "高血压 3 年",
	})
	if err != nil {
		t.Fatalf("SaveProfile: %v", err)
	}
	if saved.Id != "mem-1" || saved.Version != 1 {
		t.Errorf("SaveProfile 返回异常: %+v", saved)
	}
	if fake.lastCreate.UserId != "u1" || fake.lastCreate.Kind != "condition" {
		t.Errorf("CreateMemory 参数透传错误: %+v", fake.lastCreate)
	}
	if fake.lastCreate.Source != "user_stated" {
		t.Errorf("Source 默认应为 user_stated，得到 %q", fake.lastCreate.Source)
	}

	list, err := svc.GetActiveProfiles(ctx, "u1")
	if err != nil {
		t.Fatalf("GetActiveProfiles: %v", err)
	}
	if len(list.Items) != 1 || list.Items[0].Content != "高血压 3 年" {
		t.Errorf("GetActiveProfiles 返回异常: %+v", list.Items)
	}

	updated, err := svc.UpdateProfile(ctx, "u1", "m1", "高血压 5 年")
	if err != nil {
		t.Fatalf("UpdateProfile: %v", err)
	}
	if updated.Version != 2 {
		t.Errorf("版本链更新后 version 应递增，得到 %d", updated.Version)
	}
	if fake.lastUpdate.EntryId != "m1" || fake.lastUpdate.NewContent != "高血压 5 年" {
		t.Errorf("UpdateMemory 参数透传错误: %+v", fake.lastUpdate)
	}

	confirmed, err := svc.ConfirmProfile(ctx, "u1", "m1")
	if err != nil {
		t.Fatalf("ConfirmProfile: %v", err)
	}
	if confirmed.Confidence != 1.0 || confirmed.PendingConfirmation {
		t.Errorf("确认后应 confidence=1.0 且清除待确认: %+v", confirmed)
	}

	if err := svc.DeleteProfile(ctx, "u1", "m1"); err != nil {
		t.Fatalf("DeleteProfile: %v", err)
	}
	if fake.lastDelete.UserId != "u1" || fake.lastDelete.EntryId != "m1" {
		t.Errorf("DeleteMemory 参数透传错误: %+v", fake.lastDelete)
	}

	n, err := svc.DeleteAllProfiles(ctx, "u1")
	if err != nil {
		t.Fatalf("DeleteAllProfiles: %v", err)
	}
	if n != 3 {
		t.Errorf("DeleteAllProfiles count = %d, want 3", n)
	}

	audit, err := svc.ListProfileAudit(ctx, "u1", 100)
	if err != nil {
		t.Fatalf("ListProfileAudit: %v", err)
	}
	if len(audit.Items) != 1 || audit.Items[0].Action != "write" {
		t.Errorf("ListProfileAudit 返回异常: %+v", audit.Items)
	}
	if fake.lastAuditUser != "u1" {
		t.Errorf("ListMemoryAudit user 透传错误: %q", fake.lastAuditUser)
	}
}
