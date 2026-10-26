
package researchv1

import (
	context "context"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
)

const _ = grpc.SupportPackageIsVersion9

const (
	ResearchService_SubmitTask_FullMethodName  = "/research.v1.ResearchService/SubmitTask"
	ResearchService_StreamTask_FullMethodName  = "/research.v1.ResearchService/StreamTask"
	ResearchService_ResumeTask_FullMethodName  = "/research.v1.ResearchService/ResumeTask"
	ResearchService_CancelTask_FullMethodName  = "/research.v1.ResearchService/CancelTask"
	ResearchService_GetTaskCost_FullMethodName = "/research.v1.ResearchService/GetTaskCost"
	ResearchService_Chat_FullMethodName        = "/research.v1.ResearchService/Chat"
)

type ResearchServiceClient interface {

	SubmitTask(ctx context.Context, in *SubmitTaskRequest, opts ...grpc.CallOption) (*SubmitTaskResponse, error)

	StreamTask(ctx context.Context, in *StreamTaskRequest, opts ...grpc.CallOption) (grpc.ServerStreamingClient[TaskEvent], error)

	ResumeTask(ctx context.Context, in *ResumeTaskRequest, opts ...grpc.CallOption) (*ResumeTaskResponse, error)
	CancelTask(ctx context.Context, in *CancelTaskRequest, opts ...grpc.CallOption) (*CancelTaskResponse, error)

	GetTaskCost(ctx context.Context, in *GetTaskCostRequest, opts ...grpc.CallOption) (*GetTaskCostResponse, error)

	Chat(ctx context.Context, in *ChatRequest, opts ...grpc.CallOption) (*ChatResponse, error)
}

type researchServiceClient struct {
	cc grpc.ClientConnInterface
}

func NewResearchServiceClient(cc grpc.ClientConnInterface) ResearchServiceClient {
	return &researchServiceClient{cc}
}

func (c *researchServiceClient) SubmitTask(ctx context.Context, in *SubmitTaskRequest, opts ...grpc.CallOption) (*SubmitTaskResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(SubmitTaskResponse)
	err := c.cc.Invoke(ctx, ResearchService_SubmitTask_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *researchServiceClient) StreamTask(ctx context.Context, in *StreamTaskRequest, opts ...grpc.CallOption) (grpc.ServerStreamingClient[TaskEvent], error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	stream, err := c.cc.NewStream(ctx, &ResearchService_ServiceDesc.Streams[0], ResearchService_StreamTask_FullMethodName, cOpts...)
	if err != nil {
		return nil, err
	}
	x := &grpc.GenericClientStream[StreamTaskRequest, TaskEvent]{ClientStream: stream}
	if err := x.ClientStream.SendMsg(in); err != nil {
		return nil, err
	}
	if err := x.ClientStream.CloseSend(); err != nil {
		return nil, err
	}
	return x, nil
}

type ResearchService_StreamTaskClient = grpc.ServerStreamingClient[TaskEvent]

func (c *researchServiceClient) ResumeTask(ctx context.Context, in *ResumeTaskRequest, opts ...grpc.CallOption) (*ResumeTaskResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(ResumeTaskResponse)
	err := c.cc.Invoke(ctx, ResearchService_ResumeTask_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *researchServiceClient) CancelTask(ctx context.Context, in *CancelTaskRequest, opts ...grpc.CallOption) (*CancelTaskResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(CancelTaskResponse)
	err := c.cc.Invoke(ctx, ResearchService_CancelTask_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *researchServiceClient) GetTaskCost(ctx context.Context, in *GetTaskCostRequest, opts ...grpc.CallOption) (*GetTaskCostResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(GetTaskCostResponse)
	err := c.cc.Invoke(ctx, ResearchService_GetTaskCost_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *researchServiceClient) Chat(ctx context.Context, in *ChatRequest, opts ...grpc.CallOption) (*ChatResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(ChatResponse)
	err := c.cc.Invoke(ctx, ResearchService_Chat_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

type ResearchServiceServer interface {

	SubmitTask(context.Context, *SubmitTaskRequest) (*SubmitTaskResponse, error)

	StreamTask(*StreamTaskRequest, grpc.ServerStreamingServer[TaskEvent]) error

	ResumeTask(context.Context, *ResumeTaskRequest) (*ResumeTaskResponse, error)
	CancelTask(context.Context, *CancelTaskRequest) (*CancelTaskResponse, error)

	GetTaskCost(context.Context, *GetTaskCostRequest) (*GetTaskCostResponse, error)

	Chat(context.Context, *ChatRequest) (*ChatResponse, error)
	mustEmbedUnimplementedResearchServiceServer()
}

type UnimplementedResearchServiceServer struct{}

func (UnimplementedResearchServiceServer) SubmitTask(context.Context, *SubmitTaskRequest) (*SubmitTaskResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method SubmitTask not implemented")
}
func (UnimplementedResearchServiceServer) StreamTask(*StreamTaskRequest, grpc.ServerStreamingServer[TaskEvent]) error {
	return status.Errorf(codes.Unimplemented, "method StreamTask not implemented")
}
func (UnimplementedResearchServiceServer) ResumeTask(context.Context, *ResumeTaskRequest) (*ResumeTaskResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ResumeTask not implemented")
}
func (UnimplementedResearchServiceServer) CancelTask(context.Context, *CancelTaskRequest) (*CancelTaskResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method CancelTask not implemented")
}
func (UnimplementedResearchServiceServer) GetTaskCost(context.Context, *GetTaskCostRequest) (*GetTaskCostResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method GetTaskCost not implemented")
}
func (UnimplementedResearchServiceServer) Chat(context.Context, *ChatRequest) (*ChatResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method Chat not implemented")
}
func (UnimplementedResearchServiceServer) mustEmbedUnimplementedResearchServiceServer() {}
func (UnimplementedResearchServiceServer) testEmbeddedByValue()                         {}

type UnsafeResearchServiceServer interface {
	mustEmbedUnimplementedResearchServiceServer()
}

func RegisterResearchServiceServer(s grpc.ServiceRegistrar, srv ResearchServiceServer) {

	if t, ok := srv.(interface{ testEmbeddedByValue() }); ok {
		t.testEmbeddedByValue()
	}
	s.RegisterService(&ResearchService_ServiceDesc, srv)
}

func _ResearchService_SubmitTask_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(SubmitTaskRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ResearchServiceServer).SubmitTask(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ResearchService_SubmitTask_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ResearchServiceServer).SubmitTask(ctx, req.(*SubmitTaskRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _ResearchService_StreamTask_Handler(srv interface{}, stream grpc.ServerStream) error {
	m := new(StreamTaskRequest)
	if err := stream.RecvMsg(m); err != nil {
		return err
	}
	return srv.(ResearchServiceServer).StreamTask(m, &grpc.GenericServerStream[StreamTaskRequest, TaskEvent]{ServerStream: stream})
}

type ResearchService_StreamTaskServer = grpc.ServerStreamingServer[TaskEvent]

func _ResearchService_ResumeTask_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ResumeTaskRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ResearchServiceServer).ResumeTask(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ResearchService_ResumeTask_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ResearchServiceServer).ResumeTask(ctx, req.(*ResumeTaskRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _ResearchService_CancelTask_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(CancelTaskRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ResearchServiceServer).CancelTask(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ResearchService_CancelTask_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ResearchServiceServer).CancelTask(ctx, req.(*CancelTaskRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _ResearchService_GetTaskCost_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(GetTaskCostRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ResearchServiceServer).GetTaskCost(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ResearchService_GetTaskCost_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ResearchServiceServer).GetTaskCost(ctx, req.(*GetTaskCostRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _ResearchService_Chat_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ChatRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(ResearchServiceServer).Chat(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: ResearchService_Chat_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(ResearchServiceServer).Chat(ctx, req.(*ChatRequest))
	}
	return interceptor(ctx, in, info, handler)
}

var ResearchService_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "research.v1.ResearchService",
	HandlerType: (*ResearchServiceServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "SubmitTask",
			Handler:    _ResearchService_SubmitTask_Handler,
		},
		{
			MethodName: "ResumeTask",
			Handler:    _ResearchService_ResumeTask_Handler,
		},
		{
			MethodName: "CancelTask",
			Handler:    _ResearchService_CancelTask_Handler,
		},
		{
			MethodName: "GetTaskCost",
			Handler:    _ResearchService_GetTaskCost_Handler,
		},
		{
			MethodName: "Chat",
			Handler:    _ResearchService_Chat_Handler,
		},
	},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "StreamTask",
			Handler:       _ResearchService_StreamTask_Handler,
			ServerStreams: true,
		},
	},
	Metadata: "research/v1/research.proto",
}

const (
	MemoryService_ListMemory_FullMethodName      = "/research.v1.MemoryService/ListMemory"
	MemoryService_CreateMemory_FullMethodName    = "/research.v1.MemoryService/CreateMemory"
	MemoryService_UpdateMemory_FullMethodName    = "/research.v1.MemoryService/UpdateMemory"
	MemoryService_DeleteMemory_FullMethodName    = "/research.v1.MemoryService/DeleteMemory"
	MemoryService_DeleteAllMemory_FullMethodName = "/research.v1.MemoryService/DeleteAllMemory"
	MemoryService_ConfirmMemory_FullMethodName   = "/research.v1.MemoryService/ConfirmMemory"
	MemoryService_ListMemoryAudit_FullMethodName = "/research.v1.MemoryService/ListMemoryAudit"
)

type MemoryServiceClient interface {

	ListMemory(ctx context.Context, in *ListMemoryRequest, opts ...grpc.CallOption) (*ListMemoryResponse, error)

	CreateMemory(ctx context.Context, in *CreateMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error)

	UpdateMemory(ctx context.Context, in *UpdateMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error)

	DeleteMemory(ctx context.Context, in *DeleteMemoryRequest, opts ...grpc.CallOption) (*DeleteMemoryResponse, error)

	DeleteAllMemory(ctx context.Context, in *DeleteAllMemoryRequest, opts ...grpc.CallOption) (*DeleteMemoryResponse, error)

	ConfirmMemory(ctx context.Context, in *ConfirmMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error)

	ListMemoryAudit(ctx context.Context, in *ListMemoryAuditRequest, opts ...grpc.CallOption) (*ListMemoryAuditResponse, error)
}

type memoryServiceClient struct {
	cc grpc.ClientConnInterface
}

func NewMemoryServiceClient(cc grpc.ClientConnInterface) MemoryServiceClient {
	return &memoryServiceClient{cc}
}

func (c *memoryServiceClient) ListMemory(ctx context.Context, in *ListMemoryRequest, opts ...grpc.CallOption) (*ListMemoryResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(ListMemoryResponse)
	err := c.cc.Invoke(ctx, MemoryService_ListMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) CreateMemory(ctx context.Context, in *CreateMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(MemoryItem)
	err := c.cc.Invoke(ctx, MemoryService_CreateMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) UpdateMemory(ctx context.Context, in *UpdateMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(MemoryItem)
	err := c.cc.Invoke(ctx, MemoryService_UpdateMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) DeleteMemory(ctx context.Context, in *DeleteMemoryRequest, opts ...grpc.CallOption) (*DeleteMemoryResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(DeleteMemoryResponse)
	err := c.cc.Invoke(ctx, MemoryService_DeleteMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) DeleteAllMemory(ctx context.Context, in *DeleteAllMemoryRequest, opts ...grpc.CallOption) (*DeleteMemoryResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(DeleteMemoryResponse)
	err := c.cc.Invoke(ctx, MemoryService_DeleteAllMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) ConfirmMemory(ctx context.Context, in *ConfirmMemoryRequest, opts ...grpc.CallOption) (*MemoryItem, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(MemoryItem)
	err := c.cc.Invoke(ctx, MemoryService_ConfirmMemory_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *memoryServiceClient) ListMemoryAudit(ctx context.Context, in *ListMemoryAuditRequest, opts ...grpc.CallOption) (*ListMemoryAuditResponse, error) {
	cOpts := append([]grpc.CallOption{grpc.StaticMethod()}, opts...)
	out := new(ListMemoryAuditResponse)
	err := c.cc.Invoke(ctx, MemoryService_ListMemoryAudit_FullMethodName, in, out, cOpts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

type MemoryServiceServer interface {

	ListMemory(context.Context, *ListMemoryRequest) (*ListMemoryResponse, error)

	CreateMemory(context.Context, *CreateMemoryRequest) (*MemoryItem, error)

	UpdateMemory(context.Context, *UpdateMemoryRequest) (*MemoryItem, error)

	DeleteMemory(context.Context, *DeleteMemoryRequest) (*DeleteMemoryResponse, error)

	DeleteAllMemory(context.Context, *DeleteAllMemoryRequest) (*DeleteMemoryResponse, error)

	ConfirmMemory(context.Context, *ConfirmMemoryRequest) (*MemoryItem, error)

	ListMemoryAudit(context.Context, *ListMemoryAuditRequest) (*ListMemoryAuditResponse, error)
	mustEmbedUnimplementedMemoryServiceServer()
}

type UnimplementedMemoryServiceServer struct{}

func (UnimplementedMemoryServiceServer) ListMemory(context.Context, *ListMemoryRequest) (*ListMemoryResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ListMemory not implemented")
}
func (UnimplementedMemoryServiceServer) CreateMemory(context.Context, *CreateMemoryRequest) (*MemoryItem, error) {
	return nil, status.Errorf(codes.Unimplemented, "method CreateMemory not implemented")
}
func (UnimplementedMemoryServiceServer) UpdateMemory(context.Context, *UpdateMemoryRequest) (*MemoryItem, error) {
	return nil, status.Errorf(codes.Unimplemented, "method UpdateMemory not implemented")
}
func (UnimplementedMemoryServiceServer) DeleteMemory(context.Context, *DeleteMemoryRequest) (*DeleteMemoryResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method DeleteMemory not implemented")
}
func (UnimplementedMemoryServiceServer) DeleteAllMemory(context.Context, *DeleteAllMemoryRequest) (*DeleteMemoryResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method DeleteAllMemory not implemented")
}
func (UnimplementedMemoryServiceServer) ConfirmMemory(context.Context, *ConfirmMemoryRequest) (*MemoryItem, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ConfirmMemory not implemented")
}
func (UnimplementedMemoryServiceServer) ListMemoryAudit(context.Context, *ListMemoryAuditRequest) (*ListMemoryAuditResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ListMemoryAudit not implemented")
}
func (UnimplementedMemoryServiceServer) mustEmbedUnimplementedMemoryServiceServer() {}
func (UnimplementedMemoryServiceServer) testEmbeddedByValue()                       {}

type UnsafeMemoryServiceServer interface {
	mustEmbedUnimplementedMemoryServiceServer()
}

func RegisterMemoryServiceServer(s grpc.ServiceRegistrar, srv MemoryServiceServer) {

	if t, ok := srv.(interface{ testEmbeddedByValue() }); ok {
		t.testEmbeddedByValue()
	}
	s.RegisterService(&MemoryService_ServiceDesc, srv)
}

func _MemoryService_ListMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ListMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).ListMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_ListMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).ListMemory(ctx, req.(*ListMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_CreateMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(CreateMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).CreateMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_CreateMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).CreateMemory(ctx, req.(*CreateMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_UpdateMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(UpdateMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).UpdateMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_UpdateMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).UpdateMemory(ctx, req.(*UpdateMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_DeleteMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(DeleteMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).DeleteMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_DeleteMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).DeleteMemory(ctx, req.(*DeleteMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_DeleteAllMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(DeleteAllMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).DeleteAllMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_DeleteAllMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).DeleteAllMemory(ctx, req.(*DeleteAllMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_ConfirmMemory_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ConfirmMemoryRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).ConfirmMemory(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_ConfirmMemory_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).ConfirmMemory(ctx, req.(*ConfirmMemoryRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _MemoryService_ListMemoryAudit_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ListMemoryAuditRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(MemoryServiceServer).ListMemoryAudit(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: MemoryService_ListMemoryAudit_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(MemoryServiceServer).ListMemoryAudit(ctx, req.(*ListMemoryAuditRequest))
	}
	return interceptor(ctx, in, info, handler)
}

var MemoryService_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "research.v1.MemoryService",
	HandlerType: (*MemoryServiceServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "ListMemory",
			Handler:    _MemoryService_ListMemory_Handler,
		},
		{
			MethodName: "CreateMemory",
			Handler:    _MemoryService_CreateMemory_Handler,
		},
		{
			MethodName: "UpdateMemory",
			Handler:    _MemoryService_UpdateMemory_Handler,
		},
		{
			MethodName: "DeleteMemory",
			Handler:    _MemoryService_DeleteMemory_Handler,
		},
		{
			MethodName: "DeleteAllMemory",
			Handler:    _MemoryService_DeleteAllMemory_Handler,
		},
		{
			MethodName: "ConfirmMemory",
			Handler:    _MemoryService_ConfirmMemory_Handler,
		},
		{
			MethodName: "ListMemoryAudit",
			Handler:    _MemoryService_ListMemoryAudit_Handler,
		},
	},
	Streams:  []grpc.StreamDesc{},
	Metadata: "research/v1/research.proto",
}
