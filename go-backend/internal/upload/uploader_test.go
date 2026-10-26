package upload

import (
	"bytes"
	"errors"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"testing"
)

func TestSniff(t *testing.T) {
	cases := []struct {
		name string
		head []byte
		ext  string
		ok   bool
	}{
		{"jpeg", []byte{0xFF, 0xD8, 0xFF, 0xE0}, ".jpg", true},
		{"png", []byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A}, ".png", true},
		{"gif", []byte("GIF89a"), ".gif", true},
		{"webp", append(append([]byte("RIFF"), make([]byte, 4)...), []byte("WEBP")...), ".webp", true},
		{"fake", []byte("MZ\x90\x00this is an exe"), "", false},
		{"empty", nil, "", false},
	}
	for _, c := range cases {
		ext, _, ok := Sniff(c.head)
		if ext != c.ext || ok != c.ok {
			t.Errorf("%s: Sniff() = (%q, %v), want (%q, %v)", c.name, ext, ok, c.ext, c.ok)
		}
	}
}

func pngBytes(t *testing.T, w, h int) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatalf("encode png: %v", err)
	}
	return buf.Bytes()
}

func TestSave_ValidPNG(t *testing.T) {
	dir := t.TempDir()
	s := NewStore(dir, DefaultOptions())

	sf, err := s.Save(bytes.NewReader(pngBytes(t, 16, 8)), "photo.png")
	if err != nil {
		t.Fatalf("Save: %v", err)
	}
	if sf.Width != 16 || sf.Height != 8 {
		t.Errorf("dimensions = %dx%d, want 16x8", sf.Width, sf.Height)
	}
	if sf.Mime != "image/png" || sf.Ext != ".png" {
		t.Errorf("mime/ext = %s/%s, want image/png/.png", sf.Mime, sf.Ext)
	}

	if _, err := os.Stat(filepath.Join(dir, sf.Name)); err != nil {
		t.Errorf("saved file missing: %v", err)
	}
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if filepath.Ext(e.Name()) == ".tmp" {
			t.Errorf("tmp file left behind: %s", e.Name())
		}
	}
}

func TestSave_FakeExtension(t *testing.T) {
	dir := t.TempDir()
	s := NewStore(dir, DefaultOptions())

	fake := append([]byte("MZ\x90\x00"), []byte("not really an image")...)
	_, err := s.Save(bytes.NewReader(fake), "innocent.png")
	if !errors.Is(err, ErrUnsupportedFormat) {
		t.Errorf("Save() error = %v, want ErrUnsupportedFormat", err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 0 {
		t.Errorf("rejected file left on disk: %v", entries)
	}
}

func TestSave_TooLarge(t *testing.T) {
	dir := t.TempDir()
	s := NewStore(dir, Options{MaxBytes: 1 << 10})

	big := make([]byte, 2<<10)
	copy(big, []byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A})
	_, err := s.Save(bytes.NewReader(big), "big.png")
	if !errors.Is(err, ErrTooLarge) {
		t.Errorf("Save() error = %v, want ErrTooLarge", err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 0 {
		t.Errorf("oversized file left on disk: %v", entries)
	}
}

func TestAllowIP(t *testing.T) {
	s := NewStore(t.TempDir(), Options{RateLimitRPS: 1, RateLimitBurst: 2})
	ip := "10.0.0.1"
	if !s.AllowIP(ip) || !s.AllowIP(ip) {
		t.Fatal("burst 内应全部放行")
	}
	if s.AllowIP(ip) {
		t.Fatal("超出 burst 应拒绝")
	}
}

func TestSave_Empty(t *testing.T) {
	s := NewStore(t.TempDir(), DefaultOptions())
	_, err := s.Save(bytes.NewReader(nil), "empty.png")
	if !errors.Is(err, ErrEmptyFile) {
		t.Errorf("Save() error = %v, want ErrEmptyFile", err)
	}
}
