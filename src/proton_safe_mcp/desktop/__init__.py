"""Native desktop assistant.

Importing this package pulls in Qt, so nothing outside it may import it at module level:
the MCP server, its CLI and the test suite must keep working without Qt installed.
"""
