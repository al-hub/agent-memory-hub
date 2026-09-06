# Memcarry 기존 설치 전환 안내

이 문서는 이전 al-hub 설치를 현재 `al-hub/memcarry` runtime으로 전환할 때만 사용한다.
저장소를 자동 이동·합치기·삭제하지 않으며, 다른 도구의 데이터는 호환된다고 가정하지 않는다.

| 구분 | 이전 | 현재 |
| --- | --- | --- |
| 구분 | 이전 설치 식별자 | 현재 |
| 제품·skill | 이전 skill 이름 | Memcarry / `memcarry` |
| GitHub | 이전 al-hub 저장소 | `al-hub/memcarry` |
| npm 이름 | 이전 scoped 이름 | `@al-hub/memcarry` (공개 전) |
| 패키지 CLI | 이전 CLI | `memcarry` |
| 기본 저장 경로 | `~/.agent-memory-hub` | `~/.memcarry` |
| 환경변수 | `AGENT_MEMORY_HUB_HOME` | `MEMCARRY_HOME` (이전 변수도 fallback 지원) |
| Python 패키지 | `agent_memory_hub` | `memcarry` |
| 저장기 스크립트 | `scripts/memory_hub.py` | `scripts/memcarry_store.py` (이전 shim 유지) |

현재 `--agents all`에는 Codex, Claude Code, Gemini CLI, Antigravity CLI(`agy`)가 포함된다. AGY는 `~/.gemini/antigravity-cli/plugins/memcarry/`에 native plugin으로 설치된다.

## 기존 기억을 그대로 사용하기

이름이 같은 외부 도구의 데이터를 건드리지 않기 위해 기존 디렉터리를 자동 이동·합치기·삭제하지 않는다.
먼저 해당 디렉터리가 al-hub 설치의 저장소인지 확인하고 DB·raw·events·checkpoint를 백업한다.
기존 저장소를 그대로 선택해 설치한다:

```bash
npx --allow-git=all -y github:al-hub/memcarry install --home "$HOME/.agent-memory-hub"
npx --allow-git=all -y github:al-hub/memcarry status --home "$HOME/.agent-memory-hub"
```

새 runtime은 선택한 디렉터리의 `runtime/`만 교체하고 기억 데이터와 checkpoint는 유지한다.
hook 명령에는 선택한 `--home`이 기록된다. 같은 runtime을 가리키는 정확한 기존 al-hub hook만 교체하며,
다른 hook과 같은 그룹 안의 다른 명령은 보존한다.

이후 수동 명령에는 `--home`을 계속 지정하거나 셸에 다음을 설정한다:

```bash
export MEMCARRY_HOME="$HOME/.agent-memory-hub"
```

경로 선택 순서는 **명령의 `--home` → `MEMCARRY_HOME` → `AGENT_MEMORY_HUB_HOME` → `~/.memcarry`**다.
Node 경로 옵션·환경변수는 절대 경로를 권장한다. 셸의 따옴표 안 `~` 대신 `$HOME`을 사용한다.
설치된 hook의 명시적 경로가 환경변수보다 우선한다.

새 경로를 선택하면 기존 저장소를 자동 합치지 않는다. 별도의 이전·충돌 검토 없이 폴더를 덮어쓰지 않는다.

## 옛 skill 정리

새 skill을 설치하고 정상 동작을 확인한 다음, 이전 skill의 출처가 al-hub인지 확인한다.
확인된 이전 skill만 명시적으로 제거한다:

```bash
OLD_SKILL_NAME="<이전 skill 이름>"
npx -y skills@latest remove "$OLD_SKILL_NAME" -g -y
```

새 installer는 출처가 불명확한 동일 이름의 skill을 자동 삭제하지 않는다.
`--no-skill`은 skill 관리 호출을 생략할 뿐, 기존 skill을 제거하지 않는다.

## repository 이름과 기억 범위

repository ID는 Git origin을 정규화한 값이다. GitHub 저장소 이름 변경만으로 DB의 scope가 다시 쓰이지 않는다.
기존 clone의 origin URL을 유지하면 기존 scope ID를 유지한다.
origin을 새 URL로 바꾸거나 새 URL로 clone하면 ID가 달라지므로 옛 repository 기억이 자동 승계된다고 가정하지 않는다.
같은 repository ID·호환 HEAD/branch의 fresh clone 재개 기능은 그대로 유지된다.
다른 ID 사이의 기억 이전은 검토가 필요한 별도 작업이며 이 릴리스는 자동 retag하지 않는다.

## 호환성의 경계

- SQLite 스키마·기억 ID·scope 인코딩·checkpoint 형식·검색/판정 알고리즘은 개명으로 바꾸지 않는다.
- 외부 Python 사용자는 import를 `memcarry`로 변경한다. 옛 Python 패키지 import alias는 제공하지 않는다.
- 이전 CLI 실행 파일 alias는 만들지 않는다. 이름 충돌과 오작동을 피하기 위함이다.
- benchmark 식별자와 기본 출력 파일명이 `memcarry`로 바뀐다. 과거 수치는 재측정 결과가 아니다.
- uninstall은 선택한 runtime과 관리 hook/skill을 정리하지만 기억 DB·raw·events·checkpoint는 남긴다.

성능의 동일성은 실행 시간의 문자 그대로 일치가 아니라 **동일 입력의 결과 일치와 같은 환경에서 측정한 회귀 여부**로 확인한다.
