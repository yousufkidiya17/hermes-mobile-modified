---
name: mcp-market
description: "Browse MCP servers and agent skills on mcpmarket.com."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [MCP, servers, skills, tools, marketplace]
    related_skills: [mcporter]
---

# MCP Market

Browse, search, and discover MCP servers, agent skills, and tools at [mcpmarket.com](https://mcpmarket.com).

## When to Use
- User wants to find MCP servers for specific tools
- User needs agent skills for tasks
- User asks about MCP ecosystem or marketplace
- Search for tools to integrate with AI agents

## Key Info
- **Total MCP Servers:** 40,586+
- **URL:** https://mcpmarket.com
- **Categories:** Developer Tools, API Development, Data Science, Security, DevOps, Browser Automation, E-commerce, Social Media, Game Dev, Mobile Dev, etc.

## How to Browse

### Step 1: Navigate to Website
```
browser_navigate(url="https://mcpmarket.com")
```

### Step 2: Search for Specific Tools
Use the search box or browse categories:
- Developer Tools
- API Development
- Data Science & ML
- Security & Testing
- Deployment & DevOps
- Browser Automation
- Database Management

### Step 3: Popular Servers
| Server | Category | Stars | Use Case |
|--------|----------|-------|----------|
| Superpowers | Dev Tools | 261k | AI coding workflows |
| Task Master | Dev Tools | 28k | Task management |
| FastAPI | API Dev | 12k | FastAPI endpoints |
| Ghidra | Security | 9.6k | Reverse engineering |
| Firecrawl | Web Scraping | 4.2k | Web data extraction |

### Step 4: Popular Agent Skills
| Skill | Category | Stars | Use Case |
|-------|----------|-------|----------|
| Diagram Maker | Docs | 379k | SVG/HTML diagrams |
| GH Issues Auto-Fixer | Collab | 330k | GitHub issue automation |
| Discord Integration | Collab | 313k | Discord management |
| React Code Fix | Dev Tools | 243k | Code linting/formatting |
| GitHub Integration | Collab | 229k | PR/issue management |

## Install MCP Server
Each server page has install instructions. Typically:
```bash
npx @modelcontextprotocol/server-<name>
# or
uvx mcp-server-<name>
```

## Pitfalls
- Some servers require API keys
- Check server compatibility with your client (Claude, Cursor, etc.)
- Some servers may need local dependencies
