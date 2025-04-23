import os
import json

NOTES_DIR = "/app/notes"
META_FILE = os.path.join(NOTES_DIR, ".meta.json")

def load_all_notes():
    notes = []

    if os.path.exists(META_FILE):
        with open(META_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        metadata = {}

    for filename in os.listdir(NOTES_DIR):
        if filename.endswith(".md"):
            notes.append({
                "filename": filename,
                "tags": metadata.get(filename, {}).get("tags", []),
                "device_ids": metadata.get(filename, {}).get("device_ids", []),
            })

    return notes
