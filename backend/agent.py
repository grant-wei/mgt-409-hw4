from __future__ import annotations

import os
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import AgentChatResult, ChatDependencies
from tools import register_tools


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ENV = BACKEND_ROOT.parent / ".env"
ASSIGNMENT_ENV = BACKEND_ROOT.parent.parent / ".env"
PROMPT_PATH = BACKEND_ROOT / "prompts" / "prompt.md"


def _load_assignment_environment() -> None:
    for env_path in (PROJECT_ENV, ASSIGNMENT_ENV):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if not item or item.startswith("#") or "=" not in item:
                continue
            name, value = item.split("=", 1)
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if name in {"OPENAI_API_KEY", "OPENAI_MODEL"} and value:
                os.environ.setdefault(name, value)


_load_assignment_environment()
MODEL_NAME = os.getenv("OPENAI_MODEL", "").strip()
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CONFIGURED = bool(MODEL_NAME and API_KEY)

if CONFIGURED:
    model = OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(api_key=API_KEY))
    shop_agent: Agent[ChatDependencies, AgentChatResult] | None = Agent(
        model,
        deps_type=ChatDependencies,
        output_type=AgentChatResult,
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
    )
    register_tools(shop_agent)

    @shop_agent.instructions
    def shopper_context(ctx: RunContext[ChatDependencies]) -> str:
        deps = ctx.deps
        lines = [f"Current page: {deps.current_page}"]
        if deps.shopper_name and deps.shopper_email:
            lines.append(f"Signed-in shopper: {deps.shopper_name} ({deps.shopper_email}). Use the name naturally when helpful. Keep the email private and do not repeat it unless directly relevant.")
        else:
            lines.append("The shopper is a guest. No account identity is available.")
        if deps.current_product:
            lines.append("Current product on this page, from the database: " + deps.current_product.model_dump_json())
        else:
            lines.append("No current product is selected on this page.")
        return "\n".join(lines)
else:
    shop_agent = None
