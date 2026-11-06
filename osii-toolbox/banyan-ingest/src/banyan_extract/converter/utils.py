from pathlib import Path

def file_requires_conversion(filepath: str) -> bool:
    """
    Check if the file is an Office document that requires conversion to PDF.
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if the file needs conversion, False otherwise
    """
    supported_extensions = {'.docx', '.pptx', '.xlsx', '.doc', '.ppt', '.xls'}
    return Path(filepath).suffix.lower() in supported_extensions
