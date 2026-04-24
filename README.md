# claude-hermes

Planner ↔ Generator ↔ Evaluator 세 에이전트가 파일로만 통신하며 원하는
프로그램을 자동으로 반복 개발하는 Claude Code 하네스.
Anthropic 의
[Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
기고의 패턴을 **Claude Code sub-agents + skill** 만으로 구현한다. Python 이나
별도 SDK 설치는 필요 없다.

---

## 구조

```
claude-hermes/
├── .claude/
│   ├── agents/
│   │   ├── planner.md      # brief → spec.md
│   │   ├── generator.md    # spec + 피드백 → project/
│   │   └── evaluator.md    # project → reports/iter_NN.md (verdict: PASS|FAIL)
│   └── skills/
│       └── hermes/
│           └── SKILL.md    # /hermes 가 루프 오케스트레이션
├── briefs/                 # 당신이 쓰는 한 장짜리 요청서들
│   └── example-todo-cli.md
├── workspace/
│   └── runs/               # 각 run 의 산출물이 쌓이는 곳
└── README.md
```

### 동작 원리

1. 사용자가 Claude Code 세션에서 `/hermes <brief> [iterations]` 를 친다.
2. 메인 대화가 **skill** 을 로드하여 오케스트레이터 역할을 맡는다.
3. 오케스트레이터는 `Task` 툴로 **sub-agent** 들을 호출한다:
   `planner` → (`generator` → `evaluator`) × N
4. 세 sub-agent 는 독립 컨텍스트로 돌고, 모든 통신은 `workspace/runs/<ts>/`
   아래 파일로만 이뤄진다.
5. Evaluator 가 리포트의 마지막 줄에 `verdict: PASS` 를 쓰거나 iteration 이
   상한에 닿으면 루프가 끝난다.

### 핵심 설계 원칙 (아티클 대응)

- **역할별 독립 컨텍스트.** 세 sub-agent 는 `Task` 툴 호출마다 clean context.
- **파일 기반 핸드오프.** `brief.md → spec.md → project/ → reports/latest.md`.
- **회의적 Evaluator.** 코드만 읽지 않고 실제 빌드·테스트를 Bash 로 돌리고,
  스펙의 각 acceptance criterion 에 MET/PARTIAL/NOT MET 을 붙인다.
  리포트의 **마지막 줄** 은 반드시 `verdict: PASS` 또는 `verdict: FAIL`.
- **write-first 리포트.** Evaluator 의 첫 tool call 은 항상 skeleton 리포트를
  `verdict: FAIL` 로 먼저 쓰는 것. 도중에 중단돼도 보수적 결과가 남는다.
- **설정 가능한 iteration.** `/hermes` 호출 시 두 번째 인자로 지정.

---

## 사전 준비

1. **Claude Code CLI 설치 & 로그인**

   ```bash
   npm install -g @anthropic-ai/claude-code
   claude --version
   claude login          # 브라우저로 Anthropic 로그인
   ```

   Python 환경, `.env`, API 키, 별도 의존성 모두 **불필요**하다. `claude login`
   으로 만들어진 OAuth 세션을 그대로 쓴다.

2. **Claude Code 를 이 프로젝트 루트에서 연다**

   ```bash
   cd /Users/ask.ahn/Documents/works/ai/claude-hermes
   claude
   ```

   Claude Code 가 이 디렉토리에서 열리면 `.claude/agents/` 와
   `.claude/skills/hermes/` 를 자동 인식한다.

---

## 시작하기 (3단계)

### 1. brief 를 하나 쓴다

`briefs/` 밑에 1~10문장짜리 마크다운을 하나 만든다. 예시는
`briefs/example-todo-cli.md` 를 참고. Brief 는 "무엇을 왜" 까지만 적는다.
스택·파일 구조·라이브러리 선택은 Planner 가 한다.

### 2. `/hermes` 로 실행

Claude Code 세션의 프롬프트에 입력:

```
# Iteration 1 진행
/hermes briefs/example-todo-cli.md 1 todo

# Iteration 2 진행, Iteration 시 PASS 가 나도 다음 Iteration 진행, 매 iteration 마다 plan 재실행
/hermes briefs/example-todo-cli.md 2 todo, don't stop on PASS, replan every 1 iterations
```

인자 규약:

| 위치 | 이름        | 필수 | 기본값 | 설명                                     |
|------|-------------|------|--------|------------------------------------------|
| 1    | brief_path  | ✓    | —      | 브리프 마크다운 경로                     |
| 2    | iterations  | —    | `5`    | Generator↔Evaluator 최대 라운드          |
| 3    | label       | —    | 없음   | run 디렉토리 이름 뒤에 붙일 짧은 태그    |

자연어 호출도 된다: "run hermes on briefs/foo.md for 3 iterations".

진행 중에는 main 대화가 sub-agent 를 호출할 때마다 Task 툴의 상태가 UI 에
표시된다. Planner (약 1 분) → Generator (2~5 분) → Evaluator (2~5 분) 순으로
진행된다.

### 3. 산출물 확인

```
workspace/runs/20260424-130001-todo/
├── brief.md            # 원본 brief 의 복사본
├── spec.md             # Planner 산출 (최종)
├── project/            # ← 실제로 만들어진 프로그램
├── reports/
│   ├── iter_01.md
│   ├── iter_02.md
│   └── latest.md
└── (run.log 없음 — 메인 대화 자체가 로그)
```

- `project/` 는 독립된 repo 다. 그대로 복사해서 쓰면 된다.
- 성공 판정은 `reports/latest.md` 마지막 줄의 `verdict: PASS`.

---

## 동작 타임라인

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
  호출 시 "replan every 2 iterations" 같이 말하거나, SKILL.md 상단의 기본값을
  편집해 `replan_every = 2` 로 둔다. Planner 가 중간에 Milestones 를 다시
  쪼개게 된다.
- **Generator 가 자꾸 gold-plate 할 때**
  `.claude/agents/generator.md` 의 "Build what the spec says, not more."
  섹션을 프로젝트 도메인에 맞게 강화한다.
- **Evaluator 가 너무 관대할 때**
  `.claude/agents/evaluator.md` 의 "not the Generator's cheerleader" 문단을
  구체적 예시로 교체한다. Few-shot 예시 한두 개만 붙여도 체감 품질이 크게
  오른다.
- **PASS 후에도 계속 돌리고 싶을 때**
  "keep going past PASS" 또는 "don't stop on PASS" 같이 말한다. 스킬이
  `stop_on_pass = false` 로 해석한다.

---

## 이전 버전과의 차이

이전에는 Python Anthropic Agent SDK 기반 오케스트레이터(`src/hermes/`) 였다.
지금 버전은 그 역할을 Claude Code 의 sub-agents + skill 로 대체했고, 다음
파일들이 더 이상 없다: `src/`, `pyproject.toml`, `config.yaml`,
`.env.example`, `prompts/`. 변경의 장점:

- Python/venv/API 키 설정 전무 — `claude login` 만 하면 된다.
- 오케스트레이션이 대화 내에서 투명하게 보인다 (sub-agent Task 툴 표시).
- 프롬프트·절차 조정이 파일 편집만으로 끝난다. 코드 수정과 재설치 없음.

기존에 만들어 둔 `workspace/runs/*` 결과물은 그대로 남아있고, 신규 run 도
같은 디렉토리 구조를 쓴다.

---

## 트러블슈팅

- **`/hermes` 를 쳤는데 skill 을 못 찾는다** → Claude Code 를 **이 프로젝트
  루트** (`claude-hermes/`) 에서 실행했는지 확인. `.claude/skills/hermes/SKILL.md`
  가 존재해야 한다.
- **Sub-agent 이름(planner/generator/evaluator)을 못 찾는다** →
  `.claude/agents/*.md` 파일 존재 확인. 파일 이름과 프론트매터의 `name:` 이
  일치해야 한다.
- **Evaluator 가 `verdict:` 줄 없이 끝남** → skeleton 이 `verdict: FAIL` 로
  시작하므로 최소 FAIL 은 남는다. 완전히 파일이 비면 `.claude/agents/evaluator.md`
  의 write-first 섹션을 건드렸는지 확인.
- **Generator 가 `project/` 바깥 파일을 건드림** → `.claude/agents/generator.md`
  의 "Stay in project/" 문단을 강화. 필요하면 `tools:` 에서 `Edit/Write`
  허용 범위를 조정할 수 있다.
- **Bash 단계에서 hang** → Evaluator 프롬프트에 이미 "Prefer `timeout 60`"
  가이드가 있다. 재발하면 구체적 명령(예: `pytest -q --timeout=60`)을
  acceptance criterion 에 못 박는다.
