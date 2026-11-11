import csv 
import io
import os
import json

from PIL import Image, ImageDraw
from dataclasses import dataclass

from .output import ModelOutput
from ..converter import convert_latex_table_to_csv


@dataclass
class NemoparseData:
    text: list 
    bbox_json: str
    images: list
    tables: list
    bbox_image: Image
    page_number: int


class NemoparseOutput(ModelOutput):

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.images: list[list] = []
        self.tables: list[list] = []
        self.bboxdata: list[str] = []
        self.bbox_image: list[Image] = []
        self.page_number_list: list[int] = []
        
    def add_output(self, output_data):
        self.text.append(output_data.text)
        self.images.append(output_data.images)
        self.tables.append(output_data.tables)
        self.bboxdata.append(output_data.bbox_json)
        self.bbox_image.append(output_data.bbox_image)
        self.page_number_list.append(output_data.page_number)
        
    @classmethod
    def get_output_path(cls, output_directory, filename_base):
        return os.path.join(output_directory, f"{filename_base}.md")
        
    def save_output(self, output_directory, filename_base, save_images=False,
                    save_bbox_data=False, save_tables=False, save_page_numbers=False):
        img_index = 0
        img_filenames = []
        for image_list in self.images:
            for img in image_list:
                img_filename = f"{filename_base}_image_{img_index}.png"
                if save_images:
                    try:
                        img.save(os.path.join(output_directory, img_filename))
                    except Exception as e:
                        print(f"An error occurred trying to save the image: {img_filename}: {e}")

                img_index += 1
                img_filenames.append(img_filename)

        if save_bbox_data:
            with open(
                os.path.join(output_directory, f"{filename_base}_bbox.json"),
                "w+",
                encoding="utf-8",
            ) as f:
                json.dump(self.get_bbox_output(), f, indent=2)

            for index, bbox_image in enumerate(self.bbox_image):
                bbox_image.save(os.path.join(output_directory, f"{filename_base}_bbox_image_{index}.png"))

        if save_tables:
            table_index = 0
            for table_list in self.tables:
                for table in table_list:
                    table_name = f"{filename_base}_table_{table_index}.csv"
                    converted_table = convert_latex_table_to_csv(table)

                    with open(os.path.join(output_directory, table_name), 'w') as csv_file:
                        csv_writer = csv.writer(csv_file)
                        for row in converted_table:
                            csv_writer.writerow(row)

                    table_index += 1

        # Track line numbers for each text output 
        line_ranges = [0]

        # Write final markdown output
        with open(
            os.path.join(output_directory, f"{filename_base}.md"), "w+") as f:
            img_index = 0
            for idx, text_list in enumerate(self.text):
                line_count = 0
                for text in text_list:
                    if "![{}]({})" in text:
                        text = text.format(f"Image {img_index}", img_filenames[img_index])
                        img_index += 1
                    f.write(text + "\n\n")
                    line_count += len(text.split("\n")) + 1
                    #print(text)

                f.write("\n")
                
                prev_line_count = line_ranges[idx]
                line_ranges.append(line_count + prev_line_count + 1)

        if save_page_numbers:
            with open(
                os.path.join(output_directory, f"{filename_base}.metadata"), "w") as f:
                f.write("Page_Number,Markdown_Lines\n")
                for idx in range(len(self.text)):
                    text_start = line_ranges[idx]
                    text_end = line_ranges[idx+1]
                    page_num = self.page_number_list[idx]
                    row = f"{page_num},{text_start}-{text_end}\n"
                    f.write(row)
                #f.write("\n")

    def return_bytes(self, output_directory, filename_base, save_images=False,
                     save_bbox_data=False, save_tables=False, save_page_numbers=False):

        bytes_return_dict = dict()
        encoding = "utf-8"

        bytes_return_dict["encoding"] = encoding
        
        img_index = 0
        img_filenames = []
        image_bytes_list = []
        for image_list in self.images:
            for img in image_list:
                img_filename = f"{filename_base}_image_{img_index}.png"
                if save_images:
                    image_buffer = io.BytesIO()
                    img.save(image_buffer, format="PNG")
                    image_bytes_list.append(image_buffer.getvalue())

                img_index += 1
                img_filenames.append(img_filename)

        if save_images:
            bytes_return_dict["images"] = image_bytes_list
            bytes_return_dict["image_filenames"] = img_filenames

        if save_bbox_data:

            bbox_summary_string = ""
            for bboxdata in self.bboxdata:
                bbox_summary_string += json.dumps(bboxdata, indent=2) + "\n"

            bbox_summary = bbox_summary_string.encode(encoding)
            bytes_return_dict["bbox_summary"] = bbox_summary

            bbox_bytes_list = []            
            for bbox_image in self.bbox_image:
                image_buffer = io.BytesIO()
                bbox_image.save(image_buffer, format="PNG")
                bbox_bytes_list.append(image_buffer.getvalue())
            bytes_return_dict["bbox_images"] = bbox_bytes_list
        
        if save_tables:
            table_index = 0

            table_bytes_list = []            
            for table_list in self.tables:
                for table in table_list:
                    table_name = f"{filename_base}_table_{table_index}.csv"
                    converted_table = convert_latex_table_to_csv(table)

                    #with open(os.path.join(output_directory, table_name), 'w') as csv_file:
                    #    csv_writer = csv.writer(csv_file)
                    #    for row in converted_table:
                    #        csv_writer.writerow(row)

                    if isinstance(converted_table, list):
                        #print(f"converted_table: {type(converted_table)}")
                        #print(f"converted_table: {converted_table}")
                        #print(f"converted_table: {'\n'.join(converted_table)}")
                        #table_string = "\n".join(converted_table) + "\n"
                        table_string = ""
                        for row in converted_table:
                            row_string = ",".join(row) + "\n"
                            table_string += row_string

                    elif isinstance(converted_table, str):
                        table_string = converted_table
                    else:
                        raise NotImplementedError(f"\n[*] ERROR: unexpected type '{type(converted_table)}' for converted_table encountered...\n")

                    table_bytes_list.append(table_string.encode(encoding))

                    table_index += 1

            bytes_return_dict["tables"] = table_bytes_list

        # Track line numbers for each text output 
        line_ranges = [0]

        # Write final markdown output
        #with open(
        #    os.path.join(output_directory, f"{filename_base}.md"), "w+") as f:
        img_index = 0
        raw_markdown_string = ""
        for idx, text_list in enumerate(self.text):
            line_count = 0
            for text in text_list:
                if ("![{}]({})" in text):
                    text = text.format(f"Image {img_index}", img_filenames[img_index])
                    img_index += 1
                #f.write(text + "\n\n")
                raw_markdown_string += text + "\n\n"
                line_count += len(text.split("\n")) + 1
                #print(text)

            #f.write("\n")
            raw_markdown_string += "\n"

            prev_line_count = line_ranges[idx]
            line_ranges.append(line_count + prev_line_count + 1)
                    

        bytes_return_dict["markdown"] = raw_markdown_string.encode(encoding)

        if save_page_numbers:
            #with open(
            #    os.path.join(output_directory, f"{filename_base}.metadata"), "w") as f:
            #    f.write("Page_Number,Markdown_Lines\n")
            page_number_lines_list = []
            for idx in range(len(self.text)):
                text_start = line_ranges[idx]
                text_end = line_ranges[idx+1]
                page_num = self.page_number_list[idx]
                #row = f"{page_num},{text_start}-{text_end}\n"
                #f.write(row)
                page_number_lines_list.append( (page_num, (text_start, text_end))  )
                
            bytes_return_dict["page_number_lines"] = page_number_lines_list

        return bytes_return_dict
            

    def get_bbox_output(self, with_bbox_data=True):
        dict_data = {}
        for i, data in enumerate(self.bboxdata):
            if with_bbox_data:
                dict_data[f"page_{i}"] = data
            else:
                tmp_data = []
                for entry in data:
                    tmp_entry = {}
                    for key in entry:
                        if key != "bbox":
                            tmp_entry[key] = entry[key]
                    tmp_data.append(tmp_entry)
                dict_data[f"page_{i}"] = tmp_data
        return dict_data
        #return self.bboxdata

    def get_output_as_json(self, with_bbox_data=True):
        if with_bbox_data:
            return json.dumps(self.bboxdata)
        else:
            cleaned_data = []
            for bboxdata in self.bboxdata:
                tmp_data = []
                for entry in bboxdata:
                    tmp_entry = {}
                    for key in entry:
                        if key != "bbox":
                            tmp_entry[key] = entry[key]
                    tmp_data.append(tmp_entry)
                cleaned_data.append(tmp_data)
            return json.dumps(cleaned_data)

    def get_output_as_markdown(self):
        full_text = ""

        img_index = 0
        for page_number, page_text in enumerate(self.text):
            full_text += f"# Page {page_number}\n"
            for text in page_text:
                if "![{}]({})" in text:
                    text = text.format(f"Image {img_index}", f"image_{img_index}.png")
                    img_index += 1
                full_text += text
            full_text += "\n"

        return full_text

    def get_content_list(self):
        content = []
        for page_text in self.text:
            tmp_data = ""
            for text in page_text:
                tmp_data += text
            content.append(tmp_data)
        return content

    def get_images(self):
        images = []
        for image_list in self.images:
            for img in image_list:
                images.append(img)
        
        return images

    def get_output_status(self):
        no_outputs = []
