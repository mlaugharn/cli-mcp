# cli MCP server

cli bridge

<img width="870" alt="image" src="https://github.com/user-attachments/assets/a7b78531-c681-40fc-bd65-044980547629">


## Components

### Resources

The server implements a simple note storage system with:
- Custom cli:// URI scheme for accessing individual notes
- Each note resource has a name, help menu subtree, and text/plain mimetype

### Tools

The server implements one tool:
- add (cmd): Recursively parses cli help menu subtrees and stores definition
  - Takes "cmd" 
  - Updates server state and notifies clients of resource changes
- help (cmd): Return subtrees definition
- run (cmd, cmd_args | None): Run a known command
## Quickstart

### Install

#### Claude Desktop
Note: I had to use `/opt/homebrew/bin/uv` instead of just `uv` in the command field in this json:

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`



```
{"mcpServers": {
  "cli": {
    "command": "uv",
    "args": [
      "run",
      "--directory",
      "\<path to repo folder\>",
      "cli"
    ]}
  }
}
```




### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).


You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory <path to repo> run cli
```


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.
