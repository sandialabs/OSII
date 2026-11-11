import os

from dotenv import dotenv_values


def get_nemoparse_config(config_file: str | None = ".env"):
    """Return Nemotron configuration, preferring explicit environment values.

    A partial .env file should not hide values supplied by a deployment
    environment.  Keeping the two expected keys present also gives callers a
    consistent validation surface.
    """
    config_values = dotenv_values(config_file) if config_file and os.path.exists(config_file) else {}
    return {
        "NEMOPARSE_ENDPOINT": os.getenv("NEMOPARSE_ENDPOINT") or config_values.get("NEMOPARSE_ENDPOINT"),
        "NEMOPARSE_MODEL": os.getenv("NEMOPARSE_MODEL") or config_values.get("NEMOPARSE_MODEL"),
        "NEMOPARSE_API_KEY": os.getenv("NEMOPARSE_API_KEY") or config_values.get("NEMOPARSE_API_KEY"),
    }
