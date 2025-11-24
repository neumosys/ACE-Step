# RunPod Worker for ACE-Step

This directory contains the necessary files to deploy ACE-Step as a serverless worker on RunPod.

## Files

- `handler.py`: The RunPod handler script that wraps the `ACEStepPipeline`.
- `Dockerfile.runpod`: The Dockerfile to build the worker image.

## Building the Docker Image

To build the Docker image, run the following command:

```bash
docker build -f Dockerfile.runpod -t your-username/ace-step-worker:latest .
```

Replace `your-username` with your Docker Hub username.

## Pushing to Docker Hub

```bash
docker push your-username/ace-step-worker:latest
```

## Deploying on RunPod

1. Go to the [RunPod Serverless Console](https://www.runpod.io/console/serverless).
2. Click "New Endpoint".
3. Enter the image name: `your-username/ace-step-worker:latest`.
4. Configure the endpoint:
   - **Container Disk**: Ensure it's large enough (e.g., 20GB+).
   - **Volume**: (Optional) The Docker image now includes the models baked in at `/app/checkpoints`. You can still mount a volume at `/app/checkpoints` if you want to override them or persist new downloads, but it is no longer strictly required for the base models.
   - **Environment Variables**: You MUST set the following environment variables for S3 upload:
     - `S3_BUCKET_NAME`: The name of your S3 bucket.
     - `AWS_ACCESS_KEY_ID`: Your AWS access key ID.
     - `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key.
     - `AWS_REGION`: Your AWS region (e.g., `us-east-1`).
     - `S3_ENDPOINT_URL`: (Optional) Custom S3 endpoint URL (e.g., for MinIO, R2, etc.).
5. Create the endpoint.

## Usage & Input Parameters

The worker accepts a JSON payload with an `input` object.

### Basic Text-to-Music

```json
{
  "input": {
    "task": "text2music",
    "prompt": "A cinematic orchestral piece with dramatic strings and percussion.",
    "audio_duration": 30.0,
    "infer_step": 50,
    "guidance_scale": 7.5
  }
}
```

### Inpainting (Repaint/Retake)

Requires `src_audio_path` as a base64 encoded string or a URL.

```json
{
  "input": {
    "task": "repaint",
    "prompt": "A cinematic orchestral piece...",
    "src_audio_path": "https://example.com/audio.wav",
    "repaint_start": 10.0,
    "repaint_end": 20.0,
    "audio_duration": 30.0
  }
}
```

### Lyrics Editing (Edit)

Requires `src_audio_path` as a base64 encoded string or a URL.

```json
{
  "input": {
    "task": "edit",
    "edit_target_prompt": "A pop song with new lyrics...",
    "edit_target_lyrics": "New lyrics go here...",
    "src_audio_path": "https://example.com/audio.wav",
    "audio_duration": 30.0
  }
}
```

### Audio-to-Audio

Requires `ref_audio_input` as a base64 encoded string or a URL.

```json
{
  "input": {
    "task": "text2music",
    "prompt": "A remix of the input audio...",
    "audio2audio_enable": true,
    "ref_audio_input": "https://example.com/audio.wav",
    "ref_audio_strength": 0.5,
    "audio_duration": 30.0
  }
}
```

### Full Parameter List

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | str | "text2music" | Task type: `text2music`, `retake`, `repaint`, `extend`, `edit`, `audio2audio` |
| `prompt` | str | None | Text prompt for generation |
| `lyrics` | str | "" | Lyrics for generation |
| `audio_duration` | float | 60.0 | Duration of generated audio in seconds |
| `infer_step` | int | 60 | Number of inference steps |
| `guidance_scale` | float | 15.0 | Guidance scale for CFG |
| `manual_seeds` | list[int] | None | Seeds for generation |
| `src_audio_path` | str (base64/URL) | None | Source audio for repaint/edit/extend |
| `ref_audio_input` | str (base64/URL) | None | Reference audio for audio2audio |
| `repaint_start` | float | 0 | Start time for inpainting |
| `repaint_end` | float | 0 | End time for inpainting |
| `edit_target_prompt` | str | None | Target prompt for edit task |
| `edit_target_lyrics` | str | None | Target lyrics for edit task |

## Output

The handler returns a JSON object containing a presigned URL to the generated audio file:

```json
{
  "audio_url": "https://s3.amazonaws.com/your-bucket/uuid.wav?...",
  "format": "wav",
  "duration": 30.0,
  "task": "text2music"
}
```
