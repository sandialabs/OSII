
verbose_warnings = False
    
try:
    from .marker_processor import MarkerProcessor 
except Exception as e:
    if verbose_warnings:
        print(f"Marker not installed, cannot use MarkerProcessor, {e}")

try:
    from .papermage_processor import PaperMageProcessor
except:
    if verbose_warnings:
        print("papermage not installed, cannot use PaperMageProcessor")

from .nemoparse_processor import NemoparseProcessor 
from .pptx_processor import PptxProcessor 
