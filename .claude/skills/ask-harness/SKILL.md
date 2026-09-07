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

브리프는 짧은 문장 몇 개짜리 브리프여도 되고, `/simple-e2e:prd-creator`의
`prd.md`와 `/simple-e2e:system-design`의 `sdd.md`를 사용자가 하나로 합친
문서여도 됩니다. 후자의 경우 Planner는 그 안의 아키텍처/DB/API 설계를
재설계하지 않고 그대로 `spec.md`에 반영합니다. Generator는 `spec.md`를
`plan.md`(TDD 체크리스트)로 쪼개 자율적으로 Red-Green-Refactor 사이클을
돌립니다 — 자세한 내용은 각 에이전트 정의를 참고하세요.

이미 PASS까지 끝난 run을 더 발전시키고 싶다면, 브리프 대신 그 run
디렉터리를 넘겨 **resume**할 수 있습니다. 이때는 사람이 새 요구사항을
적어주지 않아도 Planner가 알아서 다음 확장 방향을 창의적으로 정합니다
(아래 3.5 참고).

## 호출 방법

예상되는 형태:

- `/ask-harness <brief_path> [iterations=5] [label]` — 새 run 시작.
- `/ask-harness briefs/example-todo-cli.md 3 todo`
- 자유 형식: "run ask-harness on briefs/foo.md for 4 iterations"
- `/ask-harness <run_dir> [iterations=5]` — **기존 run 이어서 진행(resume)**.
  첫 번째 인자가 브리프 파일이 아니라 이미 `spec.md`를 포함한 run
  디렉터리(`workspace/runs/...`)이면 새로 만들지 않고 그 자리에서 이어갑니다.
  예: `/ask-harness workspace/runs/20260907-133956-todo 2`

인자 개수/의미는 새 run과 resume이 동일합니다 — 사람이 "무엇을 추가하라"는
요구사항 텍스트를 따로 넘기지 않습니다. resume에서는 대신 **Planner가 스스로**
현재 spec.md/project를 보고 다음에 무엇을 확장할지 창의적으로 판단합니다
(아래 3.5 참고). 사람이 구체적인 새 기능을 지시하고 싶다면, 그 내용을
`brief.md`(또는 `spec.md`)에 직접 반영한 뒤 resume하거나, 새 run을 여는
편이 더 명확합니다.

- 첫 번째 위치 인자 — 파일이면 `brief_path`(새 run), 디렉터리이고 그 안에
  `spec.md`가 있으면 `resume_dir`(기존 run 이어가기)로 처리하세요. 그 외
  (존재하지 않는 경로, spec.md 없는 디렉터리)는 오류로 보고하고 중단하세요.
- `iterations` (선택, 기본값 **5**) — Generator↔Evaluator 라운드의 최대 횟수.
  resume 시에는 *이번에 새로 돌릴* 반복 횟수입니다 (기존에 몇 회 돌았는지와
  무관하게 항상 이 숫자만큼 추가로 실행).
- `label` (새 run에서만) — 실행 디렉터리 이름에 붙일 짧은 태그.
- `stop_on_pass`/`replan_every` 관련 자연어 지시("don't stop on PASS",
  "replan every N iterations")는 새 run과 resume에서 완전히 동일하게
  파싱하고 동일하게 동작합니다 — resume이라고 다르게 취급하지 마세요.

기억해둘 만한 두 개의 불리언 값(기본값 표시):

- `stop_on_pass = true` — evaluator가 PASS를 반환하면 루프를 조기 중단.
- `replan_every = 0` — 0보다 크면, N회 반복마다 planner를 다시 호출.

사용자가 이 값들을 제공하지 않았다면 기본값을 사용하세요. 사용자가 명시적으로
"PASS 이후에도 계속 진행해줘" 같은 요청을 했다면 `stop_on_pass = false`로
설정하세요.

## 절차

다음 단계를 **순서대로** 수행하세요. 도구를 직접 사용하세요 — 단계 사이에
사용자에게 확인을 요청하지 마세요.

### 1. 브리프 검증 / 기존 run 감지

- 첫 번째 인자가 **파일**이면 → 새 run 경로(아래 2, 3번을 그대로 수행).
  존재하지 않으면 보고하고 중단하세요.
- 첫 번째 인자가 **디렉터리**이고 그 안에 `spec.md`가 있으면 → **resume**
  경로. `run_dir`을 그 경로로 고정하고 2, 3번을 건너뛰어 3.5로 가세요.
- 그 외(존재하지 않는 경로, spec.md 없는 디렉터리)는 보고하고 중단하세요.
- `iterations`가 양의 정수가 아니라면 보고하고 중단하세요.

### 2. 실행 디렉터리 생성 (새 run만)

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

### 3. Planner (한 번, 새 run만)

Task 도구를 통해 `planner` 서브 에이전트를 호출하세요. 실행 디렉터리를
컨텍스트로 전달하세요. 서브 에이전트에게 보낼 프롬프트 예시:

> `<run_dir>/brief.md`를 바탕으로 `<run_dir>`에 `spec.md`를 작성하세요.
> 당신의 시스템 프롬프트에 있는 구조를 따르세요. 코딩을 시작하지 마세요.

반환된 후, `<run_dir>/spec.md`가 존재하는지 확인하세요. 존재하지 않으면
중단하고 보고하세요.

### 3.5. Resume 준비 (resume 경로만)

새 run의 3번("Planner 한 번")에 대응하는, resume의 필수 1회 Planner 호출입니다.
차이는 하나뿐입니다: 새 run은 `brief.md`를 spec.md로 옮기지만, resume은
사람이 새로 지시한 내용이 없으므로 **Planner가 스스로 다음 확장 방향을
창의적으로 정합니다.**

1. `<run_dir>/reports/`에서 기존 `iter_NN.md` 중 가장 큰 NN을 찾으세요
   (없으면 0으로 간주). 이번 루프는 `start_i = NN + 1`부터
   `start_i + iterations - 1`까지 돕니다 — 이전에 몇 회 돌았든 이번에는
   사용자가 지정한 `iterations` 횟수만큼 새로 실행합니다.
2. Task 도구로 `planner`를 **반드시 1회** 호출하세요(3번과 마찬가지로
   `replan_every` 설정과 무관한, resume 진입 시의 고정 절차입니다):

   > `<run_dir>`을 이어서 확장하세요. 사람이 지정한 새 요구사항은 없습니다 —
   > 기존 `spec.md`, `reports/latest.md`, `project/README.md`를 읽고, 지금
   > 상태에서 다음으로 추가하면 좋을 기능/사용성 개선을 당신이 직접
   > 창의적으로 판단해 `spec.md`에 새 마일스톤과 인수 기준으로 추가하세요.
   > 당신의 시스템 프롬프트에 있는 "브리프 없는 창의적 확장" 절차를
   > 따르세요.

   Planner는 이 프롬프트를 보고 자신의 시스템 프롬프트에 정의된 창의적
   확장 절차를 수행합니다 — 오케스트레이터는 무엇을 추가할지 지시하지
   않습니다.
3. `brief.md`는 건드리지 마세요 — 이전 run의 원본 브리프 그대로 둡니다.

### 4. 반복 루프

`i`를 (새 run이면) 1부터, (resume이면) `start_i`부터 시작해 각각
`iterations`번(즉 새 run은 `iterations`까지, resume은
`start_i + iterations - 1`까지) 돌면서:

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
