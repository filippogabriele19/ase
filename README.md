# ASE - Autonomous Software Engineer

**AI-powered code refactoring engine with context-aware parsing and surgical AST modification.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## The Problem

Modern AI coding assistants (Copilot, Cursor, etc.) are great for **writing new code**, but they fail catastrophically at **refactoring existing codebases**:
- They overwrite files blindly, losing comments and formatting
- They consume massive token budgets re-indexing the same code
- They can't safely edit production code in regulated industries (banking, healthcare)
- They require sending proprietary code to third-party APIs

**ASE solves this with a surgical approach**: it parses your codebase into a queryable database, plans changes through a multi-step reasoning pipeline, and patches code at the AST level—preserving your original structure.

---

## Why This Is Hard (Technical Edge)

### 1. Hybrid Patching Engine
ASE doesn't just call `LLM.write(file)`. It uses:
- **LibCST Transformers** for Python (preserves comments, docstrings, and whitespace)
- **Fuzzy SEARCH/REPLACE blocks** with tolerance to LLM formatting errors
- **Semantic deletion** via AST node removal (no regex hacks)

### 2. Token-Efficient Context Building
Instead of feeding entire files to the LLM every time:
- Indexes codebase into **SQLite** with symbol-level granularity (functions, classes, imports)
- Only retrieves relevant entities based on task + dependency graph
- Tested on 50k+ LOC projects with <10k token context windows

### 3. Three-Phase Planning Pipeline
**Process 1 (LLM Draft):** Generates initial plan with reasoning and search criteria  
**Process 2 (Python Enrichment):** Queries DB for real symbols, resolves file paths deterministically  
**Process 3 (LLM Validation):** Selects entities, validates coherence, calculates impact  

This prevents the "hallucination → apply → break production" loop.

---

## Quick Start

### Installation

git clone https://github.com/yourusername/ase.git
cd ase
pip install -r requirements.txt

### Configure LLM Provider

export ANTHROPIC_API_KEY="your-key-here"
export LLM_PROVIDER="anthropic"  # or "ollama" for local

## Basic Workflow

### 1. Index your project
python ase.py scan .

### 2. Run autonomous refactoring
python ase.py apply "Extract all database logic into a new repository pattern" --path "." --loop=3

### 3. Review changes in the web UI (auto-opens)
Approve or discard each file individually
Example: Real Refactoring Task
Task: "Move all validation functions from utils.py to a new validators.py file"

What ASE does automatically:

Scans the project and indexes 127 symbols across 23 files
Plans the extraction (identifies 8 validation functions)
Generates validators.py with correct imports
Updates utils.py to remove functions (preserving unrelated code)
Finds 5 dependent files and patches their imports
Stages all changes for review
Human decision: Approve/discard in the UI. No merge conflicts, no broken imports.

# Architecture

ase/
├── core/
│   ├── engine.py          # Orchestrator (scan → plan → work)
│   ├── scanner.py         # SQLite indexer + parser factory
│   ├── planner/           # 3-phase planning pipeline
│   │   ├── strategies/    # Draft, Enrichment, Validation
│   │   └── types.py       # Pydantic models for plans
│   ├── worker/            # Code generation + patching
│   └── ast_patcher.py     # LibCST/AST manipulation
├── parsers/               # Language-specific parsers
│   ├── python_parser.py   # Full AST support
│   ├── regex_parser.py    # JS/TS/Dart/Go (heuristic)
│   └── config_parser.py   # JSON/YAML/TOML
├── llm/                   # LLM abstraction layer
├── server/                # FastAPI review UI
└── utils/                 # Visualization (Mermaid graphs)

# Features

✅ MVP (Available Now)

Python full AST support (functions, classes, imports)
Multi-language indexing (JS, TS, Dart, Go, Rust, PHP)
Web-based diff review UI
Automatic backup/undo system
Interactive dependency graph visualization
Anthropic Claude integration
Ollama support (experimental)

🚧 In Progress

Local LLM fine-tuning for enterprise privacy
Java/C#/COBOL parsing (Tree-sitter integration)
CI/CD integration (GitHub Actions, GitLab)
Multi-file transaction rollback
Permissions/policy engine for regulated industries

# Use Cases

## Startups

Rapid prototyping with AI, then refactor safely as codebase grows
Migrate legacy code without breaking production

## Enterprises

Banking/Healthcare: Refactor mainframe COBOL with local LLMs (no API calls)
Large codebases: 100k+ LOC projects where manual refactoring is infeasible
Compliance: Audit trail via .ase/history/ for every change

# Why Build This?

I'm a software engineer and quant trader. 
The insight: LLMs are great at generating code, but terrible at changing existing large systems. They don't understand context, they don't preserve intent, and they don't work in environments where you can't send code to OpenAI's servers.
ASE is designed to be the missing layer between "AI writes a function" and "AI refactors your entire codebase without human supervision."

# Roadmap

## Q1 2026:

Local LLM benchmarking (Qwen, DeepSeek, Llama)
Tree-sitter parsers for Java/C#
VSCode extension

## Q2 2026:

Enterprise licensing with RBAC
GraphRAG integration for cross-repo refactoring
Synthetic data generation for fine-tuning

## Long-term vision:

ASE becomes the "autopilot for legacy code modernization"—a tool that lets one engineer safely refactor what used to require a team of 10.

Contributing
This is an open-source MVP. If you want to:

Add support for a new language parser

Improve LLM prompts

Test on large codebases

Open an issue or PR. The codebase is intentionally modular (see parsers/ and llm/ abstractions).

License
MIT License. See LICENSE for details.

Contact
Building something similar? Want to collaborate?
Reach out: filippogabriele19@gmail.com

# Applying to Y Combinator W26 batch.

ASE is not just a tool—it's a bet that the next wave of software productivity comes from AI that can safely modify existing systems, not just generate new ones.