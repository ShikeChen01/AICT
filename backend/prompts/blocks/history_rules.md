Conversation history rules:
- Your visible context includes the last 5 sessions. Each session is separated by a boundary marker showing the session ID and start date.
- History may be truncated if it exceeds the context budget. Older messages within a session are removed first.
- Use list_sessions to discover your past sessions (ID, start/end time, status, message count).
- Use read_history(session_id=<uuid>) to retrieve messages from a specific past session.
- Use read_history with limit and offset for pagination within a session.
- The full message history is always stored permanently — nothing is lost, only hidden from the current context window.
