"""Project context management tools.

Tools the agent uses to build, maintain, and recall project-specific context.
These become MCP tools the Gemini agent can call via Google Cloud Agent Builder.
"""

import json
from datetime import datetime, timezone
from typing import Optional


class ProjectContextTool:
    """Manages project-level context: stack, conventions, architecture.

    Exposed as MCP tools:
      - set_project_context: Define project stack, conventions, structure
      - get_project_context: Recall current project context
      - update_convention: Add or modify a coding convention
      - list_projects: List all known projects
    """

    def __init__(self, memory_backend):
        self.memory = memory_backend

    async def set_project_context(
        self,
        project: str,
        stack: Optional[dict] = None,
        conventions: Optional[list[str]] = None,
        architecture: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Store project context in agent memory.

        Called when a developer first introduces their project, or when
        the project's stack/conventions change.
        """
        facts = []

        if stack:
            facts.append(f"Tech stack: {json.dumps(stack)}")
            for key, value in stack.items():
                from agent.memory.backend import MemoryEntry
                await self.memory.remember(MemoryEntry(
                    content=f"Project {project} uses {key}: {value}",
                    category="fact",
                    project=project,
                    tags=["stack", key],
                ))

        if conventions:
            for conv in conventions:
                from agent.memory.backend import MemoryEntry
                await self.memory.remember(MemoryEntry(
                    content=conv,
                    category="preference",
                    project=project,
                    tags=["convention"],
                ))

        if architecture:
            from agent.memory.backend import MemoryEntry
            await self.memory.remember(MemoryEntry(
                content=f"Architecture: {architecture}",
                category="fact",
                project=project,
                tags=["architecture"],
            ))

        return {
            "status": "stored",
            "project": project,
            "stack_components": len(stack) if stack else 0,
            "conventions": len(conventions) if conventions else 0,
            "architecture_stored": architecture is not None,
        }

    async def get_project_context(self, project: str) -> dict:
        """Retrieve all remembered context for a project.

        Uses wildcard recall scoped by category, then splits facts by
        their stored tags — keyword queries like "conventions" only
        matched memories that literally contained that word, so stored
        conventions ("Use type hints everywhere") were never recalled.
        """
        facts = await self.memory.recall(
            query="*", project=project, category="fact", limit=50
        )
        conventions = await self.memory.recall(
            query="*", project=project, category="preference", limit=50
        )

        stack = [r.entry.content for r in facts if "stack" in r.entry.tags]
        architecture = [
            r.entry.content for r in facts if "architecture" in r.entry.tags
        ]

        return {
            "project": project,
            "stack": stack,
            "conventions": [r.entry.content for r in conventions],
            "architecture": architecture,
            "total_facts": len(facts) + len(conventions),
        }
