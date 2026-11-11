# Deploy

The service runs in Docker on both platforms: get the code, build with
`docker compose`, open port 8000.

- [Raspberry Pi 5](#raspberry-pi-5)
- [Windows laptop](#windows-laptop)
- [Everyday commands](#everyday-commands)
- [Optional password](#optional-password)
- [Remove and clean up](#remove-and-clean-up)

## Raspberry Pi 5

1. **Install the OS.** In Raspberry Pi Imager, flash **Raspberry Pi OS
   (64-bit)**. In its settings, set a hostname (for example `ocr`) and a user,
   and turn on SSH. Boot the Pi on your network.

2. **Connect from your laptop:**

   ```bash
   ssh <user>@ocr.local
   ```

3. **Update the system and install Git:**

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y git
   ```

4. **Install Docker** (this includes the `docker compose` plugin):

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   ```

5. **Get the code:**

   ```bash
   git clone https://github.com/Chevit/OCR.git
   cd OCR
   ```

   If the repository is private, GitHub asks for a username and a personal
   access token. Instead, you can add an SSH key on the Pi and clone
   `git@github.com:Chevit/OCR.git`.

6. **Build and start.** The first build takes several minutes because it
   downloads Tesseract and the "best" models.

   ```bash
   sudo docker compose up -d --build
   ```

7. **Check it:**

   ```bash
   curl http://localhost:8000/health
   ```

   A healthy service answers with HTTP 200. A 503 means Tesseract or a language
   is missing, and the `tesseract` block in the reply shows which.

8. **Open it from another device.** Run `hostname -I` on the Pi to get its
   address, then open `http://<pi-address>:8000` (or `http://ocr.local:8000`).

The service comes back on its own after a reboot: Docker starts at boot, and
the container has `restart: unless-stopped`.

## Windows laptop

1. **Install Docker Desktop** from docker.com with the **WSL 2** backend. It
   needs Windows 10 22H2 or Windows 11, with virtualization turned on in the
   BIOS. If it asks, run `wsl --install` in an admin PowerShell and reboot.
   Start Docker Desktop and wait until it shows "Engine running".

2. **Install Git.** Use the Git for Windows installer, or run:

   ```powershell
   winget install Git.Git
   ```

3. **Get the code** (PowerShell):

   ```powershell
   git clone https://github.com/Chevit/OCR.git
   cd OCR
   ```

4. **Build and start:**

   ```powershell
   docker compose up -d --build
   ```

5. **Check it.** Type `curl.exe`: in PowerShell, `curl` is an alias for a
   different command.

   ```powershell
   curl.exe http://localhost:8000/health
   ```

6. **Open** `http://localhost:8000` in a browser.

7. **Optional: let other devices on your network use it.** Get the laptop's
   IPv4 address with `ipconfig`, then open the port in an **admin** PowerShell:

   ```powershell
   New-NetFirewallRule -DisplayName "OCR 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```

   Your Wi-Fi must use the **Private** network profile. Other devices then open
   `http://<laptop-ip>:8000`.

To start the service after a reboot, turn on **Start Docker Desktop when you
sign in** in Docker Desktop (Settings → General). The container then comes back
on its own, but only after you sign in to Windows.

## Everyday commands

Run these in the `OCR` folder. On the Pi, put `sudo` in front of `docker`.

| Task | Command |
| --- | --- |
| Update to the latest code | `git pull`, then `docker compose up -d --build` |
| Watch logs | `docker compose logs -f` |
| Usage and statistics logs | `tail logs/usage.log logs/stats.jsonl` (see README, Logs) |
| Stop | `docker compose down` |
| Start again | `docker compose up -d` |

## Optional password

Before the service can be reached from outside your home network, open
`docker-compose.yml`. Uncomment the `environment:` and `API_TOKEN:` lines and
set your own secret, then run `docker compose up -d` again. The web page then
shows a field for the token, and API requests need the header
`Authorization: Bearer <token>`.

## Remove and clean up

The service stores no documents or results. Its only data is the usage and
statistics logs in the `logs` folder inside `OCR` (no text or file names).
Removing the container, the image and the folder removes everything.

### Remove the service

In the `OCR` folder (on the Pi, with `sudo`):

```bash
docker compose down --rmi local   # stop, remove the container and its image
docker builder prune -f           # free the build cache (Tesseract, models, pip)
```

Then delete the folder:

- Pi: `cd ~ && rm -rf OCR`
- Windows (PowerShell): `cd ..; Remove-Item -Recurse -Force OCR`

On Windows, also remove the firewall rule, if you added one (admin
PowerShell):

```powershell
Remove-NetFirewallRule -DisplayName "OCR 8000"
```

### Optional: remove Docker itself

Skip this if anything else on the machine uses Docker.

**Pi:**

```bash
sudo apt purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo rm -rf /var/lib/docker /var/lib/containerd
```

**Windows:** uninstall **Docker Desktop** in Settings → Apps → Installed apps.
To remove WSL as well, uninstall **Windows Subsystem for Linux** there too.
Don't remove WSL if you use it for anything else.
