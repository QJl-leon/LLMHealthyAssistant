package repository

import (
	"context"
	"database/sql"
	"time"
)

// UploadedFile's image key is also its relative storage name. No client path is stored.
type UploadedFile struct {
	Key       string
	TenantID  string
	UserID    string
	MIME      string
	Size      int64
	CreatedAt time.Time
}

type UploadRepository interface {
	Create(context.Context, UploadedFile) error
	GetOwned(ctx context.Context, key, tenantID, userID string) (*UploadedFile, error)
}

type postgresUploadRepo struct{ db *sql.DB }

func NewUploadRepo(db *sql.DB) UploadRepository { return &postgresUploadRepo{db: db} }
func (r *postgresUploadRepo) Create(ctx context.Context, f UploadedFile) error {
	_, err := r.db.ExecContext(ctx, `INSERT INTO uploaded_files (image_key, tenant_id, user_id, mime, size_bytes) VALUES ($1,$2,$3,$4,$5)`, f.Key, f.TenantID, f.UserID, f.MIME, f.Size)
	return err
}
func (r *postgresUploadRepo) GetOwned(ctx context.Context, key, tenantID, userID string) (*UploadedFile, error) {
	var f UploadedFile
	err := r.db.QueryRowContext(ctx, `SELECT image_key, tenant_id, user_id, mime, size_bytes, created_at FROM uploaded_files WHERE image_key=$1 AND tenant_id=$2 AND user_id=$3`, key, tenantID, userID).Scan(&f.Key, &f.TenantID, &f.UserID, &f.MIME, &f.Size, &f.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &f, nil
}
