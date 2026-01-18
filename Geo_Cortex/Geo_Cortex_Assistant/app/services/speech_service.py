from __future__ import annotations

import base64
import os
import tempfile
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from sqlalchemy.orm import Session

from app.services.master_agent_service import run_master_agent


def _collapse_ws(s: str) -> str:
    return " ".join((s or "").strip().split())


def normalize_for_speech_ar(text: str) -> str:
    """
    Simple Arabic speech normalization:
    - trim / collapse whitespace
    - add final punctuation for better cadence
    """
    t = _collapse_ws(text)
    if t and t[-1] not in ".؟!":
        t += "."
    return t


def chunk_for_tts(text: str, max_chars: int = 300) -> list[str]:
    """
    Chunk Arabic text to improve TTS stability.
    Splits by punctuation; falls back to char slicing.
    """
    t = (text or "").strip()
    if not t:
        return []

    seps = ["。", ".", "؟", "!", "…", "،", "\n"]
    chunks: list[str] = []
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


_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        import whisper  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Speech requires Whisper. Install optional deps (see requirements-speech.txt). "
            "Also ensure ffmpeg is installed and on PATH."
        ) from e
    model_name = os.getenv("WHISPER_MODEL", "small")
    _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def whisper_ar_transcribe(audio_path: str) -> Dict[str, Any]:
    """
    Arabic speech -> Arabic text using Whisper transcribe.

    Returns a small dict so callers can log/debug what Whisper produced without leaking audio.
    """
    model = _get_whisper_model()

    # Prefer deterministic decoding; make CPU inference robust (fp16 must be False on CPU).
    # Some Whisper versions may not support all kwargs; fall back to minimal call.
    try:
        result = model.transcribe(
            audio_path,
            task="transcribe",
            language="ar",
            fp16=False,
            temperature=0,
            best_of=1,
            beam_size=5,
            patience=1.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            verbose=False,
        )
    except TypeError:
        result = model.transcribe(audio_path, task="transcribe", language="ar")

    text = (result.get("text") or "").strip()
    segs = result.get("segments") or []
    return {
        "text": text,
        "language": result.get("language"),
        "segments": len(segs) if isinstance(segs, list) else None,
    }


def _looks_arabic_text(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    ar_chars = sum(1 for ch in s if "\u0600" <= ch <= "\u06FF")
    latin_chars = sum(1 for ch in s if ("a" <= ch.lower() <= "z"))
    # Require at least a few Arabic letters and not be dominated by Latin.
    return ar_chars >= 3 and ar_chars >= latin_chars


def _integration_root() -> Path:
    # .../integration/twuiq_proj/Geo_Cortex/Geo_Cortex_Assistant/app/services/speech_service.py
    # parents[5] -> .../integration
    here = Path(__file__).resolve()
    return here.parents[5] if len(here.parents) >= 6 else here.parent


def _looks_like_service_account_json(p: Path) -> bool:
    if not p.exists() or not p.is_file():
        return False
    if p.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        isinstance(data, dict)
        and data.get("type") == "service_account"
        and isinstance(data.get("client_email"), str)
        and isinstance(data.get("private_key"), str)
    )


def _pick_service_account_json_path() -> Path:
    """
    Prefer an explicit env var path. If it's missing or wrong, fall back to a single
    service-account JSON found at the integration root (common in this repo).
    """
    env_candidates = [
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip(),  # supported by StoS1.py
    ]
    for c in env_candidates:
        if not c:
            continue
        p = Path(c)
        if p.exists() and p.is_file():
            return p

    root = _integration_root()
    matches: list[Path] = []
    for p in root.glob("*.json"):
        if _looks_like_service_account_json(p):
            matches.append(p)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple service-account JSON files found at the integration root. "
            "Set GOOGLE_APPLICATION_CREDENTIALS to the exact file path you want to use."
        )

    raise RuntimeError(
        "Missing Google credentials. Set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON file path "
        "(or place exactly one service-account JSON at the integration root)."
    )


def _service_account_project_id(p: Path) -> str:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pid = (data.get("project_id") or "").strip()
        return pid
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _get_google_clients():
    try:
        from google.cloud import translate_v3  # type: ignore
        from google.cloud import texttospeech  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Google Translate/TTS not installed. Install optional deps (see requirements-speech.txt) "
            "and set GOOGLE_APPLICATION_CREDENTIALS + GCP_PROJECT_ID (or set GOOGLE_API_KEY for REST fallback)."
        ) from e

    key_path = _pick_service_account_json_path()
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=scopes)

    return (
        translate_v3.TranslationServiceClient(credentials=creds),
        texttospeech.TextToSpeechClient(credentials=creds),
        texttospeech,
        str(key_path),
    )


def _get_google_api_key() -> str:
    # Prefer a dedicated env var; avoid overloading GOOGLE_APPLICATION_CREDENTIALS.
    return (os.getenv("GOOGLE_API_KEY", "") or os.getenv("GCP_API_KEY", "")).strip()


def _translate_v2_api_key(text_en: str, api_key: str) -> str:
    """
    English -> Arabic via Google Translate v2 REST API (API key).

    This avoids the need for a service-account JSON, but requires enabling the API and providing an API key.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for Translate v2 fallback.")

    try:
        import requests  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing 'requests' dependency for Translate v2 REST fallback.") from e

    url = f"https://translation.googleapis.com/language/translate/v2?key={api_key}"
    payload = {
        "q": text_en,
        "source": "en",
        "target": "ar",
        "format": "text",
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Translate v2 failed ({resp.status_code}): {resp.text[:500]}")
    data = resp.json() if resp.content else {}
    translated = (((data.get("data") or {}).get("translations") or [{}])[0].get("translatedText")) or ""
    return str(translated).strip()


def translate_en_to_ar(text_en: str, project_id: str) -> str:
    """
    English -> Arabic via Google Translate v3.
    """
    project_id = (project_id or "").strip()
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID is required for Translation v3 (or provide a service-account JSON with project_id).")
    translate_client, _, _, _ = _get_google_clients()
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


def _tts_v1_api_key_mp3(text_ar: str, api_key: str, voice_name: str = "ar-XA-Wavenet-B") -> bytes:
    """
    Arabic text -> MP3 bytes via Google Text-to-Speech v1 REST API (API key).
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for TTS REST fallback.")

    try:
        import requests  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing 'requests' dependency for TTS REST fallback.") from e

    # Chunking helps avoid request limits and improves stability.
    chunks = chunk_for_tts(text_ar, max_chars=300)
    outs: list[bytes] = []
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    for c in chunks:
        payload = {
            "input": {"text": c},
            "voice": {"languageCode": "ar-XA", "name": voice_name},
            "audioConfig": {"audioEncoding": "MP3"},
        }
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"TTS v1 failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json() if resp.content else {}
        audio_b64 = data.get("audioContent") or ""
        if not audio_b64:
            continue
        outs.append(base64.b64decode(audio_b64))
    return b"".join(outs)


def tts_arabic_to_mp3(text_ar: str, voice_name: str = "ar-XA-Wavenet-B") -> bytes:
    """
    Arabic text -> MP3 bytes via Google TTS.
    """
    _, tts_client, texttospeech, _ = _get_google_clients()
    chunks = chunk_for_tts(text_ar, max_chars=300)
    outs: list[bytes] = []
    for c in chunks:
        synthesis_input = texttospeech.SynthesisInput(text=c)
        voice = texttospeech.VoiceSelectionParams(language_code="ar-XA", name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        resp = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        outs.append(resp.audio_content)
    return b"".join(outs)


def agent_answer_english(
    db: Session, english_text: str, max_steps: int = 3
) -> Tuple[str, List[Dict[str, Any]], list[Any], Dict[str, Any], Dict[str, Any]]:
    """
    English text -> GeoCortex agent answer (English) + the same data payload the UI needs:
    - tool_trace
    - occurrences
    - artifacts
    """
    answer, trace, occs, artifacts = run_master_agent(db, english_text, max_steps=max_steps)
    meta = {
        "occurrences_count": len(occs or []),
        "artifacts_keys": list((artifacts or {}).keys()),
    }
    # Note: we intentionally return occurrences/artifacts so /speech/process can update map/table like /agent/.
    return answer, trace, (occs or []), (artifacts or {}), meta


def process_text(
    db: Session,
    text_en: str,
    *,
    voice: str = "ar-XA-Wavenet-B",
    return_audio_base64: bool = True,
    max_steps: int = 3,
) -> Dict[str, Any]:
    answer_en, trace, occs, artifacts, meta = agent_answer_english(db, text_en, max_steps=max_steps)

    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    api_key = _get_google_api_key()

    # If project id isn't set, try to derive it from the service-account JSON file.
    # This matches StoS1.py behavior and avoids "it works in python but not in uvicorn env" issues.
    if not project_id:
        try:
            key_path = _pick_service_account_json_path()
            project_id = _service_account_project_id(key_path)
        except Exception:
            project_id = ""

    # Prefer Translate v3 if configured; otherwise fall back to Translate v2 via API key.
    arabic_raw = ""
    last_err: Optional[Exception] = None
    if project_id:
        try:
            arabic_raw = translate_en_to_ar(answer_en, project_id=project_id)
        except Exception as e:
            last_err = e
    if (not arabic_raw) and api_key:
        try:
            arabic_raw = _translate_v2_api_key(answer_en, api_key=api_key)
        except Exception as e:
            last_err = e

    if not arabic_raw:
        if project_id and last_err is None:
            raise RuntimeError("GCP_PROJECT_ID is set but Arabic translation returned empty output.")
        if project_id and last_err is not None:
            raise RuntimeError(
                "Failed to translate EN->AR. If using Translate v3, set GOOGLE_APPLICATION_CREDENTIALS and ensure "
                "Cloud Translation API is enabled. Alternatively set GOOGLE_API_KEY to use the REST fallback. "
                f"Last error: {type(last_err).__name__}: {last_err}"
            )
        raise RuntimeError(
            "Arabic translation requires either (GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS) for Translate v3 "
            "or GOOGLE_API_KEY for Translate v2 REST fallback."
        )

    arabic_text = normalize_for_speech_ar(arabic_raw)

    result: Dict[str, Any] = {
        "input_english": text_en,
        "agent_english": answer_en,
        "arabic_text": arabic_text,
        "voice_used": voice,
        "audio_format": "mp3",
        "meta": meta,
        # Include UI payload so voice queries populate map/table/chart like typed queries.
        "tool_trace": trace,
        "occurrences": occs,
        "artifacts": artifacts,
    }
    if return_audio_base64:
        # Prefer Google client libraries (ADC) if available; otherwise use API-key REST fallback.
        audio: bytes = b""
        last_tts_err: Optional[Exception] = None
        try:
            audio = tts_arabic_to_mp3(arabic_text, voice_name=voice)
        except Exception as e:
            last_tts_err = e
            if api_key:
                audio = _tts_v1_api_key_mp3(arabic_text, api_key=api_key, voice_name=voice)
            else:
                raise RuntimeError(
                    "Arabic TTS requires either GOOGLE_APPLICATION_CREDENTIALS (ADC) or GOOGLE_API_KEY (REST). "
                    f"Last error: {type(last_tts_err).__name__}: {last_tts_err}"
                ) from e
        result["audio_base64"] = base64.b64encode(audio).decode("utf-8")
    return result


async def process_audio_upload(
    db: Session,
    audio_bytes: bytes,
    filename: str,
    *,
    voice: str = "ar-XA-Wavenet-B",
    return_audio_base64: bool = True,
    max_steps: int = 3,
) -> Dict[str, Any]:
    suffix = os.path.splitext(filename or "")[-1] or ".wav"
    tmp_path = ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        tmp.write(audio_bytes)

    try:
        stt = whisper_ar_transcribe(tmp_path)
        stt_arabic = str(stt.get("text") or "").strip()
        if (not stt_arabic) or (len(stt_arabic) < 4) or (not _looks_arabic_text(stt_arabic)):
            raise RuntimeError("Could not understand the Arabic audio clearly. Please re-record and speak the query more slowly.")

        # Feed Arabic transcript to the agent. Our agent stack supports Arabic keywords like السعودية/جميع/نقاط.
        result = process_text(db, stt_arabic, voice=voice, return_audio_base64=return_audio_base64, max_steps=max_steps)
        result["stt_arabic"] = stt_arabic
        result["stt_meta"] = {k: stt.get(k) for k in ("language", "segments")}
        result["whisper_model"] = os.getenv("WHISPER_MODEL", "small")
        return result
    finally:
        try:
            if tmp_path:
                os.remove(tmp_path)
        except Exception:
            pass

