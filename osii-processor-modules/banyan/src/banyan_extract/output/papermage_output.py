import pathlib
import json

from .output import ModelOutput

class PaperMageOutput(ModelOutput):
    def __init__(self, output_data):
        super().__init__()
        self.output_data = output_data
        print(self.output_data)

    def get_output_path(self, output_directory, filename_base):
        return os.path.join(output_directory, f"{filename_base}.json")
        
    def save_output(self, output_directory, filename_base, mode, options=None):
        save_path = pathlib.Path(output_directory)

        if mode == 'bound_single':
            for idx, plotted in enumerate(self.output_data):
                plotted.save(save_path / f'{filename_base}_page_{idx+1}.png', is_overwrite=True, format='PNG')

        elif mode == 'bound_batch':
            for file, single_output in self.output_data.items():
                file_path = pathlib.Path(save_path / file)
                file_path.mkdir(parents=True, exist_ok=True)
                for idx, plotted in enumerate(single_output):
                    plotted.save(file_path / f'{filename_base}_page_{idx+1}.png', is_overwrite=True, format='PNG')

        elif mode == 'extract_single':
            with open(save_path / f"{filename_base}.json", "w+") as f_out:
                print(f"saving to {save_path}")
                json.dump(self.output_data.to_json(), f_out, indent=2)

            if options:
                for option in options:
                    with open(save_path / f"{filename_base}_{option}.txt", "w+") as f:
                        for elem in self.output_data.get_layer(option):
                            f.write(''.join((str(elem),'\n')))
                        f.close()

        elif mode == 'extract_batch':
            for filename, extracted in self.output_data.items():
                file_path = pathlib.Path(save_path / filename)
                file_path.mkdir(parents=True, exist_ok=True)

                with open(file_path / f"{filename_base}.json", "w+") as f_out:
                    json.dump(extracted.to_json(), f_out, indent=2)

                if options:
                    for option in options:
                        with open(file_path / f"{option}.txt", "w+") as f:
                            for elem in extracted.get_layer(option):
                                f.write(''.join((str(elem),'\n')))
                            f.close()

