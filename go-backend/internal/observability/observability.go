package observability

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"google.golang.org/grpc/metadata"
)

type routeKey struct {
	Method, Route string
	Status        int
}
type routeStats struct {
	Count   uint64
	Seconds float64
	Buckets [12]uint64
}

var bounds = [...]float64{.005, .01, .025, .05, .1, .25, .5, 1, 5, 30, 120, 600}
var mu sync.Mutex
var routes = map[routeKey]*routeStats{}
var active int64
var reportWrites atomic.Uint64
var reportWriteErrors atomic.Uint64
var logger *log.Logger

func Event(event string, fields map[string]any) {
	if logger == nil {
		return
	}
	fields["event"] = event
	fields["ts"] = time.Now().UTC().Format(time.RFC3339Nano)
	b, err := json.Marshal(fields)
	if err == nil {
		logger.Print(string(b))
	}
}

func ReportWrite(taskID, reportID string, elapsed time.Duration, err error) {
	outcome := "ok"
	if err != nil {
		outcome = "error"
		reportWriteErrors.Add(1)
	} else {
		reportWrites.Add(1)
	}
	Event("report_write", map[string]any{"task_id": taskID, "report_id": reportID, "outcome": outcome, "duration_ms": elapsed.Seconds() * 1000})
}

func Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		trace := c.GetHeader("X-Trace-Id")
		if len(trace) == 0 || len(trace) > 128 {
			trace = uuid.NewString()
		}
		run := c.GetHeader("X-Run-Id")
		if len(run) > 100 {
			run = run[:100]
		}
		c.Header("X-Trace-Id", trace)
		c.Set("observation_trace", trace)
		c.Request = c.Request.WithContext(metadata.AppendToOutgoingContext(c.Request.Context(), "x-trace-id", trace, "x-run-id", run))
		start := time.Now()
		mu.Lock()
		active++
		mu.Unlock()
		defer func() {
			route := c.FullPath()
			if route == "" {
				route = "unmatched"
			}
			duration := time.Since(start).Seconds()
			key := routeKey{c.Request.Method, route, c.Writer.Status()}
			mu.Lock()
			active--
			stats := routes[key]
			if stats == nil {
				stats = &routeStats{}
				routes[key] = stats
			}
			stats.Count++
			stats.Seconds += duration
			for i, b := range bounds {
				if duration <= b {
					stats.Buckets[i]++
				}
			}
			mu.Unlock()
			Event("http_request", map[string]any{"method": key.Method, "route": route, "status": key.Status, "trace_id": trace, "run_id": run, "task_id": c.Param("id"), "duration_ms": duration * 1000, "bytes": c.Writer.Size(), "cancelled": c.Request.Context().Err() != nil})
		}()
		c.Next()
	}
}

// A dedicated loopback listener keeps metrics outside the public Gin router.
func Start(pool *sql.DB) error {
	path := os.Getenv("LHA_GO_OBSERVATION_LOG")
	if path == "" {
		path = "/home/ubuntu/RAG-job/线上测试部署/logs/go-events.jsonl"
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	logger = log.New(f, "", 0)
	mux := http.NewServeMux()
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintf(w, "lha_report_writes_total %d\nlha_report_write_errors_total %d\n", reportWrites.Load(), reportWriteErrors.Load())
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		fmt.Fprintf(w, "lha_go_goroutines %d\nlha_go_heap_bytes %d\nlha_go_gc_cycles_total %d\n", runtime.NumGoroutine(), m.HeapAlloc, m.NumGC)
		d := pool.Stats()
		fmt.Fprintf(w, "lha_go_db_open %d\nlha_go_db_in_use %d\nlha_go_db_idle %d\nlha_go_db_wait_total %d\nlha_go_db_wait_seconds_total %f\nlha_go_db_max_open %d\n", d.OpenConnections, d.InUse, d.Idle, d.WaitCount, d.WaitDuration.Seconds(), d.MaxOpenConnections)
		mu.Lock()
		defer mu.Unlock()
		fmt.Fprintf(w, "lha_http_active %d\n", active)
		for k, s := range routes {
			labels := fmt.Sprintf("method=%s,route=%s,status=%s", strconv.Quote(k.Method), strconv.Quote(k.Route), strconv.Quote(strconv.Itoa(k.Status)))
			fmt.Fprintf(w, "lha_http_request_seconds_count{%s} %d\nlha_http_request_seconds_sum{%s} %f\n", labels, s.Count, labels, s.Seconds)
			for i, b := range bounds {
				fmt.Fprintf(w, "lha_http_request_seconds_bucket{%s,le=\"%g\"} %d\n", labels, b, s.Buckets[i])
			}
			fmt.Fprintf(w, "lha_http_request_seconds_bucket{%s,le=\"+Inf\"} %d\n", labels, s.Count)
		}
	})
	l, err := net.Listen("tcp", "127.0.0.1:9109")
	if err != nil {
		return err
	}
	go func() {
		if err := http.Serve(l, mux); err != nil {
			log.Printf("metrics listener: %v", err)
		}
	}()
	return nil
}
