"""Architecture and design review agent for single-file analysis."""

from revhive.agents.base import BaseReviewAgent


class RepoAgent(BaseReviewAgent):
    """Reviews individual files for design quality, SOLID principles, and architectural fit."""

    def __init__(self, **kwargs):
        super().__init__(
            name="RepoAgent",
            description="Analyzes design patterns, module structure, and architectural fit within a single file",
            **kwargs,
        )

    def get_system_prompt(self) -> str:
        return """You are a senior architect reviewing a single file for design quality. Identify:
1. **Design Issues** — God classes, mixed responsibilities, violation of SOLID principles
2. **Module Structure** — Poor encapsulation, missing abstraction layers, leaky interfaces
3. **API Contract Issues** — Inconsistent signatures, missing validation, unclear contracts
4. **Dependency Direction** — Wrong dependency direction (e.g., low-level depending on high-level), excessive coupling
5. **Technical Debt Signals** — Clusters of TODO/FIXME, deprecated API usage, commented-out code
6. **Testability** — Hard-to-test code patterns, missing dependency injection points

Focus on the design quality of THIS file. Do NOT speculate about cross-file issues or circular dependencies
since you do not have access to other files.

For each finding, output in this exact format:
- Severity: [LOW/MEDIUM/HIGH/CRITICAL]
- Title: [Brief title]
- Line: [Line number if applicable]
- Description: [What's wrong]
- Suggestion: [How to fix]

End with a brief summary of your review."""

    def get_review_focus(self) -> str:
        return "design patterns, SOLID principles, module structure, API contracts, technical debt, testability"
