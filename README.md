# claude-hermes

Planner ↔ Generator ↔ Evaluator 에이전트가 파일로만 통신하며 원하는 프로그램을
자동으로 반복 개발하는 harness. Anthropic의
[Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
기고를 기반으로 함.

---

## 구조

```
claude-hermes/
├── config.yaml                 # max_iterations, 모델, 권한 모드 등
├── briefs/                     # 당신이 쓰는 한 장짜리 요청서들
│   └── example-todo-cli.md
├── prompts/
│   ├── planner.md              # Planner 시스템 프롬프트
│   ├── generator.md            # Generator 시스템 프롬프트
│   └── evaluator.md            # Evaluator 시스템 프롬프트 (회의적 톤)
├── src/hermes/
│   ├── cli.py                  # hermes 진입점
│   ├── config.py               # YAML → HermesConfig
│   ├── io.py                   # 한 run 의 파일 레이아웃 규약
│   ├── agents.py               # Claude Agent SDK 호출 래퍼
│   └── orchestrator.py         # Planner→Generator→Evaluator 루프
└── workspace/
    └── runs/
        └── 20260423-140000-<label>/
            ├── brief.md        # 입력 (복사본)
            ├── spec.md         # Planner 산출
            ├── project/        # Generator 가 만드는 실제 프로그램
            ├── reports/
            │   ├── iter_01.md
            │   ├── iter_02.md
            │   └── latest.md   # 최신 리포트 (Generator 가 다음 iter 때 읽음)
            └── run.log
```

### 핵심 설계 원칙

1. **역할별 독립 컨텍스트.** 세 에이전트는 매번 clean context 로 호출된다.
   이전 상태는 전부 디스크에 있고, 다음 에이전트는 디스크에서 읽는다.
2. **파일 기반 핸드오프.** `brief.md → spec.md → project/ → reports/latest.md`
   의 단방향 흐름. 공유 메모리, 세션 재사용 없음.
3. **회의적 Evaluator.** Evaluator 는 코드만 읽지 않고 실제로 빌드·테스트를
   돌려보고, 스펙 각 항목에 MET/PARTIAL/NOT MET 을 붙인다. 마지막 줄은
   `verdict: PASS` 또는 `verdict: FAIL` 하나. 이 한 줄이 루프 종료 신호.
4. **설정 가능한 iteration.** `config.yaml` 의 `max_iterations` 또는
   `--iterations N` 플래그로 조절. `stop_on_pass: true` 면 PASS 즉시 종료.

---

## 설치

```bash
cd /Users/ask.ahn/Documents/works/ai/claude-hermes

# (권장) 가상환경
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치 (editable install)
pip install -e .

# API 키
cp .env.example .env
# .env 를 열어서 ANTHROPIC_API_KEY 에 실제 키 입력
```

Claude Agent SDK 는 Node.js 로 실행되는 Claude Code CLI 를 내부적으로 호출한다.
먼저 다음이 PATH 에 있어야 한다.

```bash
node --version          # v18 이상 권장
npm install -g @anthropic-ai/claude-code   # claude CLI 설치
claude --version
```

---

## 시작하기 (5단계)

### 1. brief 를 하나 쓴다

`briefs/` 밑에 1~10문장짜리 마크다운을 하나 만든다. 예시는
`briefs/example-todo-cli.md` 를 참고.

brief 는 "무엇을 왜" 까지만 적는다. 스택이나 파일 구조는 Planner 가 고른다.

### 2. iteration 수를 정한다

`config.yaml` 에서 `max_iterations` 를 바꾸거나, 실행할 때
`--iterations N` 으로 오버라이드한다.

```yaml
max_iterations: 5     # Generator↔Evaluator 라운드 최대치
stop_on_pass: true    # PASS 나오면 즉시 종료
replan_every: 0       # > 0 이면 N iteration 마다 Planner 다시 호출 (spec 보정)
```

### 3. 실행

```bash
# 가상환경이 활성화돼 있으면 이 이름으로 실행
claude-hermes briefs/example-todo-cli.md --iterations 5 --label todo

# 시스템에 다른 hermes CLI 가 있거나 PATH 충돌이 걱정되면 모듈 실행이 안전
python -m hermes briefs/example-todo-cli.md --iterations 5 --label todo
```

> 참고: CLI 이름이 `claude-hermes` 인 이유는 시스템에 다른 `hermes` 명령이
> 이미 존재하는 경우(예: 별도의 Hermes 도구)를 피하기 위함. 충돌이 없는
> 환경이라면 `pyproject.toml` 의 `[project.scripts]` 에서 이름을 바꿔도 된다.

콘솔은 이렇게 흐른다.

```
──── Planner (initial) ────────────────────────────────
[14:00:02] planner: turns=6 cost=$0.0412
──── Generator — iteration 1 ──────────────────────────
[14:01:10] generator[1]: turns=32 cost=$0.1833
──── Evaluator — iteration 1 ──────────────────────────
[14:02:05] evaluator[1]: turns=14 cost=$0.0521
[14:02:05] iteration 1 verdict: FAIL
──── Generator — iteration 2 ──────────────────────────
...
```

### 4. 산출물 확인

`workspace/runs/<timestamp>-<label>/` 안을 본다.

```bash
ls workspace/runs
cd workspace/runs/20260423-140000-todo
cat spec.md                    # Planner 가 쓴 스펙
ls project/                    # 실제 프로그램
cat reports/latest.md          # 마지막 평가 (verdict 포함)
cat run.log                    # 타임라인 + 비용
```

최종 프로그램은 `project/` 디렉토리 통째로 독립적인 repo 다.
그대로 복사해서 사용하면 된다.

### 5. 반복

brief 를 다듬거나 `max_iterations` 를 늘려 다시 실행. 각 run 은 새 타임스탬프
폴더에 들어가므로 이전 결과는 보존된다.

---

## 동작 타임라인

한 run 한 iteration 을 시간 순서로 보면:

```
brief.md ──► Planner ──► spec.md
                             │
                             ▼
                         Generator ──► project/ (code + README)
                             │
                             ▼
                         Evaluator ──► reports/iter_01.md
                             │             (마지막 줄: verdict: PASS|FAIL)
                             ▼
                         verdict 확인
                         ├─ PASS + stop_on_pass → 종료
                         └─ FAIL → Generator (iter 2) 가 latest.md 를 읽고 수정
                                    ──► project/ 업데이트
                                    ──► Evaluator (iter 2)
                                    ...
```

---

## 흔한 조정 포인트

- **범위가 너무 넓어서 한 iteration 으로 커버 안 될 때**
  `config.yaml` 의 `replan_every: 2` 로 설정하면 Planner 가 스펙을
  중간에 다시 다듬는다 (Milestones 를 잘게 쪼개게 됨).
- **Generator 가 자꾸 gold-plate 할 때**
  `prompts/generator.md` 의 "Stay in project/" 와 "No extra features"
  섹션을 프로젝트 도메인에 맞게 강화한다.
- **Evaluator 가 너무 관대할 때**
  `prompts/evaluator.md` 상단의 "You are not the Generator's cheerleader"
  문단을 더 구체적인 예시로 교체한다. LLM 평가자는 튜닝 가능한 지표이므로
  몇 가지 good/bad 예시를 프롬프트에 붙이면 체감 품질이 크게 오른다.
- **비용 관리**
  `models.generator` 를 `claude-haiku-4-5-20251001` 로 내리면 싸진다.
  Planner/Evaluator 는 Opus/Sonnet 유지 권장 (판단이 품질을 좌우).

---

## 트러블슈팅

- `claude: command not found` → 위의 `npm install -g @anthropic-ai/claude-code`.
- `ANTHROPIC_API_KEY not set` → `.env` 확인, 또는 쉘에 export.
- Evaluator 가 `verdict:` 줄 없이 끝남 → `UNKNOWN` 으로 기록되고 루프는 계속.
  `prompts/evaluator.md` 의 마지막 섹션이 수정되었다면 되돌린다.
- Generator 가 `project/` 바깥 파일을 건드림 → 프롬프트 재강조.
  필요하면 `src/hermes/agents.py` 의 `GENERATOR_TOOLS` 에서 `Write/Edit` 을
  제한하거나, Generator cwd 를 `layout.project` 로 바꿔 루트 접근을 막는다.
