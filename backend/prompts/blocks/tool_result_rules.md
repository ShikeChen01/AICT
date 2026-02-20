Tool result rules:
- Tool calls in a batch are independent. If one fails, others may have succeeded. Check all results before deciding your next action.
- Tool results are delivered as messages after your response. Do not assume a result until you have seen it.
- Large tool results may be truncated. When you see "[output truncated]", the full output is saved to a temp file — use execute_command (e.g. cat the temp file path) to access it.
- Read error messages carefully. The error text tells you what went wrong and how to fix it. Retry with a corrected input before escalating.
- Tool calls within a single response share the same iteration. Results from all of them are delivered together before your next response.
