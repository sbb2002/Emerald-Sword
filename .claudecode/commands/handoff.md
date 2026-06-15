---
name: handoff
description: "저런! 이번 세션이 너무 길어져서 성능이 떨어지나요?! /handoff를 수행하면 현재까지 작업을 요약하여 다음 세션에서 이어나갈 수 있습니다."
---

---
name: handoff
description: Write or update a handoff document so the next agent with fresh context can continue this work.
---

Write or update a handoff document so the next agent with fresh context can continue this work.

Steps:
1. Check if HANDOFF.md already exists in the project
2. If it exists, read it first to understand prior context before updating
3. Create or update the document with:
   - **Goal**: What we're trying to accomplish
   - **Current Progress**: What's been done so far
   - **What Worked**: Approaches that succeeded
   - **What Didn't Work**: Approaches that failed (so they're not repeated)
   - **Next Steps**: Clear action items for continuing

Save as HANDOFF.md in the project root and tell the user the file path so they can start a fresh conversation with just that path.