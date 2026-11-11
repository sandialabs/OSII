from abc import ABC, abstractmethod

class ModelOutput(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get_output_path(self, output_directory, filename_base):
        pass
    
    @abstractmethod
    def save_output(self, output_directory, filename_base):
        pass
