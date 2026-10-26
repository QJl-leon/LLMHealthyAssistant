
package errors

const (

	CodeImageQualityLow  = "IMAGE_QUALITY_LOW"
	CodeOCRLowConfidence = "OCR_LOW_CONFIDENCE"

	CodeRetrievalEmpty = "RETRIEVAL_EMPTY"

	CodeModelTimeout = "MODEL_TIMEOUT"

	CodeCitationMismatch = "CITATION_MISMATCH"

	CodePermissionDenied = "PERMISSION_DENIED"

	CodeMemoryConfirmRequired = "MEMORY_CONFIRM_REQUIRED"

	CodeRateLimited = "RATE_LIMITED"

	CodeUpstreamUnavailable = "UPSTREAM_UNAVAILABLE"

	CodeBadRequest   = "BAD_REQUEST"
	CodeInternal     = "INTERNAL_ERROR"
	CodeTaskNotFound = "TASK_NOT_FOUND"
)

func IsRetryable(code string) bool {
	switch code {
	case CodeImageQualityLow, CodeOCRLowConfidence,
		CodeModelTimeout, CodeRateLimited, CodeUpstreamUnavailable:
		return true
	default:
		return false
	}
}

func UIAction(code string) string {
	actions := map[string]string{
		CodeImageQualityLow:        "引导补拍（附具体动作）",
		CodeOCRLowConfidence:       "标记低置信区域，建议补拍",
		CodeRetrievalEmpty:         "显示'未找到证据'，非报错",
		CodeModelTimeout:           "'模型繁忙'，自动重试一次",
		CodeCitationMismatch:       "报告回炉，用户无感知",
		CodePermissionDenied:       "明确拒绝文案",
		CodeMemoryConfirmRequired:  "弹出记忆确认卡片",
		CodeRateLimited:            "提示稍后重试",
		CodeUpstreamUnavailable:    "降级提示",
		CodeBadRequest:             "检查请求参数",
		CodeInternal:               "内部错误，联系管理员",
		CodeTaskNotFound:           "任务不存在或已过期",
	}
	if a, ok := actions[code]; ok {
		return a
	}
	return "未知错误"
}
