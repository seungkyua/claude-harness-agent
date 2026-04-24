# Brief: tiny todo CLI

Build a Python CLI called `todo` that stores tasks in a local SQLite file
under `~/.todo.db`.

It must support:

- `todo add "<text>"` — add a task, print its numeric id.
- `todo list` — print open tasks, one per line, newest first.
- `todo done <id>` — mark a task done.
- `todo rm <id>` — delete a task.

Include pytest tests that exercise the happy path and the "task not found"
error path. `pytest -q` should pass.
