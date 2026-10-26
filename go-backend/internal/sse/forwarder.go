package sse

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"time"

	"llm-healthy-assistant/go-backend/internal/aiclient"
	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"
	"llm-healthy-assistant/go-backend/internal/observability"

	"github.com/gin-gonic/gin"
	"google.golang.org/protobuf/encoding/protojson"
)

const (
	eventChanSize = 64
	writeTimeout  = 30 * time.Second
	recentMaxPer  = 256
)

type Forwarder struct {
	aiClient *aiclient.Client
	store    EventStore
}

func NewForwarder(aiClient *aiclient.Client, store EventStore) *Forwarder {
	return &Forwarder{
		aiClient: aiClient,
		store:    store,
	}
}

func (f *Forwarder) replay(ctx context.Context, taskID string, lastSeq int64, w io.Writer) int {
	events, err := f.store.ReadAfter(ctx, taskID, lastSeq)
	if err != nil {
		log.Printf("[SSE] 重放读取失败: %v", err)
		return 0
	}
	n := 0
	for _, e := range events {
		fmt.Fprintf(w, "id: %d\ndata: %s\n\n", e.Seq, e.Data)
		n++
	}
	return n
}

func (f *Forwarder) GinStreamHandler(c *gin.Context) {
	taskID := c.Param("id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "missing task_id"})
		return
	}
	traceID := c.GetHeader("X-Trace-Id")
	if traceID == "" {
		traceID = taskID
	}

	observability.Event("sse_open", map[string]any{"task_id": taskID, "trace_id": traceID, "run_id": c.GetHeader("X-Run-Id")})
	defer func() {
		observability.Event("sse_close", map[string]any{"task_id": taskID, "trace_id": traceID, "run_id": c.GetHeader("X-Run-Id"), "cancelled": c.Request.Context().Err() != nil})
	}()

	lastID := int64(0)
	if raw := c.GetHeader("Last-Event-ID"); raw != "" {
		if n, err := strconv.ParseInt(raw, 10, 64); err == nil {
			lastID = n
		}
	}

	w := c.Writer
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)

	ctx, cancel := context.WithCancel(c.Request.Context())
	defer cancel()

	if replayed := f.replay(ctx, taskID, lastID, w); replayed > 0 {
		c.Writer.Flush()
		observability.Event("sse_replay", map[string]any{"task_id": taskID, "trace_id": traceID, "events": replayed, "last_id": lastID})
		log.Printf("[SSE] 重放 %d 条历史事件 task_id=%s last_id=%d", replayed, taskID, lastID)
	}

	events := make(chan *researchv1.TaskEvent, eventChanSize)
	streamErr := make(chan error, 1)

	go func() {

		err := f.aiClient.StreamTask(ctx, taskID, traceID, func(ev *researchv1.TaskEvent) {

			if lastID > 0 && ev.Seq <= lastID {
				return
			}
			select {
			case events <- ev:
			case <-ctx.Done():
			}
		})
		streamErr <- err
		close(events)
	}()

	marshaler := protojson.MarshalOptions{
		UseProtoNames:   false,
		EmitUnpopulated: false,
	}
	rc := http.NewResponseController(w)

	writeEvent := func(ev *researchv1.TaskEvent) bool {
		data, err := marshaler.Marshal(ev)
		if err != nil {
			log.Printf("[SSE] marshal 失败: %v", err)
			return false
		}

		_ = rc.SetWriteDeadline(time.Now().Add(writeTimeout))
		if _, werr := fmt.Fprintf(w, "id: %d\ndata: %s\n\n", ev.Seq, data); werr != nil {
			log.Printf("[SSE] 写失败（客户端断开或慢消费者）: %v", werr)
			return false
		}
		c.Writer.Flush()

		if err := f.store.Append(ctx, taskID, ev.Seq, data); err != nil {
			log.Printf("[SSE] 事件落共享存储失败（不阻塞推送）: %v", err)
		}
		return true
	}

	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case ev, ok := <-events:
			if !ok {

				if err := <-streamErr; err != nil && err != io.EOF && ctx.Err() == nil {
					log.Printf("[SSE] stream error: %v", err)
					fmt.Fprintf(w, "event: error\ndata: {\"error\":\"%s\"}\n\n", err.Error())
					c.Writer.Flush()
				}
				return
			}
			if !writeEvent(ev) {
				return
			}
		case <-ticker.C:
			_ = rc.SetWriteDeadline(time.Now().Add(writeTimeout))
			if _, err := fmt.Fprintf(w, ": heartbeat\n\n"); err != nil {
				log.Printf("[SSE] 心跳写失败，关闭流: %v", err)
				return
			}
			c.Writer.Flush()
		case <-ctx.Done():
			return
		}
	}
}
