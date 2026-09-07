# Brief: tiny todo CLI

`~/.todo.db` 아래에 로컬 SQLite 파일로 작업을 저장하는 `todo`라는 이름의
Python CLI를 만들어줘.

다음을 지원해야 해:

- `todo add "<text>"` — 작업을 추가하고, 그 숫자 id를 출력.
- `todo list` — 미완료 작업을 한 줄에 하나씩, 최신순으로 출력.
- `todo done <id>` — 작업을 완료로 표시.
- `todo rm <id>` — 작업을 삭제.

정상 경로와 "task not found" 오류 경로를 모두 검증하는 pytest 테스트를
포함해줘. `pytest -q`가 통과해야 해.
