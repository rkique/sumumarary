import os
import json
import sys

#!/usr/bin/env python3

def build_stem_to_filename_map(directory: str) -> dict:
    # Determine current script to exclude it from mapping (if running as a script)
    current_script = os.path.basename(__file__) if '__file__' in globals() else None

    mapping = {}
    for entry in os.listdir(directory):
        full_path = os.path.join(directory, entry)
        if not os.path.isfile(full_path):
            continue
        if current_script and entry == current_script:
            continue  # exclude this script from "other files"
        stem = entry.split('.')[0]
        mapping[stem] = entry
    return mapping

def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    mapping = build_stem_to_filename_map(directory)
    output_path = "file_map.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    print(f"Wrote {output_path}")

if __name__ == "__main__":
    main()