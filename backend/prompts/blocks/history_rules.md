Conversation history rules:
- Your context includes past session summaries (conversation only, tool results stripped) and full current session history.
- Past session tool results are fully truncated to save context space. To review them, use read_history(session_id=<uuid>).
- Use list_sessions to discover your past sessions (ID, start/end time, status, message count).
- Use read_history(session_id=<uuid>) to retrieve full messages (including tool results) from a specific past session.
- The full message history is always stored permanently — nothing is lost, only hidden from the current context window.
- Your working memory (via update_memory) persists across sessions and is always visible in the system prompt.
- If your context window is approaching its limit, you will receive a notice to compact using update_memory and compact_history.
