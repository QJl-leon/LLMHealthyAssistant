package service

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"regexp"
	"syscall"

	"llm-healthy-assistant/go-backend/internal/repository"
	"llm-healthy-assistant/go-backend/internal/upload"
)

var ErrUploadNotFound = errors.New("image not found")
var uploadKeyPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|gif|webp)$`)

func ValidUploadKey(key string) bool { return uploadKeyPattern.MatchString(key) }

type UploadService struct {
	repo  repository.UploadRepository
	store *upload.Store
	dir   string
}

func NewUploadService(repo repository.UploadRepository, dir string) *UploadService {
	return &UploadService{repo: repo, store: upload.NewStore(dir, upload.DefaultOptions()), dir: dir}
}
func (s *UploadService) AllowIP(ip string) bool { return s.store.AllowIP(ip) }
func (s *UploadService) Save(ctx context.Context, tenantID, userID string, src io.Reader, original string) (upload.SavedFile, error) {
	if tenantID == "" || userID == "" {
		return upload.SavedFile{}, ErrUploadNotFound
	}
	saved, err := s.store.Save(src, original)
	if err != nil {
		return saved, err
	}
	err = s.repo.Create(ctx, repository.UploadedFile{Key: saved.Name, TenantID: tenantID, UserID: userID, MIME: saved.Mime, Size: saved.Size})
	if err != nil {
		// File and SQL cannot share a transaction. Fail closed and compensate on errors.
		root, openErr := os.OpenRoot(s.dir)
		if openErr == nil {
			if removeErr := root.Remove(saved.Name); removeErr != nil {
				log.Printf("[Upload] cleanup failed key=%s: %v", saved.Name, removeErr)
			}
			root.Close()
		} else {
			log.Printf("[Upload] cleanup root failed: %v", openErr)
		}
		return upload.SavedFile{}, fmt.Errorf("save upload ownership: %w", err)
	}
	return saved, nil
}
func (s *UploadService) OpenOwned(ctx context.Context, key, tenantID, userID string) (*os.File, *repository.UploadedFile, error) {
	if !ValidUploadKey(key) || tenantID == "" || userID == "" {
		return nil, nil, ErrUploadNotFound
	}
	record, err := s.repo.GetOwned(ctx, key, tenantID, userID)
	if err != nil {
		return nil, nil, err
	}
	if record == nil || record.Key != key || record.TenantID != tenantID || record.UserID != userID {
		return nil, nil, ErrUploadNotFound
	}
	root, err := os.OpenRoot(s.dir)
	if err != nil {
		return nil, nil, ErrUploadNotFound
	}
	defer root.Close()
	// Reject symlinks as well as traversal. OpenRoot additionally prevents escaping
	// the storage directory even if a path is swapped between Lstat and Open.
	info, err := root.Lstat(key)
	if err != nil || !info.Mode().IsRegular() {
		return nil, nil, ErrUploadNotFound
	}
	file, err := root.OpenFile(key, os.O_RDONLY|syscall.O_NONBLOCK|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, nil, ErrUploadNotFound
	}
	info, err = file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		file.Close()
		return nil, nil, ErrUploadNotFound
	}
	return file, record, nil
}
func (s *UploadService) CheckOwned(ctx context.Context, keys []string, tenantID, userID string) error {
	for _, key := range keys {
		file, _, err := s.OpenOwned(ctx, key, tenantID, userID)
		if err != nil {
			return err
		}
		file.Close()
	}
	return nil
}
