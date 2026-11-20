# Security Backend

Flask backend (served by waitress on port 5000) for the DIY security camera, running on a Raspberry Pi Zero W with a camera module. `main.py` starts both the camera loop (`capture_images.py`) and the API (`app.py`).

ssh connection:

```
ssh admin@raspberrypi
```

## Installation Guide

Requires Raspberry Pi OS with `git`, `python3` and `rpicam-apps` (for `rpicam-jpeg`).

1. Clone the repository into the home folder of the user that runs the service (here `admin`):

    ```
    cd ~
    git clone https://github.com/StackOverflowIsBetterThanAnyAI/security-backend.git security
    cd security
    ```

    All paths are derived from this folder, so no code needs to be changed for a different user name.

2. Create the virtual environment and install the pinned dependencies:

    ```
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    ```

3. Create a `.env` with the admin credentials:

    ```
    ADMIN_USERNAME=...
    ADMIN_PASSWORD=...
    ```

4. Install and start the systemd service, see [etc/systemd/system/security.service](etc/systemd/system/security.service). Adjust `User` and the paths if the user is not `admin`.

    ```
    sudo cp etc/systemd/system/security.service /etc/systemd/system/security.service
    # reload daemon after configuration files have been changed
    sudo systemctl daemon-reload
    # automatically start service on boot
    sudo systemctl enable --now security.service
    # show service status
    sudo systemctl status security.service
    # show real time logs
    sudo journalctl -u security.service -f
    ```

5. Allow the service to power off the Pi from the admin tab, see [etc/sudoers.d/security-shutdown](etc/sudoers.d/security-shutdown). Adjust the user if it is not `admin`.

    ```
    sudo install -m 0440 etc/sudoers.d/security-shutdown /etc/sudoers.d/security-shutdown
    # check the syntax, a broken sudoers file locks out sudo
    sudo visudo -c
    ```

`database.db` and the image folders `security_images/` and `security_image_live/` are created automatically on first start. They, `.env`, `venv/` and `certificate/` are git-ignored and stay local on the Pi, so back them up separately.

## Update Guide

```
cd ~/security
git pull
venv/bin/pip install -r requirements.txt
sudo systemctl restart security.service
```

## Usage Guide

1. User Authentication: Registration and login. All new users receive a default user role.

2. Role Management: The admin has endpoints to upgrade or manage other users' roles.

3. Image Access Control: Ensures that the sensitive image endpoint is only accessible to users with the member role or better.

4. Raspberry Pi Integration: Captures a live image every 10 seconds and an archive image every 5 minutes, keeping one week (2016 images) of archive images.

## Frontend Repository

[Frontend Repository](https://github.com/StackOverflowIsBetterThanAnyAI/security-app)
