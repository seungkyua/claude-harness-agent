---
name: ask-harness
description: Planner→Generator→Evaluator 루프를 실행하여 짧은 브리프로부터 프로그램을 자율적으로 개발합니다. 사용자가 /ask-harness를 입력하거나 브리프 파일에 대해 "ask-harness 루프를 실행해줘"라고 요청할 때 사용하세요. Task 도구를 통해 세 개의 서브 에이전트를 오케스트레이션하고 PASS가 나오거나 최대 반복 횟수에 도달할 때까지 반복합니다.
---

# Ask-Harness — 반복적 프로그램 개발 루프

이 스킬은 `.claude/agents/`에 정의된 세 개의 서브 에이전트를 오케스트레이션합니다:

- **planner** → 브리프를 읽고 `spec.md`를 작성
- **generator** → spec과 최신 보고서를 읽고 `project/`를 작성/수정
- **evaluator** → `project/`에 테스트를 실행하고 `verdict: PASS` 또는
  `verdict: FAIL`로 끝나는 `reports/iter_NN.md`를 작성

세 에이전트는 컨텍스트를 공유하지 않습니다. 이들은 오직 실행 디렉터리 안의
파일을 통해서만 소통합니다. 당신(메인 대화)이 오케스트레이터입니다.

## 호출 방법

예상되는 형태:

- `/ask-harness <brief_path> [iterations=5] [label]`
- `/ask-harness briefs/example-todo-cli.md 3 todo`
- 자유 형식: "run ask-harness on briefs/foo.md for 4 iterations"

인자는 다음과 같이 파싱하세요:

- `brief_path` (필수) — 마크다운 브리프의 상대 또는 절대 경로.
- `iterations` (선택, 기본값 **5**) — Generator↔Evaluator 라운드의 최대 횟수.
- `label` (선택) — 실행 디렉터리 이름에 붙일 짧은 태그.

기억해둘 만한 두 개의 불리언 값(기본값 표시):

- `stop_on_pass = true` — evaluator가 PASS를 반환하면 루프를 조기 중단.
- `replan_every = 0` — 0보다 크면, N회 반복마다 planner를 다시 호출.

사용자가 이 값들을 제공하지 않았다면 기본값을 사용하세요. 사용자가 명시적으로
"PASS 이후에도 계속 진행해줘" 같은 요청을 했다면 `stop_on_pass = false`로
설정하세요.

## 절차

다음 단계를 **순서대로** 수행하세요. 도구를 직접 사용하세요 — 단계 사이에
사용자에게 확인을 요청하지 마세요.

### 1. 브리프 검증

- `brief_path`가 존재하는지 확인하세요. 없다면 보고하고 중단하세요.
- `iterations`가 양의 정수가 아니라면 보고하고 중단하세요.

### 2. 실행 디렉터리 생성

```
workspace/runs/<YYYYMMDD-HHMMSS>[-<label>]/
├── brief.md       ← 원본 브리프의 복사본
├── spec.md        ← planner가 작성
├── project/       ← generator가 작성
└── reports/       ← evaluator가 작성
```

Bash를 사용해 디렉터리를 만들고 브리프를 복사하세요. 예시:

```bash
ts=$(date +%Y%m%d-%H%M%S)
run="workspace/runs/${ts}${label:+-$label}"
mkdir -p "$run/project" "$run/reports"
cp "$brief_path" "$run/brief.md"
```

실행 디렉터리 경로를 기억해두세요 — 모든 서브 에이전트 호출이 이를 참조합니다.

### 3. Planner (한 번)

Task 도구를 통해 `planner` 서브 에이전트를 호출하세요. 실행 디렉터리를
컨텍스트로 전달하세요. 서브 에이전트에게 보낼 프롬프트 예시:

> `<run_dir>/brief.md`를 바탕으로 `<run_dir>`에 `spec.md`를 작성하세요.
> 당신의 시스템 프롬프트에 있는 구조를 따르세요. 코딩을 시작하지 마세요.

반환된 후, `<run_dir>/spec.md`가 존재하는지 확인하세요. 존재하지 않으면
중단하고 보고하세요.

### 4. 반복 루프

`i`를 1부터 `iterations`까지 돌면서:

#### 4a. (선택) 재계획

`replan_every > 0`이고 `i > 1`이며 `(i - 1) % replan_every == 0`이면, 다음과
같은 프롬프트로 planner를 다시 호출하세요:

> `<run_dir>/reports/latest.md`를 바탕으로 `<run_dir>/spec.md`를 수정하세요.
> 범위를 부풀리지 않으면서 evaluator의 지적 사항을 해결하세요.

#### 4b. Generator

`generator` 서브 에이전트를 호출하세요. 프롬프트:

> Iteration `<i>`. 실행 디렉터리: `<run_dir>`. `spec.md`를 읽고(2회차 이상
> 반복이면 `reports/latest.md`도) 그에 맞게 `project/`를 구현하거나 수정하세요.
> 끝내기 전에 빌드가 되고 자체 테스트가 통과함을 증명하세요.

#### 4c. Evaluator

`evaluator` 서브 에이전트를 호출하세요. 프롬프트:

> Iteration `<i>`. 실행 디렉터리: `<run_dir>`. 보고서를 `reports/iter_<NN>.md`
> (NN은 `<i>`를 2자리로 0 채움한 값)에 작성하고 `reports/latest.md`에도
> 그대로 반영하세요. 당신의 시스템 프롬프트에 있는 선(先)작성 프로토콜을
> 따르세요. `verdict: PASS` 또는 `verdict: FAIL`로 끝내세요.

#### 4d. 판정 결과 파싱

`<run_dir>/reports/iter_<NN>.md`의 마지막 비어있지 않은 줄을 읽으세요. 이는
`verdict: PASS` 또는 `verdict: FAIL`과 일치해야 합니다(대소문자 무시). 둘 중
어느 것과도 일치하지 않으면 `UNKNOWN`으로 기록하세요.

- 판정 결과가 PASS이고 `stop_on_pass`가 참이면, 루프를 중단하세요.
- 서브 에이전트에 오류가 발생했다면(Task가 오류를 반환) 기록하고 중단하세요 —
  이후 반복은 그저 실패를 재생산할 뿐입니다.

### 5. 요약

루프가 끝난 후, 사용자에게 간결한 요약을 출력하세요:

- 실행 디렉터리 (절대 경로)
- 실제로 실행된 반복 횟수
- 최종 판정 결과 (마지막 반복 보고서 기준)
- `project/` 경로 (실제 산출물)
- `reports/latest.md` 경로 (최종 평가)

예시:

```
Run directory: /…/workspace/runs/20260424-120001-todo
Iterations ran: 2
Final verdict: PASS
Project:       /…/workspace/runs/20260424-120001-todo/project
Latest report: /…/workspace/runs/20260424-120001-todo/reports/latest.md
```

## 오케스트레이터(당신)를 위한 규칙

- **`project/`나 `reports/`를 직접 건드리지 마세요.** 서브 에이전트만 그곳에
  씁니다. 당신은 디렉터리 골격을 만들고 판정 결과를 확인하기 위해 파일을
  읽기만 하세요.
- **`replan_every`가 지시하지 않는 한 재계획하지 마세요.** planner는 비용이
  크고, 너무 자주 재계획하면 spec이 불안정해집니다.
- **서브 에이전트의 텍스트 출력을, 실행 종료 요약 외에는 메인 대화에서
  요약하지 마세요.** 디스크 위의 산출물이 진실의 원천입니다.
- **서브 에이전트 실패 시 우아하게 중단하세요.** 그 시점까지 성공한 것을
  보고하세요; 실행 중간에 복구를 시도하지 마세요.
- **타임아웃은 서브 에이전트의 책임입니다.** 서브 에이전트가 Bash 호출 안에서
  멈춘다면, 이는 당신이 우회할 문제가 아니라 프롬프트 조정 문제입니다
  (evaluator 프롬프트의 타임아웃 안내 참고).

## 인증 참고 사항

프로그램 실행은 Claude Code CLI 세션 자체를 사용합니다 — API 키나 `.env`
설정이 필요하지 않습니다. 로그인되어 있다면(`claude login`), 이 루프는
별도 설정 없이 바로 동작합니다.
