import os
import re

HTML_FOLDER_LOCATION = os.path.dirname(os.path.abspath(__file__))
IMAGE_FOLDER_LOCATION = os.path.join(HTML_FOLDER_LOCATION, "security_images")
IMAGE_FOLDER_LOCATION_LIVE = os.path.join(HTML_FOLDER_LOCATION, "security_image_live")

IMAGE_FILENAME_PATTERN = re.compile(
    r"^security_image_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$"
)

MAX_ARCHIVE_IMAGES = 2016
