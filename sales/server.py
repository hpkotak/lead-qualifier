"""Exposes the agent's tools over MCP (stdio).

Set by the test harness through environment variables, never by the model:
LEAD_DB (database path, with the lead already stored) and LEAD_VERSION (v1 or v2).
"""
import functools
import os
import traceback

from mcp.server.mcpserver import MCPServer

from sales.tools import TOOL_NAMES, VERSIONS

version = os.environ.get("LEAD_VERSION", "v1")
tools = VERSIONS[version](os.environ["LEAD_DB"])
server = MCPServer("sales")


def recorded(fn):
    """A crashing tool is a bug in the test harness, not the agent. Record it so the run is marked
    as an error instead of being graded."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            tools.con.execute("INSERT INTO harness_errors (error) VALUES (?)", (traceback.format_exc(),))
            tools.con.commit()
            raise
    return wrapper


for name in TOOL_NAMES[version]:
    server.tool()(recorded(getattr(tools, name)))

if __name__ == "__main__":
    server.run()
