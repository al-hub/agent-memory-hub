# Memcarry 실전 사용 시나리오

> 기억을 많이 쌓는 도구가 아니라, 다음 작업자가 근거를 확인하고 바로 이어가게 하는 continuity skill이다.

이 문서는 worktree를 제외하고, 처음 설치한 사용자가 한 PC에서 Codex·Claude·Gemini·AGY를 번갈아 사용하는 실제 흐름을 다룬다. AGY는 Antigravity CLI의 native `PreInvocation` plugin으로 같은 bounded context를 받는다.

## 먼저 보는 차이

| 상황 | Memcarry 없이 | Memcarry 사용 |
| --- | --- | --- |
| 다음 날 재개 | 긴 대화, 메모, 현재 diff를 다시 훑으며 추측 | `RESUME` 맥락으로 목표·완료·다음 행동을 받고 파일과 대조 |
| AI 교대 | 이전 AI의 판단·실패·검증 결과를 수동 복사 | Codex → Claude → Gemini → AGY가 같은 L2 기록과 인계로 연결 |
| 중단/재시작 | 마지막 메시지 이후 상태가 불명확 | checkpoint와 durable progress를 기준으로 누락 구간을 표시 |
| 결정 재사용 | 같은 실험을 다시 하거나 이유를 잊음 | 결정·근거·불확실성을 scope-first recall로 조회 |
| 성능/버그 장기 작업 | 측정 조건과 가설이 세션마다 섞임 | 조건·원본·판정·다음 실험을 분리해 누적 |

핵심은 자동 저장이 아니다. “memcarry에 남겨줘”라고 요청하면 agent가 실제 durable write를 실행하고 ID·범위·요약을 확인해야 한다. hook은 시작 시 bounded context를 주지만 대화 전체를 백업하지 않는다.

## 설치와 확인

```bash
npx --allow-git=all -y github:al-hub/memcarry install --agents all
npx --allow-git=all -y github:al-hub/memcarry status --agents all
```

`status`의 `hooked`는 설정이 존재한다는 뜻이다. 실제 소비 여부는 각 CLI의 hook 실행을 확인해야 한다. `--agents all`은 Codex, Claude, Gemini, AGY를 함께 구성한다.

## 기본방식 — 한 AI와 다음 세션으로 이어가기

### 1. 결정과 이유 보존

**상황:** startup A/B 결과가 미미해 중복 fast-path를 보류했다.

사용하지 않으면 다음 세션에서 “왜 안 했지?”를 다시 조사하거나 같은 최적화를 반복한다.

```text
두 번의 A/B 조건·결과·해석을 구분해 기록하고,
명확한 개선이 없어 fast-path 중복 구현을 보류한 이유를
memcarry에 남겨줘. 저장 ID와 repository scope도 확인해줘.
```

사용하면 실제 결과 파일과 판정을 함께 남기고, 환경이 달라질 때는 결론을 재검증 대상으로 표시한다.

### 2. 다음 날 작업 재개

```text
[오늘]
현재 목표, 완료 파일, 실패/미해결, 다음 행동, 테스트 결과를
memcarry에 남기고 저장 결과를 알려줘.

[다음 날]
memcarry 기록을 읽고 현재 파일·Git 상태와 대조한 뒤
저장되지 않은 내용은 추측하지 말고 다음 작업부터 계속해줘.
```

사용하지 않으면 새 세션은 저장되지 않은 대화에 의존한다. 사용하면 `RESUME`이 관련 상태를 좁혀 주고, 실제 HEAD와 불일치하는 volatile state는 재검증한다.

### 3. 과거 판단 조회

```text
scope-first FTS를 선택한 이유와 당시 검증 결과만 찾아줘.
관련 기록이 없으면 없다고 말해줘.
```

사용하지 않으면 저장소 전체와 기억을 다시 검색하며 답을 추정하기 쉽다. 사용하면 관련 결정·근거만 조회하고, 없는 사실을 만들어내지 않는다.

## 응용방식 — AI를 교대해 한 흐름으로 만들기

### 1. Codex 구현 → Claude 리뷰 → Gemini 문서화 → AGY 확인

```text
Codex:  구현과 테스트를 끝내고 Claude 리뷰용 인계를 memcarry에 남겨줘.
Claude: 인계를 확인하고 재현 테스트부터 만들어 리뷰해줘.
Gemini: 구현·리뷰·테스트를 실제 코드와 대조해 사용법을 문서화해줘.
AGY:   지금까지의 결정과 제한을 확인하고 사용자가 따라 할 검증 절차를 점검해줘.
```

사용하지 않으면 각 AI에 목적·변경 파일·실패·검증 범위를 매번 붙여 넣는다. 누락된 실패가 “통과”로 둔갑하거나, 문서와 코드가 어긋날 수 있다.

사용하면 마지막 agent identity와 checkpoint를 바탕으로 `HANDOFF`가 선택되고, 네 agent가 같은 governed L2를 읽는다. AGY도 첫 `PreInvocation`에서 bounded 인계를 받아 별도 복사 없이 시작한다. 그래도 이전 판단은 정답이 아니므로 현재 코드와 테스트로 확인한다.

### 2. 리뷰를 TDD 수정으로 연결

```text
확정 오류, 의심, 재현 조건, 확인하지 못한 범위를 나눠 memcarry에 남겨줘.
다음 AI는 그 인계를 읽고 실패 테스트를 먼저 만든 뒤 수정·전체 테스트를 실행해줘.
```

사용하지 않으면 리뷰 코멘트만 남고 재현 조건이 사라진다. 사용하면 가설은 `unverified`로 유지되고 실제 테스트가 통과한 뒤에만 확정된다.

### 3. 예기치 않은 중단

```text
마지막 durable 기록과 현재 변경 사항을 대조해
완료·미완료·손실 가능 구간을 나눠줘.
```

사용하지 않으면 마지막 메시지 이후를 완료로 착각한다. 사용하면 checkpoint는 관측값으로, durable memory는 근거로 분리되어 복구 범위를 보여준다. 디스크 백업이나 원격 동기화는 아니다.

## 전문활용방식 — 반복되는 팀/프로젝트 절차에 포함하기

### 1. 성능 실험 누적

기준 측정 → 동일 조건 개선 → 결과 파일 보존 → 채택/보류 판단 → 다음 가설 순서로 기록한다.

```text
이번 benchmark의 환경·명령·메모리 수·p50/p95·JSON 위치를
실측값과 해석으로 나눠 memcarry에 남겨줘.
다음 실험에서는 미검증 가설부터 진행해줘.
```

사용하지 않으면 PC/버전 차이와 단발성 p50을 섞어 성능이 좋아졌다고 주장하기 쉽다. 사용하면 동일성은 결과 순서·mode·회귀 여부로 판단하고, wall-clock 편차는 환경 의존으로 남긴다.

### 2. 장기 버그 조사

```text
재현 조건, 확인 사실, 배제한 원인, 미검증 가설, 다음 실험을
각각 기록해줘. verified는 로그나 테스트가 있는 항목에만 사용해줘.
```

사용하지 않으면 가설이 여러 번 전달되며 사실처럼 굳어진다. 사용하면 다음 AI가 이미 배제한 경로를 알면서도 환경 변화가 있으면 다시 검토할 수 있다.

### 3. 릴리스 준비

```text
구현·검증 기록을 실제 diff와 대조해
확정 기능, 미실행 항목, 제한 사항, 다음 릴리스 행동을 정리해줘.
```

사용하지 않으면 문서의 설치법·버전·지원 agent가 실제 코드와 어긋난다. 사용하면 Codex/Claude/Gemini/AGY 설치·hook·benchmark 결과까지 같은 근거 묶음으로 점검한다. Memcarry는 CI나 승인 시스템이 아니므로 commit/push는 별도 명시가 필요하다.

## 기대 범위와 안전선

- 기록 요청은 실제 write와 확인을 요구한다. 실행 없이 “저장했다”고 말하지 않는다.
- SessionStart/AGY `PreInvocation`은 전체 대화 저장이 아니라 bounded continuity context를 주입한다.
- scope는 `task > branch > repository > global` 순으로 좁힌다. 다른 저장소의 비슷한 이름을 섞지 않는다.
- 현재 파일·HEAD·테스트가 기억과 다르면 현재 상태를 우선하고, stale/충돌을 표시한다.
- 제공되는 CLI 명령은 `install`, `status`, `uninstall`, `benchmark`다. `memcarry save/resume/handoff`라는 별도 subcommand는 없다.

실용성의 기준은 “얼마나 많이 저장했는가”가 아니라 **다음 agent가 무엇을 근거로 어디서부터 이어갈지 즉시 알 수 있는가**다.
