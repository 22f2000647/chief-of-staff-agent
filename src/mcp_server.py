"""MCP server exposing the chief-of-staff read/draft tools.

Safety design: the server can READ (mail, calendar, web) and DRAFT, but cannot
act on the world. Sending, booking, paying and cancelling live in the agent's
approval queue, never in this server.
Run: python src/mcp_server.py   (stdio transport)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
from tools_impl import mail_search, mail_read, calendar_list, web_lookup, draft_create

mcp = FastMCP("chief-of-staff")

mcp.tool()(mail_search)
mcp.tool()(mail_read)
mcp.tool()(calendar_list)
mcp.tool()(web_lookup)
mcp.tool()(draft_create)

if __name__ == "__main__":
    mcp.run()
