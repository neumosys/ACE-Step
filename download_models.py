import os
from huggingface_hub import snapshot_download

REPO_ID = "ACE-Step/ACE-Step-v1-3.5B"
CHECKPOINT_DIR = "/app/checkpoints"

def download_models():
    print(f"Downloading models from {REPO_ID} to {CHECKPOINT_DIR}...")
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    snapshot_download(repo_id=REPO_ID, local_dir=CHECKPOINT_DIR)
    print("Download complete.")

if __name__ == "__main__":
    download_models()
