
package researchv1

import (
	protoreflect "google.golang.org/protobuf/reflect/protoreflect"
	protoimpl "google.golang.org/protobuf/runtime/protoimpl"
	reflect "reflect"
	sync "sync"
	unsafe "unsafe"
)

const (

	_ = protoimpl.EnforceVersion(20 - protoimpl.MinVersion)

	_ = protoimpl.EnforceVersion(protoimpl.MaxVersion - 20)
)

type ChatHistoryItem struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Role          string                 `protobuf:"bytes,1,opt,name=role,proto3" json:"role,omitempty"`
	Content       string                 `protobuf:"bytes,2,opt,name=content,proto3" json:"content,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ChatHistoryItem) Reset() {
	*x = ChatHistoryItem{}
	mi := &file_research_v1_research_proto_msgTypes[0]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ChatHistoryItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ChatHistoryItem) ProtoMessage() {}

func (x *ChatHistoryItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[0]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ChatHistoryItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{0}
}

func (x *ChatHistoryItem) GetRole() string {
	if x != nil {
		return x.Role
	}
	return ""
}

func (x *ChatHistoryItem) GetContent() string {
	if x != nil {
		return x.Content
	}
	return ""
}

type ChatRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	Query         string                 `protobuf:"bytes,2,opt,name=query,proto3" json:"query,omitempty"`
	TraceId       string                 `protobuf:"bytes,3,opt,name=trace_id,json=traceId,proto3" json:"trace_id,omitempty"`
	History       []*ChatHistoryItem     `protobuf:"bytes,4,rep,name=history,proto3" json:"history,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ChatRequest) Reset() {
	*x = ChatRequest{}
	mi := &file_research_v1_research_proto_msgTypes[1]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ChatRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ChatRequest) ProtoMessage() {}

func (x *ChatRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[1]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ChatRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{1}
}

func (x *ChatRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *ChatRequest) GetQuery() string {
	if x != nil {
		return x.Query
	}
	return ""
}

func (x *ChatRequest) GetTraceId() string {
	if x != nil {
		return x.TraceId
	}
	return ""
}

func (x *ChatRequest) GetHistory() []*ChatHistoryItem {
	if x != nil {
		return x.History
	}
	return nil
}

type ChatResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Refused       bool                   `protobuf:"varint,1,opt,name=refused,proto3" json:"refused,omitempty"`
	Answer        string                 `protobuf:"bytes,2,opt,name=answer,proto3" json:"answer,omitempty"`
	Evidence      []*EvidenceFound       `protobuf:"bytes,3,rep,name=evidence,proto3" json:"evidence,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ChatResponse) Reset() {
	*x = ChatResponse{}
	mi := &file_research_v1_research_proto_msgTypes[2]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ChatResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ChatResponse) ProtoMessage() {}

func (x *ChatResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[2]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ChatResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{2}
}

func (x *ChatResponse) GetRefused() bool {
	if x != nil {
		return x.Refused
	}
	return false
}

func (x *ChatResponse) GetAnswer() string {
	if x != nil {
		return x.Answer
	}
	return ""
}

func (x *ChatResponse) GetEvidence() []*EvidenceFound {
	if x != nil {
		return x.Evidence
	}
	return nil
}

type GetTaskCostRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	UserId        string                 `protobuf:"bytes,2,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *GetTaskCostRequest) Reset() {
	*x = GetTaskCostRequest{}
	mi := &file_research_v1_research_proto_msgTypes[3]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *GetTaskCostRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*GetTaskCostRequest) ProtoMessage() {}

func (x *GetTaskCostRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[3]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*GetTaskCostRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{3}
}

func (x *GetTaskCostRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *GetTaskCostRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

type CostItem struct {
	state            protoimpl.MessageState `protogen:"open.v1"`
	CallType         string                 `protobuf:"bytes,1,opt,name=call_type,json=callType,proto3" json:"call_type,omitempty"`
	Model            string                 `protobuf:"bytes,2,opt,name=model,proto3" json:"model,omitempty"`
	Calls            int32                  `protobuf:"varint,3,opt,name=calls,proto3" json:"calls,omitempty"`
	Tokens           int64                  `protobuf:"varint,4,opt,name=tokens,proto3" json:"tokens,omitempty"`
	PromptTokens     int64                  `protobuf:"varint,5,opt,name=prompt_tokens,json=promptTokens,proto3" json:"prompt_tokens,omitempty"`
	CompletionTokens int64                  `protobuf:"varint,6,opt,name=completion_tokens,json=completionTokens,proto3" json:"completion_tokens,omitempty"`
	AvgLatencyMs     int32                  `protobuf:"varint,7,opt,name=avg_latency_ms,json=avgLatencyMs,proto3" json:"avg_latency_ms,omitempty"`
	unknownFields    protoimpl.UnknownFields
	sizeCache        protoimpl.SizeCache
}

func (x *CostItem) Reset() {
	*x = CostItem{}
	mi := &file_research_v1_research_proto_msgTypes[4]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *CostItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CostItem) ProtoMessage() {}

func (x *CostItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[4]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*CostItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{4}
}

func (x *CostItem) GetCallType() string {
	if x != nil {
		return x.CallType
	}
	return ""
}

func (x *CostItem) GetModel() string {
	if x != nil {
		return x.Model
	}
	return ""
}

func (x *CostItem) GetCalls() int32 {
	if x != nil {
		return x.Calls
	}
	return 0
}

func (x *CostItem) GetTokens() int64 {
	if x != nil {
		return x.Tokens
	}
	return 0
}

func (x *CostItem) GetPromptTokens() int64 {
	if x != nil {
		return x.PromptTokens
	}
	return 0
}

func (x *CostItem) GetCompletionTokens() int64 {
	if x != nil {
		return x.CompletionTokens
	}
	return 0
}

func (x *CostItem) GetAvgLatencyMs() int32 {
	if x != nil {
		return x.AvgLatencyMs
	}
	return 0
}

type GetTaskCostResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	TotalTokens   int64                  `protobuf:"varint,2,opt,name=total_tokens,json=totalTokens,proto3" json:"total_tokens,omitempty"`
	CallCount     int32                  `protobuf:"varint,3,opt,name=call_count,json=callCount,proto3" json:"call_count,omitempty"`
	Items         []*CostItem            `protobuf:"bytes,4,rep,name=items,proto3" json:"items,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *GetTaskCostResponse) Reset() {
	*x = GetTaskCostResponse{}
	mi := &file_research_v1_research_proto_msgTypes[5]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *GetTaskCostResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*GetTaskCostResponse) ProtoMessage() {}

func (x *GetTaskCostResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[5]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*GetTaskCostResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{5}
}

func (x *GetTaskCostResponse) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *GetTaskCostResponse) GetTotalTokens() int64 {
	if x != nil {
		return x.TotalTokens
	}
	return 0
}

func (x *GetTaskCostResponse) GetCallCount() int32 {
	if x != nil {
		return x.CallCount
	}
	return 0
}

func (x *GetTaskCostResponse) GetItems() []*CostItem {
	if x != nil {
		return x.Items
	}
	return nil
}

type SubmitTaskRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	TenantId      string                 `protobuf:"bytes,2,opt,name=tenant_id,json=tenantId,proto3" json:"tenant_id,omitempty"`
	UserId        string                 `protobuf:"bytes,3,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	ClientTaskId  string                 `protobuf:"bytes,4,opt,name=client_task_id,json=clientTaskId,proto3" json:"client_task_id,omitempty"`
	Images        []*ImageAsset          `protobuf:"bytes,5,rep,name=images,proto3" json:"images,omitempty"`
	ReportDate    string                 `protobuf:"bytes,6,opt,name=report_date,json=reportDate,proto3" json:"report_date,omitempty"`
	Institution   string                 `protobuf:"bytes,7,opt,name=institution,proto3" json:"institution,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *SubmitTaskRequest) Reset() {
	*x = SubmitTaskRequest{}
	mi := &file_research_v1_research_proto_msgTypes[6]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *SubmitTaskRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*SubmitTaskRequest) ProtoMessage() {}

func (x *SubmitTaskRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[6]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*SubmitTaskRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{6}
}

func (x *SubmitTaskRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *SubmitTaskRequest) GetTenantId() string {
	if x != nil {
		return x.TenantId
	}
	return ""
}

func (x *SubmitTaskRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *SubmitTaskRequest) GetClientTaskId() string {
	if x != nil {
		return x.ClientTaskId
	}
	return ""
}

func (x *SubmitTaskRequest) GetImages() []*ImageAsset {
	if x != nil {
		return x.Images
	}
	return nil
}

func (x *SubmitTaskRequest) GetReportDate() string {
	if x != nil {
		return x.ReportDate
	}
	return ""
}

func (x *SubmitTaskRequest) GetInstitution() string {
	if x != nil {
		return x.Institution
	}
	return ""
}

type ImageAsset struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Key           string                 `protobuf:"bytes,1,opt,name=key,proto3" json:"key,omitempty"`
	Position      string                 `protobuf:"bytes,2,opt,name=position,proto3" json:"position,omitempty"`
	PresignedUrl  string                 `protobuf:"bytes,3,opt,name=presigned_url,json=presignedUrl,proto3" json:"presigned_url,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ImageAsset) Reset() {
	*x = ImageAsset{}
	mi := &file_research_v1_research_proto_msgTypes[7]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ImageAsset) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ImageAsset) ProtoMessage() {}

func (x *ImageAsset) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[7]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ImageAsset) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{7}
}

func (x *ImageAsset) GetKey() string {
	if x != nil {
		return x.Key
	}
	return ""
}

func (x *ImageAsset) GetPosition() string {
	if x != nil {
		return x.Position
	}
	return ""
}

func (x *ImageAsset) GetPresignedUrl() string {
	if x != nil {
		return x.PresignedUrl
	}
	return ""
}

type SubmitTaskResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	Status        string                 `protobuf:"bytes,2,opt,name=status,proto3" json:"status,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *SubmitTaskResponse) Reset() {
	*x = SubmitTaskResponse{}
	mi := &file_research_v1_research_proto_msgTypes[8]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *SubmitTaskResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*SubmitTaskResponse) ProtoMessage() {}

func (x *SubmitTaskResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[8]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*SubmitTaskResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{8}
}

func (x *SubmitTaskResponse) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *SubmitTaskResponse) GetStatus() string {
	if x != nil {
		return x.Status
	}
	return ""
}

type StreamTaskRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	TraceId       string                 `protobuf:"bytes,2,opt,name=trace_id,json=traceId,proto3" json:"trace_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *StreamTaskRequest) Reset() {
	*x = StreamTaskRequest{}
	mi := &file_research_v1_research_proto_msgTypes[9]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *StreamTaskRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*StreamTaskRequest) ProtoMessage() {}

func (x *StreamTaskRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[9]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*StreamTaskRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{9}
}

func (x *StreamTaskRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *StreamTaskRequest) GetTraceId() string {
	if x != nil {
		return x.TraceId
	}
	return ""
}

type TaskEvent struct {
	state   protoimpl.MessageState `protogen:"open.v1"`
	TaskId  string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	TraceId string                 `protobuf:"bytes,2,opt,name=trace_id,json=traceId,proto3" json:"trace_id,omitempty"`
	Seq     int64                  `protobuf:"varint,3,opt,name=seq,proto3" json:"seq,omitempty"`

	Payload       isTaskEvent_Payload `protobuf_oneof:"payload"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *TaskEvent) Reset() {
	*x = TaskEvent{}
	mi := &file_research_v1_research_proto_msgTypes[10]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *TaskEvent) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*TaskEvent) ProtoMessage() {}

func (x *TaskEvent) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[10]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*TaskEvent) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{10}
}

func (x *TaskEvent) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *TaskEvent) GetTraceId() string {
	if x != nil {
		return x.TraceId
	}
	return ""
}

func (x *TaskEvent) GetSeq() int64 {
	if x != nil {
		return x.Seq
	}
	return 0
}

func (x *TaskEvent) GetPayload() isTaskEvent_Payload {
	if x != nil {
		return x.Payload
	}
	return nil
}

func (x *TaskEvent) GetStageChange() *StageChange {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_StageChange); ok {
			return x.StageChange
		}
	}
	return nil
}

func (x *TaskEvent) GetObservation() *Observation {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_Observation); ok {
			return x.Observation
		}
	}
	return nil
}

func (x *TaskEvent) GetEvidenceFound() *EvidenceFound {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_EvidenceFound); ok {
			return x.EvidenceFound
		}
	}
	return nil
}

func (x *TaskEvent) GetReportDelta() *ReportDelta {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_ReportDelta); ok {
			return x.ReportDelta
		}
	}
	return nil
}

func (x *TaskEvent) GetMissingInfo() *MissingInfo {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_MissingInfo); ok {
			return x.MissingInfo
		}
	}
	return nil
}

func (x *TaskEvent) GetMemoryProposal() *MemoryProposal {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_MemoryProposal); ok {
			return x.MemoryProposal
		}
	}
	return nil
}

func (x *TaskEvent) GetResult() *TaskResult {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_Result); ok {
			return x.Result
		}
	}
	return nil
}

func (x *TaskEvent) GetError() *Error {
	if x != nil {
		if x, ok := x.Payload.(*TaskEvent_Error); ok {
			return x.Error
		}
	}
	return nil
}

type isTaskEvent_Payload interface {
	isTaskEvent_Payload()
}

type TaskEvent_StageChange struct {
	StageChange *StageChange `protobuf:"bytes,4,opt,name=stage_change,json=stageChange,proto3,oneof"`
}

type TaskEvent_Observation struct {
	Observation *Observation `protobuf:"bytes,5,opt,name=observation,proto3,oneof"`
}

type TaskEvent_EvidenceFound struct {
	EvidenceFound *EvidenceFound `protobuf:"bytes,6,opt,name=evidence_found,json=evidenceFound,proto3,oneof"`
}

type TaskEvent_ReportDelta struct {
	ReportDelta *ReportDelta `protobuf:"bytes,7,opt,name=report_delta,json=reportDelta,proto3,oneof"`
}

type TaskEvent_MissingInfo struct {
	MissingInfo *MissingInfo `protobuf:"bytes,8,opt,name=missing_info,json=missingInfo,proto3,oneof"`
}

type TaskEvent_MemoryProposal struct {
	MemoryProposal *MemoryProposal `protobuf:"bytes,9,opt,name=memory_proposal,json=memoryProposal,proto3,oneof"`
}

type TaskEvent_Result struct {
	Result *TaskResult `protobuf:"bytes,10,opt,name=result,proto3,oneof"`
}

type TaskEvent_Error struct {
	Error *Error `protobuf:"bytes,11,opt,name=error,proto3,oneof"`
}

func (*TaskEvent_StageChange) isTaskEvent_Payload() {}

func (*TaskEvent_Observation) isTaskEvent_Payload() {}

func (*TaskEvent_EvidenceFound) isTaskEvent_Payload() {}

func (*TaskEvent_ReportDelta) isTaskEvent_Payload() {}

func (*TaskEvent_MissingInfo) isTaskEvent_Payload() {}

func (*TaskEvent_MemoryProposal) isTaskEvent_Payload() {}

func (*TaskEvent_Result) isTaskEvent_Payload() {}

func (*TaskEvent_Error) isTaskEvent_Payload() {}

type StageChange struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Previous      string                 `protobuf:"bytes,1,opt,name=previous,proto3" json:"previous,omitempty"`
	To            string                 `protobuf:"bytes,2,opt,name=to,proto3" json:"to,omitempty"`
	Message       string                 `protobuf:"bytes,3,opt,name=message,proto3" json:"message,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *StageChange) Reset() {
	*x = StageChange{}
	mi := &file_research_v1_research_proto_msgTypes[11]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *StageChange) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*StageChange) ProtoMessage() {}

func (x *StageChange) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[11]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*StageChange) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{11}
}

func (x *StageChange) GetPrevious() string {
	if x != nil {
		return x.Previous
	}
	return ""
}

func (x *StageChange) GetTo() string {
	if x != nil {
		return x.To
	}
	return ""
}

func (x *StageChange) GetMessage() string {
	if x != nil {
		return x.Message
	}
	return ""
}

type Observation struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	ImageKey      string                 `protobuf:"bytes,1,opt,name=image_key,json=imageKey,proto3" json:"image_key,omitempty"`
	Region        string                 `protobuf:"bytes,2,opt,name=region,proto3" json:"region,omitempty"`
	Text          string                 `protobuf:"bytes,3,opt,name=text,proto3" json:"text,omitempty"`
	Confidence    float32                `protobuf:"fixed32,4,opt,name=confidence,proto3" json:"confidence,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *Observation) Reset() {
	*x = Observation{}
	mi := &file_research_v1_research_proto_msgTypes[12]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *Observation) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*Observation) ProtoMessage() {}

func (x *Observation) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[12]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*Observation) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{12}
}

func (x *Observation) GetImageKey() string {
	if x != nil {
		return x.ImageKey
	}
	return ""
}

func (x *Observation) GetRegion() string {
	if x != nil {
		return x.Region
	}
	return ""
}

func (x *Observation) GetText() string {
	if x != nil {
		return x.Text
	}
	return ""
}

func (x *Observation) GetConfidence() float32 {
	if x != nil {
		return x.Confidence
	}
	return 0
}

type EvidenceFound struct {
	state            protoimpl.MessageState `protogen:"open.v1"`
	EvidenceId       string                 `protobuf:"bytes,1,opt,name=evidence_id,json=evidenceId,proto3" json:"evidence_id,omitempty"`
	SourceName       string                 `protobuf:"bytes,2,opt,name=source_name,json=sourceName,proto3" json:"source_name,omitempty"`
	SourceLevel      int32                  `protobuf:"varint,3,opt,name=source_level,json=sourceLevel,proto3" json:"source_level,omitempty"`
	Quote            string                 `protobuf:"bytes,4,opt,name=quote,proto3" json:"quote,omitempty"`
	Page             int32                  `protobuf:"varint,5,opt,name=page,proto3" json:"page,omitempty"`
	KnowledgeVersion string                 `protobuf:"bytes,6,opt,name=knowledge_version,json=knowledgeVersion,proto3" json:"knowledge_version,omitempty"`
	SourceUrl        string                 `protobuf:"bytes,7,opt,name=source_url,json=sourceUrl,proto3" json:"source_url,omitempty"`
	unknownFields    protoimpl.UnknownFields
	sizeCache        protoimpl.SizeCache
}

func (x *EvidenceFound) Reset() {
	*x = EvidenceFound{}
	mi := &file_research_v1_research_proto_msgTypes[13]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *EvidenceFound) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*EvidenceFound) ProtoMessage() {}

func (x *EvidenceFound) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[13]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*EvidenceFound) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{13}
}

func (x *EvidenceFound) GetEvidenceId() string {
	if x != nil {
		return x.EvidenceId
	}
	return ""
}

func (x *EvidenceFound) GetSourceName() string {
	if x != nil {
		return x.SourceName
	}
	return ""
}

func (x *EvidenceFound) GetSourceLevel() int32 {
	if x != nil {
		return x.SourceLevel
	}
	return 0
}

func (x *EvidenceFound) GetQuote() string {
	if x != nil {
		return x.Quote
	}
	return ""
}

func (x *EvidenceFound) GetPage() int32 {
	if x != nil {
		return x.Page
	}
	return 0
}

func (x *EvidenceFound) GetKnowledgeVersion() string {
	if x != nil {
		return x.KnowledgeVersion
	}
	return ""
}

func (x *EvidenceFound) GetSourceUrl() string {
	if x != nil {
		return x.SourceUrl
	}
	return ""
}

type ReportDelta struct {
	state   protoimpl.MessageState `protogen:"open.v1"`
	Section string                 `protobuf:"bytes,1,opt,name=section,proto3" json:"section,omitempty"`

	Content       string             `protobuf:"bytes,2,opt,name=content,proto3" json:"content,omitempty"`
	Metrics       []*MetricItem      `protobuf:"bytes,3,rep,name=metrics,proto3" json:"metrics,omitempty"`
	MetricTrends  []*MetricTrendItem `protobuf:"bytes,4,rep,name=metric_trends,json=metricTrends,proto3" json:"metric_trends,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ReportDelta) Reset() {
	*x = ReportDelta{}
	mi := &file_research_v1_research_proto_msgTypes[14]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ReportDelta) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ReportDelta) ProtoMessage() {}

func (x *ReportDelta) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[14]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ReportDelta) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{14}
}

func (x *ReportDelta) GetSection() string {
	if x != nil {
		return x.Section
	}
	return ""
}

func (x *ReportDelta) GetContent() string {
	if x != nil {
		return x.Content
	}
	return ""
}

func (x *ReportDelta) GetMetrics() []*MetricItem {
	if x != nil {
		return x.Metrics
	}
	return nil
}

func (x *ReportDelta) GetMetricTrends() []*MetricTrendItem {
	if x != nil {
		return x.MetricTrends
	}
	return nil
}

type MetricItem struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	MetricCode    string                 `protobuf:"bytes,1,opt,name=metric_code,json=metricCode,proto3" json:"metric_code,omitempty"`
	MetricName    string                 `protobuf:"bytes,2,opt,name=metric_name,json=metricName,proto3" json:"metric_name,omitempty"`
	Category      string                 `protobuf:"bytes,3,opt,name=category,proto3" json:"category,omitempty"`
	ValueNum      float64                `protobuf:"fixed64,4,opt,name=value_num,json=valueNum,proto3" json:"value_num,omitempty"`
	ValueText     string                 `protobuf:"bytes,5,opt,name=value_text,json=valueText,proto3" json:"value_text,omitempty"`
	Unit          string                 `protobuf:"bytes,6,opt,name=unit,proto3" json:"unit,omitempty"`
	RefLow        float64                `protobuf:"fixed64,7,opt,name=ref_low,json=refLow,proto3" json:"ref_low,omitempty"`
	RefHigh       float64                `protobuf:"fixed64,8,opt,name=ref_high,json=refHigh,proto3" json:"ref_high,omitempty"`
	RefText       string                 `protobuf:"bytes,9,opt,name=ref_text,json=refText,proto3" json:"ref_text,omitempty"`
	Flag          string                 `protobuf:"bytes,10,opt,name=flag,proto3" json:"flag,omitempty"`
	MeasuredAt    string                 `protobuf:"bytes,11,opt,name=measured_at,json=measuredAt,proto3" json:"measured_at,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MetricItem) Reset() {
	*x = MetricItem{}
	mi := &file_research_v1_research_proto_msgTypes[15]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MetricItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MetricItem) ProtoMessage() {}

func (x *MetricItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[15]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MetricItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{15}
}

func (x *MetricItem) GetMetricCode() string {
	if x != nil {
		return x.MetricCode
	}
	return ""
}

func (x *MetricItem) GetMetricName() string {
	if x != nil {
		return x.MetricName
	}
	return ""
}

func (x *MetricItem) GetCategory() string {
	if x != nil {
		return x.Category
	}
	return ""
}

func (x *MetricItem) GetValueNum() float64 {
	if x != nil {
		return x.ValueNum
	}
	return 0
}

func (x *MetricItem) GetValueText() string {
	if x != nil {
		return x.ValueText
	}
	return ""
}

func (x *MetricItem) GetUnit() string {
	if x != nil {
		return x.Unit
	}
	return ""
}

func (x *MetricItem) GetRefLow() float64 {
	if x != nil {
		return x.RefLow
	}
	return 0
}

func (x *MetricItem) GetRefHigh() float64 {
	if x != nil {
		return x.RefHigh
	}
	return 0
}

func (x *MetricItem) GetRefText() string {
	if x != nil {
		return x.RefText
	}
	return ""
}

func (x *MetricItem) GetFlag() string {
	if x != nil {
		return x.Flag
	}
	return ""
}

func (x *MetricItem) GetMeasuredAt() string {
	if x != nil {
		return x.MeasuredAt
	}
	return ""
}

type MetricPoint struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Date          string                 `protobuf:"bytes,1,opt,name=date,proto3" json:"date,omitempty"`
	Value         float64                `protobuf:"fixed64,2,opt,name=value,proto3" json:"value,omitempty"`
	Flag          string                 `protobuf:"bytes,3,opt,name=flag,proto3" json:"flag,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MetricPoint) Reset() {
	*x = MetricPoint{}
	mi := &file_research_v1_research_proto_msgTypes[16]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MetricPoint) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MetricPoint) ProtoMessage() {}

func (x *MetricPoint) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[16]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MetricPoint) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{16}
}

func (x *MetricPoint) GetDate() string {
	if x != nil {
		return x.Date
	}
	return ""
}

func (x *MetricPoint) GetValue() float64 {
	if x != nil {
		return x.Value
	}
	return 0
}

func (x *MetricPoint) GetFlag() string {
	if x != nil {
		return x.Flag
	}
	return ""
}

type MetricTrendItem struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	MetricCode    string                 `protobuf:"bytes,1,opt,name=metric_code,json=metricCode,proto3" json:"metric_code,omitempty"`
	MetricName    string                 `protobuf:"bytes,2,opt,name=metric_name,json=metricName,proto3" json:"metric_name,omitempty"`
	Unit          string                 `protobuf:"bytes,3,opt,name=unit,proto3" json:"unit,omitempty"`
	Points        []*MetricPoint         `protobuf:"bytes,4,rep,name=points,proto3" json:"points,omitempty"`
	FirstValue    float64                `protobuf:"fixed64,5,opt,name=first_value,json=firstValue,proto3" json:"first_value,omitempty"`
	LastValue     float64                `protobuf:"fixed64,6,opt,name=last_value,json=lastValue,proto3" json:"last_value,omitempty"`
	Delta         float64                `protobuf:"fixed64,7,opt,name=delta,proto3" json:"delta,omitempty"`
	Direction     string                 `protobuf:"bytes,8,opt,name=direction,proto3" json:"direction,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MetricTrendItem) Reset() {
	*x = MetricTrendItem{}
	mi := &file_research_v1_research_proto_msgTypes[17]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MetricTrendItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MetricTrendItem) ProtoMessage() {}

func (x *MetricTrendItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[17]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MetricTrendItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{17}
}

func (x *MetricTrendItem) GetMetricCode() string {
	if x != nil {
		return x.MetricCode
	}
	return ""
}

func (x *MetricTrendItem) GetMetricName() string {
	if x != nil {
		return x.MetricName
	}
	return ""
}

func (x *MetricTrendItem) GetUnit() string {
	if x != nil {
		return x.Unit
	}
	return ""
}

func (x *MetricTrendItem) GetPoints() []*MetricPoint {
	if x != nil {
		return x.Points
	}
	return nil
}

func (x *MetricTrendItem) GetFirstValue() float64 {
	if x != nil {
		return x.FirstValue
	}
	return 0
}

func (x *MetricTrendItem) GetLastValue() float64 {
	if x != nil {
		return x.LastValue
	}
	return 0
}

func (x *MetricTrendItem) GetDelta() float64 {
	if x != nil {
		return x.Delta
	}
	return 0
}

func (x *MetricTrendItem) GetDirection() string {
	if x != nil {
		return x.Direction
	}
	return ""
}

type MissingInfo struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Items         []string               `protobuf:"bytes,1,rep,name=items,proto3" json:"items,omitempty"`
	Guidance      string                 `protobuf:"bytes,2,opt,name=guidance,proto3" json:"guidance,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MissingInfo) Reset() {
	*x = MissingInfo{}
	mi := &file_research_v1_research_proto_msgTypes[18]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MissingInfo) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MissingInfo) ProtoMessage() {}

func (x *MissingInfo) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[18]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MissingInfo) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{18}
}

func (x *MissingInfo) GetItems() []string {
	if x != nil {
		return x.Items
	}
	return nil
}

func (x *MissingInfo) GetGuidance() string {
	if x != nil {
		return x.Guidance
	}
	return ""
}

type MemoryProposal struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	CandidateId   string                 `protobuf:"bytes,1,opt,name=candidate_id,json=candidateId,proto3" json:"candidate_id,omitempty"`
	Kind          string                 `protobuf:"bytes,2,opt,name=kind,proto3" json:"kind,omitempty"`
	Content       string                 `protobuf:"bytes,3,opt,name=content,proto3" json:"content,omitempty"`
	Source        string                 `protobuf:"bytes,4,opt,name=source,proto3" json:"source,omitempty"`
	Confidence    float32                `protobuf:"fixed32,5,opt,name=confidence,proto3" json:"confidence,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MemoryProposal) Reset() {
	*x = MemoryProposal{}
	mi := &file_research_v1_research_proto_msgTypes[19]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MemoryProposal) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MemoryProposal) ProtoMessage() {}

func (x *MemoryProposal) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[19]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MemoryProposal) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{19}
}

func (x *MemoryProposal) GetCandidateId() string {
	if x != nil {
		return x.CandidateId
	}
	return ""
}

func (x *MemoryProposal) GetKind() string {
	if x != nil {
		return x.Kind
	}
	return ""
}

func (x *MemoryProposal) GetContent() string {
	if x != nil {
		return x.Content
	}
	return ""
}

func (x *MemoryProposal) GetSource() string {
	if x != nil {
		return x.Source
	}
	return ""
}

func (x *MemoryProposal) GetConfidence() float32 {
	if x != nil {
		return x.Confidence
	}
	return 0
}

type TaskResult struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	ReportVersion string                 `protobuf:"bytes,1,opt,name=report_version,json=reportVersion,proto3" json:"report_version,omitempty"`
	Status        string                 `protobuf:"bytes,2,opt,name=status,proto3" json:"status,omitempty"`
	Reason        string                 `protobuf:"bytes,3,opt,name=reason,proto3" json:"reason,omitempty"`
	Metrics       []*MetricItem          `protobuf:"bytes,4,rep,name=metrics,proto3" json:"metrics,omitempty"`
	MetricTrends  []*MetricTrendItem     `protobuf:"bytes,5,rep,name=metric_trends,json=metricTrends,proto3" json:"metric_trends,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *TaskResult) Reset() {
	*x = TaskResult{}
	mi := &file_research_v1_research_proto_msgTypes[20]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *TaskResult) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*TaskResult) ProtoMessage() {}

func (x *TaskResult) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[20]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*TaskResult) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{20}
}

func (x *TaskResult) GetReportVersion() string {
	if x != nil {
		return x.ReportVersion
	}
	return ""
}

func (x *TaskResult) GetStatus() string {
	if x != nil {
		return x.Status
	}
	return ""
}

func (x *TaskResult) GetReason() string {
	if x != nil {
		return x.Reason
	}
	return ""
}

func (x *TaskResult) GetMetrics() []*MetricItem {
	if x != nil {
		return x.Metrics
	}
	return nil
}

func (x *TaskResult) GetMetricTrends() []*MetricTrendItem {
	if x != nil {
		return x.MetricTrends
	}
	return nil
}

type Error struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	ErrorCode     string                 `protobuf:"bytes,1,opt,name=error_code,json=errorCode,proto3" json:"error_code,omitempty"`
	Message       string                 `protobuf:"bytes,2,opt,name=message,proto3" json:"message,omitempty"`
	Retryable     bool                   `protobuf:"varint,3,opt,name=retryable,proto3" json:"retryable,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *Error) Reset() {
	*x = Error{}
	mi := &file_research_v1_research_proto_msgTypes[21]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *Error) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*Error) ProtoMessage() {}

func (x *Error) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[21]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*Error) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{21}
}

func (x *Error) GetErrorCode() string {
	if x != nil {
		return x.ErrorCode
	}
	return ""
}

func (x *Error) GetMessage() string {
	if x != nil {
		return x.Message
	}
	return ""
}

func (x *Error) GetRetryable() bool {
	if x != nil {
		return x.Retryable
	}
	return false
}

type ResumeTaskRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	TraceId       string                 `protobuf:"bytes,2,opt,name=trace_id,json=traceId,proto3" json:"trace_id,omitempty"`
	Action        string                 `protobuf:"bytes,3,opt,name=action,proto3" json:"action,omitempty"`
	NewImages     []*ImageAsset          `protobuf:"bytes,4,rep,name=new_images,json=newImages,proto3" json:"new_images,omitempty"`
	CandidateId   string                 `protobuf:"bytes,5,opt,name=candidate_id,json=candidateId,proto3" json:"candidate_id,omitempty"`
	Confirmed     bool                   `protobuf:"varint,6,opt,name=confirmed,proto3" json:"confirmed,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ResumeTaskRequest) Reset() {
	*x = ResumeTaskRequest{}
	mi := &file_research_v1_research_proto_msgTypes[22]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ResumeTaskRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ResumeTaskRequest) ProtoMessage() {}

func (x *ResumeTaskRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[22]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ResumeTaskRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{22}
}

func (x *ResumeTaskRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *ResumeTaskRequest) GetTraceId() string {
	if x != nil {
		return x.TraceId
	}
	return ""
}

func (x *ResumeTaskRequest) GetAction() string {
	if x != nil {
		return x.Action
	}
	return ""
}

func (x *ResumeTaskRequest) GetNewImages() []*ImageAsset {
	if x != nil {
		return x.NewImages
	}
	return nil
}

func (x *ResumeTaskRequest) GetCandidateId() string {
	if x != nil {
		return x.CandidateId
	}
	return ""
}

func (x *ResumeTaskRequest) GetConfirmed() bool {
	if x != nil {
		return x.Confirmed
	}
	return false
}

type ResumeTaskResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	Status        string                 `protobuf:"bytes,2,opt,name=status,proto3" json:"status,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ResumeTaskResponse) Reset() {
	*x = ResumeTaskResponse{}
	mi := &file_research_v1_research_proto_msgTypes[23]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ResumeTaskResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ResumeTaskResponse) ProtoMessage() {}

func (x *ResumeTaskResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[23]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ResumeTaskResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{23}
}

func (x *ResumeTaskResponse) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *ResumeTaskResponse) GetStatus() string {
	if x != nil {
		return x.Status
	}
	return ""
}

type CancelTaskRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	Reason        string                 `protobuf:"bytes,2,opt,name=reason,proto3" json:"reason,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *CancelTaskRequest) Reset() {
	*x = CancelTaskRequest{}
	mi := &file_research_v1_research_proto_msgTypes[24]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *CancelTaskRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CancelTaskRequest) ProtoMessage() {}

func (x *CancelTaskRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[24]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*CancelTaskRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{24}
}

func (x *CancelTaskRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *CancelTaskRequest) GetReason() string {
	if x != nil {
		return x.Reason
	}
	return ""
}

type CancelTaskResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	TaskId        string                 `protobuf:"bytes,1,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
	Status        string                 `protobuf:"bytes,2,opt,name=status,proto3" json:"status,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *CancelTaskResponse) Reset() {
	*x = CancelTaskResponse{}
	mi := &file_research_v1_research_proto_msgTypes[25]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *CancelTaskResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CancelTaskResponse) ProtoMessage() {}

func (x *CancelTaskResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[25]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*CancelTaskResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{25}
}

func (x *CancelTaskResponse) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

func (x *CancelTaskResponse) GetStatus() string {
	if x != nil {
		return x.Status
	}
	return ""
}

type MemoryItem struct {
	state               protoimpl.MessageState `protogen:"open.v1"`
	Id                  string                 `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
	Kind                string                 `protobuf:"bytes,2,opt,name=kind,proto3" json:"kind,omitempty"`
	Content             string                 `protobuf:"bytes,3,opt,name=content,proto3" json:"content,omitempty"`
	MetricCodes         []string               `protobuf:"bytes,4,rep,name=metric_codes,json=metricCodes,proto3" json:"metric_codes,omitempty"`
	Source              string                 `protobuf:"bytes,5,opt,name=source,proto3" json:"source,omitempty"`
	Confidence          float32                `protobuf:"fixed32,6,opt,name=confidence,proto3" json:"confidence,omitempty"`
	Version             int32                  `protobuf:"varint,7,opt,name=version,proto3" json:"version,omitempty"`
	PendingConfirmation bool                   `protobuf:"varint,8,opt,name=pending_confirmation,json=pendingConfirmation,proto3" json:"pending_confirmation,omitempty"`
	CreatedAt           string                 `protobuf:"bytes,9,opt,name=created_at,json=createdAt,proto3" json:"created_at,omitempty"`
	unknownFields       protoimpl.UnknownFields
	sizeCache           protoimpl.SizeCache
}

func (x *MemoryItem) Reset() {
	*x = MemoryItem{}
	mi := &file_research_v1_research_proto_msgTypes[26]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MemoryItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MemoryItem) ProtoMessage() {}

func (x *MemoryItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[26]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MemoryItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{26}
}

func (x *MemoryItem) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

func (x *MemoryItem) GetKind() string {
	if x != nil {
		return x.Kind
	}
	return ""
}

func (x *MemoryItem) GetContent() string {
	if x != nil {
		return x.Content
	}
	return ""
}

func (x *MemoryItem) GetMetricCodes() []string {
	if x != nil {
		return x.MetricCodes
	}
	return nil
}

func (x *MemoryItem) GetSource() string {
	if x != nil {
		return x.Source
	}
	return ""
}

func (x *MemoryItem) GetConfidence() float32 {
	if x != nil {
		return x.Confidence
	}
	return 0
}

func (x *MemoryItem) GetVersion() int32 {
	if x != nil {
		return x.Version
	}
	return 0
}

func (x *MemoryItem) GetPendingConfirmation() bool {
	if x != nil {
		return x.PendingConfirmation
	}
	return false
}

func (x *MemoryItem) GetCreatedAt() string {
	if x != nil {
		return x.CreatedAt
	}
	return ""
}

type ListMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ListMemoryRequest) Reset() {
	*x = ListMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[27]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ListMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListMemoryRequest) ProtoMessage() {}

func (x *ListMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[27]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ListMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{27}
}

func (x *ListMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

type ListMemoryResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Items         []*MemoryItem          `protobuf:"bytes,1,rep,name=items,proto3" json:"items,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ListMemoryResponse) Reset() {
	*x = ListMemoryResponse{}
	mi := &file_research_v1_research_proto_msgTypes[28]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ListMemoryResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListMemoryResponse) ProtoMessage() {}

func (x *ListMemoryResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[28]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ListMemoryResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{28}
}

func (x *ListMemoryResponse) GetItems() []*MemoryItem {
	if x != nil {
		return x.Items
	}
	return nil
}

type CreateMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	Kind          string                 `protobuf:"bytes,2,opt,name=kind,proto3" json:"kind,omitempty"`
	Content       string                 `protobuf:"bytes,3,opt,name=content,proto3" json:"content,omitempty"`
	MetricCodes   []string               `protobuf:"bytes,4,rep,name=metric_codes,json=metricCodes,proto3" json:"metric_codes,omitempty"`
	Source        string                 `protobuf:"bytes,5,opt,name=source,proto3" json:"source,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *CreateMemoryRequest) Reset() {
	*x = CreateMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[29]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *CreateMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CreateMemoryRequest) ProtoMessage() {}

func (x *CreateMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[29]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*CreateMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{29}
}

func (x *CreateMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *CreateMemoryRequest) GetKind() string {
	if x != nil {
		return x.Kind
	}
	return ""
}

func (x *CreateMemoryRequest) GetContent() string {
	if x != nil {
		return x.Content
	}
	return ""
}

func (x *CreateMemoryRequest) GetMetricCodes() []string {
	if x != nil {
		return x.MetricCodes
	}
	return nil
}

func (x *CreateMemoryRequest) GetSource() string {
	if x != nil {
		return x.Source
	}
	return ""
}

type UpdateMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	EntryId       string                 `protobuf:"bytes,2,opt,name=entry_id,json=entryId,proto3" json:"entry_id,omitempty"`
	NewContent    string                 `protobuf:"bytes,3,opt,name=new_content,json=newContent,proto3" json:"new_content,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *UpdateMemoryRequest) Reset() {
	*x = UpdateMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[30]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *UpdateMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*UpdateMemoryRequest) ProtoMessage() {}

func (x *UpdateMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[30]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*UpdateMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{30}
}

func (x *UpdateMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *UpdateMemoryRequest) GetEntryId() string {
	if x != nil {
		return x.EntryId
	}
	return ""
}

func (x *UpdateMemoryRequest) GetNewContent() string {
	if x != nil {
		return x.NewContent
	}
	return ""
}

type DeleteMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	EntryId       string                 `protobuf:"bytes,2,opt,name=entry_id,json=entryId,proto3" json:"entry_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *DeleteMemoryRequest) Reset() {
	*x = DeleteMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[31]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *DeleteMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*DeleteMemoryRequest) ProtoMessage() {}

func (x *DeleteMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[31]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*DeleteMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{31}
}

func (x *DeleteMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *DeleteMemoryRequest) GetEntryId() string {
	if x != nil {
		return x.EntryId
	}
	return ""
}

type DeleteAllMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *DeleteAllMemoryRequest) Reset() {
	*x = DeleteAllMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[32]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *DeleteAllMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*DeleteAllMemoryRequest) ProtoMessage() {}

func (x *DeleteAllMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[32]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*DeleteAllMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{32}
}

func (x *DeleteAllMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

type DeleteMemoryResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Ok            bool                   `protobuf:"varint,1,opt,name=ok,proto3" json:"ok,omitempty"`
	DeletedCount  int32                  `protobuf:"varint,2,opt,name=deleted_count,json=deletedCount,proto3" json:"deleted_count,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *DeleteMemoryResponse) Reset() {
	*x = DeleteMemoryResponse{}
	mi := &file_research_v1_research_proto_msgTypes[33]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *DeleteMemoryResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*DeleteMemoryResponse) ProtoMessage() {}

func (x *DeleteMemoryResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[33]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*DeleteMemoryResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{33}
}

func (x *DeleteMemoryResponse) GetOk() bool {
	if x != nil {
		return x.Ok
	}
	return false
}

func (x *DeleteMemoryResponse) GetDeletedCount() int32 {
	if x != nil {
		return x.DeletedCount
	}
	return 0
}

type ConfirmMemoryRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	EntryId       string                 `protobuf:"bytes,2,opt,name=entry_id,json=entryId,proto3" json:"entry_id,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ConfirmMemoryRequest) Reset() {
	*x = ConfirmMemoryRequest{}
	mi := &file_research_v1_research_proto_msgTypes[34]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ConfirmMemoryRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ConfirmMemoryRequest) ProtoMessage() {}

func (x *ConfirmMemoryRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[34]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ConfirmMemoryRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{34}
}

func (x *ConfirmMemoryRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *ConfirmMemoryRequest) GetEntryId() string {
	if x != nil {
		return x.EntryId
	}
	return ""
}

type ListMemoryAuditRequest struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	UserId        string                 `protobuf:"bytes,1,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	Limit         int32                  `protobuf:"varint,2,opt,name=limit,proto3" json:"limit,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ListMemoryAuditRequest) Reset() {
	*x = ListMemoryAuditRequest{}
	mi := &file_research_v1_research_proto_msgTypes[35]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ListMemoryAuditRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListMemoryAuditRequest) ProtoMessage() {}

func (x *ListMemoryAuditRequest) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[35]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ListMemoryAuditRequest) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{35}
}

func (x *ListMemoryAuditRequest) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *ListMemoryAuditRequest) GetLimit() int32 {
	if x != nil {
		return x.Limit
	}
	return 0
}

type MemoryAuditItem struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Id            string                 `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
	UserId        string                 `protobuf:"bytes,2,opt,name=user_id,json=userId,proto3" json:"user_id,omitempty"`
	Action        string                 `protobuf:"bytes,3,opt,name=action,proto3" json:"action,omitempty"`
	TargetId      string                 `protobuf:"bytes,4,opt,name=target_id,json=targetId,proto3" json:"target_id,omitempty"`
	Detail        string                 `protobuf:"bytes,5,opt,name=detail,proto3" json:"detail,omitempty"`
	CreatedAt     string                 `protobuf:"bytes,6,opt,name=created_at,json=createdAt,proto3" json:"created_at,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *MemoryAuditItem) Reset() {
	*x = MemoryAuditItem{}
	mi := &file_research_v1_research_proto_msgTypes[36]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *MemoryAuditItem) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*MemoryAuditItem) ProtoMessage() {}

func (x *MemoryAuditItem) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[36]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*MemoryAuditItem) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{36}
}

func (x *MemoryAuditItem) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

func (x *MemoryAuditItem) GetUserId() string {
	if x != nil {
		return x.UserId
	}
	return ""
}

func (x *MemoryAuditItem) GetAction() string {
	if x != nil {
		return x.Action
	}
	return ""
}

func (x *MemoryAuditItem) GetTargetId() string {
	if x != nil {
		return x.TargetId
	}
	return ""
}

func (x *MemoryAuditItem) GetDetail() string {
	if x != nil {
		return x.Detail
	}
	return ""
}

func (x *MemoryAuditItem) GetCreatedAt() string {
	if x != nil {
		return x.CreatedAt
	}
	return ""
}

type ListMemoryAuditResponse struct {
	state         protoimpl.MessageState `protogen:"open.v1"`
	Items         []*MemoryAuditItem     `protobuf:"bytes,1,rep,name=items,proto3" json:"items,omitempty"`
	unknownFields protoimpl.UnknownFields
	sizeCache     protoimpl.SizeCache
}

func (x *ListMemoryAuditResponse) Reset() {
	*x = ListMemoryAuditResponse{}
	mi := &file_research_v1_research_proto_msgTypes[37]
	ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
	ms.StoreMessageInfo(mi)
}

func (x *ListMemoryAuditResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListMemoryAuditResponse) ProtoMessage() {}

func (x *ListMemoryAuditResponse) ProtoReflect() protoreflect.Message {
	mi := &file_research_v1_research_proto_msgTypes[37]
	if x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

func (*ListMemoryAuditResponse) Descriptor() ([]byte, []int) {
	return file_research_v1_research_proto_rawDescGZIP(), []int{37}
}

func (x *ListMemoryAuditResponse) GetItems() []*MemoryAuditItem {
	if x != nil {
		return x.Items
	}
	return nil
}

var File_research_v1_research_proto protoreflect.FileDescriptor

const file_research_v1_research_proto_rawDesc = "" +
	"\n" +
	"\x1aresearch/v1/research.proto\x12\vresearch.v1\"?\n" +
	"\x0fChatHistoryItem\x12\x12\n" +
	"\x04role\x18\x01 \x01(\tR\x04role\x12\x18\n" +
	"\acontent\x18\x02 \x01(\tR\acontent\"\x8f\x01\n" +
	"\vChatRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x14\n" +
	"\x05query\x18\x02 \x01(\tR\x05query\x12\x19\n" +
	"\btrace_id\x18\x03 \x01(\tR\atraceId\x126\n" +
	"\ahistory\x18\x04 \x03(\v2\x1c.research.v1.ChatHistoryItemR\ahistory\"x\n" +
	"\fChatResponse\x12\x18\n" +
	"\arefused\x18\x01 \x01(\bR\arefused\x12\x16\n" +
	"\x06answer\x18\x02 \x01(\tR\x06answer\x126\n" +
	"\bevidence\x18\x03 \x03(\v2\x1a.research.v1.EvidenceFoundR\bevidence\"F\n" +
	"\x12GetTaskCostRequest\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x17\n" +
	"\auser_id\x18\x02 \x01(\tR\x06userId\"\xe3\x01\n" +
	"\bCostItem\x12\x1b\n" +
	"\tcall_type\x18\x01 \x01(\tR\bcallType\x12\x14\n" +
	"\x05model\x18\x02 \x01(\tR\x05model\x12\x14\n" +
	"\x05calls\x18\x03 \x01(\x05R\x05calls\x12\x16\n" +
	"\x06tokens\x18\x04 \x01(\x03R\x06tokens\x12#\n" +
	"\rprompt_tokens\x18\x05 \x01(\x03R\fpromptTokens\x12+\n" +
	"\x11completion_tokens\x18\x06 \x01(\x03R\x10completionTokens\x12$\n" +
	"\x0eavg_latency_ms\x18\a \x01(\x05R\favgLatencyMs\"\x9d\x01\n" +
	"\x13GetTaskCostResponse\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12!\n" +
	"\ftotal_tokens\x18\x02 \x01(\x03R\vtotalTokens\x12\x1d\n" +
	"\n" +
	"call_count\x18\x03 \x01(\x05R\tcallCount\x12+\n" +
	"\x05items\x18\x04 \x03(\v2\x15.research.v1.CostItemR\x05items\"\xfc\x01\n" +
	"\x11SubmitTaskRequest\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x1b\n" +
	"\ttenant_id\x18\x02 \x01(\tR\btenantId\x12\x17\n" +
	"\auser_id\x18\x03 \x01(\tR\x06userId\x12$\n" +
	"\x0eclient_task_id\x18\x04 \x01(\tR\fclientTaskId\x12/\n" +
	"\x06images\x18\x05 \x03(\v2\x17.research.v1.ImageAssetR\x06images\x12\x1f\n" +
	"\vreport_date\x18\x06 \x01(\tR\n" +
	"reportDate\x12 \n" +
	"\vinstitution\x18\a \x01(\tR\vinstitution\"_\n" +
	"\n" +
	"ImageAsset\x12\x10\n" +
	"\x03key\x18\x01 \x01(\tR\x03key\x12\x1a\n" +
	"\bposition\x18\x02 \x01(\tR\bposition\x12#\n" +
	"\rpresigned_url\x18\x03 \x01(\tR\fpresignedUrl\"E\n" +
	"\x12SubmitTaskResponse\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x16\n" +
	"\x06status\x18\x02 \x01(\tR\x06status\"G\n" +
	"\x11StreamTaskRequest\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x19\n" +
	"\btrace_id\x18\x02 \x01(\tR\atraceId\"\xc3\x04\n" +
	"\tTaskEvent\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x19\n" +
	"\btrace_id\x18\x02 \x01(\tR\atraceId\x12\x10\n" +
	"\x03seq\x18\x03 \x01(\x03R\x03seq\x12=\n" +
	"\fstage_change\x18\x04 \x01(\v2\x18.research.v1.StageChangeH\x00R\vstageChange\x12<\n" +
	"\vobservation\x18\x05 \x01(\v2\x18.research.v1.ObservationH\x00R\vobservation\x12C\n" +
	"\x0eevidence_found\x18\x06 \x01(\v2\x1a.research.v1.EvidenceFoundH\x00R\revidenceFound\x12=\n" +
	"\freport_delta\x18\a \x01(\v2\x18.research.v1.ReportDeltaH\x00R\vreportDelta\x12=\n" +
	"\fmissing_info\x18\b \x01(\v2\x18.research.v1.MissingInfoH\x00R\vmissingInfo\x12F\n" +
	"\x0fmemory_proposal\x18\t \x01(\v2\x1b.research.v1.MemoryProposalH\x00R\x0ememoryProposal\x121\n" +
	"\x06result\x18\n" +
	" \x01(\v2\x17.research.v1.TaskResultH\x00R\x06result\x12*\n" +
	"\x05error\x18\v \x01(\v2\x12.research.v1.ErrorH\x00R\x05errorB\t\n" +
	"\apayload\"S\n" +
	"\vStageChange\x12\x1a\n" +
	"\bprevious\x18\x01 \x01(\tR\bprevious\x12\x0e\n" +
	"\x02to\x18\x02 \x01(\tR\x02to\x12\x18\n" +
	"\amessage\x18\x03 \x01(\tR\amessage\"v\n" +
	"\vObservation\x12\x1b\n" +
	"\timage_key\x18\x01 \x01(\tR\bimageKey\x12\x16\n" +
	"\x06region\x18\x02 \x01(\tR\x06region\x12\x12\n" +
	"\x04text\x18\x03 \x01(\tR\x04text\x12\x1e\n" +
	"\n" +
	"confidence\x18\x04 \x01(\x02R\n" +
	"confidence\"\xea\x01\n" +
	"\rEvidenceFound\x12\x1f\n" +
	"\vevidence_id\x18\x01 \x01(\tR\n" +
	"evidenceId\x12\x1f\n" +
	"\vsource_name\x18\x02 \x01(\tR\n" +
	"sourceName\x12!\n" +
	"\fsource_level\x18\x03 \x01(\x05R\vsourceLevel\x12\x14\n" +
	"\x05quote\x18\x04 \x01(\tR\x05quote\x12\x12\n" +
	"\x04page\x18\x05 \x01(\x05R\x04page\x12+\n" +
	"\x11knowledge_version\x18\x06 \x01(\tR\x10knowledgeVersion\x12\x1d\n" +
	"\n" +
	"source_url\x18\a \x01(\tR\tsourceUrl\"\xb7\x01\n" +
	"\vReportDelta\x12\x18\n" +
	"\asection\x18\x01 \x01(\tR\asection\x12\x18\n" +
	"\acontent\x18\x02 \x01(\tR\acontent\x121\n" +
	"\ametrics\x18\x03 \x03(\v2\x17.research.v1.MetricItemR\ametrics\x12A\n" +
	"\rmetric_trends\x18\x04 \x03(\v2\x1c.research.v1.MetricTrendItemR\fmetricTrends\"\xbe\x02\n" +
	"\n" +
	"MetricItem\x12\x1f\n" +
	"\vmetric_code\x18\x01 \x01(\tR\n" +
	"metricCode\x12\x1f\n" +
	"\vmetric_name\x18\x02 \x01(\tR\n" +
	"metricName\x12\x1a\n" +
	"\bcategory\x18\x03 \x01(\tR\bcategory\x12\x1b\n" +
	"\tvalue_num\x18\x04 \x01(\x01R\bvalueNum\x12\x1d\n" +
	"\n" +
	"value_text\x18\x05 \x01(\tR\tvalueText\x12\x12\n" +
	"\x04unit\x18\x06 \x01(\tR\x04unit\x12\x17\n" +
	"\aref_low\x18\a \x01(\x01R\x06refLow\x12\x19\n" +
	"\bref_high\x18\b \x01(\x01R\arefHigh\x12\x19\n" +
	"\bref_text\x18\t \x01(\tR\arefText\x12\x12\n" +
	"\x04flag\x18\n" +
	" \x01(\tR\x04flag\x12\x1f\n" +
	"\vmeasured_at\x18\v \x01(\tR\n" +
	"measuredAt\"K\n" +
	"\vMetricPoint\x12\x12\n" +
	"\x04date\x18\x01 \x01(\tR\x04date\x12\x14\n" +
	"\x05value\x18\x02 \x01(\x01R\x05value\x12\x12\n" +
	"\x04flag\x18\x03 \x01(\tR\x04flag\"\x8d\x02\n" +
	"\x0fMetricTrendItem\x12\x1f\n" +
	"\vmetric_code\x18\x01 \x01(\tR\n" +
	"metricCode\x12\x1f\n" +
	"\vmetric_name\x18\x02 \x01(\tR\n" +
	"metricName\x12\x12\n" +
	"\x04unit\x18\x03 \x01(\tR\x04unit\x120\n" +
	"\x06points\x18\x04 \x03(\v2\x18.research.v1.MetricPointR\x06points\x12\x1f\n" +
	"\vfirst_value\x18\x05 \x01(\x01R\n" +
	"firstValue\x12\x1d\n" +
	"\n" +
	"last_value\x18\x06 \x01(\x01R\tlastValue\x12\x14\n" +
	"\x05delta\x18\a \x01(\x01R\x05delta\x12\x1c\n" +
	"\tdirection\x18\b \x01(\tR\tdirection\"?\n" +
	"\vMissingInfo\x12\x14\n" +
	"\x05items\x18\x01 \x03(\tR\x05items\x12\x1a\n" +
	"\bguidance\x18\x02 \x01(\tR\bguidance\"\x99\x01\n" +
	"\x0eMemoryProposal\x12!\n" +
	"\fcandidate_id\x18\x01 \x01(\tR\vcandidateId\x12\x12\n" +
	"\x04kind\x18\x02 \x01(\tR\x04kind\x12\x18\n" +
	"\acontent\x18\x03 \x01(\tR\acontent\x12\x16\n" +
	"\x06source\x18\x04 \x01(\tR\x06source\x12\x1e\n" +
	"\n" +
	"confidence\x18\x05 \x01(\x02R\n" +
	"confidence\"\xd9\x01\n" +
	"\n" +
	"TaskResult\x12%\n" +
	"\x0ereport_version\x18\x01 \x01(\tR\rreportVersion\x12\x16\n" +
	"\x06status\x18\x02 \x01(\tR\x06status\x12\x16\n" +
	"\x06reason\x18\x03 \x01(\tR\x06reason\x121\n" +
	"\ametrics\x18\x04 \x03(\v2\x17.research.v1.MetricItemR\ametrics\x12A\n" +
	"\rmetric_trends\x18\x05 \x03(\v2\x1c.research.v1.MetricTrendItemR\fmetricTrends\"^\n" +
	"\x05Error\x12\x1d\n" +
	"\n" +
	"error_code\x18\x01 \x01(\tR\terrorCode\x12\x18\n" +
	"\amessage\x18\x02 \x01(\tR\amessage\x12\x1c\n" +
	"\tretryable\x18\x03 \x01(\bR\tretryable\"\xd8\x01\n" +
	"\x11ResumeTaskRequest\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x19\n" +
	"\btrace_id\x18\x02 \x01(\tR\atraceId\x12\x16\n" +
	"\x06action\x18\x03 \x01(\tR\x06action\x126\n" +
	"\n" +
	"new_images\x18\x04 \x03(\v2\x17.research.v1.ImageAssetR\tnewImages\x12!\n" +
	"\fcandidate_id\x18\x05 \x01(\tR\vcandidateId\x12\x1c\n" +
	"\tconfirmed\x18\x06 \x01(\bR\tconfirmed\"E\n" +
	"\x12ResumeTaskResponse\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x16\n" +
	"\x06status\x18\x02 \x01(\tR\x06status\"D\n" +
	"\x11CancelTaskRequest\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x16\n" +
	"\x06reason\x18\x02 \x01(\tR\x06reason\"E\n" +
	"\x12CancelTaskResponse\x12\x17\n" +
	"\atask_id\x18\x01 \x01(\tR\x06taskId\x12\x16\n" +
	"\x06status\x18\x02 \x01(\tR\x06status\"\x91\x02\n" +
	"\n" +
	"MemoryItem\x12\x0e\n" +
	"\x02id\x18\x01 \x01(\tR\x02id\x12\x12\n" +
	"\x04kind\x18\x02 \x01(\tR\x04kind\x12\x18\n" +
	"\acontent\x18\x03 \x01(\tR\acontent\x12!\n" +
	"\fmetric_codes\x18\x04 \x03(\tR\vmetricCodes\x12\x16\n" +
	"\x06source\x18\x05 \x01(\tR\x06source\x12\x1e\n" +
	"\n" +
	"confidence\x18\x06 \x01(\x02R\n" +
	"confidence\x12\x18\n" +
	"\aversion\x18\a \x01(\x05R\aversion\x121\n" +
	"\x14pending_confirmation\x18\b \x01(\bR\x13pendingConfirmation\x12\x1d\n" +
	"\n" +
	"created_at\x18\t \x01(\tR\tcreatedAt\",\n" +
	"\x11ListMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\"C\n" +
	"\x12ListMemoryResponse\x12-\n" +
	"\x05items\x18\x01 \x03(\v2\x17.research.v1.MemoryItemR\x05items\"\x97\x01\n" +
	"\x13CreateMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x12\n" +
	"\x04kind\x18\x02 \x01(\tR\x04kind\x12\x18\n" +
	"\acontent\x18\x03 \x01(\tR\acontent\x12!\n" +
	"\fmetric_codes\x18\x04 \x03(\tR\vmetricCodes\x12\x16\n" +
	"\x06source\x18\x05 \x01(\tR\x06source\"j\n" +
	"\x13UpdateMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x19\n" +
	"\bentry_id\x18\x02 \x01(\tR\aentryId\x12\x1f\n" +
	"\vnew_content\x18\x03 \x01(\tR\n" +
	"newContent\"I\n" +
	"\x13DeleteMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x19\n" +
	"\bentry_id\x18\x02 \x01(\tR\aentryId\"1\n" +
	"\x16DeleteAllMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\"K\n" +
	"\x14DeleteMemoryResponse\x12\x0e\n" +
	"\x02ok\x18\x01 \x01(\bR\x02ok\x12#\n" +
	"\rdeleted_count\x18\x02 \x01(\x05R\fdeletedCount\"J\n" +
	"\x14ConfirmMemoryRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x19\n" +
	"\bentry_id\x18\x02 \x01(\tR\aentryId\"G\n" +
	"\x16ListMemoryAuditRequest\x12\x17\n" +
	"\auser_id\x18\x01 \x01(\tR\x06userId\x12\x14\n" +
	"\x05limit\x18\x02 \x01(\x05R\x05limit\"\xa6\x01\n" +
	"\x0fMemoryAuditItem\x12\x0e\n" +
	"\x02id\x18\x01 \x01(\tR\x02id\x12\x17\n" +
	"\auser_id\x18\x02 \x01(\tR\x06userId\x12\x16\n" +
	"\x06action\x18\x03 \x01(\tR\x06action\x12\x1b\n" +
	"\ttarget_id\x18\x04 \x01(\tR\btargetId\x12\x16\n" +
	"\x06detail\x18\x05 \x01(\tR\x06detail\x12\x1d\n" +
	"\n" +
	"created_at\x18\x06 \x01(\tR\tcreatedAt\"M\n" +
	"\x17ListMemoryAuditResponse\x122\n" +
	"\x05items\x18\x01 \x03(\v2\x1c.research.v1.MemoryAuditItemR\x05items2\xd5\x03\n" +
	"\x0fResearchService\x12M\n" +
	"\n" +
	"SubmitTask\x12\x1e.research.v1.SubmitTaskRequest\x1a\x1f.research.v1.SubmitTaskResponse\x12F\n" +
	"\n" +
	"StreamTask\x12\x1e.research.v1.StreamTaskRequest\x1a\x16.research.v1.TaskEvent0\x01\x12M\n" +
	"\n" +
	"ResumeTask\x12\x1e.research.v1.ResumeTaskRequest\x1a\x1f.research.v1.ResumeTaskResponse\x12M\n" +
	"\n" +
	"CancelTask\x12\x1e.research.v1.CancelTaskRequest\x1a\x1f.research.v1.CancelTaskResponse\x12P\n" +
	"\vGetTaskCost\x12\x1f.research.v1.GetTaskCostRequest\x1a .research.v1.GetTaskCostResponse\x12;\n" +
	"\x04Chat\x12\x18.research.v1.ChatRequest\x1a\x19.research.v1.ChatResponse2\xcf\x04\n" +
	"\rMemoryService\x12M\n" +
	"\n" +
	"ListMemory\x12\x1e.research.v1.ListMemoryRequest\x1a\x1f.research.v1.ListMemoryResponse\x12I\n" +
	"\fCreateMemory\x12 .research.v1.CreateMemoryRequest\x1a\x17.research.v1.MemoryItem\x12I\n" +
	"\fUpdateMemory\x12 .research.v1.UpdateMemoryRequest\x1a\x17.research.v1.MemoryItem\x12S\n" +
	"\fDeleteMemory\x12 .research.v1.DeleteMemoryRequest\x1a!.research.v1.DeleteMemoryResponse\x12Y\n" +
	"\x0fDeleteAllMemory\x12#.research.v1.DeleteAllMemoryRequest\x1a!.research.v1.DeleteMemoryResponse\x12K\n" +
	"\rConfirmMemory\x12!.research.v1.ConfirmMemoryRequest\x1a\x17.research.v1.MemoryItem\x12\\\n" +
	"\x0fListMemoryAudit\x12#.research.v1.ListMemoryAuditRequest\x1a$.research.v1.ListMemoryAuditResponseBKZIllm-healthy-assistant/go-backend/internal/aiclient/research/v1;researchv1b\x06proto3"

var (
	file_research_v1_research_proto_rawDescOnce sync.Once
	file_research_v1_research_proto_rawDescData []byte
)

func file_research_v1_research_proto_rawDescGZIP() []byte {
	file_research_v1_research_proto_rawDescOnce.Do(func() {
		file_research_v1_research_proto_rawDescData = protoimpl.X.CompressGZIP(unsafe.Slice(unsafe.StringData(file_research_v1_research_proto_rawDesc), len(file_research_v1_research_proto_rawDesc)))
	})
	return file_research_v1_research_proto_rawDescData
}

var file_research_v1_research_proto_msgTypes = make([]protoimpl.MessageInfo, 38)
var file_research_v1_research_proto_goTypes = []any{
	(*ChatHistoryItem)(nil),
	(*ChatRequest)(nil),
	(*ChatResponse)(nil),
	(*GetTaskCostRequest)(nil),
	(*CostItem)(nil),
	(*GetTaskCostResponse)(nil),
	(*SubmitTaskRequest)(nil),
	(*ImageAsset)(nil),
	(*SubmitTaskResponse)(nil),
	(*StreamTaskRequest)(nil),
	(*TaskEvent)(nil),
	(*StageChange)(nil),
	(*Observation)(nil),
	(*EvidenceFound)(nil),
	(*ReportDelta)(nil),
	(*MetricItem)(nil),
	(*MetricPoint)(nil),
	(*MetricTrendItem)(nil),
	(*MissingInfo)(nil),
	(*MemoryProposal)(nil),
	(*TaskResult)(nil),
	(*Error)(nil),
	(*ResumeTaskRequest)(nil),
	(*ResumeTaskResponse)(nil),
	(*CancelTaskRequest)(nil),
	(*CancelTaskResponse)(nil),
	(*MemoryItem)(nil),
	(*ListMemoryRequest)(nil),
	(*ListMemoryResponse)(nil),
	(*CreateMemoryRequest)(nil),
	(*UpdateMemoryRequest)(nil),
	(*DeleteMemoryRequest)(nil),
	(*DeleteAllMemoryRequest)(nil),
	(*DeleteMemoryResponse)(nil),
	(*ConfirmMemoryRequest)(nil),
	(*ListMemoryAuditRequest)(nil),
	(*MemoryAuditItem)(nil),
	(*ListMemoryAuditResponse)(nil),
}
var file_research_v1_research_proto_depIdxs = []int32{
	0,
	13,
	4,
	7,
	11,
	12,
	13,
	14,
	18,
	19,
	20,
	21,
	15,
	17,
	16,
	15,
	17,
	7,
	26,
	36,
	6,
	9,
	22,
	24,
	3,
	1,
	27,
	29,
	30,
	31,
	32,
	34,
	35,
	8,
	10,
	23,
	25,
	5,
	2,
	28,
	26,
	26,
	33,
	33,
	26,
	37,
	33,
	20,
	20,
	20,
	0,
}

func init() { file_research_v1_research_proto_init() }
func file_research_v1_research_proto_init() {
	if File_research_v1_research_proto != nil {
		return
	}
	file_research_v1_research_proto_msgTypes[10].OneofWrappers = []any{
		(*TaskEvent_StageChange)(nil),
		(*TaskEvent_Observation)(nil),
		(*TaskEvent_EvidenceFound)(nil),
		(*TaskEvent_ReportDelta)(nil),
		(*TaskEvent_MissingInfo)(nil),
		(*TaskEvent_MemoryProposal)(nil),
		(*TaskEvent_Result)(nil),
		(*TaskEvent_Error)(nil),
	}
	type x struct{}
	out := protoimpl.TypeBuilder{
		File: protoimpl.DescBuilder{
			GoPackagePath: reflect.TypeOf(x{}).PkgPath(),
			RawDescriptor: unsafe.Slice(unsafe.StringData(file_research_v1_research_proto_rawDesc), len(file_research_v1_research_proto_rawDesc)),
			NumEnums:      0,
			NumMessages:   38,
			NumExtensions: 0,
			NumServices:   2,
		},
		GoTypes:           file_research_v1_research_proto_goTypes,
		DependencyIndexes: file_research_v1_research_proto_depIdxs,
		MessageInfos:      file_research_v1_research_proto_msgTypes,
	}.Build()
	File_research_v1_research_proto = out.File
	file_research_v1_research_proto_goTypes = nil
	file_research_v1_research_proto_depIdxs = nil
}
