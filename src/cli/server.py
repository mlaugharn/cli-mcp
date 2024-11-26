import asyncio
import sys
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
from typing import Any
# Store clis as a simple key-value dict to demonstrate state management
clis: dict[str, str] = {}
import logging
import subprocess
server = Server("cli")
import os

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available cli resources.
    Each cli is exposed as a resource with a custom cli:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"cli://internal/{cli}"),
            name=f"cli: {cli}",
            description=f"cli for {cli}",
            mimeType="text/plain",
        )
        for cli in clis
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific cli's content by its URI.
    The cli name is extracted from the URI host component.
    """
    if uri.scheme != "cli":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    cli = uri.path
    if cli is not None:
        name = cli.lstrip("/")
        return clis[cli]
    raise ValueError(f"cli not found: {cli}")

#@server.list_prompts()
#async def handle_list_prompts() -> list[types.Prompt]:
#    """
#    List available prompts.
#    Each prompt can have optional arguments to customize its behavior.
#    """
#    return [
#        types.Prompt(
#            name="summarize-notes",
#            description="Creates a summary of all notes",
#            arguments=[
#                types.PromptArgument(
#                    name="style",
#                    description="Style of the summary (brief/detailed)",
#                    required=False,
#                )
#            ],
#        )
#    ]

#@server.get_prompt()
#async def handle_get_prompt(
#    name: str, arguments: dict[str, str] | None
#) -> types.GetPromptResult:
#    """
#    Generate a prompt by combining arguments with server state.
#    The prompt includes all current notes and can be customized via arguments.
#    """
#    if name != "summarize-notes":
#        raise ValueError(f"Unknown prompt: {name}")
#
#    style = (arguments or {}).get("style", "brief")
#    detail_prompt = " Give extensive details." if style == "detailed" else ""
#
#    return types.GetPromptResult(
#        description="Summarize the current notes",
#        messages=[
#            types.PromptMessage(
#                role="user",
#                content=types.TextContent(
#                    type="text",
#                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
#                    + "\n".join(
#                        f"- {name}: {content}"
#                        for name, content in notes.items()
#                    ),
#                ),
#            )
#        ],
#    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add",
            description="Add a new cli schema learned by traversing parsing all help menu subtrees.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                },
                "required": ["cmd",],
            },
        ),
        types.Tool(
            name="help",
            description="Returns learned schema of cli.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                },
                "required": ["cmd",],
            },
        ),
        types.Tool(
            name="run",
            description="Run a command",
            inputSchema={
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cmd_args": {"type": "string"},
                },
                "required": ["cmd"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name not in ("add", "help", "run"):
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    cmd = arguments.get("cmd")
    cmd_args = arguments.get("cmd_args")

    if not cmd:
        raise ValueError("Missing 'cmd' argument")

    # Update server state
    if name == 'add':
        if cmd in clis:
            schema = clis[cmd]
            return [types.TextContent(
                type="text",
                text=f"{schema}"
                )]
        else:
            from .cliexplorer import CLIExplorer
            explorer = CLIExplorer(cmd)
            schema = explorer.generate_schema()
            clis[cmd] = schema
            # Notify clients that resources have changed
            await server.request_context.session.send_resource_list_changed()
            return [
                types.TextContent(
                    type="text",
                    text=f"{schema}",
                )]

    elif name == 'help':
        if cmd in clis:
            schema = clis[cmd]
            return [types.TextContent(
                type="text",
                text=f"{schema}"
                )]
        else:
            from .cliexplorer import CLIExplorer
            explorer = CLIExplorer(cmd)
            schema = explorer.generate_schema()
            clis[cmd] = schema
            # Notify clients that resources have changed
            await server.request_context.session.send_resource_list_changed()
            return [
                types.TextContent(
                    type="text",
                    text=f"{schema}",
                )]

    elif name == 'run':
        if cmd not in clis:
            raise ValueError(f"Unknown cli - run `add {cmd}` first")
        else:
            import shlex

            # Sanitize command and arguments
            sanitized_cmd = shlex.quote(cmd)
            sanitized_args = shlex.split(cmd_args) if cmd_args else []

            # Build the command
            command = [sanitized_cmd] + sanitized_args

            try:
                # Set a timeout (e.g., 10 seconds)
                timeout = 10

                # Create subprocess without using the shell for safety
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Wait for the process to complete with timeout
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

                contents = stdout.decode().strip()
                errs = stderr.decode().strip()

                response = f"Command executed: {' '.join(command)}\n\nstdout:\n{contents}\n\nstderr:\n{errs}"
                return [
                    types.TextContent(
                        type="text",
                        text=response
                    )
                ]
            except asyncio.TimeoutError:
                # Kill the process if it exceeds timeout
                process.kill()
                await process.communicate()
                return [
                    types.TextContent(
                        type="text",
                        text=f"The command {' '.join(command)} timed out after {timeout} seconds."
                    )
                ]
            except Exception as e:
                # Handle other exceptions
                return [
                    types.TextContent(
                        type="text",
                        text=f"An error occurred while executing the command: {e}"
                    )
                ]

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="cli",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
