"""Thin LLM provider abstraction supporting Anthropic and DeepSeek (OpenAI-compatible)."""

from __future__ import annotations

from intelligent_chat.config import (
    ANTHROPIC_API_KEY,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    LLM_PROVIDER,
    NORMALIZATION_MODEL,
)


def call_save_knowledge(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str = NORMALIZATION_MODEL,
) -> dict | None:
    """Call the configured LLM with the save_knowledge tool. Returns the tool input dict or None."""
    if LLM_PROVIDER == "deepseek":
        return _call_openai_compatible(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=tool_schema,
        )
    return _call_anthropic(
        api_key=ANTHROPIC_API_KEY,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=tool_schema,
    )


def _call_anthropic(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
) -> dict | None:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        tools=[tool_schema],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_schema["name"]:
            return block.input
    return None


def _call_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
) -> dict | None:
    import json

    from openai import OpenAI

    # Convert Anthropic tool schema to OpenAI function format
    openai_tool = {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema["input_schema"],
        },
    }

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=[openai_tool],
        tool_choice="required",
        max_tokens=4096,
    )

    for choice in response.choices:
        msg = choice.message
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == tool_schema["name"]:
                    try:
                        return json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        return None
    return None
