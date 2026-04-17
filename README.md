# FFmpeg Video Transcoding Scripts

A collection of cross-platform video transcoding scripts using FFmpeg. Supports both H.264 and HEVC/H.265 encoding with optional hardware acceleration.

## Features

- **Cross-platform**: Bash scripts for Linux/macOS, PowerShell scripts for Windows
- **Codec support**: H.264 (AVC) and HEVC/H.265 encoding
- **Hardware acceleration**: Intel Quick Sync, NVIDIA NVENC, AMD AMF
- **Batch processing**: Process single directory or recursively
- **Safe operation**: Verifies output integrity before deleting source files
- **Progress tracking**: Shows "Processing file X of Y" for batch operations
- **Smart 4K downscaling**: Automatically downscales 4K+ video to aspect-safe 1080p
- **Smart file handling**: Auto-renames files with spaces, skips already-processed files

## Repository Structure

```
.
├── unix/
│   ├── h264-transcode.sh      # H.264 encoding (Bash)
│   └── hevc-transcode.sh      # HEVC/H.265 encoding (Bash)
├── windows/
│   ├── h264-transcode.ps1     # H.264 encoding (PowerShell)
│   └── hevc-transcode.ps1     # HEVC/H.265 encoding (PowerShell)
├── HARDWARE_ACCEL_GUIDE.md    # Hardware acceleration setup guide
└── README.md                  # This file
```

## Requirements

- **FFmpeg** 4.0 or later (must be in PATH)
- **Bash** 4.0+ (for Unix scripts)
- **PowerShell** 5.1+ (for Windows scripts)
- **ffprobe** (for output verification)

### Installing FFmpeg

**Windows:**
```powershell
# Using winget
winget install Gyan.FFmpeg

# Or download from https://www.gyan.dev/ffmpeg/builds/
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Linux (Arch):**
```bash
sudo pacman -S ffmpeg
```

## Usage

### Basic Usage

Process all `.mp4` files in the current directory:

```bash
# Linux/macOS - H.264 encoding
./unix/h264-transcode.sh

# Linux/macOS - HEVC encoding
./unix/hevc-transcode.sh

# Windows - H.264 encoding (PowerShell)
.\windows\h264-transcode.ps1

# Windows - HEVC encoding (PowerShell)
.\windows\hevc-transcode.ps1
```

### Recursive Processing

Process all `.mp4` files from the current directory downward:

```bash
# Linux/macOS
./unix/h264-transcode.sh -r
./unix/hevc-transcode.sh -r

# Windows
.\windows\h264-transcode.ps1 -Recurse
.\windows\hevc-transcode.ps1 -Recurse
```

### Hardware Acceleration

Use hardware encoders for significantly faster processing (2-10x speedup):

| Flag | Encoder | Platform |
|------|---------|----------|
| `-q` / `-UseQuickSync` | Intel Quick Sync | Intel 4th gen+ |
| `-n` / `-UseNVENC` | NVIDIA NVENC | GTX 600+ / RTX |
| `-a` / `-UseAMF` | AMD AMF | RX 400+ / Vega |

**Examples:**

```bash
# Linux/macOS with Intel Quick Sync
./unix/h264-transcode.sh -r -q
./unix/hevc-transcode.sh -q

# Linux/macOS with NVIDIA GPU
./unix/h264-transcode.sh -r -n
./unix/hevc-transcode.sh -n

# Windows with NVIDIA GPU
.\windows\h264-transcode.ps1 -Recurse -UseNVENC
.\windows\hevc-transcode.ps1 -UseNVENC
```

See [HARDWARE_ACCEL_GUIDE.md](HARDWARE_ACCEL_GUIDE.md) for detailed setup instructions.

## How It Works

1. **File Preparation**: Renames files with spaces to use underscores
2. **File Collection**: Scans for eligible `.mp4` files (skips already-transcoded files)
3. **UHD/4K Detection**: Detects if input video is larger than 1080p and applies aspect-safe downscaling
4. **Transcoding**: Converts video using specified codec, copies audio without re-encoding
5. **Verification**: Validates output file integrity with ffprobe
6. **Cleanup**: Deletes source file only after successful verification

## Output Files

- **H.264**: Creates `*_REDU.mp4` files
- **HEVC**: Creates `*_HEVC.mp4` files
- **Temporary**: Uses `*.tmp.mp4` during processing (auto-cleaned)

## Safety Features

- ✓ Output file is verified with ffprobe before source deletion
- ✓ Temporary files are cleaned up on interruption (Ctrl+C)
- ✓ Skips files that already have processed versions
- ✓ Handles filenames with spaces safely
- ✓ Validates file paths to prevent injection attacks

## Encoding Settings

| Setting | Software | Intel QSV | NVIDIA NVENC | AMD AMF |
|---------|----------|-----------|--------------|---------|
| Quality | CRF 24 | Global Quality 24 | CQ 24 | QP 24 |
| H.264 Preset | veryfast | fast | p4 | speed |
| HEVC Preset | medium | medium | p4 | speed |

**Note:** Hardware encoders trade some quality for speed. For archival storage, software encoding is recommended.

## Troubleshooting

### "No eligible MP4 files found to process"
- The script found no `.mp4` files that haven't already been processed
- Check that your files have the `.mp4` extension
- Check that you don't already have `*_REDU.mp4` or `*_HEVC.mp4` versions

### "ffmpeg failed" or "Output file verification failed"
- Ensure FFmpeg is installed and in your PATH: `ffmpeg -version`
- Check that the source file isn't corrupted: `ffprobe -v error input.mp4`
- For hardware encoding, ensure your GPU/drivers support the codec

### Hardware encoding not available
- Check supported encoders: `ffmpeg -encoders | grep -E "(qsv|nvenc|amf)"`
- Update your GPU drivers
- Some FFmpeg builds don't include hardware encoders

## Performance Comparison

Approximate encoding speeds (relative to software encoding):

| Method | Speed | Quality | Power Usage |
|--------|-------|---------|-------------|
| Software (CPU) | 1x (baseline) | Best | High |
| Intel Quick Sync | 2-5x | Good | Low |
| NVIDIA NVENC | 3-10x | Good | Medium |
| AMD AMF | 2-5x | Good | Medium |

## License

These scripts are provided as-is for personal and commercial use. No warranty is provided.

## Contributing

Feel free to submit issues or pull requests for bug fixes and improvements.
