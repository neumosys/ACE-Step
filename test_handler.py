import os
import sys
import json
import argparse

# Ensure we can import the handler
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from handler import handler
except ImportError:
    print("Error: Could not import 'handler'. Make sure you are in the root of the repo.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Test RunPod handler with custom URL")
    parser.add_argument("--url", type=str, required=True, help="URL of the source audio file")
    parser.add_argument("--task", type=str, default="repaint", help="Task to perform (repaint, edit, etc.)")
    parser.add_argument("--prompt", type=str, default="", help="Prompt for generation")
    parser.add_argument("--lyrics", type=str, default="", help="Lyrics for generation")
    parser.add_argument("--repaint_start", type=float, default=0.0, help="Start time for inpainting (seconds)")
    parser.add_argument("--repaint_end", type=float, default=10.0, help="End time for inpainting (seconds)")
    
    args = parser.parse_args()

    print(f"--- Testing Handler with URL: {args.url} ---")
    print(f"Task: {args.task}")
    print(f"Prompt: {args.prompt}")
    if args.lyrics:
        print(f"Lyrics: {args.lyrics}")
    print(f"Repaint Range: {args.repaint_start}s - {args.repaint_end}s")
    
    # Check S3 Env Vars
    required_vars = ["S3_BUCKET_NAME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"WARNING: Missing environment variables for S3 upload: {', '.join(missing)}")
        print("The handler will fail to upload the result unless you set these variables.")
    
    # Construct Event
    event = {
        "input": {
            "task": args.task,
            "prompt": args.prompt,
            "lyrics": args.lyrics,
            "src_audio_path": args.url,
            "repaint_start": args.repaint_start,
            "repaint_end": args.repaint_end,
            "audio_duration": 30.0,
            "infer_step": 30,
            "guidance_scale": 7.5
        }
    }
    
    print("\n--- Invoking Handler ---")
    try:
        result = handler(event)
        print("\n--- Handler Result ---")
        print(json.dumps(result, indent=2))
        
        if "audio_url" in result:
            print(f"\nSuccess! Audio URL: {result['audio_url']}")
        elif "error" in result:
            print(f"\nFailed! Error: {result['error']}")
            
    except Exception as e:
        print(f"\nException occurred: {e}")

if __name__ == "__main__":
    main()
