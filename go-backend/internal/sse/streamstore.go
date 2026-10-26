
package sse

import (
	"context"
	"fmt"
	"log"
	"strconv"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

type StoredEvent struct {
	Seq  int64
	Data []byte
}

type EventStore interface {

	Append(ctx context.Context, taskID string, seq int64, data []byte) error

	ReadAfter(ctx context.Context, taskID string, lastSeq int64) ([]StoredEvent, error)

	Close() error
}

const (
	redisKeyPrefix = "sse:events:"
	redisMaxLen    = 1000
	redisTTL       = 2 * time.Hour
)

type RedisStreamStore struct {
	cli *redis.Client
}

func NewRedisStreamStore(redisURL string) (*RedisStreamStore, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	cli := redis.NewClient(opt)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := cli.Ping(ctx).Err(); err != nil {
		_ = cli.Close()
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	return &RedisStreamStore{cli: cli}, nil
}

func (s *RedisStreamStore) key(taskID string) string { return redisKeyPrefix + taskID }

func (s *RedisStreamStore) Append(ctx context.Context, taskID string, seq int64, data []byte) error {
	key := s.key(taskID)

	id := strconv.FormatInt(seq, 10) + "-0"
	if err := s.cli.XAdd(ctx, &redis.XAddArgs{
		Stream: key,
		MaxLen: redisMaxLen,
		Approx: true,
		ID:     id,
		Values: map[string]any{"seq": seq, "data": data},
	}).Err(); err != nil {
		return fmt.Errorf("xadd: %w", err)
	}

	_ = s.cli.Expire(ctx, key, redisTTL).Err()
	return nil
}

func (s *RedisStreamStore) ReadAfter(ctx context.Context, taskID string, lastSeq int64) ([]StoredEvent, error) {

	start := "(" + strconv.FormatInt(lastSeq, 10) + "-0"
	msgs, err := s.cli.XRange(ctx, s.key(taskID), start, "+").Result()
	if err != nil {
		return nil, fmt.Errorf("xrange: %w", err)
	}
	out := make([]StoredEvent, 0, len(msgs))
	for _, m := range msgs {
		seq, _ := strconv.ParseInt(fmt.Sprint(m.Values["seq"]), 10, 64)
		var data []byte
		switch v := m.Values["data"].(type) {
		case string:
			data = []byte(v)
		case []byte:
			data = v
		}
		out = append(out, StoredEvent{Seq: seq, Data: data})
	}
	return out, nil
}

func (s *RedisStreamStore) Close() error { return s.cli.Close() }

type memoryStore struct {
	mu     sync.Mutex
	tasks  map[string][]StoredEvent
	maxPer int
}

func newMemoryStore(maxPer int) *memoryStore {
	return &memoryStore{tasks: make(map[string][]StoredEvent), maxPer: maxPer}
}

func (m *memoryStore) Append(_ context.Context, taskID string, seq int64, data []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	buf := m.tasks[taskID]
	if len(buf) >= m.maxPer {
		buf = append(buf[1:], StoredEvent{Seq: seq, Data: data})
	} else {
		buf = append(buf, StoredEvent{Seq: seq, Data: data})
	}
	m.tasks[taskID] = buf
	return nil
}

func (m *memoryStore) ReadAfter(_ context.Context, taskID string, lastSeq int64) ([]StoredEvent, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []StoredEvent
	for _, e := range m.tasks[taskID] {
		if e.Seq > lastSeq {
			out = append(out, e)
		}
	}
	return out, nil
}

func (m *memoryStore) Close() error { return nil }

type FailoverStore struct {
	primary EventStore
	backup  EventStore

	mu        sync.RWMutex
	redisDown bool
}

func NewFailoverStore(redisURL string, memMaxPer int) *FailoverStore {
	f := &FailoverStore{backup: newMemoryStore(memMaxPer)}
	if redisURL == "" {
		log.Printf("[SSE] 未配置 REDIS_URL，事件缓冲为内存模式（单实例可用，多副本/重启重放不可用）")
		return f
	}
	rs, err := NewRedisStreamStore(redisURL)
	if err != nil {
		log.Printf("[SSE] ⚠️ Redis 不可用（%v），事件缓冲降级为内存模式", err)
		return f
	}
	f.primary = rs
	log.Printf("[SSE] 事件共享存储：Redis Stream（MAXLEN=%d TTL=%s），内存降级备用", redisMaxLen, redisTTL)
	return f
}

func (f *FailoverStore) Append(ctx context.Context, taskID string, seq int64, data []byte) error {

	_ = f.backup.Append(ctx, taskID, seq, data)

	if f.primary == nil {
		return nil
	}
	if err := f.primary.Append(ctx, taskID, seq, data); err != nil {
		f.mu.Lock()
		if !f.redisDown {
			log.Printf("[SSE] ⚠️ Redis 写入失败，事件缓冲降级为内存模式: %v", err)
		}
		f.redisDown = true
		f.mu.Unlock()
		return nil
	}
	f.mu.Lock()
	if f.redisDown {
		log.Printf("[SSE] ✅ Redis 恢复，事件缓冲回到共享存储模式")
	}
	f.redisDown = false
	f.mu.Unlock()
	return nil
}

func (f *FailoverStore) ReadAfter(ctx context.Context, taskID string, lastSeq int64) ([]StoredEvent, error) {
	if f.primary != nil {
		events, err := f.primary.ReadAfter(ctx, taskID, lastSeq)
		if err == nil && len(events) > 0 {
			return events, nil
		}
		if err != nil {
			log.Printf("[SSE] ⚠️ Redis 读取失败，回落内存缓冲: %v", err)
		}

	}
	return f.backup.ReadAfter(ctx, taskID, lastSeq)
}

func (f *FailoverStore) Close() error {
	if f.primary != nil {
		return f.primary.Close()
	}
	return nil
}
