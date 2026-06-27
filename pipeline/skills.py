"""Runtime skills integration.

Mounts the installed skills directory (``.agents/skills/``) on the builder agent
via ``SkillsCapability`` so React, Tailwind, accessibility, Playwright, and
Netlify guidance is available at runtime through progressive disclosure:

- L1 metadata (name + description) is always in the system prompt,
- L2 ``load_skill(name)`` loads full instructions on demand,
- L3 ``read_skill_resource(name, resource)`` loads deeper references on demand,
- ``run_skill_script`` executes skill scripts (kept enabled per design decision).

A usage tracker records every skill-related tool call so a run can report
whether (and which) skills the model actually used.

See spec ``pipeline-orchestration`` → "Mount runtime skills for the builder".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Tool names exposed by pydantic-ai-skills (progressive disclosure).
_SKILL_TOOLS = {"list_skills", "load_skill", "read_skill_resource", "run_skill_script"}


@dataclass
class SkillUsage:
    """Records skill tool invocations during a run."""

    calls: list[dict] = field(default_factory=list)

    def record(self, tool_name: str, args: dict) -> None:
        self.calls.append({"tool": tool_name, "args": args})

    @property
    def used(self) -> bool:
        return bool(self.calls)

    @property
    def loaded_skills(self) -> list[str]:
        names: list[str] = []
        for c in self.calls:
            if c["tool"] in {"load_skill", "read_skill_resource", "run_skill_script"}:
                name = c["args"].get("skill_name") or c["args"].get("name")
                if name and name not in names:
                    names.append(name)
        return names

    def summary(self) -> str:
        if not self.used:
            return "Skills: none of the runtime skills were loaded by the model."
        lines = [f"Skills: {len(self.calls)} skill tool call(s)."]
        for c in self.calls:
            lines.append(f"  - {c['tool']}({c['args']})")
        if self.loaded_skills:
            lines.append(f"  loaded skills: {', '.join(self.loaded_skills)}")
        return "\n".join(lines)


def build_skills_capabilities(skills_dir: Path | None) -> tuple[list, SkillUsage | None]:
    """Return ``(capabilities, usage)``.

    ``capabilities`` is a list to attach to the builder agent (a
    ``SkillsCapability`` plus a ``Hooks`` capability that records usage), or an
    empty list when no skills directory is available. ``usage`` is the tracker
    (``None`` when skills are unavailable).
    """
    if skills_dir is None or not Path(skills_dir).is_dir():
        return [], None

    from pydantic_ai import RunContext
    from pydantic_ai.capabilities.hooks import Hooks
    from pydantic_ai_skills import SkillsCapability

    usage = SkillUsage()
    hooks = Hooks()

    @hooks.on.before_tool_execute
    async def _track(ctx: RunContext, call, tool_def, args: dict) -> dict:
        if call.tool_name in _SKILL_TOOLS:
            usage.record(call.tool_name, dict(args) if args else {})
        return args

    skills_cap = SkillsCapability(
        directories=[str(skills_dir)],
        # run_skill_script enabled (no exclusions) per the accepted tradeoff.
    )
    return [skills_cap, hooks], usage


def build_skills_capability(skills_dir: Path | None):
    """Backwards-compatible helper returning only the SkillsCapability (or None)."""
    caps, _ = build_skills_capabilities(skills_dir)
    return caps[0] if caps else None
