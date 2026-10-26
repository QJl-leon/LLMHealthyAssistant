
package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"llm-healthy-assistant/go-backend/internal/model"

	"github.com/google/uuid"
)

type UserRepository interface {

	Ensure(ctx context.Context, userID, tenantID, nickname string) error

	CreateAccount(ctx context.Context, user *model.User) error

	GetByEmail(ctx context.Context, tenantID, email string) (*model.User, error)

	GetByID(ctx context.Context, userID string) (*model.User, error)
}

type TaskRepository interface {

	CreateOrGet(ctx context.Context, task *model.Task) (*model.Task, error)

	GetByID(ctx context.Context, tenantID, taskID string) (*model.Task, error)

	UpdateStatus(ctx context.Context, taskID, status string) error

	ListByUser(ctx context.Context, tenantID, userID string, limit, offset int) ([]model.Task, error)
}

type ReportRepository interface {

	Create(ctx context.Context, report *model.Report) error

	GetLatestByTask(ctx context.Context, taskID string) (*model.Report, error)

	GetByTaskAndVersion(ctx context.Context, taskID string, version int) (*model.Report, error)

	GetByID(ctx context.Context, reportID string) (*model.Report, error)

	ListByUser(ctx context.Context, userID string, limit, offset int) ([]model.Report, error)

	ListByTask(ctx context.Context, taskID string) ([]model.Report, error)

}

type ProfileRepository interface {

	Upsert(ctx context.Context, profile *model.Profile) (*model.Profile, error)

	ListActive(ctx context.Context, userID string) ([]model.Profile, error)

	SoftDelete(ctx context.Context, profileID string) error
}

type FeedbackRepository interface {

	Create(ctx context.Context, feedback *model.Feedback) error

	ListByReport(ctx context.Context, reportID string) ([]model.Feedback, error)
}

type postgresUserRepo struct {
	db *sql.DB
}

func NewUserRepo(db *sql.DB) UserRepository {
	return &postgresUserRepo{db: db}
}

func (r *postgresUserRepo) Ensure(ctx context.Context, userID, tenantID, nickname string) error {
	if nickname == "" {
		nickname = "dev-user"
	}
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO users (id, tenant_id, nickname, role, created_at)
		VALUES ($1, $2, $3, 'user', now())
		ON CONFLICT (id) DO NOTHING
	`, userID, tenantID, nickname)
	if err != nil {
		return fmt.Errorf("ensure user: %w", err)
	}
	return nil
}

func (r *postgresUserRepo) CreateAccount(ctx context.Context, user *model.User) error {
	if user.ID == "" {
		user.ID = uuid.New().String()
	}
	if user.Role == "" {
		user.Role = model.RoleUser
	}
	if user.CreatedAt.IsZero() {
		user.CreatedAt = time.Now()
	}
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO users (id, tenant_id, nickname, email, password_hash, role, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`, user.ID, user.TenantID, user.Nickname, nullIfEmpty(user.Email),
		nullIfEmpty(user.PasswordHash), user.Role, user.CreatedAt)
	if err != nil {
		return fmt.Errorf("create account: %w", err)
	}
	return nil
}

func (r *postgresUserRepo) GetByEmail(ctx context.Context, tenantID, email string) (*model.User, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, tenant_id, nickname, COALESCE(email,''), COALESCE(password_hash,''),
		       COALESCE(role,'user'), created_at
		FROM users WHERE tenant_id = $1 AND email = $2
	`, tenantID, email)
	return scanUser(row)
}

func (r *postgresUserRepo) GetByID(ctx context.Context, userID string) (*model.User, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, tenant_id, nickname, COALESCE(email,''), COALESCE(password_hash,''),
		       COALESCE(role,'user'), created_at
		FROM users WHERE id = $1
	`, userID)
	return scanUser(row)
}

func scanUser(row *sql.Row) (*model.User, error) {
	var u model.User
	err := row.Scan(&u.ID, &u.TenantID, &u.Nickname, &u.Email, &u.PasswordHash, &u.Role, &u.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func nullIfEmpty(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}

type postgresTaskRepo struct {
	db *sql.DB
}

func NewTaskRepo(db *sql.DB) TaskRepository {
	return &postgresTaskRepo{db: db}
}

func (r *postgresTaskRepo) CreateOrGet(ctx context.Context, task *model.Task) (*model.Task, error) {
	if task.ID == "" {
		task.ID = uuid.New().String()
	}
	task.CreatedAt = time.Now()

	imageKeysJSON, err := json.Marshal(task.ImageKeys)
	if err != nil {
		return nil, fmt.Errorf("marshal image_keys: %w", err)
	}

	row := r.db.QueryRowContext(ctx, `
		INSERT INTO tasks (id, tenant_id, user_id, client_task_id, status, image_keys, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (tenant_id, user_id, client_task_id)
		DO UPDATE SET client_task_id = EXCLUDED.client_task_id
		RETURNING id, tenant_id, user_id, client_task_id, status, image_keys, created_at
	`, task.ID, task.TenantID, task.UserID, task.ClientTaskID, task.Status, imageKeysJSON, task.CreatedAt)

	var result model.Task
	var imageKeysRaw []byte
	err = row.Scan(&result.ID, &result.TenantID, &result.UserID, &result.ClientTaskID,
		&result.Status, &imageKeysRaw, &result.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("CreateOrGet: %w", err)
	}
	json.Unmarshal(imageKeysRaw, &result.ImageKeys)
	return &result, nil
}

func (r *postgresTaskRepo) GetByID(ctx context.Context, tenantID, taskID string) (*model.Task, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, tenant_id, user_id, client_task_id, status, image_keys, created_at
		FROM tasks WHERE id = $1 AND tenant_id = $2
	`, taskID, tenantID)

	var task model.Task
	var imageKeysRaw []byte
	err := row.Scan(&task.ID, &task.TenantID, &task.UserID, &task.ClientTaskID,
		&task.Status, &imageKeysRaw, &task.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("GetByID: %w", err)
	}
	json.Unmarshal(imageKeysRaw, &task.ImageKeys)
	return &task, nil
}

func (r *postgresTaskRepo) UpdateStatus(ctx context.Context, taskID, status string) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE tasks SET status = $2 WHERE id = $1`,
		taskID, status)
	return err
}

func (r *postgresTaskRepo) ListByUser(ctx context.Context, tenantID, userID string, limit, offset int) ([]model.Task, error) {
	if limit <= 0 {
		limit = 20
	}

	rows, err := r.db.QueryContext(ctx, `
		SELECT id, tenant_id, user_id, client_task_id, status, image_keys, created_at
		FROM tasks WHERE tenant_id = $1 AND user_id = $2
		ORDER BY created_at DESC LIMIT $3 OFFSET $4
	`, tenantID, userID, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("ListByUser: %w", err)
	}
	defer rows.Close()

	var tasks []model.Task
	for rows.Next() {
		var task model.Task
		var imageKeysRaw []byte
		if err := rows.Scan(&task.ID, &task.TenantID, &task.UserID, &task.ClientTaskID,
			&task.Status, &imageKeysRaw, &task.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan task: %w", err)
		}
		json.Unmarshal(imageKeysRaw, &task.ImageKeys)
		tasks = append(tasks, task)
	}
	return tasks, rows.Err()
}

type postgresReportRepo struct {
	db *sql.DB
}

func NewReportRepo(db *sql.DB) ReportRepository {
	return &postgresReportRepo{db: db}
}

func (r *postgresReportRepo) Create(ctx context.Context, report *model.Report) error {
	if report.ID == "" {
		report.ID = uuid.New().String()
	}
	report.CreatedAt = time.Now()

	contentJSON, err := json.Marshal(report.Content)
	if err != nil {
		return fmt.Errorf("marshal content: %w", err)
	}

	_, err = r.db.ExecContext(ctx, `
		INSERT INTO reports (id, task_id, version, knowledge_version, content, status, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (task_id, version) DO NOTHING
	`, report.ID, report.TaskID, report.Version, report.KnowledgeVersion,
		contentJSON, report.Status, report.CreatedAt)
	return err
}

func (r *postgresReportRepo) GetLatestByTask(ctx context.Context, taskID string) (*model.Report, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, task_id, version, knowledge_version, content, status, created_at
		FROM reports WHERE task_id = $1 ORDER BY version DESC LIMIT 1
	`, taskID)

	return scanReport(row)
}

func (r *postgresReportRepo) GetByTaskAndVersion(ctx context.Context, taskID string, version int) (*model.Report, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, task_id, version, knowledge_version, content, status, created_at
		FROM reports WHERE task_id = $1 AND version = $2
	`, taskID, version)

	return scanReport(row)
}

func scanReport(row *sql.Row) (*model.Report, error) {
	var report model.Report
	var contentRaw []byte
	err := row.Scan(&report.ID, &report.TaskID, &report.Version, &report.KnowledgeVersion,
		&contentRaw, &report.Status, &report.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("scan report: %w", err)
	}
	json.Unmarshal(contentRaw, &report.Content)
	return &report, nil
}

func (r *postgresReportRepo) GetByID(ctx context.Context, reportID string) (*model.Report, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT id, task_id, version, knowledge_version, content, status, created_at
		FROM reports WHERE id = $1
	`, reportID)
	return scanReport(row)
}

func (r *postgresReportRepo) ListByUser(ctx context.Context, userID string, limit, offset int) ([]model.Report, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT r.id, r.task_id, r.version, r.knowledge_version, r.content, r.status, r.created_at
		FROM reports r
		JOIN tasks t ON r.task_id = t.id
		WHERE t.user_id = $1
		ORDER BY r.created_at DESC
		LIMIT $2 OFFSET $3
	`, userID, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("query reports by user: %w", err)
	}
	defer rows.Close()
	return scanReports(rows)
}

func (r *postgresReportRepo) ListByTask(ctx context.Context, taskID string) ([]model.Report, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, task_id, version, knowledge_version, content, status, created_at
		FROM reports WHERE task_id = $1
		ORDER BY version DESC
	`, taskID)
	if err != nil {
		return nil, fmt.Errorf("query reports by task: %w", err)
	}
	defer rows.Close()
	return scanReports(rows)
}

func scanReports(rows *sql.Rows) ([]model.Report, error) {
	var reports []model.Report
	for rows.Next() {
		var report model.Report
		var contentRaw []byte
		if err := rows.Scan(&report.ID, &report.TaskID, &report.Version,
			&report.KnowledgeVersion, &contentRaw, &report.Status, &report.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan report row: %w", err)
		}
		json.Unmarshal(contentRaw, &report.Content)
		reports = append(reports, report)
	}
	return reports, rows.Err()
}

type postgresProfileRepo struct {
	db *sql.DB
}

func NewProfileRepo(db *sql.DB) ProfileRepository {
	return &postgresProfileRepo{db: db}
}

func (r *postgresProfileRepo) Upsert(ctx context.Context, profile *model.Profile) (*model.Profile, error) {
	if profile.ID == "" {
		profile.ID = uuid.New().String()
	}
	profile.CreatedAt = time.Now()

	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	_, err = tx.ExecContext(ctx, `
		UPDATE profiles SET superseded_at = $1
		WHERE user_id = $2 AND kind = $3 AND superseded_at IS NULL AND deleted_at IS NULL
	`, time.Now(), profile.UserID, profile.Kind)
	if err != nil {
		return nil, fmt.Errorf("supersede old: %w", err)
	}

	profile.Version = 1
	_, err = tx.ExecContext(ctx, `
		INSERT INTO profiles (id, user_id, kind, content_enc, source, confidence, version, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`, profile.ID, profile.UserID, profile.Kind, profile.ContentEnc,
		profile.Source, profile.Confidence, profile.Version, profile.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("insert new profile: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit: %w", err)
	}
	return profile, nil
}

func (r *postgresProfileRepo) ListActive(ctx context.Context, userID string) ([]model.Profile, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, user_id, kind, content_enc, source, confidence, version, superseded_at, deleted_at, created_at
		FROM profiles WHERE user_id = $1 AND superseded_at IS NULL AND deleted_at IS NULL
		ORDER BY created_at DESC
	`, userID)
	if err != nil {
		return nil, fmt.Errorf("ListActive: %w", err)
	}
	defer rows.Close()

	var profiles []model.Profile
	for rows.Next() {
		var p model.Profile
		if err := rows.Scan(&p.ID, &p.UserID, &p.Kind, &p.ContentEnc, &p.Source,
			&p.Confidence, &p.Version, &p.SupersededAt, &p.DeletedAt, &p.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan profile: %w", err)
		}
		profiles = append(profiles, p)
	}
	return profiles, rows.Err()
}

func (r *postgresProfileRepo) SoftDelete(ctx context.Context, profileID string) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE profiles SET deleted_at = $1 WHERE id = $2`,
		time.Now(), profileID)
	return err
}

type postgresFeedbackRepo struct {
	db *sql.DB
}

func NewFeedbackRepo(db *sql.DB) FeedbackRepository {
	return &postgresFeedbackRepo{db: db}
}

func (r *postgresFeedbackRepo) Create(ctx context.Context, fb *model.Feedback) error {
	if fb.ID == "" {
		fb.ID = uuid.New().String()
	}
	fb.CreatedAt = time.Now()

	_, err := r.db.ExecContext(ctx, `
		INSERT INTO feedback (id, user_id, report_id, claim_id, issue_type, detail, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`, fb.ID, fb.UserID, fb.ReportID, fb.ClaimID, fb.IssueType, fb.Detail, fb.CreatedAt)
	return err
}

func (r *postgresFeedbackRepo) ListByReport(ctx context.Context, reportID string) ([]model.Feedback, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, user_id, report_id, claim_id, issue_type, detail, created_at
		FROM feedback WHERE report_id = $1 ORDER BY created_at DESC
	`, reportID)
	if err != nil {
		return nil, fmt.Errorf("ListByReport: %w", err)
	}
	defer rows.Close()

	var feedbacks []model.Feedback
	for rows.Next() {
		var fb model.Feedback
		if err := rows.Scan(&fb.ID, &fb.UserID, &fb.ReportID, &fb.ClaimID,
			&fb.IssueType, &fb.Detail, &fb.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan feedback: %w", err)
		}
		feedbacks = append(feedbacks, fb)
	}
	return feedbacks, rows.Err()
}
