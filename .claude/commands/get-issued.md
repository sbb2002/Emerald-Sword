---
name: get-issued
description: "작업진행도를 요약하여 git issues에 올립니다."
---

**복잡도 태그** — 제목 끝에 붙이지 않고 본문에 명시

**의존성 파악** — `docs/wiki/index.md`의 구현 의존 관계를 기준으로
blockers를 실제 GitHub issue 번호로 참조

### 3. Quiz the user

이슈 초안을 번호 목록으로 제시한다. 각 항목에:

- **제목**: `[feat|bug] #N 항목명`
- **복잡도**: ★~★★★
- **Blocked by**: 선행 이슈 번호 또는 "없음"
- **AFK/HITL**: 인간 개입 필요 여부

사용자에게 확인:
- 누락된 항목이 있는가?
- 의존 관계가 맞는가?
- 분리하거나 합칠 항목이 있는가?

승인 전까지 publish하지 않는다.

### 4. Publish to GitHub

승인 후 `.env`의 `GIT_TOKEN`을 읽어 GitHub API로 이슈를 생성한다.
레포: `sbb2002/open-pipeman`

의존 관계 순서대로 생성 (blocker 먼저).

**이슈 본문 템플릿**

```markdown
## 개요
한 줄 설명.

## 요구사항
- [ ] 항목 1
- [ ] 항목 2

## 복잡도
★★

## Blocked by
- #N 이슈명 또는 "없음"

## 참조
`docs/wiki/파일명.md` (존재하는 경우)
```

**구현 완료 항목** (`✅`)은 본문에 완료된 브랜치와 구현 내용을 함께 기술하고,
이슈 생성 직후 `state: closed`로 닫는다.

### 5. 완료 후

생성된 이슈 번호 목록을 출력한다.
`HANDOFF.md`의 상태 테이블을 업데이트할지 사용자에게 묻는다.