import os
from django.conf import settings
import environ



env = environ.Env()
environ.Env.read_env()


def get_audio_url(file_name: str) -> str:
    """
    Returns full audio URL based on environment (local or production)
    """

    env = os.getenv("CURRENT_ENV", "local")
    print("env", env)

    if env == "local":
        base_url = "http://127.0.0.1:8000"
    else:
        base_url = "https://zencoachapi.vinnisoft.org"
    return f"{base_url}{settings.MEDIA_URL}{file_name}"