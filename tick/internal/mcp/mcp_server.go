// Package mcp implements a minimal JSON-RPC 2.0 server over stdio that
// exposes the tick scheduler as three MCP tools.
//
// The wire format follows JSON-RPC 2.0 with the MCP-specific method
// names initialize, notifications/initialized, tools/list, tools/call.
// We deliberately do NOT take a dependency on the official MCP Go SDK;
// the protocol is small and stable, and our tool surface is three calls.
//
// Framing: one JSON object per line on stdin and stdout. We do not
// support batched requests in MVP.
package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/job"
	"github.com/1jehuang/lazible-jcode/tick/internal/scheduler"
	"github.com/1jehuang/lazible-jcode/tick/internal/store"
)

// Server owns a Scheduler + Store and speaks JSON-RPC 2.0 over stdio.
type Server struct {
	sched  *scheduler.Scheduler
	store  *store.Store
	reader io.Reader
	writer io.Writer
}

// New constructs a Server bound to the given streams. Use os.Stdin /
// os.Stdout in production; tests can pass in-memory pipes.
func New(sched *scheduler.Scheduler, st *store.Store, reader io.Reader, writer io.Writer) *Server {
	return &Server{sched: sched, store: st, reader: reader, writer: writer}
}

// Run reads JSON-RPC requests until EOF or ctx cancel. Each request is
// handled synchronously; tools/call that does not block (Submit / Cancel
// / List) returns immediately. The scheduler runs in the background as
// long as the caller keeps its Run loop alive (main.go manages that).
func (s *Server) Run(ctx context.Context) error {
	scanner := bufio.NewScanner(s.reader)
	// MCP messages are small; default 64KiB is enough but raise for safety.
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	enc := json.NewEncoder(s.writer)
	enc.SetEscapeHTML(false)

	for scanner.Scan() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		raw := scanner.Bytes()
		if len(raw) == 0 {
			continue
		}
		var req request
		if err := json.Unmarshal(raw, &req); err != nil {
			// Per JSON-RPC 2.0: parse error is reported as a response
			// with id=null.
			_ = enc.Encode(response{
				JSONRPC: "2.0",
				ID:      nil,
				Error: &rpcError{
					Code:    -32700,
					Message: "parse error: " + err.Error(),
				},
			})
			continue
		}
		resp := s.handle(ctx, &req)
		if resp == nil {
			// Notification (no id); no response to send.
			continue
		}
		if err := enc.Encode(resp); err != nil {
			return fmt.Errorf("mcp: write response: %w", err)
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("mcp: read stdin: %w", err)
	}
	return nil
}

// --- JSON-RPC plumbing ---

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  any             `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// handle returns nil for notifications (no response expected) or a
// response object for normal requests.
func (s *Server) handle(ctx context.Context, req *request) *response {
	switch req.Method {
	case "initialize":
		return &response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: initializeResult{
				ProtocolVersion: "2024-11-05",
				ServerInfo: serverInfo{
					Name:    "jcode-swarm-tick",
					Version: "0.1.0",
				},
				Capabilities: serverCapabilities{
					Tools: map[string]any{},
				},
			},
		}

	case "notifications/initialized":
		// Client confirms handshake. No response needed.
		return nil

	case "tools/list":
		return &response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: toolsListResult{
				Tools: []toolDef{
					toolSubmitJob, toolCancelJob, toolListJobs,
				},
			},
		}

	case "tools/call":
		var p toolsCallParams
		if err := json.Unmarshal(req.Params, &p); err != nil {
			return &response{
				JSONRPC: "2.0",
				ID:      req.ID,
				Error:   &rpcError{Code: -32602, Message: "invalid params: " + err.Error()},
			}
		}
		return s.callTool(ctx, req.ID, p)

	default:
		return &response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error:   &rpcError{Code: -32601, Message: "method not found: " + req.Method},
		}
	}
}

// --- Tool definitions ---

type toolDef struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"inputSchema"`
}

var toolSubmitJob = toolDef{
	Name:        "submit_job",
	Description: "Schedule a delayed wakeup to a jcode session. The daemon fires via NotifySession at fire_at = now + fire_in_seconds. fire_in_seconds must be > 0 and < 86400 (24h cap, longer intervals require multiple jobs).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"wake_session_id": map[string]any{
				"type":        "string",
				"description": "Target session id (e.g. session_xxx). The daemon will silently fallback to the swarm coordinator if the target session is dead at fire time.",
			},
			"fire_in_seconds": map[string]any{
				"type":        "number",
				"description": "How many seconds from now to wait before firing.",
				"minimum":     1,
				"maximum":     86400,
			},
			"message": map[string]any{
				"type":        "string",
				"description": "Message to deliver to the session. Plain text, no formatting.",
			},
		},
		"required": []string{"wake_session_id", "fire_in_seconds", "message"},
	},
}

var toolCancelJob = toolDef{
	Name:        "cancel_job",
	Description: "Cancel a previously submitted job by id. Idempotent: returns cancelled=false for unknown ids.",
	InputSchema: map[string]any{
		"type":     "object",
		"properties": map[string]any{
			"job_id": map[string]any{"type": "string"},
		},
		"required": []string{"job_id"},
	},
}

var toolListJobs = toolDef{
	Name:        "list_jobs",
	Description: "List all pending jobs in the daemon's heap.",
	InputSchema: map[string]any{
		"type":       "object",
		"properties": map[string]any{},
	},
}

// --- Initialize / tools/list result types ---

type initializeResult struct {
	ProtocolVersion string             `json:"protocolVersion"`
	ServerInfo      serverInfo         `json:"serverInfo"`
	Capabilities    serverCapabilities `json:"capabilities"`
}

type serverInfo struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

type serverCapabilities struct {
	Tools map[string]any `json:"tools"`
}

type toolsListResult struct {
	Tools []toolDef `json:"tools"`
}

// --- tools/call plumbing ---

type toolsCallParams struct {
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments"`
}

// callTool dispatches by tool name. Unknown names return
// method-not-found-shaped errors.
func (s *Server) callTool(ctx context.Context, id json.RawMessage, p toolsCallParams) *response {
	switch p.Name {
	case "submit_job":
		return s.toolSubmitJob(ctx, id, p.Arguments)
	case "cancel_job":
		return s.toolCancelJob(ctx, id, p.Arguments)
	case "list_jobs":
		return s.toolListJobs(ctx, id, p.Arguments)
	default:
		return &response{
			JSONRPC: "2.0",
			ID:      id,
			Error:   &rpcError{Code: -32602, Message: "unknown tool: " + p.Name},
		}
	}
}

// toolSubmitJob result schema:
//
//	{
//	  "content": [{"type": "text", "text": "<json>"}],
//	  "isError": false
//	}
type submitArgs struct {
	WakeSessionID string  `json:"wake_session_id"`
	FireInSeconds float64 `json:"fire_in_seconds"`
	Message       string  `json:"message"`
}

type submitResult struct {
	JobID    string `json:"job_id"`
	FireAtMs int64  `json:"fire_at_ms"`
}

func (s *Server) toolSubmitJob(ctx context.Context, id json.RawMessage, args json.RawMessage) *response {
	var a submitArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return toolError(id, "invalid arguments: "+err.Error())
	}
	if a.WakeSessionID == "" {
		return toolError(id, "wake_session_id is required")
	}
	if a.FireInSeconds <= 0 {
		return toolError(id, "fire_in_seconds must be > 0")
	}
	if a.FireInSeconds > 86400 {
		return toolError(id, "fire_in_seconds must be <= 86400 (24h)")
	}

	fireAt := time.Now().Add(time.Duration(a.FireInSeconds * float64(time.Second)))
	j := job.New(a.WakeSessionID, a.Message, fireAt)
	if err := s.sched.Submit(j); err != nil {
		return toolError(id, "submit failed: "+err.Error())
	}
	if err := s.store.Append(j); err != nil {
		// Best-effort: roll back scheduler so heap and store stay in sync.
		s.sched.Cancel(j.ID)
		return toolError(id, "persist failed (job not scheduled): "+err.Error())
	}

	body, _ := json.Marshal(submitResult{JobID: j.ID, FireAtMs: j.FireAtMs})
	return &response{
		JSONRPC: "2.0",
		ID:      id,
		Result: toolResult{
			Content: []toolContent{{Type: "text", Text: string(body)}},
			IsError: false,
		},
	}
}

type cancelArgs struct {
	JobID string `json:"job_id"`
}

type cancelResult struct {
	Cancelled bool `json:"cancelled"`
}

func (s *Server) toolCancelJob(ctx context.Context, id json.RawMessage, args json.RawMessage) *response {
	var a cancelArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return toolError(id, "invalid arguments: "+err.Error())
	}
	if a.JobID == "" {
		return toolError(id, "job_id is required")
	}
	ok := s.sched.Cancel(a.JobID)
	if ok {
		// Best-effort remove from store; failure is not fatal (daemon
		// will re-load on next start and the sched will refuse duplicates).
		_ = s.store.Remove(a.JobID)
	}
	body, _ := json.Marshal(cancelResult{Cancelled: ok})
	return &response{
		JSONRPC: "2.0",
		ID:      id,
		Result: toolResult{
			Content: []toolContent{{Type: "text", Text: string(body)}},
			IsError: false,
		},
	}
}

type listArgs struct{}

type listEntry struct {
	JobID         string `json:"job_id"`
	FireAtMs      int64  `json:"fire_at_ms"`
	WakeSessionID string `json:"wake_session_id"`
	MessagePreview string `json:"message_preview"`
}

func (s *Server) toolListJobs(ctx context.Context, id json.RawMessage, args json.RawMessage) *response {
	var a listArgs
	_ = json.Unmarshal(args, &a) // empty schema; ignore errors

	all := s.sched.List()
	entries := make([]listEntry, 0, len(all))
	for _, j := range all {
		preview := j.Message
		if len(preview) > 80 {
			preview = preview[:80] + "..."
		}
		entries = append(entries, listEntry{
			JobID:          j.ID,
			FireAtMs:       j.FireAtMs,
			WakeSessionID:  j.WakeSessionID,
			MessagePreview: preview,
		})
	}
	body, _ := json.Marshal(entries)
	return &response{
		JSONRPC: "2.0",
		ID:      id,
		Result: toolResult{
			Content: []toolContent{{Type: "text", Text: string(body)}},
			IsError: false,
		},
	}
}

// --- Tool response envelope (MCP-spec) ---

type toolResult struct {
	Content []toolContent `json:"content"`
	IsError bool         `json:"isError"`
}

type toolContent struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

func toolError(id json.RawMessage, msg string) *response {
	body, _ := json.Marshal(map[string]string{"error": msg})
	return &response{
		JSONRPC: "2.0",
		ID:      id,
		Result: toolResult{
			Content: []toolContent{{Type: "text", Text: string(body)}},
			IsError: true,
		},
	}
}