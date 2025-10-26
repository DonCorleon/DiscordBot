"""
JSON Editor API endpoints.
Provides generic JSON file viewing and editing capabilities.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("discordbot.web.json_editor")

router = APIRouter(prefix="/api/v1/json-files", tags=["JSON Editor"])

# Base directory for JSON files (relative to project root)
# Get project root by going up from web/routes/ directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
JSON_BASE_DIR = PROJECT_ROOT / "docs"
BACKUP_DIR = PROJECT_ROOT / "docs" / "backups"

# Ensure directories exist
JSON_BASE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


class JSONFileList(BaseModel):
    """Model for listing JSON files."""
    files: List[Dict[str, Any]]


class JSONContent(BaseModel):
    """Model for JSON file content."""
    data: Any  # Can be list, dict, etc.


@router.get("/", response_model=JSONFileList)
async def list_json_files():
    """
    List all JSON files in the docs/ directory.

    Returns file metadata including name, size, and last modified date.
    """
    try:
        files = []

        for json_file in JSON_BASE_DIR.glob("*.json"):
            stat = json_file.stat()
            files.append({
                "filename": json_file.name,
                "path": str(json_file.relative_to(PROJECT_ROOT)),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_array": None  # Will be determined when loaded
            })

        # Sort by modified date (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)

        return {"files": files}

    except Exception as e:
        logger.error(f"Error listing JSON files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filename}")
async def get_json_file(filename: str):
    """
    Load a JSON file's content.

    Args:
        filename: Name of the JSON file (must be in docs/)

    Returns:
        JSON content and metadata
    """
    try:
        # Security: prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = JSON_BASE_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Load JSON content
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Get file stats
        stat = file_path.stat()

        return {
            "filename": filename,
            "data": data,
            "is_array": isinstance(data, list),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filename}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    except Exception as e:
        logger.error(f"Error loading JSON file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{filename}")
async def save_json_file(filename: str, content: JSONContent):
    """
    Save edited JSON file content.

    Creates a backup before saving.

    Args:
        filename: Name of the JSON file
        content: New JSON content

    Returns:
        Success message and backup info
    """
    try:
        # Security: prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = JSON_BASE_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Create backup before saving
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{file_path.stem}_{timestamp}.json"
        backup_path = BACKUP_DIR / backup_filename

        # Copy original to backup
        with open(file_path, 'r', encoding='utf-8') as f:
            original_data = f.read()

        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_data)

        logger.info(f"Created backup: {backup_path}")

        # Save new content
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(content.data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved JSON file: {filename}")

        return {
            "success": True,
            "filename": filename,
            "backup": str(backup_path.relative_to(PROJECT_ROOT)),
            "message": f"Successfully saved {filename}"
        }

    except Exception as e:
        logger.error(f"Error saving JSON file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{filename}/validate")
async def validate_json(filename: str, content: JSONContent):
    """
    Validate JSON content without saving.

    Args:
        filename: Name of the JSON file
        content: JSON content to validate

    Returns:
        Validation result
    """
    try:
        # Basic validation: ensure it's valid JSON (already done by Pydantic)
        # Additional validation can be added here based on filename/schema

        data = content.data

        # Determine type
        is_array = isinstance(data, list)
        is_object = isinstance(data, dict)

        validation = {
            "valid": True,
            "type": "array" if is_array else "object" if is_object else "other",
            "item_count": len(data) if (is_array or is_object) else None,
            "warnings": []
        }

        # Specific validation for config_inventory.json
        if filename == "config_inventory.json" and is_array:
            required_fields = ["var_name", "value_type", "suggested_category", "new_existing"]

            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    validation["warnings"].append(f"Item {i} is not an object")
                    continue

                for field in required_fields:
                    if field not in item:
                        validation["warnings"].append(f"Item {i} missing required field: {field}")

        return validation

    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


@router.get("/{filename}/download")
async def download_json(filename: str):
    """
    Download a JSON file.

    Args:
        filename: Name of the JSON file

    Returns:
        File download response
    """
    try:
        # Security: prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = JSON_BASE_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/json"
        )

    except Exception as e:
        logger.error(f"Error downloading JSON file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filename}/backups")
async def list_backups(filename: str):
    """
    List all backups for a specific JSON file.

    Args:
        filename: Name of the JSON file

    Returns:
        List of backup files with metadata
    """
    try:
        # Security: prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_stem = Path(filename).stem
        backups = []

        for backup_file in BACKUP_DIR.glob(f"{file_stem}_*.json"):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file.relative_to(PROJECT_ROOT)),
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        # Sort by created date (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)

        return {"backups": backups}

    except Exception as e:
        logger.error(f"Error listing backups for {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
