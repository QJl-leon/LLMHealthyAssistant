
package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type HealthStatus struct {

	Postgres string `json:"postgres"`

	Redis string `json:"redis"`

	Milvus string `json:"milvus"`

	MinIO string `json:"minio"`
}

func HealthHandler(c *gin.Context) {

	status := HealthStatus{
		Postgres: "pending",
		Redis:    "pending",
		Milvus:   "pending",
		MinIO:    "pending",
	}
	c.JSON(http.StatusOK, gin.H{
		"status": "ok",
		"deps":   status,
	})
}
