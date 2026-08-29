"""`python -m quookly_cli` — the same entry point the console script is.

Here for the MCP bridge. A host that launches a stdio server names a command, and inside a
launcher the console script is often not on the path: an interpreter and a module are the
two things such a host can always be given.
"""

from quookly_cli.cli import main

if __name__ == "__main__":
    main()
