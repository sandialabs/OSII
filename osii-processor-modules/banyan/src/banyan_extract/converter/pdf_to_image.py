import pymupdf

from PIL import Image

def convert_pdf_to_images(file_path, dpi=200):
    """
    Converts pdf to images
    Args:
        file_path (str): The path to the PDF file.
    Return:
        list of PIL images
    """
    images = []
    pdf_file = pymupdf.open(file_path) 
    for page in pdf_file:
        pix = page.get_pixmap(dpi=dpi)
        images.append(pix.pil_image())
    return images

def convert_bytes_to_images(byte_stream, dpi=200):
    """
    Converts pdf byte stream to images
    Args:
        byte_stream (BytesIO): The byte-stream from the pdf
    Return:
        list of PIL images
    """
    images = []
    pdf_file = pymupdf.open("pdf", byte_stream)
    for page in pdf_file:
        pix = page.get_pixmap(dpi=dpi)
        images.append(pix.pil_image())
    return images
