from abc import ABC, abstractmethod
from typing import Union, List, Optional

class Processor(ABC):
    """
    Abstract base class for document processors.
    
    All concrete processors must implement the process_document and process_batch_documents methods.
    """
    
    def __init__(self):
        """Initialize the processor."""
        pass

    @abstractmethod
    def process_document(self, filepath, rotation_angle: Union[int, float] = 0, 
                       auto_detect_rotation: bool = False, 
                       rotation_confidence_threshold: float = 0.7):
        """
        Process a single document with optional rotation.
        
        Args:
            filepath: Path to the document file
            rotation_angle: Rotation angle in degrees (default: 0)
            auto_detect_rotation: Whether to automatically detect rotation (default: False)
            rotation_confidence_threshold: Minimum confidence for auto rotation detection (default: 0.7)
            
        Returns:
            Processed document output object specific to the processor implementation
            
        Raises:
            FileNotFoundError: If the input file cannot be found
            PermissionError: If the input file cannot be read
            ValueError: If rotation parameters are invalid
            Exception: For other processing errors
        """
        pass

    @abstractmethod
    def process_batch_documents(self, filepaths, rotation_angle: Union[int, float] = 0,
                               auto_detect_rotation: bool = False, 
                               rotation_confidence_threshold: float = 0.7):
        """
        Process multiple documents with optional rotation.
        
        Args:
            filepaths: List of paths to document files
            rotation_angle: Rotation angle in degrees (default: 0)
            auto_detect_rotation: Whether to automatically detect rotation (default: False)
            rotation_confidence_threshold: Minimum confidence for auto rotation detection (default: 0.7)
            
        Returns:
            List of processed document output objects
            
        Raises:
            FileNotFoundError: If any input file cannot be found
            PermissionError: If any input file cannot be read
            ValueError: If rotation parameters are invalid
            Exception: For other processing errors
        """
        pass
