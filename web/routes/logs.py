"""
Logs API endpoints for viewing and filtering log files.
"""

import logging
import re
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

logger = logging.getLogger("discordbot.web.logs")

router = APIRouter(prefix="/api/v1/logs", tags=["Logs"])


def parse_log_line(line: str) -> Optional[dict]:
    """
    Parse a log line into structured data.

    Expected format: [timestamp] [level] logger: message
    Example: [2025-10-23 22:00:01] [INFO    ] discordbot: Bot ready
    """
    # Pattern: [timestamp] [level] logger: message
    pattern = r'\[([^\]]+)\]\s+\[(\w+)\s*\]\s+([^:]+):\s+(.*)'
    match = re.match(pattern, line)

    if match:
        return {
            "timestamp": match.group(1),
            "level": match.group(2).strip(),
            "logger": match.group(3).strip(),
            "message": match.group(4).strip(),
            "raw": line
        }

    # If line doesn't match pattern, return as raw message
    return {
        "timestamp": "",
        "level": "UNKNOWN",
        "logger": "",
        "message": line.strip(),
        "raw": line
    }


def get_log_level_value(level: str) -> int:
    """
    Get numeric value for log level.
    Higher numbers = higher severity.
    """
    levels = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
        "UNKNOWN": 0
    }
    return levels.get(level.upper(), 0)


@router.get("/files")
async def list_log_files():
    """
    List all available log files in data/logs directory.
    Returns files sorted by modification time (newest first).
    """
    try:
        log_dir = Path("data/logs")

        if not log_dir.exists():
            return {
                "files": [],
                "message": "Log directory does not exist"
            }

        # Get all .log files
        log_files = []
        for log_file in log_dir.glob("*.log*"):
            if log_file.is_file():
                stat = log_file.stat()
                log_files.append({
                    "name": log_file.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "path": str(log_file)
                })

        # Sort by modification time (newest first)
        log_files.sort(key=lambda x: x["modified"], reverse=True)

        return {
            "files": log_files,
            "count": len(log_files)
        }

    except Exception as e:
        logger.error(f"Error listing log files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/read")
async def read_logs(
    file: str = Query(..., description="Log file name"),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"),
    search: Optional[str] = Query(None, description="Search term to filter logs"),
    lines: int = Query(500, description="Maximum number of lines to return"),
    tail: bool = Query(True, description="Read from end of file (tail)")
):
    """
    Read and filter logs from a specific log file.

    Parameters:
    - file: Name of the log file to read
    - level: Filter by log level (optional)
    - search: Search term to filter messages (optional, case-insensitive)
    - lines: Maximum number of lines to return (default 500)
    - tail: If True, read from end of file; if False, from beginning
    """
    try:
        log_dir = Path("data/logs")
        log_file = log_dir / file

        # Security: Ensure file is within log directory
        if not log_file.resolve().is_relative_to(log_dir.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")

        if not log_file.exists():
            raise HTTPException(status_code=404, detail="Log file not found")

        # Read log file
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            if tail:
                # Read last N lines efficiently
                all_lines = f.readlines()
                log_lines = all_lines[-lines*2:] if len(all_lines) > lines*2 else all_lines
            else:
                # Read first N lines
                log_lines = [f.readline() for _ in range(lines*2)]

        # Parse and filter logs
        parsed_logs = []
        for line in log_lines:
            if not line.strip():
                continue

            log_entry = parse_log_line(line)

            # Filter by level (show selected level and higher severity levels)
            if level and level.upper() != "ALL":
                min_level_value = get_log_level_value(level)
                entry_level_value = get_log_level_value(log_entry["level"])
                if entry_level_value < min_level_value:
                    continue

            # Filter by search term
            if search:
                search_lower = search.lower()
                if search_lower not in log_entry["message"].lower() and \
                   search_lower not in log_entry["logger"].lower():
                    continue

            parsed_logs.append(log_entry)

        # Limit results
        parsed_logs = parsed_logs[-lines:] if tail else parsed_logs[:lines]

        return {
            "file": file,
            "logs": parsed_logs,
            "count": len(parsed_logs),
            "filters": {
                "level": level or "ALL",
                "search": search,
                "tail": tail
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading log file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_log(filename: str):
    """
    Download a log file.
    """
    try:
        log_dir = Path("data/logs")
        log_file = log_dir / filename

        # Security: Ensure file is within log directory
        if not log_file.resolve().is_relative_to(log_dir.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")

        if not log_file.exists():
            raise HTTPException(status_code=404, detail="Log file not found")

        return FileResponse(
            path=str(log_file),
            filename=filename,
            media_type='text/plain'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading log file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tail")
async def tail_logs(
    file: str = Query(..., description="Log file name"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    lines: int = Query(100, description="Number of lines to tail")
):
    """
    Get the last N lines of a log file (like tail -f but one-shot).
    For continuous streaming, use the WebSocket endpoint.
    """
    return await read_logs(file=file, level=level, lines=lines, tail=True)
