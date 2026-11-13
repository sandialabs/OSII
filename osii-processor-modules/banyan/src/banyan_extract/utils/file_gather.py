from pathlib import Path
from typing import List, Set

def gather_files(path: Path, extensions: Set[str], max_depth: int = 1) -> List[Path]:
    """
    Gather files with matching extensions from a given path with depth control.

    Args:
        path: The root path to start gathering files from.
        extensions: A set of allowed file extensions (without leading dots).
        max_depth: Maximum recursion depth. 1 for immediate subdirectories, 
                  -1 for infinite recursion, or a positive integer for specific depth.

    Returns:
        A list of paths to files with matching extensions, relative to the input path.
    """
    # Normalize extensions to lowercase and remove leading dots
    normalized_extensions = {ext.lower().lstrip(".") for ext in extensions}
    gathered_files = []

    if path.is_file():
        if path.suffix.lower().lstrip(".") in normalized_extensions:
            # Use .name to get the relative path for a single file to maintain consistency
            gathered_files.append(path.name)
    elif path.is_dir():
        # We use a manual walk or similar to control depth
        # Since rglob doesn't support depth, we'll use a recursive helper or os.walk
        
        def _walk(current_path: Path, current_depth: int):
            if max_depth != -1 and current_depth > max_depth:
                return

            try:
                for item in current_path.iterdir():
                    # Ignore hidden files/directories
                    if item.name.startswith("."):
                        continue
                    
                    if item.is_file():
                        if item.suffix.lower().lstrip(".") in normalized_extensions:
                            gathered_files.append(item.relative_to(path))
                    elif item.is_dir():
                        _walk(item, current_depth + 1)
            except PermissionError:
                pass

        _walk(path, 0)

    return sorted([Path(p) for p in gathered_files])
