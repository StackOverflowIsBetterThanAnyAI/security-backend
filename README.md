# Security Backend

Flask backend (served by waitress on port 5000) for the DIY security camera, running on a Raspberry Pi Zero W with a camera module. `main.py` starts both the camera loop (`capture_images.py`) and the API (`app.py`).

ssh connection:

```
ssh admin@raspberrypi
# or via Tailscale from any device in the tailnet
ssh admin@security-pi
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

4. Install and start the systemd service, see [etc/systemd/system/security.service](etc/systemd/system/security.service). Adjust `User` and the paths if the user is not `admin`. The service keeps the live image, which is rewritten every few seconds, in the RAM folder `/run/security` to spare the SD card.

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

6. Install [Tailscale](https://tailscale.com) so the app reaches the Pi at home and on the go without opening any port on the router:

    ```
    curl -fsSL https://tailscale.com/install.sh | sh
    # opens a login link, only needed once, the login is stored and tailscaled starts on boot
    sudo tailscale up --hostname=security-pi
    # the Tailscale address to put into the app's .env
    tailscale ip -4
    ```

    Then disable the key expiry for `security-pi` in the Tailscale admin console (Machines), otherwise the Pi drops out of the tailnet after 180 days. The backend listens on all interfaces, so it is reachable via Tailscale without further configuration.

7. Optional: keep the system log across reboots to be able to debug hangs, limited to 50 MB:

    ```
    sudo mkdir -p /var/log/journal
    echo "SystemMaxUse=50M" | sudo tee -a /etc/systemd/journald.conf
    sudo systemctl restart systemd-journald
    # log of the previous boot
    sudo journalctl -b -1
    ```

`database.db` and the image folder `security_images/` are created automatically on first start. They, `.env`, `venv/` and `certificate/` are git-ignored and stay local on the Pi, so back them up separately.

## Update Guide

```
cd ~/security
git pull
venv/bin/pip install -r requirements.txt
# only if a file in etc/ changed, copy it again as in the installation guide, then
sudo systemctl daemon-reload
sudo systemctl restart security.service
```

## Usage Guide

1. User Authentication: Registration and login. All new users receive a default user role.

2. Role Management: The admin has endpoints to upgrade or manage other users' roles.

3. Image Access Control: Ensures that the sensitive image endpoint is only accessible to users with the member role or better.

4. Raspberry Pi Integration: Captures a live image every 10 seconds and an archive image every 5 minutes, keeping one week (2016 images) of archive images.

## Frontend Repository

[Frontend Repository](https://github.com/StackOverflowIsBetterThanAnyAI/security-app)
