#!/usr/bin/env python3
"""Compatibility entry point for the shared HEVC MKV transcoder.

The implementation lives in transcode_cli.py so checkpoint validation, locking,
segmentation, concatenation, and finalization are identical on every platform.
Legacy flags (-q/-n/-a/-t) are accepted directly by transcode_cli.py.
"""
import sys

import transcode_cli


def main():
    sys.argv[1:1] = ["--profile", "hevc_mkv_legacy"]
    return transcode_cli.main()


if __name__ == "__main__":
    sys.exit(main())