# Memcarry 검증 기록

이 문서는 현재 `al-hub/memcarry` 배포물의 동작·문서·성능 계약을 확인한 기록이다.

## 범위

- 기준 커밋: `9f8193782ebcab86ac901d2c93a5e1a8d575ba1f`
- 변경 버전: `0.2.0-alpha.18`
- 검증 대상: Python 도메인/통합 테스트, Node 설치기 테스트, CLI smoke,
  startup/continuity benchmark
- worktree 세부 운영은 사용자 시나리오에서 제외했지만, 기존 격리 테스트가
  계속 통과하는지만 회귀 검증했다.

## 동작 검증

```text
Python unittest: 114 passed
Node tests:      14 passed
compileall:      success
git diff --check: clean
```

Python 테스트 수는 기준 커밋과 동일하다. Node 테스트는 기존 11개에
리브랜딩 회귀 테스트 3개(커스텀 저장소 경로, hook 그룹 이웃 보존, legacy
hook 정확 매칭)를 추가했다.

검증한 핵심 계약:

- `memcarry` 패키지/CLI와 `~/.memcarry` 기본 경로
- `MEMCARRY_HOME` 우선순위와 설치된 hook의 명시적 `--home` 전달
- AGY native `PreInvocation` plugin hook의 bounded context 주입
- Codex/Claude/Gemini hook 설치·status·uninstall의 멱등성
- 같은 hook 그룹의 무관한 hook 보존
- SQLite schema/migration, recall, resume/handoff, clone-resume, stale HEAD
  및 실제 multi-worktree isolation

## 성능 비교

기준 커밋과 변경 커밋에서 동일한 명령을 실행했다.

```bash
python3 benchmarks/continuity_baseline.py --output /tmp/memcarry-before-baseline.json
python3 benchmarks/continuity_baseline.py --output /tmp/memcarry-after-baseline.json
```

동일한 로컬 환경에서 한 번씩 측정한 p50 비교는 다음과 같다. 프로세스
startup과 OS cache 영향이 있으므로 단일 실행값을 보장값으로 해석하지 않고,
기능 변경으로 인한 회귀가 없는지 확인하는 자료로 사용한다.

| 메모리 수 | resume p50 기준 | resume p50 변경 | hook codex p50 기준 | hook codex p50 변경 |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 8.551 ms | 8.572 ms | 70.425 ms | 70.718 ms |
| 10,000 | 9.399 ms | 9.763 ms | 67.666 ms | 70.554 ms |
| 50,000 | 12.288 ms | 11.653 ms | 80.500 ms | 80.458 ms |
| 100,000 | 15.462 ms | 14.686 ms | 86.386 ms | 84.449 ms |

측정 결과는 기준 대비 정상적인 실행 편차 범위이며, scope-first FTS의
ordered 결과와 continuity mode 결과는 테스트에서 동일하게 유지됐다.
“100% 성능 일치”는 모든 wall-clock 숫자가 같다는 뜻이 아니라, 동작 결과와
성능 특성에 회귀가 없다는 의미로 판정했다.

## 이름·호환성 원칙

- 새 문서·설치 명령·skill은 `memcarry`를 사용한다.
- 기존 사용자는 마이그레이션 문서의 명시적 `--home` 지정으로 데이터를 재사용할 수 있다.
- 호환 shim과 legacy hook 식별자는 기존 데이터·설정을 안전하게 이어가기 위한 내부 경계에만 남긴다.
