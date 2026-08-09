<div align="center">

<img src="assets/logo.png" width="110" alt="WattHog">

# WattHog

**How many watts your PC is eating right now, and what that costs over a day**

[![Release](https://img.shields.io/github/v/release/scarrymany/watthog?style=for-the-badge&color=ffd23f&labelColor=161b22)](https://github.com/scarrymany/watthog/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/scarrymany/watthog/ci.yml?branch=main&style=for-the-badge&label=CI&labelColor=161b22)](https://github.com/scarrymany/watthog/actions/workflows/ci.yml)
[![Downloads](https://img.shields.io/github/downloads/scarrymany/watthog/total?style=for-the-badge&color=43d675&labelColor=161b22)](https://github.com/scarrymany/watthog/releases)
[![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge&labelColor=161b22)](LICENSE)
[![Platform](https://img.shields.io/badge/Windows%20%7C%20Linux-161b22?style=for-the-badge&logo=windows&logoColor=ffd23f)](#installation)
[![Telegram](https://img.shields.io/badge/@yeet17-161b22?style=for-the-badge&logo=telegram&logoColor=ffd23f)](https://t.me/yeet17)

[Installation](#installation) · [Usage](#usage) · [How it works](#how-it-works) · [Accuracy](#accuracy) · [Русский](README.md)

<img src="docs/dashboard.svg" width="900" alt="WattHog live dashboard">

</div>

> **Note.** The application interface is in Russian. This page describes what the tool
> does and how to run it; the commands and config keys below are the real ones.

---

## What it is

A wall plug power meter costs money and most people do not own one. WattHog answers the
same question in software: it runs for a minute, samples hardware telemetry twice per
second, and tells you how much your machine draws and what that adds up to.

It does not guess from a single TDP number. Wherever the hardware exposes a real power
sensor, that reading is used. Everything else is filled in by a physical model, and the
report states plainly which part was measured and which part was computed.

```
                  Average over one minute: 308 W

  1 hour      0.308 kWh          12 hours    3.70 kWh
  10 hours    3.08  kWh          24 hours    7.39 kWh
```

## Features

| | |
|---|---|
| ⚡ **Real sensors** | NVML for NVIDIA GPUs, RAPL for the CPU on Linux, hwmon for AMD and Intel GPUs, battery discharge rate on laptops |
| 📊 **Live dashboard** | Current draw in large digits, per-component breakdown, chart across the whole run |
| 🧮 **Projections** | 1 hour, 10 hours, 12 hours, a day, a week, a month - in kWh and in money at your tariff |
| 🔌 **Wall power, not DC** | PSU losses are added from an 80 PLUS efficiency curve, not a flat coefficient |
| 🖥 **Windows and Linux** | Desktops, laptops, mini PCs. No administrator rights required |
| 📦 **Single file** | `WattHog.exe` with no install and no Python. Or `pip install` if you prefer |
| 📁 **JSON reports** | Every run is stored in full: statistics, breakdown, hardware, data sources |
| 🎛 **Calibration** | Know the real numbers for your box? Put them in the settings and the model follows |

## Installation

### Windows, one command

```powershell
irm https://raw.githubusercontent.com/scarrymany/watthog/main/install.ps1 | iex
```

Downloads the latest build into `%LOCALAPPDATA%\Programs\WattHog` and adds it to `PATH`.
No administrator rights needed.

### Linux, one command

```bash
curl -fsSL https://raw.githubusercontent.com/scarrymany/watthog/main/install.sh | bash
```

Installs through `pipx`, or into an isolated environment under `~/.local/share/watthog`
with a symlink in `~/.local/bin`.

### Standalone binaries

```powershell
curl.exe -L -o WattHog.exe https://github.com/scarrymany/watthog/releases/latest/download/WattHog.exe
```

```bash
curl -fsSL -o watthog https://github.com/scarrymany/watthog/releases/latest/download/watthog-linux-x86_64
chmod +x watthog && ./watthog
```

### pip / pipx / source

```bash
pipx install git+https://github.com/scarrymany/watthog.git
pip install git+https://github.com/scarrymany/watthog.git

git clone https://github.com/scarrymany/watthog.git
cd watthog && pip install -e ".[dev]" && python -m watthog
```

> **macOS is not supported.** There is no RAPL and no equivalent of the PDH counters, so
> there is nothing honest to measure with. The program refuses to invent a number.

## Usage

```bash
watthog                              # interactive menu
watthog run                          # 60 second run with the live dashboard
watthog run -d 300                   # five minutes
watthog run --tariff 0.34            # include cost at your price per kWh
watthog run --plain --no-save        # text only, write nothing to disk
watthog run --json report.json       # export the report
watthog info                         # detected hardware and available sensors
watthog config                       # settings
```

| Flag | Meaning |
|---|---|
| `-d`, `--duration SEC` | Run length, default 60 |
| `-i`, `--interval SEC` | Sampling interval, default 0.5 |
| `--tariff PRICE` | Price per kWh used for cost projections |
| `--currency SIGN` | Currency symbol in the report |
| `--json FILE` | Write the report to this path |
| `--no-save` | Do not write to the reports directory |
| `--plain` | No live dashboard, plain text output |
| `--save-config` | Persist the given options into the settings file |
| `-V`, `--version` | Version |

<div align="center">
<img src="docs/report.svg" width="900" alt="WattHog final report">
</div>

## How it works

A telemetry snapshot is taken twice a second, converted into per-component power, and
integrated into energy with the trapezoidal rule at the end of the run.

| Component | Where the watts come from | Quality |
|---|---|---|
| NVIDIA GPU | NVML directly via `nvml.dll` / `libnvidia-ml.so` | **measured** |
| AMD, Intel GPU | Linux `hwmon`: `power1_average` or `energy1_input` | **measured** |
| CPU on Linux | RAPL energy counter under `/sys/class/powercap` | **measured** |
| Whole laptop | Instantaneous battery discharge power | **measured** |
| CPU on Windows | Model over load and the PDH clock multiplier | modelled |
| GPU without a sensor | Model over GPU engine utilisation | modelled |
| RAM, storage, board | Model over capacity, I/O throughput and platform type | modelled |
| PSU losses | 80 PLUS efficiency curve against load fraction | modelled |

When a direct whole-system measurement is available (battery discharge or the RAPL
`psys` domain), component estimates are scaled proportionally to match it: the total
becomes exact while the breakdown stays informative.

### CPU model

```
P = P_idle + (P_peak - P_idle) · load^0.55 · (clock / 1.05)
```

The exponent below one is deliberate. The first busy cores cost more than the last ones:
with a single active core the CPU holds its maximum boost and high voltage, while at full
load clocks and voltages drop. The clock factor comes from the `% Processor Performance`
counter, which reports the real clock relative to nominal, so a light single-threaded
load is not confused with a heavy all-core one.

Package power is divided by the motherboard VRM efficiency: the CPU sensor does not see
those losses, but the wall socket does.

Integrated graphics is deliberately reported as zero watts. It is powered by the same die
as the CPU, so counting it separately would count the same watts twice.

## Accuracy

The report always states what the result rests on.

| Level | When | Typical deviation from a wall meter |
|---|---|---|
| **measured** | Laptop on battery, or the RAPL `psys` domain | A few percent |
| **high** | Both CPU and GPU sensors available | 5-10% |
| **medium** | GPU sensor available, CPU modelled | 10-20% |
| **modelled** | No sensors, everything computed | Right order of magnitude, 20-35% |

What actually improves it:

1. Set your PSU wattage and efficiency class in the settings.
2. Set CPU and GPU peak power if you know the real figures for your parts.
3. Add peripherals - monitor, speakers, anything on the same socket.
4. On Linux run with `sudo` to unlock RAPL and turn CPU power into a measurement.

Got a wall meter and see a mismatch?
[Send the numbers](https://github.com/scarrymany/watthog/issues/new?template=accuracy_report.yml) -
those reports feed straight back into the model.

## Settings

- Windows: `%APPDATA%\WattHog\config.json`
- Linux: `~/.config/watthog/config.json`

| Key | Default | Purpose |
|---|---|---|
| `duration_seconds` | 60 | Run length |
| `sample_interval` | 0.5 | Sampling interval |
| `tariff_per_kwh` | 0 | Price per kWh |
| `currency` | ₽ | Currency symbol |
| `psu_peak_efficiency` | 0.90 | Peak PSU efficiency: Bronze 0.85, Gold 0.90, Platinum 0.92 |
| `psu_rated_watts` | 650 | PSU rated power |
| `extra_devices_watts` | 0 | Monitor, speakers, other peripherals |
| `cpu_peak_watts` | auto | CPU package power at full load |
| `gpu_peak_watts` | auto | GPU board power at full load |
| `platform_watts` | auto | Motherboard, fans, chipset |
| `save_reports` | true | Store reports automatically |

## Building

```bash
pip install -e ".[dev]"
python -m pytest
python tools/make_icon.py
python -m PyInstaller --noconfirm --clean packaging/watthog.spec
```

Release binaries for Windows and Linux are built by
[GitHub Actions](.github/workflows/release.yml) on a tag.

## Privacy

No network requests at all: no telemetry, no update checks. Everything is computed
locally and reports stay on your disk.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most valuable contributions are wall meter
comparisons, entries for the hardware power tables, and testing on unusual machines.

## License

[MIT](LICENSE) © 2026 [@yeet17](https://t.me/yeet17)
