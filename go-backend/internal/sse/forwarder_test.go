package sse

import (
	"context"
	"testing"
)

func TestMemoryStore_Replay(t *testing.T) {
	m := newMemoryStore(3)
	ctx := context.Background()

	for i := int64(1); i <= 4; i++ {
		_ = m.Append(ctx, "task-1", i, []byte(`{"seq":1}`))
	}

	_ = m.Append(ctx, "task-2", 99, []byte(`{"seq":99}`))

	events, _ := m.ReadAfter(ctx, "task-1", 2)
	if len(events) != 2 {
		t.Fatalf("replay count = %d, want 2", len(events))
	}
	if events[0].Seq != 3 || events[1].Seq != 4 {
		t.Errorf("replay seq 错误: %+v", events)
	}

	events, _ = m.ReadAfter(ctx, "task-1", 100)
	if len(events) != 0 {
		t.Errorf("replay count = %d, want 0 (lastID 超前)", len(events))
	}
}

func TestMemoryStore_RingLimit(t *testing.T) {
	m := newMemoryStore(2)
	ctx := context.Background()
	for i := int64(1); i <= 5; i++ {
		_ = m.Append(ctx, "t", i, []byte("x"))
	}
	events, _ := m.ReadAfter(ctx, "t", 0)
	if len(events) != 2 {
		t.Fatalf("ring size = %d, want 2", len(events))
	}
	if events[0].Seq != 4 || events[1].Seq != 5 {
		t.Errorf("最旧事件未被淘汰: %+v", events)
	}
}
