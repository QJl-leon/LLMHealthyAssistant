package repository

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"path/filepath"
	"testing"

	"github.com/google/uuid"
	_ "github.com/lib/pq"
)

// Runs only against an explicitly supplied database, inside a disposable schema.
// No existing application table or record is changed.
func TestUploadRepositoryPostgres(t *testing.T) {
	dsn := os.Getenv("UPLOAD_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("UPLOAD_TEST_DATABASE_URL not set")
	}
	schema := "upload_test_" + uuid.New().String()[:8]
	base, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal("open test database")
	}
	defer base.Close()
	if _, err = base.Exec(`CREATE SCHEMA ` + schema); err != nil {
		t.Fatal("create isolated schema:", err)
	}
	defer base.Exec(`DROP SCHEMA ` + schema + ` CASCADE`)
	u, err := url.Parse(dsn)
	if err != nil {
		t.Fatal("parse test database URL")
	}
	query := u.Query()
	query.Set("search_path", schema)
	u.RawQuery = query.Encode()
	db, err := sql.Open("postgres", u.String())
	if err != nil {
		t.Fatal("open isolated database")
	}
	defer db.Close()
	if _, err = db.Exec(`CREATE TABLE users (id UUID PRIMARY KEY)`); err != nil {
		t.Fatal(err)
	}
	up, err := os.ReadFile(filepath.Join("..", "..", "migrations", "000004_upload_ownership.up.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(string(up)); err != nil {
		t.Fatal("migration up:", err)
	}
	user, tenant := uuid.NewString(), uuid.NewString()
	if _, err = db.Exec(`INSERT INTO users(id) VALUES ($1)`, user); err != nil {
		t.Fatal(err)
	}
	repo := NewUploadRepo(db)
	ctx := context.Background()
	f := UploadedFile{Key: uuid.NewString() + ".png", UserID: user, TenantID: tenant, MIME: "image/png", Size: 10}
	if err = repo.Create(ctx, f); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetOwned(ctx, f.Key, tenant, user)
	if err != nil || got == nil || got.MIME != f.MIME || got.Size != 10 {
		t.Fatalf("read uploaded metadata: got=%v err=%v", got, err)
	}
	for _, pair := range [][2]string{{tenant, uuid.NewString()}, {uuid.NewString(), user}} {
		got, err = repo.GetOwned(ctx, f.Key, pair[0], pair[1])
		if err != nil || got != nil {
			t.Fatal("owner isolation failed")
		}
	}
	if err = repo.Create(ctx, f); err == nil {
		t.Fatal("duplicate image key accepted")
	}
	f.Key = uuid.NewString() + ".png"
	f.UserID = uuid.NewString()
	if err = repo.Create(ctx, f); err == nil {
		t.Fatal("unknown user accepted")
	}
	down, err := os.ReadFile(filepath.Join("..", "..", "migrations", "000004_upload_ownership.down.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(string(down)); err != nil {
		t.Fatal("migration down:", err)
	}
}
