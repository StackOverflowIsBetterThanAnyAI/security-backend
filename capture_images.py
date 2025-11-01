import os
import re
import subprocess
import glob
from datetime import datetime
from time import sleep
from folder_data import IMAGE_FOLDER_LOCATION, IMAGE_FOLDER_LOCATION_LIVE

REGEX = re.compile(r"^security_image_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$")

RPICAM_CMD = [
    "rpicam-jpeg",
    "-t", "1",
    "--width", "854",
    "--height", "480",
    "--nopreview"
]


def capture_images():
    archive_counter = 0
    ARCHIVE_INTERVAL = 30

    if not os.path.exists(IMAGE_FOLDER_LOCATION):
        os.makedirs(IMAGE_FOLDER_LOCATION)
    if not os.path.exists(IMAGE_FOLDER_LOCATION_LIVE):
        os.makedirs(IMAGE_FOLDER_LOCATION_LIVE)

    try:
        while True:
            current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_filename = f"security_image_{current_time}.jpg"
            
            live_filename = os.path.join(IMAGE_FOLDER_LOCATION_LIVE, base_filename)
            command_to_run_live = RPICAM_CMD + ["--output", live_filename]
            
            subprocess.run(command_to_run_live, check=True)
            
            all_live_files = sorted(glob.glob(os.path.join(IMAGE_FOLDER_LOCATION_LIVE, "*.jpg")))
            
            for old_live_file in all_live_files[:-1]:
                try:
                    os.remove(old_live_file)
                except OSError:
                    print("Error removing old live image.")


            if archive_counter % ARCHIVE_INTERVAL == 0:
                
                archive_filename = os.path.join(IMAGE_FOLDER_LOCATION, base_filename)
                command_to_run_archive = RPICAM_CMD + ["--output", archive_filename]
                
                subprocess.run(command_to_run_archive, check=True)

                image_files = sorted(
                    [f for f in os.listdir(IMAGE_FOLDER_LOCATION) if REGEX.match(f)]
                )
                
                if len(image_files) >= 2016:
                    os.remove(os.path.join(IMAGE_FOLDER_LOCATION, image_files[0]))

                print(f"Archive image captured: {archive_filename}. Slots free: {2016 - len(image_files)}.")
            
            archive_counter = (archive_counter + 1) % ARCHIVE_INTERVAL
            
            print(f"Live image saved: {live_filename}.")
            sleep(10)

    except KeyboardInterrupt:
        print("Capturing images has been stopped.")
        
if __name__ == "__main__":
    capture_images()
