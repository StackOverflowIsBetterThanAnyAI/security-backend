import os
import re
import subprocess

from datetime import datetime
from time import sleep
from folder_data import IMAGE_FOLDER_LOCATION 

REGEX = re.compile(r"^security_image_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$")

RPICAM_CMD = [
    "rpicam-jpeg",
    "-t", "1",
    "--width", "854",
    "--height", "480",
    "--nopreview"
]


def capture_images():
    if not os.path.exists(IMAGE_FOLDER_LOCATION):
        os.makedirs(IMAGE_FOLDER_LOCATION)

    try:
        while True:
            image_files = sorted(
                [f for f in os.listdir(IMAGE_FOLDER_LOCATION) if REGEX.match(f)]
            )

            if len(image_files) >= 2016:
                os.remove(os.path.join(IMAGE_FOLDER_LOCATION, image_files[0]))

            current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{IMAGE_FOLDER_LOCATION}/security_image_{current_time}.jpg"

            command_to_run = RPICAM_CMD + ["--output", filename]
            
            subprocess.run(command_to_run, check=True) 
            
            print(f"Image captured: {filename}.")
            print(f"{2016-len(image_files)} free image slots available.")
            sleep(300)

    except KeyboardInterrupt:
        print("Capturing images has been stopped.")
    


if __name__ == "__main__":
    capture_images()
