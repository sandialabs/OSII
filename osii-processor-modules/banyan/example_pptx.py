import argparse

from banyan_extract import PptxProcessor

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", default=None, type=str, help="Path for a single file to be processed")
    parser.add_argument("output_dir", default=None, type=str, help="Path for output from single or multiple files")
    parser.add_argument("--output_base", default="banyan-extract-output", type=str,  help="Base name for output files")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()

    filename = args.input_file
    output_directory = args.output_dir
    output_base = args.output_base

    document_processor = PptxProcessor()
    outputs = document_processor.process_document(filename)

    outputs.save_output(output_directory, output_base)

