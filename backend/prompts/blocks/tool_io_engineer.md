
Engineer-only tools:
- update_task_status(task_id, status)
  - Input: task_id UUID, status string
  - Output: Task status updated: <task_uuid> -> <status>

- abort_task(reason)
  - Input: reason text
  - Output: Task aborted.

- create_branch(branch_name)
  - Input: branch_name string
  - Output: Branch created: <branch_name>

- create_pull_request(title, description?)
  - Input: title required, optional description
  - Output: PR created: <pr_url>

Sandbox display & input tools (use when you need to interact with a GUI):
- sandbox_screenshot()
  - Input: {}
  - Output: "Screenshot captured (<N> bytes). Base64 JPEG: <data>"

- sandbox_mouse_move(x, y)
  - Input: x and y pixel coordinates (0–1023, 0–767)
  - Output: "Mouse moved to (<x>, <y>)"

- sandbox_mouse_location()
  - Input: {}
  - Output: "Mouse at x=<x>, y=<y>"

- sandbox_keyboard_press(keys?, text?)
  - Input: keys (xdotool combo, e.g. "ctrl+c", "Return") OR text (raw string to type)
  - Output: "Keyboard input sent: keys=<...> text=<...>"

- sandbox_record_screen()
  - Input: {}
  - Output: "Recording started. Status: started"

- sandbox_end_record_screen()
  - Input: {}
  - Output: "Recording stopped (<N> bytes). Base64 MP4: <data>"
