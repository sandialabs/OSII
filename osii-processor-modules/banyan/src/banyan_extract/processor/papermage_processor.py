from papermage.magelib import Document
from papermage.recipes import CoreRecipe
from papermage.visualizers.visualizer import plot_entities_on_page
import pathlib
import numpy as np
from typing import Union
import logging

from .processor import Processor
from ..output.papermage_output import PaperMageOutput

# Use centralized logging
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class PaperMageProcessor(Processor):
    
    def __init__(self, output_dir=None):
        super().__init__()
        self.recipe = CoreRecipe()
        self.output_dir = output_dir

    def process_document(self, mode, filepath, options=None, colors=None, rotation_angle: Union[int, float] = 0,
                       auto_detect_rotation: bool = False, 
                       rotation_confidence_threshold: float = 0.7):
        # Note: PaperMage processor doesn't currently support rotation as it works directly with PDF files
        # For future implementation, we would need to rotate the PDF pages before processing
        if rotation_angle != 0 or auto_detect_rotation:
            logger.warning(f"Rotation is not currently supported for PaperMageProcessor. Angle {rotation_angle} and auto-detection will be ignored.")
        
        pdf_path = pathlib.Path(filepath)

        if mode == 'bound_single':
            output = []

            doc = self.recipe.from_pdf(pdf=pdf_path)

            for page_num, page in enumerate(doc.pages):
                intersect_dict = {}

                for option in options:
                    intersect_dict[option] = page.intersect_by_box(option)

                plotted = plot_entities_on_page(page_image=doc.images[page_num], entities=intersect_dict[options[0]], box_color=colors[0])

                for idx, option in enumerate(options[1:]):
                    plotted = plot_entities_on_page(page_image=plotted, entities=intersect_dict[option], box_color=colors[idx])
                 

                output.append(plotted)

        elif mode == 'extract_single':
            output = self.recipe.run(pdf_path)
             

        return PaperMageOutput(output)


    def process_batch_documents(self, mode, filepaths, options=None, colors=None, rotation_angle: Union[int, float] = 0,
                               auto_detect_rotation: bool = False, 
                               rotation_confidence_threshold: float = 0.7):
        # Note: PaperMage processor doesn't currently support rotation as it works directly with PDF files
        if rotation_angle != 0 or auto_detect_rotation:
            print(f"Warning: Rotation is not currently supported for PaperMageProcessor. Angle {rotation_angle} and auto-detection will be ignored.")
        
        parent_path = pathlib.Path(filepaths)
        file_list = list(pathlib.Path(parent_path).glob('*.pdf'))

        if mode == 'bound_batch':
            output = {}

            for filename in file_list:
                filename_strip = str(filename.name).replace('.pdf', '')
                output[filename_strip] = []

                doc = self.recipe.from_pdf(pdf=filename)

                for page_num, page in enumerate(doc.pages):
                    intersect_dict = {}

                    for option in options:
                        intersect_dict[option] = page.intersect_by_box(option)

                    plotted = plot_entities_on_page(page_image=doc.images[page_num], entities=intersect_dict[options[0]], box_color=colors[0])

                    for idx, option in enumerate(options[1:]):
                        plotted = plot_entities_on_page(page_image=plotted, entities=intersect_dict[option], box_color=colors[idx])
                     

                    output[filename_strip].append(plotted)

        elif mode == 'extract_batch':
            output = {}

            for filename in file_list:
                filename_strip = str(filename.name).replace('.pdf', '')
                output[filename_strip]=self.recipe.run(filename)

        return PaperMageOutput(output)
    
