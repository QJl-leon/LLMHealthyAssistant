package service

import (
	"bytes"
	"context"
	"errors"
	"image"
	"image/png"
	"os"
	"testing"

	"llm-healthy-assistant/go-backend/internal/repository"
)

type failingUploadRepo struct{}

func (failingUploadRepo) Create(context.Context, repository.UploadedFile) error {
	return errors.New("unavailable")
}
func (failingUploadRepo) GetOwned(context.Context, string, string, string) (*repository.UploadedFile, error) {
	return nil, nil
}
func TestUploadOwnershipWriteFailureCleansFile(t *testing.T) {
	dir := t.TempDir()
	svc := NewUploadService(failingUploadRepo{}, dir)
	var imageData bytes.Buffer
	if err := png.Encode(&imageData, image.NewRGBA(image.Rect(0, 0, 2, 2))); err != nil {
		t.Fatal(err)
	}
	if _, err := svc.Save(context.Background(), "tenant", "user", &imageData, "test.png"); err == nil {
		t.Fatal("expected database failure")
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatal("orphan file remains")
	}
}
func TestUploadKeyValidation(t *testing.T) {
	for _, key := range []string{"../a.png", "/etc/passwd", "a.png", "11111111-1111-4111-8111-111111111111.png/secret", "11111111-1111-4111-8111-111111111111.png?token=x"} {
		if ValidUploadKey(key) {
			t.Fatalf("accepted %s", key)
		}
	}
}
