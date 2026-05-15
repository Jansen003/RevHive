"""EXPERIMENTAL: Multi-turn conversational deep review engine.

Not integrated into the main workflow. May be removed or redesigned.

Each finding triggers a follow-up conversation where the reviewer
asks clarifying questions, challenges assumptions, and explores
alternative solutions. This is the highest token consumption mode.
"""

import logging
import warnings
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from revhive.agents.base import AgentResult, ReviewFinding

logger = logging.getLogger(__name__)


class ConversationReviewer:
    """Performs multi-turn deep review on each finding.

    Token consumption per session (3-5 rounds):
    - Round 1: Initial finding analysis ~3000 tokens
    - Round 2: Challenge assumptions ~3000 tokens
    - Round 3: Explore alternatives ~3000 tokens
    - Round 4: Edge case deep dive ~2000 tokens
    - Round 5: Final synthesis ~2000 tokens
    Total: ~13,000-15,000 tokens per finding

    With 5-10 findings per file, this reaches 65,000-150,000 tokens/file.
    """

    MAX_ROUNDS = 5
    MAX_CODE_LENGTH = 8000      # characters — truncate beyond this
    DEFAULT_TIMEOUT = 180       # seconds
    LARGE_FILE_THRESHOLD = 4000 # characters — scale timeout above this

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, provider: Optional[str] = None):
        warnings.warn("ConversationReviewer is EXPERIMENTAL and may be removed or redesigned.", FutureWarning, stacklevel=2)
        from revhive.utils.llm_client import create_llm_client
        self.llm = create_llm_client(
            api_key=api_key or "",
            base_url=base_url,
            model=model,
            provider=provider,
            temperature=0.3,
            max_retries=3,
            request_timeout=self.DEFAULT_TIMEOUT,
        )

    def _dynamic_timeout(self, code: str, num_findings: int) -> int:
        """Scale timeout based on code size and finding count."""
        code_len = len(code)
        if code_len <= self.LARGE_FILE_THRESHOLD:
            return self.DEFAULT_TIMEOUT
        scale = code_len / self.LARGE_FILE_THRESHOLD
        return int(self.DEFAULT_TIMEOUT * scale * (1 + num_findings * 0.1))

    async def deep_review(self, code: str, initial_findings: list[ReviewFinding],
                          file_path: str = "") -> AgentResult:
        """Run multi-turn review on each finding with adaptive timeout.

        For large files, code context is truncated and timeout is scaled
        proportionally. Falls back gracefully if individual rounds fail.
        """
        # Truncate oversized code to keep within timeout budget
        truncated_code = code
        if len(code) > self.MAX_CODE_LENGTH:
            logger.warning(
                "Truncating code from %d to %d chars for deep review of %s",
                len(code), self.MAX_CODE_LENGTH, file_path,
            )
            truncated_code = code[:self.MAX_CODE_LENGTH] + "\n# ... (truncated for deep review)"

        adjusted_timeout = self._dynamic_timeout(code, len(initial_findings))
        if adjusted_timeout > self.DEFAULT_TIMEOUT:
            logger.info(
                "Scaling timeout to %ds for %s (%d chars, %d findings)",
                adjusted_timeout, file_path, len(code), len(initial_findings),
            )
            self.llm.request_timeout = adjusted_timeout

        all_deep_findings = []
        total_tokens = 0

        for finding in initial_findings:
            conversation = [
                SystemMessage(content=self._build_system_prompt()),
                HumanMessage(content=self._initial_question(truncated_code, finding, file_path)),
            ]

            try:
                for round_num in range(self.MAX_ROUNDS):
                    response = await self.llm.ainvoke(conversation)
                    total_tokens += response.response_metadata.get("token_usage", {}).get("total_tokens", 0)

                    conversation.append(AIMessage(content=response.content))

                    if round_num < self.MAX_ROUNDS - 1:
                        follow_up = self._generate_follow_up(response.content, round_num, finding)
                        conversation.append(HumanMessage(content=follow_up))

                final_response = await self.llm.ainvoke(conversation + [
                    HumanMessage(content=(
                        "Based on our entire discussion, provide a final consolidated finding with: "
                        "1) Confirmed severity, 2) Root cause, 3) Recommended fix with complete code, "
                        "4) Test cases to verify the fix, 5) Any remaining concerns."
                    ))
                ])
                total_tokens += final_response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
            except Exception as exc:
                logger.error("ConversationReviewer: LLM call failed for %s finding '%s': %s",
                             file_path, finding.title, exc)
                deep_finding = ReviewFinding(
                    agent="ConversationReviewer",
                    severity=finding.severity,
                    title=f"[Deep Review] {finding.title}",
                    description=f"Deep review failed: {exc}",
                    line_number=finding.line_number,
                    suggestion=finding.suggestion,
                )
                all_deep_findings.append(deep_finding)
                continue

            deep_finding = ReviewFinding(
                agent="ConversationReviewer",
                severity=finding.severity,
                title=f"[Deep Review] {finding.title}",
                description=final_response.content[:500],
                line_number=finding.line_number,
                suggestion=finding.suggestion,
            )
            all_deep_findings.append(deep_finding)

        return AgentResult(
            agent_name="ConversationReviewer",
            findings=all_deep_findings,
            summary=f"Deep review completed: {len(all_deep_findings)} findings analyzed over {self.MAX_ROUNDS} rounds each.",
            token_usage=total_tokens,
        )

    def _build_system_prompt(self) -> str:
        return """You are performing a multi-round deep code review. In each round you will:
- Round 1: Analyze the finding in full context, confirm or adjust severity
- Round 2: Challenge your own assumptions — what if you're wrong? What mitigating factors exist?
- Round 3: Explore at least 2 alternative solutions, compare trade-offs
- Round 4: Deep dive into edge cases and failure modes of the proposed fix
- Round 5: Synthesize everything into a final recommendation

Be thorough and analytical. Change your mind if evidence warrants it."""

    def _initial_question(self, code: str, finding: ReviewFinding, file_path: str) -> str:
        return f"""I found a {finding.severity.value} severity issue in `{file_path}`:

**Finding:** {finding.title}
**Description:** {finding.description}
**Line:** {finding.line_number or 'N/A'}
**Current suggestion:** {finding.suggestion or 'None'}

Here's the code:

```
{code}
```

Please perform a deep analysis: Is this truly a problem? What's the root cause? What's the worst that could happen?"""

    def _generate_follow_up(self, previous_response: str, round_num: int,
                            finding: ReviewFinding) -> str:
        prompts = {
            0: "Now challenge your own analysis. What assumptions did you make? "
               "Could this pattern be intentional? Are there contexts where this isn't a bug?",
            1: "Good analysis. Now propose at least 2 different fix approaches. "
               "For each: describe the approach, show the code, list pros/cons, and estimate risk.",
            2: "For the recommended fix, what edge cases could still cause failures? "
               "Consider: concurrent access, resource exhaustion, malformed inputs, "
               "version compatibility, and interaction with other components.",
            3: "Final synthesis: Given all the analysis, provide your definitive recommendation. "
               "Include the complete fixed code, test cases, and any deployment considerations.",
        }
        return prompts.get(round_num, "Please elaborate further.")
