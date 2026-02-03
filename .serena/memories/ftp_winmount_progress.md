# FTP WinMount Progress

## Project
C:\Claude\repos\FTP WinMount - PyFTPDrive mounts FTP as Windows drive letter

## Current State
- Mount WORKS - user tested it manually, no console errors after get_security fix
- PR #1 exists at https://github.com/dansasser/ftp-winmount/pull/1
- Branch: scaffold-pyftpdrive-12384762257957858236
- Force pushed to overwrite bad Jules bot commit that gutted the codebase

## CI Fixes In Progress
1. Added `psutil` to dev dependencies (pyproject.toml, requirements-dev.txt) - DONE
2. Created `FileContext` helper function in test_filesystem.py to provide defaults for OpenedContext constructor - DONE
3. Fixed get_security_by_name tests (size is SD size not file size, security is not None) - DONE
4. Fixed isinstance check to use OpenedContext not FileContext - DONE

## Still Need to Fix (16 failing tests)
- test_read_directory tests: use `result[0]["file_name"]` not `result[0][0]` (returns dicts not tuples)
- test_cleanup tests: cleanup() needs `flags` argument  
- test_close_flushes_dirty_buffer: close() doesn't call write_file directly
- test_get_file_info_returns_context_data: comparing filetime (int) to datetime
- test_file_context_defaults: expects attributes=0 but gets FILE_ATTRIBUTE_NORMAL

## DO NOT
- Run the FTP server or test mount - user handles that
- Run dev servers without permission
