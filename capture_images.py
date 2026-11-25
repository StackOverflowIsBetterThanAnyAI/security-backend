import os
import subprocess
import glob
from datetime import datetime
from time import sleep
from folder_data import (
    IMAGE_FILENAME_PATTERN,
    IMAGE_FOLDER_LOCATION,
    IMAGE_FOLDER_LOCATION_LIVE,
    MAX_ARCHIVE_IMAGES,
)

RPICAM_CMD = [
    "rpicam-jpeg",
    "-t",
    "1",
    "--width",
    "854",
    "--height",
    "480",
    "--nopreview",
    "--thumb",
    "320:180:70",
]

CAPTURE_TIMEOUT_SECONDS = 30
MAX_CAPTURE_FAILURES = 5


def prune_archive():
    image_files = sorted(
        f for f in os.listdir(IMAGE_FOLDER_LOCATION) if IMAGE_FILENAME_PATTERN.match(f)
    )

    while len(image_files) > MAX_ARCHIVE_IMAGES:
        try:
            os.remove(os.path.join(IMAGE_FOLDER_LOCATION, image_files[0]))
        except OSError:
            print("Error removing old archive image.")
            break
        image_files.pop(0)

    return image_files


def capture(filename):
    try:
        subprocess.run(
            RPICAM_CMD + ["--output", filename],
            check=True,
            timeout=CAPTURE_TIMEOUT_SECONDS,
        )
        return True
    except subprocess.TimeoutExpired:
        print(f"Camera did not respond within {CAPTURE_TIMEOUT_SECONDS} seconds.")
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Capturing image failed: {e}")
    # do not serve a half-written image
    try:
        os.remove(filename)
    except OSError:
        pass
    return False


def capture_images():
    archive_counter = 0
    failures = 0
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

            if not capture(live_filename):
                failures += 1
                if failures >= MAX_CAPTURE_FAILURES:
                    raise SystemExit(
                        f"Camera failed {failures} times in a row, exiting."
                    )
                sleep(10)
                continue
            failures = 0

            all_live_files = sorted(
                glob.glob(os.path.join(IMAGE_FOLDER_LOCATION_LIVE, "*.jpg"))
            )

            for old_live_file in all_live_files[:-1]:
                try:
                    os.remove(old_live_file)
                except OSError:
                    print("Error removing old live image.")

            if archive_counter % ARCHIVE_INTERVAL == 0:

                archive_filename = os.path.join(IMAGE_FOLDER_LOCATION, base_filename)
                if capture(archive_filename):
                    image_files = prune_archive()

                    print(
                        f"Archive image captured: {archive_filename}. Slots free: {MAX_ARCHIVE_IMAGES - len(image_files)}."
                    )

            archive_counter = (archive_counter + 1) % ARCHIVE_INTERVAL

            print(f"Live image saved: {live_filename}.")
            sleep(10)

    except KeyboardInterrupt:
        print("Capturing images has been stopped.")


if __name__ == "__main__":
    capture_images()
