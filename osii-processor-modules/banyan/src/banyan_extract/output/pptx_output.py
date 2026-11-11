import os
import json

from .output import ModelOutput


class PptxOutput(ModelOutput):
    def __init__(self, text: list, images: list, metadata):
        super().__init__()
        self.text: list = text
        self.images: list = images
        self.metadata = metadata

    def get_output_path(self, output_directory, filename_base):
        return os.path.join(output_directory, f"{filename_base}.md")
        
    def save_output(self, output_directory, filename_base, **_ignored_options):
        with open(os.path.join(output_directory, f"{filename_base}.md"), "w+") as f:
            for slide_id, slide in enumerate(self.text):
                f.write(f"# Slide {slide_id}\n")
                f.write(slide)
                f.write("\n")

        with open(os.path.join(output_directory, f"{filename_base}_meta.json"), "w+") as f:
            f.write(json.dumps(self.metadata, indent=2))

        for slide_number, slide_images in enumerate(self.images):
            for image_id, image in enumerate(slide_images):
                img_name = f"Slide_{slide_number}_image_{image_id}.png"
                image.save(os.path.join(output_directory, img_name))
