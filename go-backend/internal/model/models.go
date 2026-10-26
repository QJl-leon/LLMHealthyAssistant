
package model

import (
	"encoding/json"
	"time"
)

type User struct {
	ID           string    `json:"id"`
	TenantID     string    `json:"tenant_id"`
	Nickname     string    `json:"nickname"`
	Email        string    `json:"email,omitempty"`
	PasswordHash string    `json:"-"`
	Role         string    `json:"role"`
	CreatedAt    time.Time `json:"created_at"`
}

const (
	RoleUser     = "user"
	RoleOperator = "operator"
	RoleAdmin    = "admin"
)

type Task struct {
	ID           string    `json:"id"`
	TenantID     string    `json:"tenant_id"`
	UserID       string    `json:"user_id"`
	ClientTaskID string    `json:"client_task_id"`
	Status       string    `json:"status"`
	ImageKeys    []string  `json:"image_keys"`
	CreatedAt    time.Time `json:"created_at"`
}

var ValidTaskStatuses = []string{
	"intake", "observing", "retrieving", "drafting", "validating",
	"awaiting_images", "awaiting_memory_confirm", "published", "refused", "persist_failed", "cancelled",
}

type ReportSection struct {
	Observation  string `json:"observation"`
	Facts        string `json:"facts"`
	Inferences   string `json:"inferences"`
	Conflicts    string `json:"conflicts,omitempty"`
	Unknowns     string `json:"unknowns"`
	RelatedToYou string `json:"related_to_you,omitempty"`

	MetricReading   string `json:"metric_reading,omitempty"`
	MetricTrend     string `json:"metric_trend,omitempty"`
	ExerciseAdvice  string `json:"exercise_advice,omitempty"`
	LifestyleAdvice string `json:"lifestyle_advice,omitempty"`
	FollowupAdvice  string `json:"followup_advice,omitempty"`
}

type ReportContent struct {
	Sections     ReportSection     `json:"sections"`
	Citations    []ReportCitation  `json:"citations"`
	Metrics      []MetricItem      `json:"metrics,omitempty"`
	MetricTrends []MetricTrend     `json:"metric_trends,omitempty"`
	Metadata     map[string]string `json:"metadata,omitempty"`
}

type MetricItem struct {
	MetricCode string  `json:"metric_code"`
	MetricName string  `json:"metric_name"`
	Category   string  `json:"category,omitempty"`
	ValueNum   float64 `json:"value_num,omitempty"`
	ValueText  string  `json:"value_text,omitempty"`
	Unit       string  `json:"unit,omitempty"`
	RefLow     float64 `json:"ref_low,omitempty"`
	RefHigh    float64 `json:"ref_high,omitempty"`
	RefText    string  `json:"ref_text,omitempty"`
	Flag       string  `json:"flag,omitempty"`
	MeasuredAt string  `json:"measured_at,omitempty"`
}

type MetricPoint struct {
	Date  string  `json:"date"`
	Value float64 `json:"value"`
	Flag  string  `json:"flag,omitempty"`
}

type MetricTrend struct {
	MetricCode string        `json:"metric_code"`
	MetricName string        `json:"metric_name"`
	Unit       string        `json:"unit,omitempty"`
	Points     []MetricPoint `json:"points,omitempty"`
	FirstValue float64       `json:"first_value,omitempty"`
	LastValue  float64       `json:"last_value,omitempty"`
	Delta      float64       `json:"delta,omitempty"`
	Direction  string        `json:"direction,omitempty"`
}

type ReportCitation struct {
	ClaimID    string `json:"claim_id"`
	EvidenceID string `json:"evidence_id"`
	SourceName string `json:"source_name"`
	Quote      string `json:"quote"`
	SourceURL  string `json:"source_url,omitempty"`
}

type Report struct {
	ID               string        `json:"id"`
	TaskID           string        `json:"task_id"`
	Version          int           `json:"version"`
	KnowledgeVersion string        `json:"knowledge_version"`
	Content          ReportContent `json:"content"`
	Status           string        `json:"status"`
	CreatedAt        time.Time     `json:"created_at"`
}

func (r *Report) ScanContent(raw []byte) error {
	return json.Unmarshal(raw, &r.Content)
}

func (r *Report) ContentBytes() ([]byte, error) {
	return json.Marshal(r.Content)
}

type ProfileKind string

const (
	ProfileBasic      ProfileKind = "basic"
	ProfileCondition  ProfileKind = "condition"
	ProfileMedication ProfileKind = "medication"
	ProfileAllergy    ProfileKind = "allergy"
	ProfileGoal       ProfileKind = "goal"
	ProfileExercise   ProfileKind = "exercise"
)

type Profile struct {
	ID           string      `json:"id"`
	UserID       string      `json:"user_id"`
	Kind         ProfileKind `json:"kind"`
	ContentEnc   []byte      `json:"-"`
	Source       string      `json:"source"`
	Confidence   *float64    `json:"confidence,omitempty"`
	Version      int         `json:"version"`
	SupersededAt *time.Time  `json:"superseded_at,omitempty"`
	DeletedAt    *time.Time  `json:"deleted_at,omitempty"`
	CreatedAt    time.Time   `json:"created_at"`
}

type FeedbackIssueType string

const (
	FeedbackWrongCitation FeedbackIssueType = "wrong_citation"
	FeedbackUnsupported   FeedbackIssueType = "unsupported"
	FeedbackOutdated      FeedbackIssueType = "outdated"
	FeedbackOther         FeedbackIssueType = "other"
)

type Feedback struct {
	ID        string            `json:"id"`
	UserID    string            `json:"user_id"`
	ReportID  string            `json:"report_id"`
	ClaimID   string            `json:"claim_id"`
	IssueType FeedbackIssueType `json:"issue_type"`
	Detail    string            `json:"detail,omitempty"`
	CreatedAt time.Time         `json:"created_at"`
}
