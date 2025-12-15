"""Simple Flask web app to run BabyAgent vision and sound analysis on uploaded videos or URLs."""

from __future__ import annotations

import io
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, render_template_string, request

from BabyAgent.vision import video_GPT

app = Flask(__name__)

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>BabyAgent Vision and Sound</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem auto; max-width: 720px; }
      form { margin-bottom: 1.5rem; padding: 1rem; border: 1px solid #ccc; border-radius: 8px; }
      label { display: block; margin: 0.5rem 0 0.2rem; font-weight: bold; }
      input[type="text"], input[type="file"] { width: 100%; padding: 0.4rem; }
      button { margin-top: 1rem; padding: 0.6rem 1.2rem; }
      .error { color: #b30000; margin-bottom: 1rem; }
      pre { white-space: pre-wrap; background: #f7f7f7; padding: 1rem; border-radius: 6px; }
    </style>
  </head>
  <body>
    <h1>BabyAgent Vision and Sound Analysis</h1>
    <p>Upload a baby video or provide a link to generate observations and soothing suggestions.</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post" enctype="multipart/form-data">
      <label for="video_file">Local baby video (MP4/MOV/…)</label>
      <input type="file" id="video_file" name="video_file" accept="video/*" />

      <label for="video_url">or Remote video URL (YouTube, Loom, etc.)</label>
      <input type="text" id="video_url" name="video_url" placeholder="https://" value="{{ request.form.video_url }}" />

      <button type="submit">Analyze Video</button>
    </form>

    {% if analysis %}
      <h2>Analysis Output</h2>
      <pre>{{ analysis }}</pre>
    {% endif %}
  </body>
</html>
"""


def run_analysis(video_source: str) -> str:
    """Invoke BabyAgent.video_GPT and capture its textual output."""

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        video_GPT(video_path=video_source)
    return buffer.getvalue()


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    analysis_output = None

    if request.method == "POST":
        video_url = (request.form.get("video_url") or "").strip()
        uploaded_file = request.files.get("video_file")

        if not video_url and (not uploaded_file or not uploaded_file.filename):
            error = "Please upload a video or provide a URL."
        elif video_url and uploaded_file and uploaded_file.filename:
            error = "Provide either a video file or a URL, not both."
        else:
            temp_path = None
            try:
                if uploaded_file and uploaded_file.filename:
                    suffix = Path(uploaded_file.filename).suffix or ".mp4"
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix
                    ) as tmp:
                        uploaded_file.save(tmp.name)
                        temp_path = tmp.name
                    source = temp_path
                else:
                    source = video_url

                analysis_output = run_analysis(source)
            except Exception as exc:  # pragma: no cover - runtime feedback
                error = f"Analysis failed: {exc}"
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

    return render_template_string(
        PAGE_TEMPLATE,
        error=error,
        analysis=analysis_output,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
