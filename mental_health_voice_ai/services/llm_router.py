"""
Resilient LLM Routing & Secondary Failover System.
Provides sub-second inference via Groq LPU with automatic Gemini Flash Lite failover and local Ollama support.
"""
import os
import sys
import time
import re
import json
from typing import Dict, Any, Optional

_groq_llm_client = None

def get_groq_client():
    global _groq_llm_client
    if _groq_llm_client is None:
        key = os.getenv("GROQ_API_KEY")
        if key:
            try:
                from groq import Groq
                _groq_llm_client = Groq(api_key=key)
            except Exception as e:
                print(f"[!] Groq import notice: {e}")
    return _groq_llm_client

def query_groq_llm(prompt: str, system_instruction: str, max_tokens: int = 550) -> Optional[Dict[str, Any]]:
    """
    Sub-second conversational LLM reasoning via Groq LPU (~300ms).
    Primary: openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b
    """
    client = get_groq_client()
    if not client:
        return None
    models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    for model_name in models:
        tokens_to_request = 1500 if model_name.startswith("openai/") else max_tokens
        for attempt in range(2):
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.15,
                    max_tokens=tokens_to_request
                )
                raw = (completion.choices[0].message.content or "").strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                cand = json.loads(raw)
                if cand and isinstance(cand, dict) and "reply_text" in cand:
                    print(f"[+] Successfully responded via Groq LPU ({model_name}) in sub-second speed")
                    return cand
            except Exception as e:
                err_str = str(e)
                print(f"[!] Groq model {model_name} attempt {attempt+1} notice: {e}")
                if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                    break
                if ("rate_limit" in err_str.lower() or "429" in err_str) and attempt == 0:
                    m = re.search(r'try again in ([\d\.]+)s', err_str)
                    wait_sec = min(35.0, float(m.group(1)) + 0.5) if m else 5.0
                    time.sleep(wait_sec)
                    continue
                break
    return None

def query_local_ollama(prompt: str, system_instruction: str, model_name: str = "qwen2.5:3b") -> Optional[Dict[str, Any]]:
    """
    Sub-second offline local inference via Ollama (only if explicitly enabled via ENABLE_LOCAL_OLLAMA=1).
    Zero-delay skip on cloud instances.
    """
    if os.getenv("ENABLE_LOCAL_OLLAMA", "0") != "1":
        return None

    import urllib.request
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    target_model = os.getenv("OLLAMA_MODEL", model_name)
    try:
        payload = json.dumps({
            "model": target_model,
            "prompt": f"{system_instruction}\n\n{prompt}",
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 450}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                response_str = (body.get("response") or "").strip()
                if response_str.startswith("```"):
                    response_str = re.sub(r"^```(?:json)?\s*", "", response_str)
                    response_str = re.sub(r"\s*```$", "", response_str)
                cand = json.loads(response_str)
                if cand and isinstance(cand, dict) and "reply_text" in cand:
                    print(f"[+] Successfully responded via Local Ollama ({target_model}) on GPU")
                    return cand
    except Exception:
        pass
    return None

def query_gemini_backup(prompt: str, system_instruction: str, max_tokens: int = 550) -> Optional[Dict[str, Any]]:
    """
    Automatic secondary LLM failover via Google Gemini Flash Lite (~400ms).
    Triggered when Groq hits 429 rate limits, token exhaustion, or connection errors.
    Uses the configured GEMINI_API_KEY with strict JSON output format.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=max_tokens
        )
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
            config=config
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        cand = json.loads(text)
        if cand and isinstance(cand, dict) and "reply_text" in cand:
            print("[+] Successfully responded via Secondary Backup (Gemini Flash Lite)")
            return cand
    except Exception as e:
        print(f"[!] Secondary Gemini backup notice: {e}")
    return None
