#!/usr/bin/env python3
"""Compatibility entry point for the shared HEVC MKV transcoder.

The implementation lives in transcode_cli.py so checkpoint validation, locking,
segmentation, concatenation, and finalization are identical on every platform.
"""
import sys

import transcode_cli


def main():
    translated = ["--profile", "hevc_mkv_legacy"]
    args = iter(sys.argv[1:])
    for arg in args:
        if arg in ("-r", "--recurse"):
            translated.append("--recurse")
        elif arg in ("-q", "--quick-sync"):
            translated += ["--hw", "qsv"]
        elif arg in ("-n", "--nvenc"):
            translated += ["--hw", "nvenc"]
        elif arg in ("-a", "--amf"):
            translated += ["--hw", "amf"]
        elif arg in ("-t", "--threads", "--quality", "--config", "--segment-duration"):
            try:
                translated += ["--threads" if arg == "-t" else arg, next(args)]
            except StopIteration:
                print(f"Error: {arg} requires a value", file=sys.stderr)
                return 1
        elif arg in ("--resume", "--strict-cleanup", "-c", "--cuda-decode"):
            translated.append(arg)
        elif arg in ("-h", "--help"):
            translated.append("--help")
        else:
            print(f"Error: unrecognized argument: {arg}", file=sys.stderr)
            return 1
    sys.argv[1:] = translated
    return transcode_cli.main()


if __name__ == "__main__":
    sys.exit(main())
