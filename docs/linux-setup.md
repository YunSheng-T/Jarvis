# Ubuntu setup notes (Huawei MateBook 2022)

Target: Ubuntu 22.04 or 24.04 (24.04 preferred — newer kernel, PipeWire by default).

## First-time bootstrap

```bash
git clone https://github.com/YunSheng-T/Jarvis.git ~/Jarvis
cd ~/Jarvis
./scripts/install-linux.sh
cp .env.example .env && $EDITOR .env    # add OPENAI_API_KEY
uv run python -m jarvis
```

## NVIDIA driver

```bash
sudo ubuntu-drivers autoinstall
sudo reboot
nvidia-smi        # verify
```

For CUDA-accelerated whisper later:
```bash
# uv sync will pull ctranslate2; CUDA runtime comes via nvidia-cudnn-cu12 wheel.
uv sync --extra audio
```

## MateBook quirks (optional cleanups)

- **Function keys / brightness**: if brightness keys don't work, add `acpi_backlight=vendor`
  to GRUB kernel cmdline.
- **Fans / temps**: install `huawei-wmi` DKMS module from AUR-mirrored source or
  https://github.com/aymanbagabas/Huawei-WMI for saner fan curves.
- **Fingerprint**: unsupported on Linux for most MateBook SKUs; skip.
- **Wi-Fi**: usually works out of the box on 24.04. If not, check `iwlwifi` firmware.

## Audio (PipeWire)

Ubuntu 24.04 ships PipeWire. Verify:
```bash
pactl info | grep "Server Name"     # should say "PulseAudio (on PipeWire ...)"
```

## Autostart as a service

```bash
mkdir -p ~/.config/systemd/user
cp systemd/jarvis.service ~/.config/systemd/user/
systemctl --user daemon-reload
loginctl enable-linger "$USER"       # keep it running without login session
systemctl --user enable --now jarvis.service
journalctl --user -u jarvis.service -f
```
