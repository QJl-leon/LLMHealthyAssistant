package observability

import (
	"bytes"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc/metadata"
)

func TestMiddlewareRedactsQueryAndPropagatesCorrelation(t *testing.T) {
	var output bytes.Buffer
	logger = log.New(&output, "", 0)
	r := gin.New()
	r.Use(Middleware())
	r.GET("/tasks/:id", func(c *gin.Context) {
		md, _ := metadata.FromOutgoingContext(c.Request.Context())
		if len(md.Get("x-run-id")) != 1 || md.Get("x-run-id")[0] != "run-test" {
			t.Error("run missing")
		}
		c.Status(http.StatusOK)
	})
	req := httptest.NewRequest("GET", "/tasks/task-1?access_token=secret-token", nil)
	req.Header.Set("X-Run-Id", "run-test")
	req.Header.Set("X-Trace-Id", "trace-test")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Header().Get("X-Trace-Id") != "trace-test" {
		t.Fatal("trace missing")
	}
	if strings.Contains(output.String(), "secret-token") {
		t.Fatal("credential logged")
	}
	if !strings.Contains(output.String(), `"task_id":"task-1"`) {
		t.Fatal("task missing")
	}
	mu.Lock()
	defer mu.Unlock()
	if active != 0 {
		t.Fatal("active handler leaked")
	}
	if routes[routeKey{"GET", "/tasks/:id", 200}].Count != 1 {
		t.Fatal("route wasn't normalized")
	}
}
