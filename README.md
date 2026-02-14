# MCP Servers Collection

> A comprehensive collection of Model Context Protocol (MCP) servers for databases, SSH, development tools, and more.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-1.0+-purple)

## 🚀 Quick Start

### Prerequisites

- **Python** 3.10 or higher
- **Node.js** 18 or higher (for TypeScript servers)
- **Claude Desktop** or any MCP-compatible client
- **uv** package manager (optional but recommended)

### Installation

Each server can be installed and used independently:

```bash
# Using uvx (recommended - no installation needed)
uvx mcp-server-postgres
uvx mcp-server-oracle

# Or install from source
cd postgresql-mcp-server
pip install -e .
```

### Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
      }
    },
    "oracle": {
      "command": "uvx",
      "args": ["mcp-server-oracle"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=user;Password=pass;Data Source=..."
      }
    }
  }
}
```

## 📦 Available Servers

### Database Servers

| Server | Description | Language | Status | Documentation |
|--------|-------------|----------|--------|---------------|
| [**PostgreSQL MCP**](./postgresql-mcp-server) | Full-featured PostgreSQL database integration with natural language queries | Python | ✅ Active | [README](./postgresql-mcp-server/README.md) |
| [**Oracle MCP**](./oracle-mcp-server) | Oracle 19c database integration with DBMS_OUTPUT support | Python | ✅ Active | [README](./oracle-mcp-server/README.md) |

**Features:**
- Execute SQL queries directly
- Natural language query support (Turkish/English)
- Database schema exploration
- Table information and statistics
- Transaction support
- Query logging and monitoring

### SSH & Remote Access

| Server | Description | Language | Status | Documentation |
|--------|-------------|----------|--------|---------------|
| [**SSH Python MCP**](./ssh-mcp-server) | Remote command execution with logging and dashboard | Python | ✅ Active | [README](./ssh-mcp-server/README.md) |
| [**SSH Terminal MCP**](./ssh-terminal-mcp) | Interactive terminal with screenshot and OCR support | Node.js | ✅ Active | [README](./ssh-terminal-mcp/README.md) |

**Features:**
- Remote command execution
- Interactive terminal sessions
- Screenshot capture
- OCR text extraction
- Session logging

### Development Tools

| Server | Description | Language | Status | Documentation |
|--------|-------------|----------|--------|---------------|
| [**Git Extended MCP**](./mcp-server-git-extended) | Advanced Git operations and repository management | Python | ✅ Active | [README](./mcp-server-git-extended/README.md) |
| [**GitHub PR Reviews**](./gh-tool) | AI-powered Pull Request analysis using Gemini | Node.js | ✅ Active | [README](./gh-tool/README.md) |

**Features:**
- Advanced Git operations
- PR review automation
- Code quality analysis
- Commit history analysis

### Integrations & APIs

| Server | Description | Language | Status | Documentation |
|--------|-------------|----------|--------|---------------|
| [**GİB API MCP**](./gib-api-mcp) | Turkish Revenue Administration (GİB) API integration | Node.js | ✅ Active | [README](./gib-api-mcp/README.md) |

### Utilities

| Component | Description | Language | Purpose |
|-----------|-------------|----------|---------|
| [**Shared Logger**](./shared_logger.py) | Centralized logging system | Python | Query logging |
| [**Query Dashboard**](./query_dashboard) | Web-based query monitoring | Python | Monitoring |

## 🏗️ Repository Structure

```
mcp-servers/
├── postgresql-mcp-server/    # PostgreSQL MCP server (Python)
├── oracle-mcp-server/         # Oracle MCP server (Python)
├── ssh-mcp-server/            # SSH MCP server (Python)
├── ssh-terminal-mcp/          # SSH Terminal MCP (Node.js)
├── mcp-server-git-extended/   # Git Extended MCP (Python)
├── gh-tool/                   # GitHub PR Reviews (Node.js)
├── gib-api-mcp/              # GİB API MCP (Node.js)
├── query_dashboard/           # Query monitoring dashboard
├── shared_logger.py           # Shared logging module
├── kill_all_mcp_servers.sh   # Utility script
└── README.md
```

## 📖 Installation Guide

### Option 1: Using uvx (Recommended)

No installation or virtual environment needed! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres"]
    }
  }
}
```

### Option 2: Install from PyPI/npm

```bash
# Python servers
pip install mcp-server-postgres
pip install mcp-server-oracle

# After publishing to PyPI
```

### Option 3: Install from Source

#### Python Servers

```bash
cd postgresql-mcp-server
pip install -e .

# Or use the old method
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Node.js Servers

```bash
cd ssh-terminal-mcp
npm install
npm run build
```

## 🛠️ Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/mcp-servers
cd mcp-servers

# For Python servers
cd <server-directory>
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# For Node.js servers
cd <server-directory>
npm install
```

### Running Tests

```bash
# Python
pytest tests/

# Node.js
npm test
```

### Code Quality

```bash
# Python
black src/
ruff check src/

# Node.js
npm run lint
npm run format
```

## 📊 Query Monitoring Dashboard

Track all database queries in real-time:

```bash
cd query_dashboard
python app.py
# Open http://localhost:5555
```

**Features:**
- Real-time query monitoring
- Execution time tracking
- Error logging
- Server type filtering
- Query history

## 🔒 Security

### Best Practices

- ✅ Store credentials in `.env` files (gitignored)
- ✅ Use environment variables for sensitive data
- ✅ Prefer read-only database users
- ✅ Enable query logging for audit trails
- ✅ Use SSH key-based authentication
- ✅ Never commit credentials to Git

### Credential Management

Each server uses `.env` files for configuration:

```env
# .env example
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=myuser
DB_PASSWORD=mypassword
```

**Important:** All `.env` files are gitignored and never committed.

## 🐛 Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check PostgreSQL is running
brew services list | grep postgresql
# or
pg_ctl status

# Test connection
psql -U postgres -h localhost -d mydb
```

### Oracle Connection Issues

```bash
# Test Oracle connection
sqlplus user/password@hostname:1521/service_name

# Check thin mode is working (no Instant Client needed)
python -c "import oracledb; print(oracledb.version)"
```

### MCP Server Not Starting

```bash
# Check Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp-server-*.log

# Test server manually
cd <server-directory>
python server.py
```

### Permission Issues

- Verify file permissions: `ls -la`
- Check user has database access
- Review `.env` file configuration

## 📝 Shared Utilities

### Centralized Query Logger

All servers use a shared logging system:

```python
from shared_logger import log_query_execution

log_query_execution(
    server_type="postgresql",
    tool_name="execute_sql",
    query_text="SELECT * FROM users",
    execution_time_ms=45.2,
    status="success",
    row_count=10
)
```

**Benefits:**
- Unified logging across all servers
- SQLite-based storage
- Real-time notifications
- Performance metrics
- Error tracking

### Utility Scripts

**Kill All MCP Servers**
```bash
./kill_all_mcp_servers.sh
```

## 🗺️ Roadmap

### Near Term
- [ ] Publish PostgreSQL MCP to PyPI
- [ ] Publish Oracle MCP to PyPI
- [ ] Add MongoDB MCP server
- [ ] Create MCPB bundles for one-click installation

### Medium Term
- [ ] Add MySQL MCP server
- [ ] Kubernetes integration MCP
- [ ] AWS services MCP suite
- [ ] Enhanced monitoring dashboard
- [ ] CI/CD pipeline

### Long Term
- [ ] Multi-database query federation
- [ ] GraphQL MCP server
- [ ] Real-time collaboration features
- [ ] Cloud-hosted MCP servers
- [ ] Enterprise support package

## 📄 License

MIT License - see [LICENSE](./LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Contribution Guidelines

- Follow existing code style
- Add tests for new features
- Update documentation
- Ensure all tests pass
- Use conventional commits

## 📞 Support & Contact

- **Issues**: [GitHub Issues](https://github.com/yourusername/mcp-servers/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/mcp-servers/discussions)
- **Email**: your.email@example.com

## 🌟 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io) by Anthropic
- [Anthropic Official MCP Servers](https://github.com/modelcontextprotocol/servers)
- Community contributors and testers

## 📚 Resources

- [Official MCP Documentation](https://modelcontextprotocol.io)
- [MCP Specification](https://spec.modelcontextprotocol.io)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [TypeScript MCP SDK](https://github.com/modelcontextprotocol/typescript-sdk)

---

**Note:** This is a monorepo containing multiple independent MCP servers. Each server can be used standalone or combined with others. Refer to individual server READMEs for specific documentation and usage examples.

**Status**: Active development | Last updated: February 2026
