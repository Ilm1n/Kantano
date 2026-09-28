import asyncio
import sys

from src.assistant.checkpoints import setup_checkpointer

if __name__ == "__main__":
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(setup_checkpointer(), loop_factory=loop_factory)
