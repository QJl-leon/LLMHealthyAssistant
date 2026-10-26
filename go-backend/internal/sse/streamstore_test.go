
package sse

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
)

func newTestRedis(t *testing.T) *miniredis.Miniredis {
	t.Helper()
	mr := miniredis.RunT(t)
	t.Cleanup(mr.Close)
	return mr
}

func TestRedisStreamStore_AppendAndReadAfter(t *testing.T) {
	mr := newTestRedis(t)
	store, err := NewRedisStreamStore("redis://" + mr.Addr())
	if err != nil {
		t.Fatalf("NewRedisStreamStore: %v", err)
	}
	defer store.Close()

	ctx := context.Background()
	for i := int64(1); i <= 5; i++ {
		if err := store.Append(ctx, "task-1", i, []byte(`{"n":`+string(rune('0'+i))+`}`)); err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
	}

	events, err := store.ReadAfter(ctx, "task-1", 0)
	if err != nil {
		t.Fatalf("ReadAfter: %v", err)
	}
	if len(events) != 5 {
		t.Fatalf("ReadAfter count = %d, want 5", len(events))
	}

	events, _ = store.ReadAfter(ctx, "task-1", 3)
	if len(events) != 2 || events[0].Seq != 4 || events[1].Seq != 5 {
		t.Errorf("增量重放错误: %+v", events)
	}

	ttl := mr.TTL("sse:events:task-1")
	if ttl <= 0 {
		t.Errorf("TTL 未设置: %v", ttl)
	}
}

func TestRedisStreamStore_MaxLenTrim(t *testing.T) {
	mr := newTestRedis(t)
	store, _ := NewRedisStreamStore("redis://" + mr.Addr())
	defer store.Close()

	ctx := context.Background()

	for i := int64(1); i <= 1100; i++ {
		_ = store.Append(ctx, "big-task", i, []byte("x"))
	}
	events, _ := store.ReadAfter(ctx, "big-task", 0)
	if len(events) >= 1100 {
		t.Errorf("MAXLEN 未生效: 保留 %d 条", len(events))
	}

	if events[len(events)-1].Seq != 1100 {
		t.Errorf("最新事件丢失: 末条 seq=%d", events[len(events)-1].Seq)
	}
}

func TestRedisStreamStore_CrossInstanceReplay(t *testing.T) {
	mr := newTestRedis(t)
	url := "redis://" + mr.Addr()
	ctx := context.Background()

	storeA, _ := NewRedisStreamStore(url)
	for i := int64(1); i <= 3; i++ {
		_ = storeA.Append(ctx, "shared-task", i, []byte("event"))
	}
	storeA.Close()

	storeB, _ := NewRedisStreamStore(url)
	defer storeB.Close()
	events, err := storeB.ReadAfter(ctx, "shared-task", 1)
	if err != nil {
		t.Fatalf("实例 B ReadAfter: %v", err)
	}
	if len(events) != 2 || events[0].Seq != 2 {
		t.Errorf("跨实例重放错误: %+v", events)
	}
}

func TestFailoverStore_RedisDown(t *testing.T) {
	mr := newTestRedis(t)
	url := "redis://" + mr.Addr()
	ctx := context.Background()

	f := NewFailoverStore(url, 256)
	if f.primary == nil {
		t.Fatal("Redis 可用时 primary 不应为 nil")
	}

	_ = f.Append(ctx, "t1", 1, []byte("a"))
	_ = f.Append(ctx, "t1", 2, []byte("b"))

	mr.Close()

	if err := f.Append(ctx, "t1", 3, []byte("c")); err != nil {
		t.Fatalf("Redis 挂掉后 Append 应降级不报错: %v", err)
	}

	events, err := f.ReadAfter(ctx, "t1", 0)
	if err != nil {
		t.Fatalf("降级 ReadAfter: %v", err)
	}
	if len(events) != 3 {
		t.Errorf("降级重放条数 = %d, want 3（内存兜底）", len(events))
	}
}

func TestFailoverStore_RedisUnavailableAtStart(t *testing.T) {
	f := NewFailoverStore("redis://127.0.0.1:1", 256)
	if f.primary != nil {
		t.Error("Redis 不可用时 primary 应为 nil（内存模式）")
	}
	ctx := context.Background()
	_ = f.Append(ctx, "t", 1, []byte("x"))
	events, err := f.ReadAfter(ctx, "t", 0)
	if err != nil || len(events) != 1 {
		t.Errorf("内存模式读写异常: events=%d err=%v", len(events), err)
	}
}

func TestFailoverStore_RedisRecover(t *testing.T) {
	mr := newTestRedis(t)
	url := "redis://" + mr.Addr()
	ctx := context.Background()

	f := NewFailoverStore(url, 256)
	defer f.Close()

	_ = f.Append(ctx, "t", 1, []byte("a"))

	mr.Close()
	_ = f.Append(ctx, "t", 2, []byte("b"))

	mr2 := miniredis.RunT(t)
	defer mr2.Close()
	f2 := NewFailoverStore("redis://"+mr2.Addr(), 256)
	defer f2.Close()
	if err := f2.Append(ctx, "t", 3, []byte("c")); err != nil {
		t.Fatalf("恢复后 Append: %v", err)
	}
	events, _ := f2.ReadAfter(ctx, "t", 0)
	if len(events) != 1 || events[0].Seq != 3 {
		t.Errorf("恢复后应走 Redis（只有新事件）: %+v", events)
	}
}

func TestFailoverStore_NoRedisURL(t *testing.T) {
	f := NewFailoverStore("", 256)
	if f.primary != nil {
		t.Error("未配置 REDIS_URL 时 primary 应为 nil")
	}
}

var _ EventStore = (*FailoverStore)(nil)
var _ EventStore = (*RedisStreamStore)(nil)

func TestMain(m *testing.M) {

	time.Sleep(0)
	m.Run()
}
