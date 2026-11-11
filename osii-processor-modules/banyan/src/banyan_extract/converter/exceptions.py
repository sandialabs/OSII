class LibreOfficeConversionError(Exception):
    """Base class for LibreOffice conversion errors."""
    pass


class LibreOfficeNotFoundError(LibreOfficeConversionError):
    """LibreOffice executable not found."""
    pass


class UnsupportedFormatError(LibreOfficeConversionError):
    """Input file format not supported for conversion."""
    pass


class ConversionTimeoutError(LibreOfficeConversionError):
    """Conversion process exceeded timeout."""
    pass


class ConversionFailedError(LibreOfficeConversionError):
    """Conversion process failed."""
    pass


class CleanupFailedError(LibreOfficeConversionError):
    """Temporary file cleanup failed."""
    pass
