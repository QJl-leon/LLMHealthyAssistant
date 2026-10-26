
package service

import (
	"context"
	"fmt"
	"log"

	"llm-healthy-assistant/go-backend/internal/aiclient"
	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"
	"llm-healthy-assistant/go-backend/internal/model"
	"llm-healthy-assistant/go-backend/internal/repository"

	"github.com/google/uuid"
)

type TaskService struct {
	taskRepo repository.TaskRepository
	userRepo repository.UserRepository

}

func NewTaskService(taskRepo repository.TaskRepository, userRepo repository.UserRepository) *TaskService {
	return &TaskService{taskRepo: taskRepo, userRepo: userRepo}
}

type CreateTaskRequest struct {
	TenantID     string
	UserID       string
	ClientTaskID string
	ImageKeys    []string
}

type CreateTaskResult struct {
	TaskID  string
	TraceID string
	Status  string
	IsNew   bool
}

func (s *TaskService) Create(ctx context.Context, req CreateTaskRequest) (*CreateTaskResult, error) {
	if req.ImageKeys == nil {
		req.ImageKeys = []string{}
	}

	if s.userRepo != nil {
		if err := s.userRepo.Ensure(ctx, req.UserID, req.TenantID, "dev-user"); err != nil {
			return nil, fmt.Errorf("ensure user: %w", err)
		}
	}

	task := &model.Task{
		ID:           uuid.New().String(),
		TenantID:     req.TenantID,
		UserID:       req.UserID,
		ClientTaskID: req.ClientTaskID,
		Status:       "intake",
		ImageKeys:    req.ImageKeys,
	}

	created, err := s.taskRepo.CreateOrGet(ctx, task)
	if err != nil {
		return nil, fmt.Errorf("task create: %w", err)
	}

	traceID := uuid.New().String()
	isNew := created.ID == task.ID

	log.Printf("[TaskService] Create task=%s client=%s isNew=%v", created.ID, req.ClientTaskID, isNew)

	return &CreateTaskResult{
		TaskID:  created.ID,
		TraceID: traceID,
		Status:  created.Status,
		IsNew:   isNew,
	}, nil
}

func (s *TaskService) GetTask(ctx context.Context, tenantID, taskID string) (*model.Task, error) {
	return s.taskRepo.GetByID(ctx, tenantID, taskID)
}

func (s *TaskService) UpdateTaskStatus(ctx context.Context, taskID, status string) error {

	return s.taskRepo.UpdateStatus(ctx, taskID, status)
}

func (s *TaskService) ListUserTasks(ctx context.Context, tenantID, userID string, limit, offset int) ([]model.Task, error) {
	return s.taskRepo.ListByUser(ctx, tenantID, userID, limit, offset)
}

type ReportService struct {
	reportRepo repository.ReportRepository
}

func NewReportService(reportRepo repository.ReportRepository) *ReportService {
	return &ReportService{reportRepo: reportRepo}
}

type CreateReportRequest struct {
	TaskID           string
	KnowledgeVersion string
	Content          model.ReportContent
	Status           string
}

func (s *ReportService) CreateReport(ctx context.Context, req CreateReportRequest) (*model.Report, error) {

	latest, err := s.reportRepo.GetLatestByTask(ctx, req.TaskID)
	if err != nil {
		return nil, fmt.Errorf("get latest: %w", err)
	}

	version := 1
	if latest != nil {
		version = latest.Version + 1
	}

	status := req.Status
	if status == "" {
		status = "draft"
	}

	report := &model.Report{
		ID:               uuid.New().String(),
		TaskID:           req.TaskID,
		Version:          version,
		KnowledgeVersion: req.KnowledgeVersion,
		Content:          req.Content,
		Status:           status,
	}

	if err := s.reportRepo.Create(ctx, report); err != nil {
		return nil, fmt.Errorf("create report: %w", err)
	}

	log.Printf("[ReportService] Created report=%s task=%s v%d status=%s", report.ID, report.TaskID, report.Version, report.Status)
	return report, nil
}

func (s *ReportService) ListVersions(ctx context.Context, taskID string) ([]model.Report, error) {
	return s.reportRepo.ListByTask(ctx, taskID)
}

func (s *ReportService) GetLatestReport(ctx context.Context, taskID string) (*model.Report, error) {
	return s.reportRepo.GetLatestByTask(ctx, taskID)
}

type ListReportsRequest struct {
	UserID string
	TaskID string
	Limit  int
	Offset int
}

func (s *ReportService) ListReports(ctx context.Context, req ListReportsRequest) ([]model.Report, error) {
	if req.TaskID != "" {
		return s.reportRepo.ListByTask(ctx, req.TaskID)
	}
	return s.reportRepo.ListByUser(ctx, req.UserID, req.Limit, req.Offset)
}

func (s *ReportService) GetReport(ctx context.Context, reportID string) (*model.Report, error) {
	return s.reportRepo.GetByID(ctx, reportID)
}

type ProfileService struct {
	ai *aiclient.Client
}

func NewProfileService(ai *aiclient.Client) *ProfileService {
	return &ProfileService{ai: ai}
}

type SaveProfileRequest struct {
	UserID  string
	Kind    model.ProfileKind
	Content string
	Source  string
}

func (s *ProfileService) SaveProfile(ctx context.Context, req SaveProfileRequest) (*researchv1.MemoryItem, error) {
	source := req.Source
	if source == "" {
		source = "user_stated"
	}
	item, err := s.ai.CreateMemory(ctx, &researchv1.CreateMemoryRequest{
		UserId:  req.UserID,
		Kind:    string(req.Kind),
		Content: req.Content,
		Source:  source,
	})
	if err != nil {
		return nil, fmt.Errorf("create memory: %w", err)
	}
	log.Printf("[ProfileService] Created memory=%s user=%s kind=%s", item.Id, req.UserID, req.Kind)
	return item, nil
}

func (s *ProfileService) GetActiveProfiles(ctx context.Context, userID string) (*researchv1.ListMemoryResponse, error) {
	resp, err := s.ai.ListMemory(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("list memory: %w", err)
	}
	return resp, nil
}

func (s *ProfileService) UpdateProfile(ctx context.Context, userID, entryID, newContent string) (*researchv1.MemoryItem, error) {
	item, err := s.ai.UpdateMemory(ctx, userID, entryID, newContent)
	if err != nil {
		return nil, fmt.Errorf("update memory: %w", err)
	}
	log.Printf("[ProfileService] Updated memory=%s user=%s → v%d", entryID, userID, item.Version)
	return item, nil
}

func (s *ProfileService) DeleteProfile(ctx context.Context, userID, entryID string) error {
	_, err := s.ai.DeleteMemory(ctx, userID, entryID)
	if err != nil {
		return fmt.Errorf("delete memory: %w", err)
	}
	return nil
}

func (s *ProfileService) DeleteAllProfiles(ctx context.Context, userID string) (int32, error) {
	resp, err := s.ai.DeleteAllMemory(ctx, userID)
	if err != nil {
		return 0, fmt.Errorf("delete all memory: %w", err)
	}
	return resp.DeletedCount, nil
}

func (s *ProfileService) ConfirmProfile(ctx context.Context, userID, entryID string) (*researchv1.MemoryItem, error) {
	item, err := s.ai.ConfirmMemory(ctx, userID, entryID)
	if err != nil {
		return nil, fmt.Errorf("confirm memory: %w", err)
	}
	return item, nil
}

func (s *ProfileService) ListProfileAudit(ctx context.Context, userID string, limit int32) (*researchv1.ListMemoryAuditResponse, error) {
	resp, err := s.ai.ListMemoryAudit(ctx, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("list memory audit: %w", err)
	}
	return resp, nil
}

type FeedbackService struct {
	feedbackRepo repository.FeedbackRepository
}

func NewFeedbackService(feedbackRepo repository.FeedbackRepository) *FeedbackService {
	return &FeedbackService{feedbackRepo: feedbackRepo}
}

type SubmitFeedbackRequest struct {
	UserID    string
	ReportID  string
	ClaimID   string
	IssueType model.FeedbackIssueType
	Detail    string
}

func (s *FeedbackService) SubmitFeedback(ctx context.Context, req SubmitFeedbackRequest) (*model.Feedback, error) {
	fb := &model.Feedback{
		ID:        uuid.New().String(),
		UserID:    req.UserID,
		ReportID:  req.ReportID,
		ClaimID:   req.ClaimID,
		IssueType: req.IssueType,
		Detail:    req.Detail,
	}

	if err := s.feedbackRepo.Create(ctx, fb); err != nil {
		return nil, fmt.Errorf("create feedback: %w", err)
	}

	log.Printf("[FeedbackService] Feedback submitted id=%s report=%s type=%s", fb.ID, req.ReportID, req.IssueType)
	return fb, nil
}

func (s *FeedbackService) ListFeedbackByReport(ctx context.Context, reportID string) ([]model.Feedback, error) {
	return s.feedbackRepo.ListByReport(ctx, reportID)
}
