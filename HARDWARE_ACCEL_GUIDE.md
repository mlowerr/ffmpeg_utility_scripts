# Hardware Acceleration Guide

This guide explains how to check if your system supports hardware-accelerated video encoding for use with the transcoding scripts.

## Quick Check

### Linux (Bash)
```bash
# Check what hardware encoders your ffmpeg supports
ffmpeg -encoders 2>/dev/null | grep -E "(qsv|nvenc|amf)"
```

### Windows (PowerShell)
```powershell
# Check what hardware encoders your ffmpeg supports
ffmpeg -encoders 2>$null | Select-String "qsv|nvenc|amf"
```

## Expected Output

If your system supports hardware acceleration, you should see lines like:

```
V..... h264_qsv             H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (Intel Quick Sync Video acceleration)
V..... hevc_qsv             HEVC (Intel Quick Sync Video acceleration)
V..... h264_nvenc           NVIDIA NVENC H.264 encoder
V..... hevc_nvenc           NVIDIA NVENC hevc encoder
V..... h264_amf             AMD AMF H.264 Encoder
V..... hevc_amf             AMD AMF HEVC encoder
```

If you don't see these encoders, your ffmpeg wasn't compiled with hardware acceleration support.

---

## Intel Quick Sync Video (QSV) - `-q` flag

### Linux

**Check for Intel GPU:**
```bash
lspci | grep -i vga | grep -i intel
```

**Check for QSV encoders:**
```bash
ffmpeg -encoders 2>/dev/null | grep qsv
```

### Windows

**Check for Intel GPU:**
```powershell
Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*Intel*" }
```

**Check for QSV encoders:**
```powershell
ffmpeg -encoders 2>$null | Select-String "qsv"
```

### Requirements

- Intel CPU with integrated graphics (4th generation Intel Core or newer)
- Intel graphics drivers installed
- **Linux:** `intel-media-driver` or `libva-intel-driver` packages
- ffmpeg compiled with `--enable-libmfx` or `--enable-libvpl`

### Usage

```bash
# Linux
./h264-transcode.sh -q
./h264-transcode.sh -r -q    # recursive
./hevc-transcode.sh -q

# Windows
.\h264-transcode.ps1 -UseQuickSync
.\h264-transcode.ps1 -Recurse -UseQuickSync
.\hevc-transcode.ps1 -UseQuickSync
```

---

## NVIDIA NVENC - `-n` flag

### Linux

**Check for NVIDIA GPU:**
```bash
lspci | grep -i vga | grep -i nvidia
```

**Check for NVENC encoders:**
```bash
ffmpeg -encoders 2>/dev/null | grep nvenc
```

### Windows

**Check for NVIDIA GPU:**
```powershell
Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
```

**Check for NVENC encoders:**
```powershell
ffmpeg -encoders 2>$null | Select-String "nvenc"
```

### Requirements

- NVIDIA GTX 600 series or newer (Maxwell architecture+)
- GTX 900 series or newer for HEVC/H.265 encoding
- Recent NVIDIA drivers (version 378.13 or newer for HEVC support)
- **Note:** Consumer cards (GTX/RTX) have a concurrent encode session limit (typically 2-3 sessions)
- ffmpeg compiled with `--enable-nvenc`

### Usage

```bash
# Linux
./h264-transcode.sh -n
./h264-transcode.sh -r -n    # recursive
./hevc-transcode.sh -n

# Windows
.\h264-transcode.ps1 -UseNVENC
.\h264-transcode.ps1 -Recurse -UseNVENC
.\hevc-transcode.ps1 -UseNVENC
```

---

## AMD AMF - `-a` flag

### Linux

**Check for AMD GPU:**
```bash
lspci | grep -i vga | grep -i amd
```

**Check for AMF encoders:**
```bash
ffmpeg -encoders 2>/dev/null | grep amf
```

### Windows

**Check for AMD GPU:**
```powershell
Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*AMD*" -or $_.Name -like "*Radeon*" }
```

**Check for AMF encoders:**
```powershell
ffmpeg -encoders 2>$null | Select-String "amf"
```

### Requirements

- AMD RX 400 series or newer (Polaris/Vega architecture+)
- AMD Ryzen APUs with Vega graphics
- Windows: AMD drivers with AMF runtime support
- **Linux:** AMF support is limited and requires specific driver versions; many distros need manual driver installation
- ffmpeg compiled with `--enable-amf`

### Usage

```bash
# Linux
./h264-transcode.sh -a
./h264-transcode.sh -r -a    # recursive
./hevc-transcode.sh -a

# Windows
.\h264-transcode.ps1 -UseAMF
.\h264-transcode.ps1 -Recurse -UseAMF
.\hevc-transcode.ps1 -UseAMF
```

---

## Troubleshooting

### ffmpeg doesn't show hardware encoders

1. **Check ffmpeg version:**
   ```bash
   ffmpeg -version | head -1
   ```
   Hardware encoding typically requires ffmpeg 4.0 or newer.

2. **Install a hardware-enabled ffmpeg build:**
   - **Windows:** Use builds from https://www.gyan.dev/ffmpeg/builds/ (includes NVENC, QSV)
   - **Linux (Ubuntu/Debian):** `sudo apt install ffmpeg` (may not include all codecs)
   - **Linux (Arch):** `sudo pacman -S ffmpeg` (usually includes most codecs)
   - For full hardware support, you may need to compile ffmpeg or use a pre-built binary with `--enable-nonfree`

3. **Check GPU drivers:**
   - Update to the latest drivers from Intel/NVIDIA/AMD
   - For Linux, proprietary drivers often work better than open-source ones for hardware encoding

### Encoding fails with "No device found" or "Invalid argument"

1. **Check GPU availability:**
   - The GPU might be in use by another process
   - On laptops with hybrid graphics, make sure the discrete GPU is active

2. **Check codec support:**
   - Not all GPUs support all codecs (e.g., older Intel iGPUs don't support HEVC encoding)

3. **Try software encoding:**
   - If hardware encoding fails, use the scripts without hardware flags for software (CPU) encoding

---

## Performance Comparison

Approximate encoding speeds (relative to software/CPU encoding):

| Method | Speed vs Software | Quality at same bitrate | Power Usage |
|--------|-------------------|------------------------|-------------|
| Software (libx264/libx265) | 1x (baseline) | Best | High |
| Intel QSV | 2-5x | Good | Low |
| NVIDIA NVENC | 3-10x | Good | Medium |
| AMD AMF | 2-5x | Good | Medium |

**Recommendation:** For archival quality, software encoding is best. For fast processing or batch conversion where file size isn't critical, hardware encoding is significantly faster.
