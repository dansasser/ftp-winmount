# VS Code FTP Mount Extension

## Project Location
C:\Claude\repos\vscode-ftp-mount

## Status
Scaffolding COMPLETE. Ready for npm install and testing.

## What's Done
Documentation:
- README.md - full project overview, features, usage
- ARCHITECTURE.md - component routing matrix, data flow diagrams
- IMPLEMENTATION.md - 10-phase implementation plan with checkboxes
- CLAUDE.md - session continuity instructions

Config:
- package.json - VS Code extension manifest
- tsconfig.json - TypeScript compilation
- .eslintrc.json - Linting rules
- .vscodeignore - Package exclusions
- .vscode/ - Debug and build configs

Source (Phase 1-4 complete):
- src/extension.ts - Entry point with all commands
- src/ftpFileSystem.ts - Full FileSystemProvider implementation
- src/ftpClient.ts - FTP client with reconnection logic
- src/connectionManager.ts - Connection pooling and credential storage
- src/cache.ts - TTL-based directory and metadata caching
- src/types.ts - TypeScript interfaces

## What's Next
1. Create GitHub repo and push
2. Run npm install
3. Press F5 to test in Extension Development Host
4. Test against pyftpdlib server
5. Fix any runtime issues
6. Add tests (Phase 5+)

## Key Decisions
- Uses VS Code FileSystemProvider API (not real drive letter)
- URI scheme: ftp://[user@]host[:port]/path
- FTP library: basic-ftp
- Credentials stored in VS Code SecretStorage
- Caching with TTL (30s dir, 60s metadata)

## Related Project
ftp-winmount (Python) - real Windows drive letter via WinFsp
Same FTP targets, different approach

## To Resume
```bash
cd C:\Claude\repos\vscode-ftp-mount
npm install
npm run compile
# Press F5 to test
```
