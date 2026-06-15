---
name: syntax-gate
description: >
  코드 생성 또는 수정 직후, 실행 전에 문법·구조 오류를 정적으로 검사하는 스킬.
  "일단 실행해보자" 대신 "통과 조건을 먼저 확인"하는 게이트를 강제한다.
  다음 상황에서 자동 적용: 코드 파일 생성/수정 완료 시점, JSX/TSX 컴포넌트 작성 후,
  Python·JS·TS 파일 패치 후. 사용자가 "문법 검사", "신택스 체크", "/syntax-gate",
  "실행 전에 확인해줘" 라고 하면 즉시 이 스킬을 적용한다.
---

# Syntax Gate

코드 생성·수정 직후 실행 전에 통과 기준을 점검하는 스킬.

## 목적

구동 실패의 가장 흔한 원인은 **"문법 오류를 실행 전에 잡지 못한 것"**이다.
Syntax Gate는 실행 전 마지막 체크포인트 역할을 한다.

---

## 환경별 체크 항목

### Claude.ai 아티팩트 (React / HTML)

```
## Syntax Gate — React

### 필수 통과 항목
- [ ] 모든 JSX 태그가 닫혀 있는가? (self-closing 포함)
- [ ] import 누락 없는가? (사용한 컴포넌트·훅 전부)
- [ ] export default 가 있는가?
- [ ] useState / useEffect 훅 규칙 위반 없는가? (조건문 안 사용 금지)
- [ ] props 타입이 실제 전달값과 일치하는가?
- [ ] map() 에 key prop 이 있는가?
- [ ] 이벤트 핸들러가 함수 레퍼런스인가? (즉시 호출 아님)

### 경고 항목 (실행은 되지만 문제 소지)
- [ ] console.log 디버그 코드 잔존
- [ ] any 타입 남용 (TypeScript)
- [ ] 하드코딩된 URL / 토큰

결과: ✅ 통과 / ⚠️ 경고 있음 / ❌ 차단
```

---

### Claude Code / 로컬 (Python)

Claude Code 환경에서는 실제 도구를 호출한다:

```bash
# 문법 검사
python -m py_compile <파일명>

# 린트 (있을 경우)
flake8 <파일명> --max-line-length=120

# 타입 검사 (있을 경우)
mypy <파일명> --ignore-missing-imports
```

출력 해석:
- 오류 없음 → ✅ 통과
- SyntaxError → ❌ 즉시 수정 후 재검사
- 경고(W) → ⚠️ 사용자에게 보고 후 판단 위임

---

### Claude Code / 로컬 (JavaScript · TypeScript)

```bash
# 문법 검사 (Node.js)
node --check <파일명>

# TypeScript 타입 검사
npx tsc --noEmit

# ESLint (있을 경우)
npx eslint <파일명>
```

---

## 결과 보고 형식

```
## Syntax Gate 결과

| 항목 | 상태 | 내용 |
|------|------|------|
| JSX 태그 닫힘 | ✅ | 이상 없음 |
| import | ❌ | useCallback 누락 |
| export default | ✅ | 있음 |
| key prop | ⚠️ | line 42 map()에 index key 사용 중 |

→ ❌ 차단: useCallback import 추가 후 재검사 필요
```

---

## 규칙

- ❌ 항목이 하나라도 있으면 **실행 전에 수정**한다
- ⚠️ 항목은 사용자에게 보고하고 진행 여부를 묻는다
- 수정 후 **해당 항목만 재검사**한다 (전체 재검사 불필요)
- 검사 범위는 **이번 작업에서 건드린 파일만** (pre-flight 목록 참조)

---

## 빠른 모드 (`/syntax-gate quick`)

아티팩트 단일 파일용 — 핵심 3개만:

```
## Syntax Gate (quick)
- 태그 닫힘: ✅
- import 완전: ✅
- export default: ✅
→ 통과. 실행해도 됩니다.
```
