"""One real turn through the Agent SDK, using this PC's Claude Code login.

Run it once after installing the SDK. It works in an empty temporary folder
and in plan mode, so it can read nothing of yours and change nothing.
"""

import asyncio
import tempfile

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)


async def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        options = ClaudeAgentOptions(cwd=folder, permission_mode="plan", setting_sources=[])
        async with ClaudeSDKClient(options=options) as client:
            await client.query("ענה במילה אחת: שלום")
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print("reply:", block.text)
                if isinstance(message, ResultMessage):
                    print("session:", message.session_id, "ok:", not message.is_error)


if __name__ == "__main__":
    asyncio.run(main())
