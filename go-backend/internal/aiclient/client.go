
package aiclient

import (
	"context"
	"fmt"
	"io"
	"log"

	researchv1 "llm-healthy-assistant/go-backend/internal/aiclient/research/v1"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type Client struct {
	conn      *grpc.ClientConn
	client    researchv1.ResearchServiceClient
	memClient researchv1.MemoryServiceClient
}

func New(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("grpc dial: %w", err)
	}
	return &Client{
		conn:      conn,
		client:    researchv1.NewResearchServiceClient(conn),
		memClient: researchv1.NewMemoryServiceClient(conn),
	}, nil
}

func NewForConn(conn *grpc.ClientConn) *Client {
	return &Client{
		conn:      conn,
		client:    researchv1.NewResearchServiceClient(conn),
		memClient: researchv1.NewMemoryServiceClient(conn),
	}
}

func (c *Client) Close() error {
	return c.conn.Close()
}

func (c *Client) SubmitTask(ctx context.Context, req *researchv1.SubmitTaskRequest) (*researchv1.SubmitTaskResponse, error) {
	return c.client.SubmitTask(ctx, req)
}

func (c *Client) StreamTask(ctx context.Context, taskID string, traceID string, callback func(*researchv1.TaskEvent)) error {
	stream, err := c.client.StreamTask(ctx, &researchv1.StreamTaskRequest{
		TaskId:  taskID,
		TraceId: traceID,
	})
	if err != nil {
		return fmt.Errorf("StreamTask: %w", err)
	}

	for {
		event, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return fmt.Errorf("stream recv: %w", err)
		}
		callback(event)
		log.Printf("[gRPC] event seq=%d task_id=%s", event.Seq, event.TaskId)
	}
}

func (c *Client) ResumeTask(ctx context.Context, req *researchv1.ResumeTaskRequest) (*researchv1.ResumeTaskResponse, error) {
	return c.client.ResumeTask(ctx, req)
}

func (c *Client) CancelTask(ctx context.Context, req *researchv1.CancelTaskRequest) (*researchv1.CancelTaskResponse, error) {
	return c.client.CancelTask(ctx, req)
}

func (c *Client) GetTaskCost(ctx context.Context, taskID, userID string) (*researchv1.GetTaskCostResponse, error) {
	return c.client.GetTaskCost(ctx, &researchv1.GetTaskCostRequest{
		TaskId: taskID,
		UserId: userID,
	})
}

func (c *Client) Chat(ctx context.Context, req *researchv1.ChatRequest) (*researchv1.ChatResponse, error) {
	return c.client.Chat(ctx, req)
}

func (c *Client) ListMemory(ctx context.Context, userID string) (*researchv1.ListMemoryResponse, error) {
	return c.memClient.ListMemory(ctx, &researchv1.ListMemoryRequest{UserId: userID})
}

func (c *Client) CreateMemory(ctx context.Context, req *researchv1.CreateMemoryRequest) (*researchv1.MemoryItem, error) {
	return c.memClient.CreateMemory(ctx, req)
}

func (c *Client) UpdateMemory(ctx context.Context, userID, entryID, newContent string) (*researchv1.MemoryItem, error) {
	return c.memClient.UpdateMemory(ctx, &researchv1.UpdateMemoryRequest{
		UserId:     userID,
		EntryId:    entryID,
		NewContent: newContent,
	})
}

func (c *Client) DeleteMemory(ctx context.Context, userID, entryID string) (*researchv1.DeleteMemoryResponse, error) {
	return c.memClient.DeleteMemory(ctx, &researchv1.DeleteMemoryRequest{
		UserId:  userID,
		EntryId: entryID,
	})
}

func (c *Client) DeleteAllMemory(ctx context.Context, userID string) (*researchv1.DeleteMemoryResponse, error) {
	return c.memClient.DeleteAllMemory(ctx, &researchv1.DeleteAllMemoryRequest{UserId: userID})
}

func (c *Client) ConfirmMemory(ctx context.Context, userID, entryID string) (*researchv1.MemoryItem, error) {
	return c.memClient.ConfirmMemory(ctx, &researchv1.ConfirmMemoryRequest{
		UserId:  userID,
		EntryId: entryID,
	})
}

func (c *Client) ListMemoryAudit(ctx context.Context, userID string, limit int32) (*researchv1.ListMemoryAuditResponse, error) {
	return c.memClient.ListMemoryAudit(ctx, &researchv1.ListMemoryAuditRequest{
		UserId: userID,
		Limit:  limit,
	})
}
