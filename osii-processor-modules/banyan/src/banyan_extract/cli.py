import argparse
import os
import sys
import logging

from banyan_extract import BanyanExtract
from banyan_extract.utils.logging_config import setup_logger
from banyan_extract.ocr import ModelVersion

# Configure logging using centralized setup
logger = setup_logger("banyan")


def validate_rotation_confidence_threshold(threshold):
    """Validate rotation confidence threshold regardless of auto-detection flag."""
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"rotation_confidence_threshold must be between 0.0 and 1.0, got {threshold}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Banyan Extract - Document Processing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single PDF file
  python -m banyan_extract input.pdf output_dir/
 
  # Process all files in a directory
  python -m banyan_extract input_dir/ output_dir/ --is_input_dir
 
  # Use specific backend
  python -m banyan_extract input.pdf output_dir/ --backend nemoparse
 
  # Enable rotation detection
  python -m banyan_extract input.pdf output_dir/ --auto_detect_rotation
 
  # Manual rotation with bounding boxes
  python -m banyan_extract input.pdf output_dir/ --rotation_angle 90 --draw_bboxes
  
  # Process PPTX with default Nemotron OCR backend
  python -m banyan_extract presentation.pptx output_dir/
  
  # Process PPTX with Surya OCR backend
  python -m banyan_extract presentation.pptx output_dir/ --pptx_ocr_backend surya
        """
    )
    
    parser.add_argument("input_file", default=None, type=str, 
                       help="Path for a single file to be processed")
    parser.add_argument("output_dir", default=None, type=str, 
                       help="Path for output from single or multiple files")
    parser.add_argument("--is_input_dir", action="store_true", 
                       help="Flag to set input file to directory")
    parser.add_argument("--preserve_input_structure", action="store_true", 
                       help="Flag to preserve input directory structure in output directory")
    parser.add_argument("--file_extensions", default=None, type=str, 
                       help="Comma-separated list of file extensions to process (e.g., 'pdf,pptx'). If not provided, defaults to common document types.")
    parser.add_argument("--recursion_depth", default=1, type=int,
                       help="Recursion depth for directory crawling: 0 = only root, 1 = root + immediate subdirectories (default), -1 = infinite, n = specific depth limit")
    parser.add_argument("--output_base", default="banyan-extract-output", type=str, 
                       help="Base name for output files (default: banyan-extract-output)")
    parser.add_argument("--backend", default="auto", type=str, 
                       help="Which backend to use: auto (auto-detect), nemoparse (Nemotron Parse), "
                            "marker (marker), pptx (PPTX processor). Default: auto")
    parser.add_argument("--config_file", default=".env", type=str, 
                       help="Which config file to use (defaults to ./.env)")
    parser.add_argument("--endpoint", default="", type=str, 
                       help="Endpoint URL for nemoretriever-parse model")
    parser.add_argument("--model_name", default="", type=str, 
                       help="Model name for nemoretriever-parse model")
    parser.add_argument("--model_version", default=ModelVersion.LATEST, type=ModelVersion, 
                       help="Model version for nemoretriever-parse model")
    parser.add_argument("--checkpointing", action="store_true", 
                       help="If enabled, batch documents will be saved as they get processed")

    parser.add_argument("--draw_bboxes", action="store_true", default=False, 
                       help="If enabled, output will include images showing detected bounding boxes")
    parser.add_argument("--save_bbox_data", action="store_true", default=False, 
                       help="If enabled, output will include bbox data")
    parser.add_argument("--save_images", action="store_true", default=False, 
                       help="If enabled, output will include images")
    parser.add_argument("--save_tables", action="store_true", default=False, 
                       help="If enabled, output will include tables")
    parser.add_argument("--save_page_numbers", action="store_true", default=False, 
                       help="If enabled, output will save page numbers associated with output lines")
    parser.add_argument("--return_bytes", action="store_true", default=False, 
                       help="If enabled, output will be returned as bytes")

    parser.add_argument("--sort_by_position", action="store_true", default=True, 
                       help="Sort elements by spatial position for logical reading order (default: True)")
    parser.add_argument("--overwrite", action="store_true", default=False, 
                       help="Overwrite existing markdown output files (default: False)")
    
    # Updated Help Descriptions for re_run and temperature
    parser.add_argument("--re_run", action="store_true", default=False, help="Enables automatic retries. Uses contour area detection to evaluate missed regions, and re-runs the model at higher temperatures (max 3 retries) if the missed area is too high. Note: This flag is ONLY supported by the nemotron parse model.")
    parser.add_argument("--temperature", default=0.0, type=float, help="Temperature setting for the model. Note: This flag is ONLY supported by the nemotron parse model.")

    # Rotation detection arguments
    parser.add_argument("--rotation_angle", default=0, type=float, 
                       help="Angle in degrees to rotate the input page(s). Default: 0 (no rotation)")
    parser.add_argument("--auto_detect_rotation", action="store_true", 
                       help="Automatically detect and correct document rotation using Tesseract OCR")
    parser.add_argument("--rotation_confidence_threshold", default=0.7, type=float, 
                       help="Minimum confidence threshold (0.0-1.0) for automatic rotation detection. "
                            "Default: 0.7")

    # Contrast filter arguments
    parser.add_argument("--apply_contrast_filter", action="store_true", default=False, help="Flag that applies a high-contrast filter to the input prior to being sent to the ocr. Results may vary")
    
    # LibreOffice conversion arguments
    parser.add_argument("--libreoffice_path", default="libreoffice", type=str, 
                        help="Path to LibreOffice executable (default: libreoffice)")
    parser.add_argument("--conversion_temp_dir", default=None, type=str, 
                        help="Temporary directory for converted PDFs (default: system temp)")
    parser.add_argument("--enable_conversion", action="store_true", default=False, 
                        help="Enable automatic conversion of Office documents to PDF")

    # Add PPTX-specific arguments
    parser.add_argument("--pptx_ocr_backend", default="nemotron", type=str, 
                       help="OCR backend for PPTX processing: surya or nemotron. Default: nemotron")
    parser.add_argument("--pptx_nemotron_endpoint", default="", type=str, 
                       help="Nemotron endpoint URL for PPTX OCR (if using nemotron backend)")
    parser.add_argument("--pptx_nemotron_model", default="", type=str, 
                       help="Nemotron model name for PPTX OCR")
    
    args = parser.parse_args()
    
    # Early validation if user explicitly sets a backend that isn't nemoparse
    if args.backend not in ["auto", "nemoparse"]:
        if args.re_run or args.temperature != 0.0:
            parser.error("The --re_run and --temperature flags can only be used with the nemotron parse model (nemoparse backend).")
    
    # Validate rotation confidence threshold regardless of auto-detection flag
    try:
        validate_rotation_confidence_threshold(args.rotation_confidence_threshold)
    except ValueError as e:
        parser.error(str(e))
    
    # Validate PPTX OCR backend argument
    if args.pptx_ocr_backend not in ["surya", "nemotron"]:
        parser.error(f"Invalid PPTX OCR backend: {args.pptx_ocr_backend}. Must be 'surya' or 'nemotron'")
    
    # Validate and compute effective extensions
    effective_extensions = {"pdf", "pptx"}
    if args.file_extensions:
        exts = [ext.strip().lower().lstrip(".") for ext in args.file_extensions.split(",")]
        if not exts or any(not ext for ext in exts):
            parser.error("Invalid --file_extensions provided. Please provide a comma-separated list of extensions.")
        effective_extensions = set(exts)
    args.effective_extensions = effective_extensions

    # Warn if both manual rotation and auto detection are specified
    if args.auto_detect_rotation and args.rotation_angle != 0:
        logger.warning("Both manual rotation angle and auto rotation detection are specified. "
                      "Manual rotation will take precedence over auto detection.")
    
    # Check Tesseract dependencies if auto-detection is enabled
    if args.auto_detect_rotation:
        try:
            from banyan_extract.utils.tesseract_dependencies import has_tesseract_dependencies
            if not has_tesseract_dependencies():
                logger.warning("Auto-rotation detection enabled but Tesseract OCR dependencies are not available.")
                logger.warning("Rotation detection will be skipped. Install Tesseract OCR and pytesseract to enable this feature.")
        except ImportError:
            # If tesseract_dependencies module is not available, log a warning
            logger.warning("Auto-rotation detection enabled but dependency checking failed.")
            logger.warning("Ensure Tesseract OCR and pytesseract are installed for rotation detection.")
    
    return args


def main():
    # Parse command-line arguments
    args = parse_arguments()
    
    # Convert argparse Namespace to dictionary
    args_dict = vars(args)

    # Pass dictionary entries as keyword arguments
    extractor = BanyanExtract(logger=logger, **args_dict)

    # Extract content from document
    extractor(input_file=args.input_file,
              output_dir=args.output_dir,
              is_input_dir=args.is_input_dir,
              output_base=args.output_base,
              )


if __name__ == '__main__':
    main()
