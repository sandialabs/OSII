import argparse
import os

from dotenv import load_dotenv, dotenv_values

from banyan_extract import NemoparseProcessor 

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", default=None, type=str, help="Path for a single file to be processed")
    parser.add_argument("output_dir", default=None, type=str, help="Path for output from single or multiple files")
    parser.add_argument("--is_input_dir", action="store_true",  help="Flags to set input file to directory")
    parser.add_argument("--output_base", default="banyan-extract-output", type=str,  help="Base name for output files")
    parser.add_argument("--endpoint", default="", type=str, help="Endpoint url for nemoretreiver-parse model")
    parser.add_argument("--model_name", default="", type=str, help="Endpoint url for nemoretreiver-parse model")
    parser.add_argument("--checkpointing", action="store_true", help="Flag where if true, then batch documents will be saved as they get processed")
    parser.add_argument("--draw_bboxes", action="store_true", default=False, help="Flag where if true, then ouptut will include images that show most bboxes found")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()

    output_directory = args.output_dir
    output_base = args.output_base
    endpoint = args.endpoint
    model_name = args.model_name

    if len(endpoint) == 0:
        config_values = dotenv_values(".env")
        endpoint = config_values["NEMOPARSE_ENDPOINT"]
        model_name = config_values["NEMOPARSE_MODEL"]
        print(f"Using endpoint: {endpoint}")
        print(f"Using model: {model_name}")

    if endpoint != "":
        document_processor = NemoparseProcessor(endpoint_url=endpoint, model_name=model_name, sort_by_position=True)

        if args.is_input_dir:
            input_directory = args.input_file

            file_paths = []
            basenames = []
            for root, _, files in os.walk(input_directory):
                for filename in files:
                    file_paths.append(os.path.join(root, filename))
                    basenames.append(os.path.basename(filename))

            print(args.draw_bboxes)
            outputs = document_processor.process_batch_documents(file_paths, use_checkpointing=args.checkpointing, draw_bboxes=args.draw_bboxes, output_dir=output_directory)
            if not args.checkpointing:
                for file_output, basename in zip(outputs, basenames):
                    file_output.save_output(output_directory, basename)
        else:
            filename = args.input_file
            outputs = document_processor.process_document(filename)

            outputs.save_output(output_directory, output_base)
    else:
        raise Exception("Missing nemotron-parse endpoint url!")
