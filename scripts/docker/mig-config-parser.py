#!/usr/bin/env python3
"""Parse MIG configuration from resource-limits.yaml"""

import json
import sys

import yaml


def main():
    if len(sys.argv) < 2:
        print("Usage: mig-config-parser.py <config-file>", file=sys.stderr)
        sys.exit(1)

    config_file = sys.argv[1]

    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # `or {}`: a comments-only section parses to None, so the dict default
        # of .get() never applies — guard both levels against a present-but-null value.
        mig_config = (config.get("gpu_allocation") or {}).get("mig_gpus") or {}

        # Convert to list format for easier bash processing
        result = []
        for gpu_id, settings in mig_config.items():
            result.append(
                {
                    "gpu_id": int(gpu_id),
                    "enable": settings.get("enable", False),
                    "profile": settings.get("profile"),
                    "instances": settings.get("instances", 0),
                }
            )

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error parsing config: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
