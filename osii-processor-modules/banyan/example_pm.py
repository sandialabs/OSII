import argparse
from banyan_extract import PaperMageProcessor

def define_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", default=None, type=str, nargs="?", help="Path for a single file to be processed")
    parser.add_argument("--input_dir", default=None, type=str, nargs="?", help="Path for multiple files to be processed")
    parser.add_argument("--output_base", default=None, type=str, nargs="?", help="Base name for output files")
    parser.add_argument("--output_dir", default=None, type=str, nargs="?", help="Path for output from single or multiple files")
    parser.add_argument("--mode", default=None, type=str, nargs="?", help="Supports bound_single, bound_batch, extract_single, extract_batch")
    parser.add_argument("--options", default=None, type=str, nargs="?", help="figures, tables, captions, paragraphs, equations, algorithms, etc")
    parser.add_argument("--colors", default=None, type=str, nargs="?", help="For bounding boxes: must have one color per option")
    return parser.parse_args()

if __name__ == '__main__':
    args = define_parser()
    document_processor = PaperMageProcessor()
    options = args.options.split(',')
    outputs = document_processor.process_document(args.mode, args.input_file, args.options.split(','), args.colors.split(','))
    outputs.save_output(args.output_dir, args.output_base, args.mode)
