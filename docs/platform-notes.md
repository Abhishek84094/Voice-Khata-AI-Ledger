# Platform Notes — Verified External APIs (Phase 1 Bake-Off)

> All facts below have been verified via live API calls against production endpoints in Phase 1.

---

## 1. Sarvam AI — Speech Services

### 1.1 Speech-to-Text (STT)
- **Active Production Model**: `saaras:v3` (`saarika:v2` is deprecated by Sarvam).
- **REST Endpoint**: `https://api.sarvam.ai/speech-to-text`
- **Method**: `POST` (`multipart/form-data`)
- **Headers**:
  - `api-subscription-key`: `<SARVAM_API_KEY>`
- **Form Fields**:
  - `file`: Audio file (`audio/wav`, `audio/mpeg`, etc., mono 16 kHz recommended).
  - `model`: `"saaras:v3"`
  - `language_code`: `"hi-IN"`, `"kn-IN"`, `"ta-IN"`, `"te-IN"`, `"mr-IN"`, `"en-IN"`, etc.
  - `with_diarization`: `false` (default)
- **Observed Response**:
  ```json
  {
    "request_id": "20261125_0aa3b64e-fe4a-42ab-b9ed-aecfcc800ed8",
    "transcript": "रमेश का ३४० उधार।",
    "language_code": "hi-IN"
  }
  ```
- **Crucial Behavioral Finding**: Hindi STT returns **Devanagari numerals** (e.g. `३४०` for 340) and Hindi punctuation (`।`). The NLU number normalizer must convert Devanagari digits `[०-९]` to standard Arabic digits.
- **Latency**: ~800–1200 ms for short utterances (~1–2s audio).

### 1.2 Text-to-Speech (TTS)
- **Active Production Models**:
  - `bulbul:v4-flash` (Optimized for speed / conversational voice; latency ~1000 ms full clip)
  - `bulbul:v3` (High naturalness; latency ~1400–1600 ms)
- **REST Endpoint**: `https://api.sarvam.ai/text-to-speech`
- **Method**: `POST` (`application/json`)
- **Headers**:
  - `api-subscription-key`: `<SARVAM_API_KEY>`
  - `Content-Type`: `application/json`
- **Request Body**:
  ```json
  {
    "inputs": ["रमेश, ₹340 उधार. हो गया."],
    "target_language_code": "hi-IN",
    "speaker": "amit_hi_conversational",
    "model": "bulbul:v4-flash"
  }
  ```
  *(For `bulbul:v3`, supported speakers include: `aditya`, `anushka`, `manisha`, `vidya`, etc.)*
- **Observed Response**:
  ```json
  {
    "audios": ["<base64-encoded WAV/PCM audio string>"]
  }
  ```

---

## 2. Groq — Low-Latency LLM Fallback (Slow Path)

- **Endpoint**: `https://api.groq.com/openai/v1/chat/completions`
- **Method**: `POST` (`application/json`)
- **Headers**:
  - `Authorization`: `Bearer <GROQ_API_KEY>`
  - `Content-Type`: `application/json`
- **Recommended Fast Model**: `qwen/qwen3.8-27b`
  - Measured latency: **~150–205 ms** (P95 < 250 ms)
  - Temperature: `0`
  - Strict JSON mode: `"response_format": {"type": "json_object"}`
- **Alternative Model**: `openai/gpt-oss-20b` (Latency: ~500–790 ms)
- **Observed Response**:
  ```json
  {
    "choices": [
      {
        "message": {
          "role": "assistant",
          "content": "{\"status\": \"ok\"}"
        }
      }
    ]
  }
  ```

---

## 3. Architecture Alignment & Latency Conclusions

1. **Deterministic Rules Fast-Path is Mandatory**:
   - Sarvam STT: ~900 ms.
   - If NLU uses fast-path rules (≤10 ms) + DB commit (≤30 ms), UI card updates in ~940 ms.
   - If LLM is invoked on every request, Groq adds ~180 ms network round-trip.
2. **TTS Caching**:
   - Generating dynamic TTS on Sarvam takes ~1000–1400 ms.
   - Pre-generating and caching static confirmation phrases ("हो गया", "लिख लिया", "काउंस सा रमेश?") reduces audio response time dramatically (§4.3.8).
