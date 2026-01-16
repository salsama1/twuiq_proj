"""
app.py — One-file Speech API (Local LLM)

Pipeline:
  Arabic audio -> Whisper (task=translate) -> English text
  -> Local LLM (English) -> English output
  -> Google Translate (EN->AR) -> Arabic text
  -> Google TTS (AR) -> WAV audio

Run:
  uvicorn app:app --host 0.0.0.0 --port 8000

POST /process (multipart form-data):
  - audio: file
  - voice: optional (default ar-XA-Wavenet-B)
  - return_audio_base64: optional true/false (default true)

ENV REQUIRED:
  GOOGLE_APPLICATION_CREDENTIALS = path to gcp key json
  GCP_PROJECT_ID = your GCP project id

ENV for local LLM:
  LOCAL_LLM_PROVIDER = "ollama" or "http"   (default: ollama)
  If ollama:
    OLLAMA_URL = http://localhost:11434
    OLLAMA_MODEL = llama3.1:8b
  If http:
    LOCAL_LLM_URL = http://localhost:8080/generate
"""

import base64
import os
import tempfile
from typing import Dict, Any

import requests
from fastapi import FastAPI, File, Form, UploadFile, HTTPException

import whisper

from google.cloud import translate_v3
from google.cloud import texttospeech


app = FastAPI(title="Arabic->English Local LLM -> Arabic TTS API")

# Whisper model load (once)
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
whisper_model = whisper.load_model(WHISPER_MODEL_NAME)

# Google clients (require GOOGLE_APPLICATION_CREDENTIALS)
translate_client = translate_v3.TranslationServiceClient()
tts_client = texttospeech.TextToSpeechClient()


def normalize_for_speech_ar(text: str) -> str:
    """
    Simple Arabic speech normalization:
    - trim / collapse whitespace
    - add final punctuation for better cadence
    """
    t = " ".join((text or "").strip().split())
    if t and t[-1] not in ".؟!":
        t += "."
    return t


def chunk_for_tts(text: str, max_chars: int = 350) -> list[str]:
    """
    Chunk Arabic text to improve TTS stability.
    Splits by sentence punctuation; falls back to char slicing.
    """
    t = (text or "").strip()
    if not t:
        return []

    seps = ["。", ".", "؟", "!", "…", "،", "\n"]
    chunks = []
    cur = ""

    for ch in t:
        cur += ch
        if ch in seps and len(cur) >= 40:
            chunks.append(cur.strip())
            cur = ""
        elif len(cur) >= max_chars:
            chunks.append(cur.strip())
            cur = ""
    if cur.strip():
        chunks.append(cur.strip())

    return [c for c in chunks if c]


def whisper_ar_to_en(audio_path: str) -> str:
    """
    Arabic speech -> English text using Whisper translate
    """
    result = whisper_model.transcribe(
        audio_path,
        task="translate",
        language="ar"
    )
    return (result.get("text") or "").strip()


def local_llm_generate(english_input: str) -> str:
    """
    English input -> English output using local LLM.
    Supports:
      - Ollama (default)
      - Generic HTTP endpoint
    """
    provider = os.getenv("LOCAL_LLM_PROVIDER", "ollama").strip().lower()

    # Strong prompt for "assistant response" in English
    system_style = (
        "You are a helpful assistant. Answer clearly and concisely in English. "
        "If the input is a question, answer it. If it is a command, comply if safe."
    )
    prompt = f"{system_style}\n\nUser:\n{english_input}\n\nAssistant:\n"

    if provider == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

        url = f"{ollama_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 512
            }
        }
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama error: {r.status_code} {r.text}")
        data = r.json()
        return (data.get("response") or "").strip()

    elif provider == "http":
        url = os.getenv("LOCAL_LLM_URL", "").strip()
        if not url:
            raise HTTPException(status_code=500, detail="LOCAL_LLM_URL is not set for LOCAL_LLM_PROVIDER=http")

        payload = {"prompt": prompt, "max_tokens": 512, "temperature": 0.2}
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Local LLM HTTP error: {r.status_code} {r.text}")
        data = r.json()
        # expected: {"text":"..."}
        text = (data.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=502, detail="Local LLM HTTP returned empty 'text'")
        return text

    else:
        raise HTTPException(status_code=500, detail=f"Unsupported LOCAL_LLM_PROVIDER: {provider}")


def translate_en_to_ar(text_en: str, project_id: str) -> str:
    """
    English -> Arabic via Google Translate v3
    """
    if not project_id:
        raise HTTPException(status_code=500, detail="GCP_PROJECT_ID is required for Translation v3.")

    parent = f"projects/{project_id}/locations/global"
    response = translate_client.translate_text(
        request={
            "parent": parent,
            "contents": [text_en],
            "mime_type": "text/plain",
            "source_language_code": "en",
            "target_language_code": "ar",
        }
    )
    if not response.translations:
        return ""
    return (response.translations[0].translated_text or "").strip()


def tts_arabic_to_wav(text_ar: str, voice_name: str = "ar-XA-Wavenet-B") -> bytes:
    """
    Arabic text -> WAV (LINEAR16) audio using Google TTS.
    For long text, this function should be called per chunk and then concatenated
    by the caller (simple WAV concat is not safe). We'll keep chunks small.
    """
    synthesis_input = texttospeech.SynthesisInput(text=text_ar)

    voice = texttospeech.VoiceSelectionParams(
        language_code="ar-XA",
        name=voice_name,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


@app.post("/process")
async def process(
    audio: UploadFile = File(...),
    voice: str = Form("ar-XA-Wavenet-B"),
    return_audio_base64: str = Form("true"),
):
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No audio file uploaded.")

    # Save uploaded audio to temp
    suffix = os.path.splitext(audio.filename)[-1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        tmp.write(await audio.read())

    try:
        # 1) Arabic speech -> English
        stt_english = whisper_ar_to_en(tmp_path)
        if not stt_english:
            raise HTTPException(status_code=400, detail="Whisper produced empty English text.")

        # 2) English -> English local LLM
        llm_english = local_llm_generate(stt_english)
        if not llm_english:
            raise HTTPException(status_code=502, detail="Local LLM produced empty output.")

        # 3) English -> Arabic translation (missing part)
        project_id = os.getenv("GCP_PROJECT_ID", "").strip()
        arabic_text = translate_en_to_ar(llm_english, project_id=project_id)
        arabic_text = normalize_for_speech_ar(arabic_text)

        if not arabic_text:
            raise HTTPException(status_code=502, detail="Translation produced empty Arabic text.")

        # 4) Arabic TTS (chunk for stability)
        chunks = chunk_for_tts(arabic_text, max_chars=300)
        # NOTE: Google TTS returns raw LINEAR16 bytes (not a WAV header).
        # For simplicity, we return the audio bytes as given. Many players expect WAV header.
        # Best practice: request MP3 or add a WAV header. We'll output MP3 to avoid header issues.

        # Switch to MP3 output to make playback easy
        # Re-synthesize using MP3
        audio_bytes_all = b""
        mp3_outputs = []
        for c in chunks:
            synthesis_input = texttospeech.SynthesisInput(text=c)
            v = texttospeech.VoiceSelectionParams(language_code="ar-XA", name=voice)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            resp = tts_client.synthesize_speech(input=synthesis_input, voice=v, audio_config=audio_config)
            mp3_outputs.append(resp.audio_content)

        # Naive MP3 concat generally works for many players; if you need perfect concat,
        # you can stitch with ffmpeg later. For "finish now", this is usually OK.
        audio_bytes_all = b"".join(mp3_outputs)

        result: Dict[str, Any] = {
            "stt_english": stt_english,
            "llm_english": llm_english,
            "arabic_text": arabic_text,
            "voice_used": voice,
            "whisper_model": WHISPER_MODEL_NAME,
            "audio_format": "mp3",
        }

        if return_audio_base64.lower() == "true":
            result["audio_base64"] = base64.b64encode(audio_bytes_all).decode("utf-8")

        return result

    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
