
package upload

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"errors"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"math"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var (
	ErrUnsupportedFormat = errors.New("unsupported image format")
	ErrTooLarge          = errors.New("file exceeds size limit")
	ErrPixelsTooLarge    = errors.New("image pixel dimensions exceed limit")
	ErrEmptyFile         = errors.New("empty file")
	ErrRateLimited       = errors.New("rate limited")
	ErrBusy              = errors.New("upload concurrency limit reached")
)

var magicTable = []struct {
	ext, mime string
	test      func(b []byte) bool
}{
	{".jpg", "image/jpeg", func(b []byte) bool {
		return len(b) >= 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF
	}},
	{".png", "image/png", func(b []byte) bool {
		return len(b) >= 8 && bytes.Equal(b[:8],
			[]byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A})
	}},
	{".webp", "image/webp", func(b []byte) bool {
		return len(b) >= 12 && bytes.Equal(b[:4], []byte("RIFF")) &&
			bytes.Equal(b[8:12], []byte("WEBP"))
	}},
	{".gif", "image/gif", func(b []byte) bool {
		return len(b) >= 6 && (bytes.Equal(b[:6], []byte("GIF87a")) ||
			bytes.Equal(b[:6], []byte("GIF89a")))
	}},
}

func Sniff(head []byte) (ext, mime string, ok bool) {
	for _, m := range magicTable {
		if m.test(head) {
			return m.ext, m.mime, true
		}
	}
	return "", "", false
}

type bucket struct {
	mu     sync.Mutex
	tokens float64
	last   time.Time
	rate   float64
	burst  float64
}

func newBucket(rate, burst float64) *bucket {
	return &bucket{tokens: burst, last: time.Now(), rate: rate, burst: burst}
}

func (b *bucket) allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := time.Now()
	b.tokens = math.Min(b.burst, b.tokens+now.Sub(b.last).Seconds()*b.rate)
	b.last = now
	if b.tokens >= 1 {
		b.tokens--
		return true
	}
	return false
}

type Options struct {
	MaxBytes       int64
	MaxPixels      int64
	MaxConcurrency int
	RateLimitRPS   float64
	RateLimitBurst int
}

func DefaultOptions() Options {
	return Options{
		MaxBytes:       10 << 20,
		MaxPixels:      40_000_000,
		MaxConcurrency: 8,
		RateLimitRPS:   10,
		RateLimitBurst: 20,
	}
}

type SavedFile struct {
	Name   string
	Ext    string
	Mime   string
	Size   int64
	Width  int
	Height int
}

type Store struct {
	dir      string
	opts     Options
	sem      chan struct{}
	limMu    sync.Mutex
	limiters map[string]*bucket
}

func NewStore(dir string, opts Options) *Store {
	o := opts
	d := DefaultOptions()
	if o.MaxBytes <= 0 {
		o.MaxBytes = d.MaxBytes
	}
	if o.MaxPixels <= 0 {
		o.MaxPixels = d.MaxPixels
	}
	if o.MaxConcurrency <= 0 {
		o.MaxConcurrency = d.MaxConcurrency
	}
	if o.RateLimitRPS <= 0 {
		o.RateLimitRPS = d.RateLimitRPS
	}
	if o.RateLimitBurst <= 0 {
		o.RateLimitBurst = d.RateLimitBurst
	}
	return &Store{
		dir:      dir,
		opts:     o,
		sem:      make(chan struct{}, o.MaxConcurrency),
		limiters: make(map[string]*bucket),
	}
}

func (s *Store) AllowIP(ip string) bool {
	s.limMu.Lock()
	b, ok := s.limiters[ip]
	if !ok {
		b = newBucket(s.opts.RateLimitRPS, float64(s.opts.RateLimitBurst))
		s.limiters[ip] = b
	}
	s.limMu.Unlock()
	return b.allow()
}

func (s *Store) Save(src io.Reader, original string) (SavedFile, error) {
	select {
	case s.sem <- struct{}{}:
		defer func() { <-s.sem }()
	case <-time.After(15 * time.Second):
		return SavedFile{}, ErrBusy
	}

	br := bufio.NewReader(src)
	head, _ := br.Peek(16)
	if len(bytes.TrimSpace(head)) == 0 {
		return SavedFile{}, ErrEmptyFile
	}
	ext, mime, ok := Sniff(head)
	if !ok {
		return SavedFile{}, fmt.Errorf("%w (from %q)", ErrUnsupportedFormat, original)
	}
	if err := os.MkdirAll(s.dir, 0755); err != nil {
		return SavedFile{}, err
	}

	name := fmt.Sprintf("%s%s", newUUID(), ext)
	tmp := filepath.Join(s.dir, name+".tmp")
	f, err := os.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	if err != nil {
		return SavedFile{}, err
	}
	cleanup := func() {
		f.Close()
		os.Remove(tmp)
	}

	written, err := io.Copy(f, io.LimitReader(br, s.opts.MaxBytes+1))
	if err != nil {
		cleanup()
		return SavedFile{}, err
	}
	if written > s.opts.MaxBytes {
		cleanup()
		return SavedFile{}, fmt.Errorf("%w: %d bytes", ErrTooLarge, written)
	}
	if written == 0 {
		cleanup()
		return SavedFile{}, ErrEmptyFile
	}
	if err := f.Sync(); err != nil {
		cleanup()
		return SavedFile{}, err
	}
	if err := f.Close(); err != nil {
		cleanup()
		return SavedFile{}, err
	}

	width, height, err := s.decodeDimensions(tmp, mime)
	if err != nil {
		cleanup()
		return SavedFile{}, err
	}

	final := filepath.Join(s.dir, name)
	if err := os.Rename(tmp, final); err != nil {
		cleanup()
		return SavedFile{}, err
	}
	return SavedFile{
		Name: name, Ext: ext, Mime: mime,
		Size: written, Width: width, Height: height,
	}, nil
}

func (s *Store) decodeDimensions(path, mime string) (int, int, error) {
	if mime == "image/webp" {
		return 0, 0, nil
	}
	f, err := os.Open(path)
	if err != nil {
		return 0, 0, err
	}
	defer f.Close()
	cfg, _, err := image.DecodeConfig(bufio.NewReader(f))
	if err != nil {
		return 0, 0, fmt.Errorf("decode image header: %w", err)
	}
	pixels := int64(cfg.Width) * int64(cfg.Height)
	if pixels > s.opts.MaxPixels {
		return 0, 0, fmt.Errorf("%w: %dx%d=%d", ErrPixelsTooLarge,
			cfg.Width, cfg.Height, pixels)
	}
	return cfg.Width, cfg.Height, nil
}

func newUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
