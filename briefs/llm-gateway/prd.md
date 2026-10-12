# PRD: llm-gateway

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 서비스 이름 | llm-gateway |
| 한 줄 설명 | vLLM 추론 서버 앞단에서 인증(API Key)·요청 제어(Rate Limit/토큰 사용량 제한)·로드밸런싱·성능 관측(TTFT/TPOT/ITL)을 담당하는 Go 기반 LLM 게이트웨이 |
| 핵심 가치 | vLLM을 직접 노출하지 않고 **안전하게**(키 기반 접근 제어), **안정적으로**(과사용/폭주 방지), **확장 가능하게**(다중 vLLM 백엔드 로드밸런싱), **관측 가능하게**(요청별 지연시간 지표) 서비스한다 |
| 언어/런타임 | Go (최신 안정 버전) |

## 2. 타겟 유저 및 사용자 시나리오

- **타겟 유저**: 내부·외부 구분 없이, 발급된 API Key를 가진 모든 클라이언트(사람/서비스). 현재 범위에서는 테넌트/조직 단위 구분은 두지 않고 "Key 단위"로만 식별·제어한다.
- **운영자(관리자)**: 별도 관리자 토큰으로 Key를 발급·폐기·조회하고, 설정 파일로 rate limit/토큰 한도/백엔드 목록/로드밸런싱 전략을 관리한다.
- **핵심 시나리오**:
  1. 운영자가 관리자 API로 신규 클라이언트용 API Key를 발급한다.
  2. 클라이언트는 기존 OpenAI SDK/클라이언트를 그대로 사용해 `base_url`만 llm-gateway로 바꿔 `/v1/chat/completions` 등을 호출한다.
  3. Gateway는 인증 → Rate limit/토큰 한도 검사 → 로드밸런싱으로 vLLM 백엔드 선택 → 프록시 → 응답(스트리밍 포함) → TTFT/TPOT/ITL 로그 기록까지 처리한다.
  4. 백엔드가 여러 대면 자동 분산되고, 한 대만 있으면 그 backend로만 전달된다.
  5. 백엔드가 죽으면 헬스체크로 자동 감지해 라우팅 대상에서 제외한다.

## 3. 핵심 기능 명세

### 필수 기능

1. **API Key 발급/폐기/조회** — 관리자 API(REST)로 처리. 관리자 API 자체는 설정 파일의 정적 관리자 토큰으로 인증.
2. **요청 인증** — 클라이언트 요청은 `Authorization: Bearer <key>` 헤더로 인증. Key는 상태 파일에 SHA-256 해시로 저장되며, 평문 Key는 발급 응답에서 단 한 번만 노출된다.
3. **Rate limit** — Key별로 요청 수(RPS/RPM)와 토큰 수(TPM)를 모두 제한. 설정 파일에서 Key/기본값 단위로 조정 가능.
4. **토큰 사용량 제한** — 두 가지를 모두 지원한다: (a) 요청당 `max_tokens` 상한치, (b) 기간(일/월 등)별 누적 토큰 할당량. 초과 시 요청을 거부한다.
5. **로드밸런싱** — 다중 vLLM 백엔드에 대해 "라운드로빈+헬스체크"와 "최소 연결/요청 기반" 두 전략을 모두 구현하고 설정 파일에서 전략을 선택할 수 있게 한다. 기본값은 라운드로빈+헬스체크. 백엔드가 1개뿐이면 해당 백엔드로만 라우팅된다.
6. **백엔드 헬스체크** — 설정된 주기(기본값 5초)마다 각 vLLM 백엔드에 능동적으로 헬스체크 요청을 보내 상태를 갱신하고, 불통 백엔드는 라우팅 대상에서 자동 제외한다.
7. **OpenAI 호환 프록시** — `/v1/chat/completions`, `/v1/completions` 등 vLLM이 이미 제공하는 OpenAI 호환 엔드포인트를 그대로 프록시한다. 스트리밍(SSE, `stream=true`) 필수 지원.
8. **토큰 카운팅** — vLLM 응답의 `usage` 필드(`prompt_tokens`/`completion_tokens`)를 신뢰하는 방식과 Gateway 자체 토크나이저로 계산하는 방식을 모두 구현하고 설정으로 선택 가능하게 한다. 기본값은 vLLM `usage` 필드 신뢰.
9. **성능 관측 로깅** — 요청당 TTFT(Time To First Token), TPOT(Time Per Output Token), ITL(Inter-Token Latency)을 측정해 로그로 남긴다. 사람이 읽기 쉬운 텍스트 로그와 구조화 JSON 로그(1요청 = 1줄)를 모두 지원하고 기본값은 구조화 JSON. 출력 대상은 stdout(기본)과 파일 중 설정으로 선택.
10. **파일 기반 상태 저장 + 스토리지 추상화** — 현재는 Key/사용량/설정 등 필요한 값을 JSON 파일로 읽고 쓴다. 다만 저장소는 Go 인터페이스(`Store`)로 추상화해, 향후 구현체만 교체하면 Redis나 RDB로 전환할 수 있도록 설계한다.

### 향후 확장 (이번 범위 아님, Out of scope에서 재확인)

- Redis/RDB 스토리지 구현체
- 다중 Gateway 인스턴스 간 분산 상태 동기화(현재는 파일 기반이라 단일 인스턴스 가정)
- 조직/테넌트 단위 관리, 관리자 웹 UI
- Key 자기발급(셀프서비스) API

## 4. 기술 스택

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 | Go (최신 안정 버전) | 요청대로, 고성능 프록시/동시성 처리에 적합 |
| 웹 프레임워크 | Gin | 라우팅/미들웨어(인증, rate limit)가 간결하고 생태계가 큼 |
| 설정 파일 | YAML (`config.yaml`) | 사람이 직접 편집하는 설정에 적합 |
| 상태 파일 | JSON (`keys.json`, `usage.json` 등) | 기계가 쓰고 읽는 상태 데이터에 적합, 추후 Redis/RDB 마이그레이션 시 구조 매핑이 쉬움 |
| 스토리지 추상화 | `storage.Store` Go 인터페이스 + 파일 구현체(`FileStore`) | Redis/RDB 구현체로 교체 시 인터페이스만 만족하면 되도록 |
| 로깅 | 구조화 JSON(요청당 1줄) 기본, 텍스트 로그 옵션 | 관측성 도구와 바로 연동 가능하면서도 로컬에서 읽기도 쉽게 |
| 빌드 | Makefile — `make build OS=darwin ARCH=arm64` 등으로 darwin/linux × amd64/arm64 단일 바이너리 크로스 컴파일 | 외부 런타임 의존 없이 바이너리 하나로 배포 |
| 배포 | Dockerfile — `linux/amd64`, `linux/arm64` 멀티 아키텍처 이미지(buildx) | Mac(Apple Silicon 포함)과 Linux 호스트 모두에서 동일 이미지로 구동 |

## 5. 주요 API 흐름

### 관리자 흐름 (Key 발급)

```
운영자 → POST /admin/keys (Authorization: Bearer <admin_token>)
       ← 201 { "key": "sk-...", "key_id": "...", "limits": {...} }   ← 평문 key는 이 응답에서만 노출
```

### 클라이언트 요청 흐름

```
Client → POST /v1/chat/completions (Authorization: Bearer <api_key>, stream=true 가능)
           │
           ▼
      [인증 미들웨어] key 해시 조회, 유효성 확인
           │
           ▼
      [Rate limit 검사] RPS/RPM, TPM 한도 확인
           │
           ▼
      [토큰 한도 검사] 요청당 max_tokens 상한 + 기간별 누적 할당량 확인
           │
           ▼
      [로드밸런서] 헬스체크 통과한 백엔드 중 전략에 따라 1개 선택
           │
           ▼
      [프록시] 선택된 vLLM으로 요청 전달 (스트리밍이면 SSE 그대로 중계)
           │
           ▼
      [메트릭 수집] TTFT / TPOT / ITL 측정, 토큰 사용량 집계(usage 필드 or 자체 토크나이저)
           │
           ▼
      [로그 기록] stdout/파일에 구조화 JSON 1줄
           │
           ▼
      Client ← 응답(스트리밍 청크 또는 완성 응답)
```

### 백엔드 헬스체크 흐름 (백그라운드)

```
매 health_check_interval(기본 5초)마다:
  각 vLLM 백엔드에 헬스체크 요청
    성공 → 라우팅 후보에 포함(복귀)
    실패 → 라우팅 후보에서 제외, 다음 주기에 재시도
```

## 6. 상세 기능 명세 및 예외 처리 정책

모든 에러 응답은 **OpenAI 에러 포맷**을 따른다: `{"error": {"message": "...", "type": "...", "code": "..."}}`.

| 상황 | HTTP 상태 | type/code 예시 | 비고 |
|---|---|---|---|
| API Key 누락/무효 | 401 | `invalid_api_key` | |
| Rate limit(RPS/RPM/TPM) 초과 | 429 | `rate_limit_exceeded` | `Retry-After` 헤더 포함 |
| 요청당 max_tokens 상한 초과 | 400 | `invalid_request_error` | 요청 자체가 잘못된 것으로 취급 |
| 기간별 토큰 할당량 소진 | 429 | `quota_exceeded` | |
| 모든 백엔드 헬스체크 실패(가용 백엔드 없음) | 503 | `no_available_backend` | |
| 관리자 API 인증 실패 | 401 | `invalid_admin_token` | |
| 설정/상태 파일 파싱 오류 | (기동 실패) | - | 프로세스는 기동하지 않고 명확한 원인을 stderr에 남긴다 |

- 백엔드로부터의 5xx 응답은 그대로 클라이언트에 전달하되, 로그에는 실패로 기록하고 다음 요청부터 헬스체크 결과에 따라 해당 백엔드를 회피할 수 있게 한다.
- 스트리밍 도중 백엔드 연결이 끊기면 이미 전송된 청크는 유지하고, 남은 스트림은 에러 이벤트로 종료한다(부분 응답+에러를 클라이언트가 구분할 수 있게).

## 7. 운영 가이드 (설정/로그 예시)

### config.yaml 예시

```yaml
server:
  listen_addr: ":8080"

admin:
  token: "${ADMIN_TOKEN}"   # 환경변수 주입, 하드코딩 금지

backends:
  - url: "http://vllm-1:8000"
  - url: "http://vllm-2:8000"

load_balancer:
  strategy: "round_robin_healthcheck"   # round_robin_healthcheck | least_requests
  health_check_interval: "5s"

rate_limit:
  default:
    rpm: 60
    tpm: 100000

token_limit:
  default:
    max_tokens_per_request: 4096
    quota_period: "monthly"
    quota_tokens: 1000000

token_counting:
  method: "usage_field"   # usage_field | tokenizer

storage:
  keys_file: "./data/keys.json"
  usage_file: "./data/usage.json"

logging:
  format: "json"          # json | text
  output: "stdout"        # stdout | file
  file_path: "./logs/llm-gateway.log"
```

### 로그 라인 예시 (구조화 JSON, 기본값)

```json
{"ts":"2026-09-08T10:00:00Z","request_id":"req_abc123","key_id":"key_001","model":"qwen2.5-7b","backend":"http://vllm-1:8000","stream":true,"ttft_ms":120,"tpot_ms":18.4,"itl_ms":[15,17,19,18],"prompt_tokens":42,"completion_tokens":256,"status":200}
```

### 관리자 API 예시

```bash
# Key 발급
curl -X POST http://gateway:8080/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name":"team-a","rpm":60,"tpm":100000}'

# Key 폐기
curl -X DELETE http://gateway:8080/admin/keys/key_001 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## 8. 제약사항 및 보안 요구사항

- **단일 인스턴스 가정**: 상태(Key/사용량)를 로컬 JSON 파일로 관리하므로, 현재 설계는 Gateway를 단일 인스턴스로 운영하는 것을 전제로 한다. 여러 인스턴스를 동시에 띄우면 rate limit/토큰 사용량 카운트가 인스턴스별로 분리되어 정합성이 깨진다. 다중 인스턴스 수평 확장은 `storage.Store`를 Redis/RDB 구현체로 교체한 이후의 범위다.
- **스토리지 교체 용이성**: `storage.Store` 인터페이스(Key 조회/생성/폐기, 사용량 증가/조회 등)를 정의하고 `FileStore`가 이를 구현한다. Redis/RDB 전환 시 이 인터페이스를 만족하는 새 구현체만 추가하면 상위 로직(인증/rate limit/토큰 한도) 변경이 없어야 한다.
- **비밀값 관리**: 관리자 토큰은 설정 파일에 직접 쓰지 않고 환경변수(`${ADMIN_TOKEN}` 형태로 YAML에서 참조)로 주입한다. 소스코드에 어떤 비밀값도 하드코딩하지 않는다.
- **API Key 저장**: 평문 저장 금지. SHA-256 해시로 저장하고, 평문은 발급 응답에서 1회만 노출한다.
- **로그의 민감정보**: 로그에 API Key 평문이나 프롬프트/응답 본문 전체를 남기지 않는다 (메트릭/메타데이터만 기록).
- **TLS**: Gateway 자체는 HTTP로 동작하고, TLS 종료는 앞단 리버스 프록시/로드밸런서에서 처리하는 것을 전제로 한다(현재 범위 밖).
- **SQL 관련 규칙**: 현재 범위(파일 저장)에는 해당 없음. 향후 RDB 구현체 추가 시 파라미터 바인딩을 강제한다.
- **오픈소스 라이선스**: 사용하는 Go 모듈(Gin 등)은 MIT/Apache 2.0 등 허용 라이선스만 사용하고, `go.mod`에 의존성과 버전을 명시한다.

## 9. Out of scope (명시적으로 이번 범위에서 제외)

- Redis/RDB 스토리지 구현체 (인터페이스만 준비, 구현은 후속)
- 다중 Gateway 인스턴스 간 분산 상태 동기화
- 조직/테넌트 단위 쿼타, 멀티테넌시
- 관리자 웹 UI (관리자 REST API만 제공)
- Key 자기발급(셀프서비스) API
- Gateway 자체 TLS 종료
- vLLM 외 다른 추론 서버(TGI 등) 지원
