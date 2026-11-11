import sys
import os
import argparse

from banyan_extract import MarkerProcessor


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", default=None, type=str, help="Path for a single file to be processed")
    parser.add_argument("output_dir", default=None, type=str, help="Path for output from single or multiple files")
    parser.add_argument("--is_input_dir", action="store_true",  help="Flags to set input file to directory")
    parser.add_argument("--output_base", default="banyan-extract-output", type=str,  help="Base name for output files")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()

    output_directory = args.output_dir
    output_base = args.output_base

    document_processor = MarkerProcessor()

    if args.is_input_dir:
        input_directory = args.input_file

        file_paths = []
        basenames = []
        for root, _, files in os.walk(input_directory):
            for filename in files:
                if ".pdf" in filename:
                    file_paths.append(os.path.join(root, filename))
                    basenames.append(os.path.basename(filename))

        outputs = document_processor.process_batch_documents(file_paths)
        for file_output, basename in zip(outputs, basenames):
            file_output.save_output(output_directory, basename)
    else:
        filename = args.input_file
        outputs = document_processor.process_document(filename)

        outputs.save_output(output_directory, output_base)
