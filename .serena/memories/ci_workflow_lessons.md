# CI/Build Workflow - CRITICAL LESSONS

## The Problem
I keep writing CI configs and dependencies without verifying they match actual code imports. This wastes time debugging CI failures.

## Proper Workflow

### 1. Scan Actual Imports BEFORE Writing Dependencies
```bash
grep -r "^import\|^from" src/ tests/ --include="*.py" | cut -d: -f2 | sort -u
```
Then ensure ALL external imports are in dependencies.

### 2. Test Locally BEFORE Pushing
```bash
pip install -e ".[dev]"
pytest tests/ -v --tb=short
```
Never push untested code to CI.

### 3. Keep Configs In Sync
- pyproject.toml [project.optional-dependencies] dev = [...]
- requirements-dev.txt
- setup.py extras_require["dev"]

All three must list the same dev dependencies.

### 4. Don't Over-Query GitHub
- Reading huge PR comments/reviews causes context bloat and compaction
- Fix issues from local files, not by repeatedly fetching GitHub data
- Check CI failures from local test runs, not GitHub API

## Common Missing Dependencies
- psutil (memory tests)
- pytest-cov (coverage)
- pyftpdlib (FTP test server)
