# Sci-Hub MCP Server

MCP server for searching Sci-Hub and downloading academic papers by DOI, title, or keyword.

## Overview

This server exposes Sci-Hub search and PDF retrieval through the Model Context Protocol. It resolves the current Sci-Hub Altcha proof-of-work challenge, handles the updated article page layout, and falls back across mirrors.

## Features

- Search by DOI, title, or keyword
- Retrieve title, author, year, and PDF URL
- Download PDFs to a local path
- Crossref-backed title and keyword resolution
- Windows-safe UTF-8 stdio handling

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`

## Installation

```bash
git clone https://github.com/thelabcorner/Sci-Hub-MCP-Server.git
cd Sci-Hub-MCP-Server
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Usage

```bash
python sci_hub_server.py
```

## MCP Configuration

```json
{
  "mcpServers": {
    "scihub": {
      "command": "python",
      "args": ["sci_hub_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `search_scihub_by_doi` | Search by DOI |
| `search_scihub_by_title` | Search by title |
| `search_scihub_by_keyword` | Search by keyword |
| `download_scihub_pdf` | Download a PDF |
| `get_paper_metadata` | Get metadata by DOI |

## Development

Run a quick smoke test:

```bash
python -c "from sci_hub_search import search_paper_by_doi; print(search_paper_by_doi('10.1038/nature09492'))"
```

## License

MIT. See `LICENSE`.

## Disclaimer

For research use only. Respect copyright laws and use responsibly.
