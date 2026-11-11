import os
import json

from .output import ModelOutput

try:
    from marker.settings import settings
except ImportError:
    # Marker is an optional dependency
    # This will be handled by the dependency check in tests
    settings = None


class MarkerOutput(ModelOutput):
    def __init__(self, output_data):
        super().__init__()
        self.text = output_data.markdown.encode(settings.OUTPUT_ENCODING, errors="replace").decode(
            settings.OUTPUT_ENCODING
        )
        self.images: list = output_data.images
        self.tables: list = output_data.tables
        self.metadata = output_data.metadata

    def save_output(self, output_directory, filename_base, **_ignored_options):
        with open(
            os.path.join(output_directory, f"{filename_base}.md"),
            "w+",
            encoding=settings.OUTPUT_ENCODING,
        ) as f:
            f.write(self.text)
        with open(
            os.path.join(output_directory, f"{filename_base}_meta.json"),
            "w+",
            encoding=settings.OUTPUT_ENCODING,
        ) as f:
            f.write(json.dumps(self.metadata, indent=2))

        for img_name, img in self.images.items():
            img.save(os.path.join(output_directory, f"{filename_base}_{img_name}"), settings.OUTPUT_IMAGE_FORMAT)

        for i, table in enumerate(self.tables):
            table_name = f"{filename_base}_table_{i}.csv"
            table.to_csv(os.path.join(output_directory, table_name))
