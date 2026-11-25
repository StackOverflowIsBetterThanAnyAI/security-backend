import os
import re

HTML_FOLDER_LOCATION = os.path.dirname(os.path.abspath(__file__))
IMAGE_FOLDER_LOCATION = os.path.join(HTML_FOLDER_LOCATION, "security_images")
# systemd provides a tmpfs folder so the live image that is rewritten every few
# seconds stays in RAM and does not wear out the SD card. Without systemd
# (local tests, manual start of main.py) it falls back to the project folder.
LIVE_BASE_LOCATION = os.environ.get("RUNTIME_DIRECTORY", HTML_FOLDER_LOCATION)
IMAGE_FOLDER_LOCATION_LIVE = os.path.join(LIVE_BASE_LOCATION, "security_image_live")

IMAGE_FILENAME_PATTERN = re.compile(
    r"^security_image_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$"
)

MAX_ARCHIVE_IMAGES = 2016
