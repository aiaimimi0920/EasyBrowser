package ipc

type Kind string

const (
	KindRequest   Kind = "request"
	KindResponse  Kind = "response"
	KindEvent     Kind = "event"
	KindHeartbeat Kind = "heartbeat"
	KindError     Kind = "error"
)

type Trace struct {
	TaskID     string `json:"task_id,omitempty"`
	RuntimeID  string `json:"runtime_id,omitempty"`
	ProviderID string `json:"provider_id,omitempty"`
}

type Envelope struct {
	ID        string         `json:"id,omitempty"`
	Kind      Kind           `json:"kind"`
	Action    string         `json:"action,omitempty"`
	Timestamp string         `json:"timestamp,omitempty"`
	Trace     Trace          `json:"trace,omitempty"`
	Payload   map[string]any `json:"payload,omitempty"`
	Error     map[string]any `json:"error,omitempty"`
}
