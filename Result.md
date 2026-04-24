전체 파일 트리와 시작 방법을 정리해 드립니다.

  만들어진 구조

  claude-hermes/
  ├── README.md                    # 시작 가이드 (아래 내용의 상세판)
  ├── config.yaml                  # max_iterations, 모델, 권한 모드
  ├── pyproject.toml               # 의존성 + hermes CLI 등록
  ├── .env.example                 # ANTHROPIC_API_KEY
  ├── briefs/
  │   └── example-todo-cli.md      # 시험용 brief
  ├── prompts/
  │   ├── planner.md               # brief.md → spec.md
  │   ├── generator.md             # spec + 피드백 → project/
  │   └── evaluator.md             # 회의적 평가 + verdict: PASS|FAIL
  └── src/hermes/
      ├── cli.py                   # 진입점 (argparse)
      ├── config.py                # YAML 로더
      ├── io.py                    # 한 run 의 파일 레이아웃 (RunLayout)
      ├── agents.py                # Claude Agent SDK 호출 래퍼 3개
      └── orchestrator.py          # Planner→(Gen→Eval) × N 루프

  설계 요점 (아티클 대응)

  - 파일 기반 핸드오프 — 에이전트는 세션을 공유하지 않고, 매 호출마다 clean context. 상태는 전부 brief.md → spec.md → project/ → reports/latest.md 파일에 있음 (src/hermes/io.py:11).
  - 역할별 도구 허용치 분리 — Planner는 읽기/쓰기, Generator는 + Bash/Edit, Evaluator는 코드 수정 금지 (src/hermes/agents.py:63, agents.py:104, agents.py:147).
  - 회의적 Evaluator — 실제 빌드·테스트를 Bash로 돌리고, 각 acceptance criterion 에 MET/PARTIAL/NOT MET. 마지막 줄 verdict: PASS|FAIL 하나로 루프 종료 판단 (prompts/evaluator.md, 파싱은
  orchestrator.py:42).
  - 설정 가능한 iteration — config.yaml 의 max_iterations, stop_on_pass, replan_every. CLI 에서 --iterations N 오버라이드.

  시작 방법

  1. 사전 준비 (Claude CLI + API 키)

  Claude Agent SDK 는 내부적으로 claude CLI 를 호출하므로 먼저 설치가 필요합니다.

  node --version      # v18 이상
  npm install -g @anthropic-ai/claude-code
  claude --version

  2. 파이썬 환경

  cd /Users/ask.ahn/Documents/works/ai/claude-hermes
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e .
  cp .env.example .env
  # .env 열어서 ANTHROPIC_API_KEY=sk-ant-... 넣기

  3. brief 작성

  briefs/my-app.md 에 1~10문장으로 "뭘 왜 만들고 싶은지" 만 적습니다. 스택 선택은 Planner 가 합니다. 샘플은 briefs/example-todo-cli.md.

  4. iteration 설정

  두 방법 중 하나:

  config.yaml 수정 (기본 5):
  max_iterations: 8
  stop_on_pass: true     # PASS 나오면 조기 종료
  replan_every: 0        # > 0 이면 N iter 마다 Planner 재호출

  CLI 로 오버라이드:
  ANTHROPIC_LOG=debug claude-hermes briefs/example-todo-cli.md --iterations 2 --label todo --no-stop-on-pass 2> todo-debug.log

  # 또는 모듈 실행 (PATH 충돌 완전 회피)
  python -m hermes briefs/example-todo-cli.md --iterations 3 --label todo
  ANTHROPIC_LOG=debug HERMES_QUIET=false python -m hermes briefs/example-todo-cli.md --iterations 2 --label todo --no-stop-on-pass 2> todo-debug.log

  # stop_on_pass 끄고 싶으면:
  claude-hermes briefs/my-app.md --iterations 8 --no-stop-on-pass

  5. 실행 & 결과 확인

  hermes briefs/example-todo-cli.md --iterations 5 --label todo

  콘솔에는 Planner → Generator(iter 1) → Evaluator(iter 1) → ... 순으로 rule 이 찍히고, 각 단계별 turn 수/비용이 로그로 남습니다.

  결과는 workspace/runs/<timestamp>-<label>/ 에:

  workspace/runs/20260423-140000-todo/
  ├── brief.md            # 당신의 원본 brief
  ├── spec.md             # Planner 산출 (최종)
  ├── project/            # ← 실제로 만들어진 프로그램. 통째로 들고 쓰면 됨
  ├── reports/
  │   ├── iter_01.md
  │   ├── iter_02.md
  │   └── latest.md
  └── run.log

  성공 판정은 reports/latest.md 마지막 줄의 verdict: PASS / FAIL.

  6. 다음 단계 (튜닝)

  - Generator 가 gold-plate 함 → prompts/generator.md 의 "No extra features" 섹션을 도메인 맞게 강화.
  - Evaluator 가 관대함 → prompts/evaluator.md 상단 톤을 구체 예시로 교체. LLM 평가자는 few-shot 예시로 기대치 고정이 가장 효과 큽니다 (아티클에서 언급한 "calibrated with few-shot examples").
  - 큰 프로젝트 → replan_every: 2 로 Planner 가 중간에 Milestones 를 다시 쪼개게.
  - 비용 ↓ → config.yaml 의 models.generator 를 claude-haiku-4-5-20251001 로. Planner/Evaluator 는 판단 품질에 직결되니 Opus/Sonnet 유지 권장.

  ---
  바로 시도해 보려면 briefs/example-todo-cli.md 로 hermes briefs/example-todo-cli.md --iterations 3 --label todo 를 돌려 보세요. 진행 중 로그가 어떻게 찍히는지, PASS 가 몇 iteration 에 나오는지 감을
  잡은 뒤 본인 brief 로 옮기면 됩니다.



  echo "say only the word PONG" | claude -p --output-format text