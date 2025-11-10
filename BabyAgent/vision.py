from moviepy.video.io.VideoFileClip import VideoFileClip
import argparse
import base64
from openai import OpenAI
import shutil
import cv2
import os
import mimetypes
import tempfile
import urllib.request
from urllib.parse import urlparse
from dotenv import load_dotenv
from typing import Optional, Tuple
import re

import openai, sys

try:
    from yt_dlp import YoutubeDL  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    YoutubeDL = None


# === Paths & constants ===
FRAME_FOLDER = "../data/crying_baby/frames"
INPUT_VIDEO_PATH = "../data/crying_baby/yongzi.mp4"
OUTPUT_AUDIO_PATH = "../data/crying_baby/video_audio.wav"
BABY_CRY_CUES = ("NEH", "OWH", "HEH", "EAIR", "EH")
TRANSCRIPTION_PROMPT = (
    "This audio features a baby. When you hear Dunstan baby language sounds like "
    "NEH, OWH, HEH, EAIR, or EH, transcribe them verbatim in uppercase (e.g., NEH)."
)

PROMPT_VISION = """You are an expert in infant development and behavioral analysis with extensive experience in pediatric care.

TASK: Analyze this sequence of video frames showing an infant and the transcript of baby cues if any, using the behavioral cue framework below.

BEHAVIORAL CUE REFERENCE:
**Hunger Signs:**
- Early: lip smacking, rooting/seeking, mouth opening wide
- Mid: stretching, hand sucking, soft grunts/sighs
- Late: crying

**Tiredness Signs:**
- Early: blank stare, lost interest in toys/people, glazed/unfocused eyes
- Mid: fussy, jerky movements, yawning, eye rubbing, finger sucking, frowning
- Late: crying

**Boredom Signs:**
- Early: turning head away, squirming, grunting
- Mid: back arching, increased movement, batting at toys, pushing things away
- Late: crying

**Pain/Discomfort Signs:**
- Knees pulled to belly, back arching/rigid body, feed refusal, unusual sleep patterns, distressed expression

**Transcript of baby cues (if any):**
- NEH (hunger), OWH (sleepy), HEH (discomfort), EAIR (lower gas), EH (burp)

ANALYSIS STRUCTURE:
1. **Behavioral Stage Identification**: Match observed behaviors to the cue categories above. Note progression if multiple stages visible.

2. **Primary Assessment**: Based on cue patterns, identify the most likely feeling (hunger/tired/bored/discomfort/pain/lower gas/burp).

3. **Caregiver Response** (2 specific actions):
   - Target interventions to the identified stage (early interventions prevent escalation)
   - Avoid creating sleep/feeding associations that become dependencies

CONSTRAINTS:
- 150 words maximum
- Supportive, informative tone
- Reference specific observed cues from frames
- Note: Frames are chronological from earliest to latest"""

# === Setup ===
load_dotenv()
openai_api = os.getenv("OPENAI_API_KEY")
print(f"OpenAI API Key Loaded: {openai_api is not None}")
client = OpenAI(api_key=openai_api)


# === Utilities ===
def ensure_clean_dir(path: str):
    os.makedirs(path, exist_ok=True)
    for fn in os.listdir(path):
        fp = os.path.join(path, fn)
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                os.unlink(fp)
            elif os.path.isdir(fp):
                shutil.rmtree(fp)
        except Exception as e:
            print(f"Failed to delete {fp}. Reason: {e}")


def is_url(source: str) -> bool:
    try:
        parsed = urlparse(source)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"}


def is_youtube_url(source: str) -> bool:
    host = urlparse(source).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def detect_baby_sounds(transcript: str) -> list[str]:
    """Return Dunstan baby cues detected in transcript text."""

    found: list[str] = []
    for cue in BABY_CRY_CUES:
        if re.search(rf"\b{cue}\b", transcript, flags=re.IGNORECASE):
            found.append(cue)
    return found


def _infer_filename_from_url(url: str, content_type: Optional[str] = None) -> str:
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path.rstrip("/")) or "remote_video"
    name, ext = os.path.splitext(basename)
    if not ext:
        guessed = None
        if content_type:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        ext = guessed or ".mp4"
    return f"{name or 'remote_video'}{ext}"


def download_youtube_video(
    url: str,
    cookie_file: Optional[str] = None,
    cookies_from_browser: Optional[Tuple[str, Optional[str]]] = None,
) -> Tuple[str, str]:
    if YoutubeDL is None:
        raise RuntimeError(
            "Downloading YouTube URLs requires the yt_dlp package. Install it via `pip install yt_dlp`."
        )

    temp_dir = tempfile.mkdtemp(prefix="babyagent_youtube_")
    outtmpl = os.path.join(temp_dir, "youtube.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }
    if cookie_file:
        ydl_opts["cookiefile"] = os.path.expanduser(cookie_file)
    if cookies_from_browser:
        browser, profile = cookies_from_browser
        ydl_opts["cookiesfrombrowser"] = (browser, profile, None)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            local_path = ydl.prepare_filename(info)
        # When merge_output_format is set, the merged file may have the target extension.
        merged_path = os.path.splitext(local_path)[0] + ".mp4"
        if os.path.isfile(merged_path):
            local_path = merged_path
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return local_path, temp_dir


def download_generic_video(url: str) -> Tuple[str, str]:
    temp_dir = tempfile.mkdtemp(prefix="babyagent_remote_")
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 BabyAgent/1.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            content_type = response.headers.get("Content-Type")
            filename = _infer_filename_from_url(url, content_type)
            local_path = os.path.join(temp_dir, filename)
            with open(local_path, "wb") as outfile:
                shutil.copyfileobj(response, outfile)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return local_path, temp_dir


def prepare_video_input(
    video_source: str,
    cookie_file: Optional[str] = None,
    cookies_from_browser: Optional[Tuple[str, Optional[str]]] = None,
) -> Tuple[str, Optional[str]]:
    if not is_url(video_source):
        return video_source, None
    if is_youtube_url(video_source):
        print(f"Downloading YouTube video from {video_source}…")
        return download_youtube_video(
            video_source,
            cookie_file=cookie_file,
            cookies_from_browser=cookies_from_browser,
        )

    print(f"Downloading remote video from {video_source}…")
    return download_generic_video(video_source)


def cleanup_paths(paths: list[Optional[str]]):
    for path in paths:
        if not path:
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                print(f"Failed to remove {path}: {exc}")


def extract_frames(
    video_path: str,
    interval_sec: float = 0.5,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
):
    """Save frames every `interval_sec` seconds, limited to [start_sec, end_sec]."""

    ensure_clean_dir(FRAME_FOLDER)

    safe_start = max(0.0, float(start_sec or 0.0))
    safe_end = float(end_sec) if end_sec is not None else None
    if safe_end is not None and safe_end <= safe_start:
        print(
            "End timestamp must be greater than start; processing full video instead."
        )
        safe_end = None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error opening video file")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_skip = max(1, int(fps * interval_sec))

    if safe_start:
        cap.set(cv2.CAP_PROP_POS_MSEC, safe_start * 1000)

    pos_frames = cap.get(cv2.CAP_PROP_POS_FRAMES)
    start_frame_idx = int(pos_frames) if pos_frames > 0 else int(safe_start * fps)
    frame_idx = 0

    while True:
        current_frame = start_frame_idx + frame_idx
        current_time = current_frame / fps if fps else 0.0
        if safe_end is not None and current_time >= safe_end:
            break

        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % frame_skip == 0:
            out_path = os.path.join(FRAME_FOLDER, f"frame_{current_frame:07d}.jpg")
            cv2.imwrite(out_path, frame)
            print(f"Saved {out_path}")
        frame_idx += 1

    cap.release()
    cv2.destroyAllWindows()


def convert_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def transcribe_audio(audio_path: str) -> str:
    """
    Prefer gpt-4o-transcribe; fall back to whisper-1 if unavailable.
    """
    try:
        with open(audio_path, "rb") as af:
            resp = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=af,
                prompt=TRANSCRIPTION_PROMPT,
            )
        return resp.text
    except Exception as e:
        print(f"gpt-4o-transcribe failed ({e}); falling back to whisper-1…")
        with open(audio_path, "rb") as af:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=af,
                prompt=TRANSCRIPTION_PROMPT,
            )
        return resp.text


def extract_audio_and_transcribe(video_path: str) -> Tuple[str, list[str]]:
    # Use WAV to avoid needing mp3 codecs (libmp3lame). mp3 is fine if your ffmpeg has the codec.
    audio_path = OUTPUT_AUDIO_PATH

    # Open the clip with a context manager so resources close cleanly
    with VideoFileClip(video_path) as clip:
        if clip.audio is None:
            transcript = "There is no audio for this video."
            print(transcript)
            return transcript, []

        # No 'verbose' kwarg; keep or remove logger. None = no progress bar/logging.
        # If you really want a progress bar: use logger="bar".
        clip.audio.write_audiofile(
            audio_path,
            logger=None,  # remove this or set to "bar" if you want progress
            # fps=16000,      # optional: downsample to 16k for ASR
            # codec="pcm_s16le"  # explicit for wav; omit for defaults
        )

    # Now run transcription
    transcript = transcribe_audio(audio_path)
    baby_cues = detect_baby_sounds(transcript)
    cues_for_log = ", ".join(baby_cues) if baby_cues else "none"
    print(f"Transcript: {transcript[:160]}{'…' if len(transcript) > 160 else ''}")
    print(f"Detected baby cues: {cues_for_log}")

    # (Optional) clean up temp file
    try:
        os.remove(audio_path)
    except OSError:
        pass

    return transcript, baby_cues


def analyze_frames_with_responses(
    prompt_text: str,
    transcript: str,
    base64frames: list[str],
    baby_cues: list[str],
):
    """
    Try the Responses API first (new multimodal). If not available in this env,
    fall back to Chat Completions with vision content blocks.
    """
    # Limit number of frames if needed (avoid huge payloads)
    MAX_FRAMES = 12
    frames = base64frames[:MAX_FRAMES]

    # Build payloads for both APIs
    cues_text = (
        "Baby cry cues detected in audio: " + ", ".join(baby_cues)
        if baby_cues
        else "No specific Dunstan baby cry cues detected in audio."
    )
    # 1) Responses API payload (input_text + input_image)
    responses_content = [
        {"type": "input_text", "text": prompt_text},
        {
            "type": "input_text",
            "text": f"Video audio transcript (may be noisy/partial): {transcript}",
        },
        {"type": "input_text", "text": cues_text},
        *(
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}
            for b64 in frames
        ),
    ]

    # 2) Chat Completions payload (text + image_url)
    chat_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "text",
                    "text": f"Video audio transcript (may be noisy/partial): {transcript}",
                },
                {"type": "text", "text": cues_text},
                *(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    }
                    for b64 in frames
                ),
            ],
        }
    ]

    # Try Responses API first
    try:
        _ = getattr(client, "responses")  # raises AttributeError if not present
        resp = client.responses.create(
            model="gpt-4.1-mini",  # or gpt-4o / gpt-4o-mini
            input=[{"role": "user", "content": responses_content}],
            max_output_tokens=300,
        )
        # Print best-effort text extraction
        if hasattr(resp, "output_text") and resp.output_text:
            print(resp.output_text)
            return
        # Fallback parse of blocks
        for block in getattr(resp, "output", []) or []:
            if getattr(block, "type", None) == "message":
                for c in block.content:
                    if c.get("type") == "output_text":
                        print(c.get("text", ""))
                        return
        print(resp)  # last resort
        return

    except AttributeError:
        # No Responses API → fall back to Chat Completions
        pass

    # Chat Completions Vision (widely available)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # vision-capable chat model
        messages=chat_messages,
        max_tokens=300,
    )
    print(resp.choices[0].message.content)


# === Main workflow ===
def video_GPT(
    video_path: str = INPUT_VIDEO_PATH,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
    cookie_file: Optional[str] = None,
    cookies_from_browser: Optional[Tuple[str, Optional[str]]] = None,
):
    local_video_path, temp_dir = prepare_video_input(
        video_path,
        cookie_file=cookie_file,
        cookies_from_browser=cookies_from_browser,
    )
    cleanup_targets = [temp_dir]

    try:
        extract_frames(
            local_video_path,
            interval_sec=0.5,
            start_sec=start_sec,
            end_sec=end_sec,
        )
        transcript, baby_cues = extract_audio_and_transcribe(local_video_path)

        # Gather all frames and encode to base64
        base64frames = []
        for filename in sorted(os.listdir(FRAME_FOLDER)):
            fp = os.path.join(FRAME_FOLDER, filename)
            if os.path.isfile(fp) and filename.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):
                base64frames.append(convert_to_base64(fp))

        analyze_frames_with_responses(
            PROMPT_VISION,
            transcript,
            base64frames,
            baby_cues,
        )
    finally:
        cleanup_paths(cleanup_targets + [FRAME_FOLDER])


def _parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Analyze baby video segments with GPT vision."
    )
    parser.add_argument(
        "--video-path",
        default=INPUT_VIDEO_PATH,
        help="Local path or URL to the video (default: %(default)s)",
    )
    parser.add_argument(
        "--start-sec",
        type=float,
        default=0.0,
        help="Start timestamp in seconds for frame extraction (default: %(default)s)",
    )
    parser.add_argument(
        "--end-sec",
        type=float,
        default=None,
        help="End timestamp in seconds for frame extraction (default: full video)",
    )
    parser.add_argument(
        "--cookie-file",
        help="Path to a cookies.txt file to authenticate YouTube downloads",
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="Use cookies from a local browser profile (format browser[:profile])",
    )

    args = parser.parse_args()

    try:
        args.cookies_from_browser = _normalize_browser_cookie_arg(
            args.cookies_from_browser
        )
    except ValueError as exc:
        parser.error(str(exc))

    return args


def _normalize_browser_cookie_arg(
    raw: Optional[str],
) -> Optional[Tuple[str, Optional[str]]]:
    if not raw:
        return None
    parts = raw.split(":", 1)
    browser = parts[0].strip()
    if not browser:
        raise ValueError(
            "--cookies-from-browser requires a browser name, e.g. chrome or firefox"
        )
    profile = parts[1].strip() if len(parts) == 2 and parts[1].strip() else None
    return browser, profile


if __name__ == "__main__":
    cli_args = _parse_cli_args()
    video_GPT(
        video_path=cli_args.video_path,
        start_sec=cli_args.start_sec,
        end_sec=cli_args.end_sec,
        cookie_file=cli_args.cookie_file,
        cookies_from_browser=cli_args.cookies_from_browser,
    )
