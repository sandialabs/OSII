import sys
import argparse
import json
import base64
import io
import os
import tempfile
import logging

from typing import Union, List
from openai import OpenAI
from PIL import Image, ImageDraw

# Use centralized logging
from ..utils.logging_config import get_logger

logger = get_logger("banyan")

from .processor import Processor
from ..converter.pdf_to_image import convert_pdf_to_images, convert_bytes_to_images
from ..output.nemoparse_output import NemoparseData, NemoparseOutput
from ..ocr.nemotron_ocr import NemotronOCR, ModelVersion

from ..utils.evaluate_extraction import evaluate_extraction
from ..utils.image_rotation import rotate_image, is_valid_rotation_angle
from ..utils.rotation_detection import detect_rotation_angle_with_fallback
from ..utils.kmeans import apply_kmeans

class NemoparseProcessor(Processor):

    def __init__(self, endpoint_url="", model_name="nvidia/nemoretriever-parse", sort_by_position=True, output_dir="./",
                 model_version=ModelVersion.LATEST, api_key: str | None = None):
        super().__init__()
        self.nemotron_ocr = NemotronOCR(
            endpoint_url=endpoint_url,
            model_name=model_name,
            model_version=model_version,
            api_key=api_key,
        )
        self.sort_by_position = sort_by_position
        self.output_dir = output_dir

    def sort_elements_by_position(self, bbox_data, width, height):
        """
        Sort document elements based on their spatial position.

        Args:
            bbox_data: List of element dictionaries from API response
            width: Page width in pixels
            height: Page height in pixels

        Returns:
            List of sorted element dictionaries
        """
        def get_sort_key(element):
            bbox = element['bbox']
            # Convert normalized coordinates to absolute pixels
            # Use top-left corner (ymin, xmin) instead of center for better reading order
            y_top = bbox['ymin'] * height
            x_left = bbox['xmin'] * width

            # Element type priority (headers first, then text, then other elements)
            type_priority = {
                'Section-header': 0,
                'Text': 1,
                'Formula': 2,
                'Code': 3,
                'Picture': 4,
                'Table': 5,
                'Caption': 6
            }.get(element['type'], 7)

            return (y_top, x_left, type_priority)

        return sorted(bbox_data, key=get_sort_key)

    def _encode_image(self, image):
        """
        Encode image data to base64 string.
        
        Args:
            image: Image data in bytes
            
        Returns:
            Base64 encoded string or None if encoding fails
            
        Raises:
            ValueError: If image data is invalid
            UnicodeDecodeError: If UTF-8 decoding fails
        """
        try:
            if not image:
                raise ValueError("Image data cannot be empty or None")
            base64_encoded_data = base64.b64encode(image)
            base64_string = base64_encoded_data.decode("utf-8")
            return base64_string
        except ValueError as e:
            logger.error(f"Invalid image data: {e}")
            return None
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode base64 data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error encoding image: {e}")
            return None

    def _run_single_ocr_pass(self, image, draw_bboxes, temperature, page_number=None):
        base64_string = self._encode_image(image)
        base64_image = f"data:image/png;base64,{base64_string}"

        # Use the wrapper for image processing with temperature
        bbox_data = self.nemotron_ocr.get_detailed_ocr_results(base64_image, temperature=temperature)

        base_image = Image.open(io.BytesIO(image))
        width, height = base_image.size

        # Sort elements by spatial position if enabled
        if self.sort_by_position:
            bbox_data = self.sort_elements_by_position(bbox_data, width, height)

        if draw_bboxes:
            bbox_draw = ImageDraw.Draw(base_image)
            color_dict = {
                        "Text": "red",
                        "Formula": "green",
                        "Code": "blue",
                        "Picture": "magenta",
                        "Table": "cyan",
                        "Caption": "yellow",
                        }

        txt = []
        images = []
        tables = []

        for entry in bbox_data:
            bbox = entry['bbox']
            xmin = bbox['xmin'] * width
            ymin = bbox['ymin'] * height
            xmax = bbox['xmax'] * width
            ymax = bbox['ymax'] * height

            element_text = entry['text']
            if entry['type'] == "Picture":
                cropped_image = base_image.crop((xmin, ymin, xmax, ymax))
                images.append(cropped_image)
                element_text = "![{}]({})"
            elif entry['type'] == "Table":
                tables.append(entry['text'])
            elif entry['type'] == "Section-header" and "#" not in entry['text']:
                element_text = f"# {entry['text']}"

            txt.append(element_text)

            if draw_bboxes:
                if entry['type'] in color_dict:
                    color = color_dict[entry['type']]
                    if ymin > ymax:
                        ymin, ymax = ymax, ymin
                    if xmin > xmax:
                        xmin, xmax = xmax, xmin
                    bbox_draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=4)

        return NemoparseData(text=txt, bbox_json=bbox_data, images=images,
                             tables=tables, bbox_image=base_image, page_number=page_number) 

    def _process_image(self, image, input_filename="image.png", temperature=0.0, draw_bboxes=True,
                       re_run=False, re_run_temp=0.4, rotation_angle: float = 0,
                       auto_detect_rotation: bool = False, rotation_confidence_threshold: float = 0.7,
                       apply_highcontrast_filter: bool = False, debug: bool = False, page_number: int | None = None):

        if debug: print(f"\nRunning with temperature {temperature}")
        
        # Auto-detect rotation using Tesseract OCR if enabled
        if auto_detect_rotation:
            try:
                # Convert image bytes to PIL Image for rotation detection
                pil_image = Image.open(io.BytesIO(image))
                
                # Detect rotation angle with fallback handling
                detected_angle = detect_rotation_angle_with_fallback(
                    pil_image, 
                    confidence_threshold=rotation_confidence_threshold
                )
                
                # Log detected rotation angle for debugging
                if detected_angle != 0:
                    logger.info(f"Auto-detected rotation angle: {detected_angle} degrees")
                else:
                    logger.debug("Auto-detection: no rotation needed (angle = 0)")
                
                # Apply detected rotation if non-zero
                if detected_angle != 0:
                    rotated_image = rotate_image(pil_image, detected_angle)
                    # Convert back to bytes for processing
                    img_byte_arr = io.BytesIO()
                    rotated_image.save(img_byte_arr, format='PNG')
                    image = img_byte_arr.getvalue()
                    
            except Exception as e:
                # Handle any errors during rotation detection gracefully
                logger.warning(f"Rotation detection failed, proceeding without rotation: {e}")
                # Continue with original image

        if apply_highcontrast_filter:
            print("Applying kmeans filter")
            image = apply_kmeans(image, input_filename=input_filename, output_dir=self.output_dir, save_fig=True)

        if rotation_angle != 0:
            print("Applying rotation")
            image = rotate_image(Image.open(io.BytesIO(image)), rotation_angle)
            # Convert back to bytes for processing
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            image = img_byte_arr.getvalue()

        # Apply manual rotation if specified (takes precedence over auto-detection)
        output = self._run_single_ocr_pass(image, draw_bboxes=draw_bboxes, temperature=temperature, page_number=page_number)

        if not re_run:
            return output

        # Evaluate the initial pass to get our starting metrics
        should_rerun, missed_percentage = evaluate_extraction(
            image_bytes=image,
            bbox_data=output.bbox_json,
            temperature=temperature
        )

        # Set the baseline for the best performing run
        best_output = output
        lowest_missed = missed_percentage

        if not should_rerun:
            logger.info("Initial pass meets criteria. Proceeding with current output.")
            return best_output

        logger.info("Initial pass flagged for improvement. Initiating retry loop.")
        attempts = 0
        max_attempts = 3
        
        while attempts < max_attempts:
            attempts += 1
            logger.info(f"\n*** Retry Attempt {attempts} of {max_attempts} (Temp: {re_run_temp}) ***")
            
            # Generate new output
            current_output = self._run_single_ocr_pass(image, draw_bboxes=draw_bboxes, temperature=re_run_temp, page_number=page_number)
            
            # Evaluate the new output
            should_rerun, missed_percentage = evaluate_extraction(
                image_bytes=image,
                bbox_data=current_output.bbox_json,
                temperature=re_run_temp
            )

            # Compare and save the run with the lowest missed percentage
            if missed_percentage < lowest_missed:
                lowest_missed = missed_percentage
                best_output = current_output

            # Stop retrying if we hit a successful threshold
            if not should_rerun:
                print(f"Retry {attempts} successful. Breaking loop.")
                break
                
            # Log when we hit the absolute limit
            if attempts == max_attempts:
                print(f"Max retries exhausted. Returning best attempt with {lowest_missed:.1f}% missed area.")
                
        return best_output

    def get_pages(self, filepath):
        file_pages = []
        if isinstance(filepath, io.BytesIO):
            images = convert_bytes_to_images(filepath.read())
            for image in images:
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                file_pages.append(img_byte_arr)
        else:
            image_extensions = set(["png", "PNG", "jpg", "JPG", "tif", "TIF"])
            long_image_extensions = set(["jpeg", "JPEG"])
            filepath_extension = filepath.split('.')[-1]
            if filepath_extension in image_extensions or filepath_extension in long_image_extensions:
                with open(filepath, "rb") as image_file:
                    file_pages.append(image_file.read())
            else:
                try:
                    images = convert_pdf_to_images(filepath)
                    for image in images:
                        img_byte_arr = io.BytesIO()
                        image.save(img_byte_arr, format='PNG')
                        img_byte_arr = img_byte_arr.getvalue()
                        file_pages.append(img_byte_arr)
                except Exception as e:
                    raise ValueError(f"Unsupported filetype or error processing file {filepath}: {e}")

        if len(file_pages) == 0:
            raise ValueError(f"Unsupported filetype or error processing file {filepath}: no pages detected")
        return file_pages

    def process_batch_documents(self, filepaths, use_checkpointing=True, output_dir="./", draw_bboxes=True, 
                               re_run=False,
                               temperature=0.0,
                               rotation_angle: Union[int, float] = 0, 
                               auto_detect_rotation: bool = False, 
                               rotation_confidence_threshold: float = 0.7,                               
                               apply_highcontrast_filter: bool = False,
                               output_basenames: List[str] | None = None,
                               overwrite: bool = False,
                               save_images: bool = False,
                               save_bbox_data: bool = False,
                               save_tables: bool = False,
                               include_failures: bool = False):
        """
        Process multiple documents with optional rotation.
        
        Args:
            filepaths: List of file paths to process
            use_checkpointing: Whether to save outputs as they are processed (default: True)
            output_dir: What directory to use for checkpointing
            draw_bboxes: Whether to draw bounding boxes on output images (default: True)
            rotation_angle: Rotation angle in degrees (default: 0)
            auto_detect_rotation: Whether to automatically detect rotation (default: False)
            rotation_confidence_threshold: Minimum confidence for auto rotation detection (default: 0.7)
            
        Returns:
            List of NemoparseOutput objects if use_checkpointing=False, else empty list.
            When include_failures is true, the list is aligned with filepaths and
            uses None for files that were skipped or failed.
        """        
        # Log batch processing information
        logger.info(f"Processing batch of {len(filepaths)} documents")
        if auto_detect_rotation:
            logger.info("Auto rotation detection enabled for batch processing")
        if rotation_angle != 0:
            logger.info(f"Manual rotation angle for batch: {rotation_angle} degrees")

        file_outputs = []
        for idx, filepath in enumerate(filepaths):
            try:

                if output_basenames is not None:
                    basename = output_basenames[idx]
                else:
                    basename = os.path.splitext(os.path.basename(filepath))[0]
                output_path = NemoparseOutput.get_output_path(self.output_dir, basename)
                if os.path.exists(output_path) and (not overwrite):
                    logger.info(f"--> output file '{output_path}' already exists; skipping...  (use '--overwrite' option to regenerate output)")
                    if include_failures and not use_checkpointing:
                        file_outputs.append(None)
                    continue

                output = self.process_document(
                    filepath, 
                    draw_bboxes=draw_bboxes, 
                    re_run=re_run,
                    temperature=temperature,
                    rotation_angle=rotation_angle,
                    auto_detect_rotation=auto_detect_rotation,
                    rotation_confidence_threshold=rotation_confidence_threshold,
                    apply_highcontrast_filter=apply_highcontrast_filter,
                )
                if use_checkpointing:
                    basename = os.path.basename(filepath)
                    logger.info(f"Saving output for: {basename}")
                    output.save_output(output_dir, basename, save_images=save_images, save_bbox_data=save_bbox_data, save_tables=save_tables)
                else:
                    file_outputs.append(output)
                    
            except Exception as e:
                logger.error(f"Failed to process file {filepath}: {e}")
                if include_failures and not use_checkpointing:
                    file_outputs.append(None)
                # Continue with next file even if one fails
                continue

        logger.info(f"Batch processing completed. Processed {len(file_outputs) if not use_checkpointing else len(filepaths)} files.")
        return file_outputs

    def process_document(self, filepath,
                         draw_bboxes=True, 
                         re_run=False,
                         temperature=0.0,
                         rotation_angle: Union[int, float] = 0,
                         auto_detect_rotation: bool = False,
                         rotation_confidence_threshold: float = 0.7,
                         apply_highcontrast_filter: bool = False,
                         output_basename: str | None = None,
                         overwrite: bool = False):
        """
        Process a single document with optional rotation.
        
        Args:
            filepath: Path to the document file
            draw_bboxes: Whether to draw bounding boxes on output images (default: True)
            rotation_angle: Rotation angle in degrees (default: 0)
            auto_detect_rotation: Whether to automatically detect rotation (default: False)
            rotation_confidence_threshold: Minimum confidence for auto rotation detection (default: 0.7)
            
        Returns:
            NemoparseOutput object containing processed document data
            
        Raises:
            FileNotFoundError: If the input file cannot be found
            PermissionError: If the input file cannot be read
            ValueError: If rotation parameters are invalid or file type is unsupported
            Exception: For other processing errors
        """
        # Validate rotation angle if provided
        if rotation_angle != 0 and not is_valid_rotation_angle(rotation_angle):
            raise ValueError(f"Invalid rotation angle: {rotation_angle}")
         
        # Validate confidence threshold
        if not (0.0 <= rotation_confidence_threshold <= 1.0):
            raise ValueError(f"rotation_confidence_threshold must be between 0.0 and 1.0, got {rotation_confidence_threshold}")
         
        # Normalize rotation angle
        from ..utils.image_rotation import normalize_rotation_angle
        normalized_angle = normalize_rotation_angle(rotation_angle) if rotation_angle != 0 else 0

        # Log rotation processing information
        if auto_detect_rotation:
            logger.info("Auto rotation detection enabled")
        if normalized_angle != 0:
            logger.info(f"Manual rotation angle: {normalized_angle} degrees")
        if auto_detect_rotation and normalized_angle != 0:
            logger.warning("Both manual rotation and auto-detection are enabled. Manual rotation will take precedence.")

        # Basic check of file type and get pages
        try:
            file_pages = self.get_pages(filepath)
        except Exception as e:
            raise ValueError(f"Error processing file {filepath}: {e}")

        output = NemoparseOutput()
        logger.info(f"Processing file: {filepath}")

        # Check if output file already exists
        if output_basename is not None:
            basename = output_basename
        else:
            basename = os.path.splitext(os.path.basename(filepath))[0]

        output_path = NemoparseOutput.get_output_path(self.output_dir, basename)
        if os.path.exists(output_path) and (not overwrite):
            logger.info(f"--> output file '{output_path}' already exists; skipping...  (use '--overwrite' option to regenerate output)")
            return None

        for page_num, page_image in enumerate(file_pages, 1):
            try:
                logger.debug(f"Processing page {page_num}")
                output.add_output(self._process_image(
                    page_image,
                    input_filename=f"page_{page_num}.png",
                    draw_bboxes=draw_bboxes, 
                    re_run=re_run,
                    temperature=temperature,
                    rotation_angle=normalized_angle,
                    auto_detect_rotation=auto_detect_rotation,
                    rotation_confidence_threshold=rotation_confidence_threshold,
                    apply_highcontrast_filter=apply_highcontrast_filter,
                    page_number=page_num,
                ))
            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                raise

        return output
