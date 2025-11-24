import runpod
import os
import base64
import time
import tempfile
import shutil
import boto3
import uuid
from botocore.exceptions import NoCredentialsError
from acestep.pipeline_ace_step import ACEStepPipeline

# Initialize the pipeline globally to load the model once
print("Initializing ACEStepPipeline...")
checkpoint_dir = os.environ.get("CHECKPOINT_DIR", "/app/checkpoints")
if not os.path.exists(checkpoint_dir):
    print(f"Checkpoint directory {checkpoint_dir} does not exist. Using default cache or downloading.")
    checkpoint_dir = None # Let the pipeline handle it (downloads to ~/.cache)

# You might want to parameterize device_id, dtype, etc. via env vars
pipeline = ACEStepPipeline(
    checkpoint_dir=checkpoint_dir,
    device_id=0,
    dtype="bfloat16", # or float32 based on env?
    torch_compile=False # Set to True if needed, might increase startup time
)
print("ACEStepPipeline initialized.")

# Initialize S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")

def upload_to_s3(file_path, bucket, object_name=None):
    """Upload a file to an S3 bucket and return the URL."""
    if object_name is None:
        object_name = os.path.basename(file_path)

    try:
        s3_client.upload_file(file_path, bucket, object_name)
        
        # Generate a presigned URL (valid for 1 hour by default)
        # url = s3_client.generate_presigned_url('get_object',
        #                                        Params={'Bucket': bucket,
        #                                                'Key': object_name},
        #                                        ExpiresIn=3600)
        
        # Or if the bucket is public / we want a permanent link format (assuming public read or similar policy)
        # url = f"https://{bucket}.s3.amazonaws.com/{object_name}"
        
        # Let's use presigned URL for safety unless configured otherwise
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': object_name},
            ExpiresIn=3600 * 24 # 24 hours
        )
        return url
    except FileNotFoundError:
        print("The file was not found")
        return None
    except NoCredentialsError:
        print("Credentials not available")
        return None
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None

import requests

def download_or_decode_audio(input_str, suffix=".wav"):
    """
    Decodes base64 string OR downloads from URL to a temporary file.
    Returns the path to the temporary file.
    """
    if not input_str:
        return None
    
    try:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd) # Close immediately, we will write to it
        
        # Check if it's a URL
        if input_str.startswith("http://") or input_str.startswith("https://"):
            print(f"Downloading audio from URL: {input_str}")
            response = requests.get(input_str, stream=True)
            response.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        else:
            # Assume base64
            # Handle data URI scheme if present
            if "," in input_str:
                input_str = input_str.split(",")[1]
            
            audio_bytes = base64.b64decode(input_str)
            with open(path, 'wb') as f:
                f.write(audio_bytes)
                
        return path
    except Exception as e:
        print(f"Error processing audio input: {e}")
        if os.path.exists(path):
            os.remove(path)
        return None

def handler(event):
    """
    RunPod handler function.
    """
    print("Received event:", event)
    job_input = event["input"]
    
    # Check for S3 configuration
    if not S3_BUCKET_NAME:
        return {"error": "S3_BUCKET_NAME environment variable is not set."}

    # Create a temporary directory for this job to avoid collisions
    job_dir = tempfile.mkdtemp()
    output_dir = os.path.join(job_dir, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    temp_files = []

    try:
        # --- Extract Parameters ---
        # Core parameters
        prompt = job_input.get("prompt")
        lyrics = job_input.get("lyrics", "")
        audio_duration = float(job_input.get("audio_duration", 60.0))
        infer_step = int(job_input.get("infer_step", 60))
        guidance_scale = float(job_input.get("guidance_scale", 15.0))
        scheduler_type = job_input.get("scheduler_type", "euler")
        cfg_type = job_input.get("cfg_type", "apg")
        omega_scale = float(job_input.get("omega_scale", 10.0))
        manual_seeds = job_input.get("manual_seeds", None)
        if manual_seeds and not isinstance(manual_seeds, list):
             # Handle case where it might be a single int or string
             if isinstance(manual_seeds, (int, str)):
                 manual_seeds = [int(manual_seeds)]
        
        # Advanced parameters
        task = job_input.get("task", "text2music") # text2music, retake, repaint, extend, edit, audio2audio
        guidance_interval = float(job_input.get("guidance_interval", 0.5))
        guidance_interval_decay = float(job_input.get("guidance_interval_decay", 0.0))
        min_guidance_scale = float(job_input.get("min_guidance_scale", 3.0))
        use_erg_tag = job_input.get("use_erg_tag", True)
        use_erg_lyric = job_input.get("use_erg_lyric", True)
        use_erg_diffusion = job_input.get("use_erg_diffusion", True)
        oss_steps = job_input.get("oss_steps", None)
        guidance_scale_text = float(job_input.get("guidance_scale_text", 0.0))
        guidance_scale_lyric = float(job_input.get("guidance_scale_lyric", 0.0))
        lora_name_or_path = job_input.get("lora_name_or_path", "none")
        
        # Audio2Audio specific
        audio2audio_enable = job_input.get("audio2audio_enable", False)
        ref_audio_strength = float(job_input.get("ref_audio_strength", 0.5))
        ref_audio_input_str = job_input.get("ref_audio_input")
        ref_audio_input = None
        if ref_audio_input_str:
            ref_audio_input = download_or_decode_audio(ref_audio_input_str)
            if ref_audio_input:
                temp_files.append(ref_audio_input)
        
        # Repaint/Retake/Extend/Edit specific
        retake_seeds = job_input.get("retake_seeds", None)
        retake_variance = float(job_input.get("retake_variance", 0.5))
        repaint_start = float(job_input.get("repaint_start", 0))
        repaint_end = float(job_input.get("repaint_end", 0))
        
        src_audio_input_str = job_input.get("src_audio_path") # Expecting base64 or URL
        src_audio_path = None
        if src_audio_input_str:
            src_audio_path = download_or_decode_audio(src_audio_input_str)
            if src_audio_path:
                temp_files.append(src_audio_path)
        
        # Edit specific
        edit_target_prompt = job_input.get("edit_target_prompt")
        edit_target_lyrics = job_input.get("edit_target_lyrics")
        edit_n_min = float(job_input.get("edit_n_min", 0.0))
        edit_n_max = float(job_input.get("edit_n_max", 1.0))
        edit_n_avg = int(job_input.get("edit_n_avg", 1))

        # Validation for tasks requiring source audio
        if task in ["repaint", "retake", "extend", "edit"] and not src_audio_path:
            return {"error": f"Task '{task}' requires 'src_audio_path' (base64 encoded audio)."}
        
        if task == "edit" and not edit_target_prompt:
             return {"error": "Task 'edit' requires 'edit_target_prompt'."}

        print(f"Starting generation for task: {task}")
        start_time = time.time()
        
        output_paths = pipeline(
            prompt=prompt,
            lyrics=lyrics,
            audio_duration=audio_duration,
            infer_step=infer_step,
            guidance_scale=guidance_scale,
            scheduler_type=scheduler_type,
            cfg_type=cfg_type,
            omega_scale=omega_scale,
            manual_seeds=manual_seeds,
            guidance_interval=guidance_interval,
            guidance_interval_decay=guidance_interval_decay,
            min_guidance_scale=min_guidance_scale,
            use_erg_tag=use_erg_tag,
            use_erg_lyric=use_erg_lyric,
            use_erg_diffusion=use_erg_diffusion,
            oss_steps=oss_steps,
            guidance_scale_text=guidance_scale_text,
            guidance_scale_lyric=guidance_scale_lyric,
            audio2audio_enable=audio2audio_enable,
            ref_audio_strength=ref_audio_strength,
            ref_audio_input=ref_audio_input,
            lora_name_or_path=lora_name_or_path,
            retake_seeds=retake_seeds,
            retake_variance=retake_variance,
            task=task,
            repaint_start=repaint_start,
            repaint_end=repaint_end,
            src_audio_path=src_audio_path,
            edit_target_prompt=edit_target_prompt,
            edit_target_lyrics=edit_target_lyrics,
            edit_n_min=edit_n_min,
            edit_n_max=edit_n_max,
            edit_n_avg=edit_n_avg,
            save_path=output_dir,
            batch_size=1, # Enforce batch size 1 for serverless worker simplicity
        )
        
        end_time = time.time()
        print(f"Generation completed in {end_time - start_time:.2f} seconds.")
        
        # output_paths is a list of audio paths + [input_params_json]
        # The audio paths are the first elements.
        
        if not output_paths or len(output_paths) < 2: # At least one audio + json
             return {"error": "No output generated."}

        audio_path = output_paths[0]
        
        if not os.path.exists(audio_path):
            return {"error": "Audio file was not generated."}
            
        # Upload to S3
        file_name = f"{uuid.uuid4()}.wav"
        s3_url = upload_to_s3(audio_path, S3_BUCKET_NAME, file_name)
        
        if not s3_url:
            return {"error": "Failed to upload to S3."}
            
        return {
            "audio_url": s3_url,
            "format": "wav",
            "duration": audio_duration,
            "task": task
        }
        
    except Exception as e:
        print(f"Error during generation: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        # Cleanup temp files and directories
        for p in temp_files:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
            except:
                pass

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
