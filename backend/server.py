from flask import Flask, request, Response, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
from google import genai
from openai import OpenAI
import os
import json
import glob
import uuid
import pathlib

app = Flask(__name__)

# ─── CORS Configuration ──────────────────────────────────────────────────────

CORS(app, resources={r"/api/*": {
    "origins": "*",  # Permissive for now, will lock down later
    "methods": ["GET", "POST", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type"],
}})

# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_REGION = "us-east-1"

PROVIDERS = {
    "bedrock": {
        "name": "AWS Bedrock",
        "models": [
            {"id": "us.anthropic.claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "default": True},
            {"id": "us.anthropic.claude-opus-4-6-v1", "name": "Claude Opus 4.6"},
            {"id": "us.anthropic.claude-haiku-4-5-20251001-v1:0", "name": "Claude Haiku 4.5"},
            {"id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0", "name": "Claude 3.7 Sonnet"},
        ],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "models": [
            {"id": "claude-sonnet-4-6-20250514", "name": "Claude Sonnet 4.6", "default": True},
            {"id": "claude-opus-4-6-20250514", "name": "Claude Opus 4.6"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
        ],
    },
    "gemini": {
        "name": "Google Gemini",
        "models": [
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "default": True},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
        ],
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "models": [
            {"id": "meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "default": True},
            {"id": "meta/llama-3.1-8b-instruct", "name": "Llama 3.1 8B"},
            {"id": "mistralai/mistral-large-2-instruct", "name": "Mistral Large 2"},
            {"id": "google/gemma-3-27b-it", "name": "Gemma 3 27B"},
            {"id": "deepseek-ai/deepseek-v3.2", "name": "DeepSeek V3.2"},
        ],
    },
}

NVIDIA_FALLBACK_ORDER = [
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "mistralai/mistral-large-2-instruct",
    "google/gemma-3-27b-it",
]

CONVERSATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conversations")

# ─── Auth State ──────────────────────────────────────────────────────────────

_provider = None          # "bedrock" | "anthropic" | "gemini"
_client = None            # Provider-specific client
_auth_method = None       # "sso" | "api_key" | "env"
_auth_error = "No authentication configured. Connect a provider to start chatting."
_sso_profile = None       # For SSO-based Bedrock auth
_auth_region = DEFAULT_REGION


# ─── Utility Functions ───────────────────────────────────────────────────────


def _sanitize_conv_id(conv_id):
    """Reject path traversal attempts."""
    if not conv_id or '/' in conv_id or '..' in conv_id or '\\' in conv_id:
        return None
    return conv_id


def _test_sso_profile(profile_name, region=None):
    """Test if an SSO profile has valid, resolvable credentials."""
    try:
        import boto3
        session = boto3.Session(
            profile_name=profile_name,
            region_name=region or DEFAULT_REGION,
        )
        creds = session.get_credentials()
        if creds is None:
            return False
        creds.get_frozen_credentials()
        return True
    except Exception:
        return False


def get_guardrail_headers(guardrail_id="", guardrail_version="DRAFT"):
    """Generate guardrail headers for Bedrock (optional)."""
    if not guardrail_id:
        return {}
    return {
        "X-Amzn-Bedrock-GuardrailIdentifier": guardrail_id,
        "X-Amzn-Bedrock-GuardrailVersion": guardrail_version,
    }


def _auto_configure_from_env():
    """Auto-configure from environment variables (for Render deployment)."""
    global _provider, _client, _auth_method, _auth_error, _auth_region

    # Check for Anthropic API key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            _client = anthropic.Anthropic(api_key=anthropic_key)
            _provider = "anthropic"
            _auth_method = "env"
            _auth_error = None
            print("Auto-configured Anthropic provider from ANTHROPIC_API_KEY")
            return
        except Exception as e:
            print(f"Failed to configure Anthropic from env: {e}")

    # Check for Gemini API key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            _client = genai.Client(api_key=gemini_key)
            _provider = "gemini"
            _auth_method = "env"
            _auth_error = None
            print("Auto-configured Gemini provider from GEMINI_API_KEY")
            return
        except Exception as e:
            print(f"Failed to configure Gemini from env: {e}")

    # Check for AWS credentials
    aws_ak = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_sk = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", DEFAULT_REGION)
    if aws_ak and aws_sk:
        try:
            kwargs = {
                "aws_access_key": aws_ak,
                "aws_secret_key": aws_sk,
                "aws_region": aws_region,
            }
            aws_st = os.environ.get("AWS_SESSION_TOKEN")
            if aws_st:
                kwargs["aws_session_token"] = aws_st
            _client = anthropic.AnthropicBedrock(**kwargs)
            _provider = "bedrock"
            _auth_method = "env"
            _auth_region = aws_region
            _auth_error = None
            print(f"Auto-configured Bedrock provider from AWS credentials (region: {aws_region})")
            return
        except Exception as e:
            print(f"Failed to configure Bedrock from env: {e}")

    # Check for NVIDIA API key
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    if nvidia_key:
        try:
            _client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            _provider = "nvidia"
            _auth_method = "env"
            _auth_error = None
            print("Auto-configured NVIDIA NIM provider from NVIDIA_API_KEY")
            return
        except Exception as e:
            print(f"Failed to configure NVIDIA from env: {e}")


# ─── Auth Endpoints ──────────────────────────────────────────────────────────


@app.route("/api/auth-status")
def auth_status():
    """Get current authentication status."""
    return jsonify({
        "provider": _provider,
        "method": _auth_method,
        "error": _auth_error,
        "profile": _sso_profile if _auth_method == "sso" else None,
        "region": _auth_region if _provider == "bedrock" else None,
    })


@app.route("/api/auth-provider", methods=["POST"])
def auth_provider():
    """Unified authentication endpoint for all providers."""
    global _provider, _client, _auth_method, _auth_error, _sso_profile, _auth_region

    data = request.json
    provider_name = data.get("provider", "").strip().lower()

    if provider_name not in PROVIDERS:
        return jsonify({"success": False, "error": f"Unknown provider: {provider_name}"})

    try:
        if provider_name == "bedrock":
            # Bedrock via API key
            access_key = data.get("access_key", "").strip()
            secret_key = data.get("secret_key", "").strip()
            session_token = data.get("session_token", "").strip() or None
            region = data.get("region", DEFAULT_REGION).strip()

            if not access_key or not secret_key:
                return jsonify({"success": False, "error": "Access key and secret key are required"})

            kwargs = {
                "aws_access_key": access_key,
                "aws_secret_key": secret_key,
                "aws_region": region,
            }
            if session_token:
                kwargs["aws_session_token"] = session_token

            _client = anthropic.AnthropicBedrock(**kwargs)
            _provider = "bedrock"
            _auth_method = "api_key"
            _sso_profile = None
            _auth_region = region
            _auth_error = None
            return jsonify({"success": True, "provider": "bedrock", "method": "api_key"})

        elif provider_name == "anthropic":
            # Anthropic via API key
            api_key = data.get("api_key", "").strip()
            if not api_key:
                return jsonify({"success": False, "error": "API key is required"})

            _client = anthropic.Anthropic(api_key=api_key)
            _provider = "anthropic"
            _auth_method = "api_key"
            _sso_profile = None
            _auth_error = None
            return jsonify({"success": True, "provider": "anthropic", "method": "api_key"})

        elif provider_name == "gemini":
            # Gemini via API key
            api_key = data.get("api_key", "").strip()
            if not api_key:
                return jsonify({"success": False, "error": "API key is required"})

            _client = genai.Client(api_key=api_key)
            _provider = "gemini"
            _auth_method = "api_key"
            _sso_profile = None
            _auth_error = None
            return jsonify({"success": True, "provider": "gemini", "method": "api_key"})

        elif provider_name == "nvidia":
            # NVIDIA NIM via API key (OpenAI-compatible)
            api_key = data.get("api_key", "").strip()
            if not api_key:
                return jsonify({"success": False, "error": "API key is required"})

            _client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
            _provider = "nvidia"
            _auth_method = "api_key"
            _sso_profile = None
            _auth_error = None
            return jsonify({"success": True, "provider": "nvidia", "method": "api_key"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/auth-sso", methods=["POST"])
def auth_sso():
    """Bedrock SSO authentication (local dev only)."""
    global _provider, _client, _auth_method, _auth_error, _sso_profile, _auth_region

    data = request.json
    profile = data.get("profile", "").strip()
    region = data.get("region", DEFAULT_REGION).strip()

    if not profile:
        return jsonify({"success": False, "error": "Profile name is required"})

    if not _test_sso_profile(profile, region):
        return jsonify({
            "success": False,
            "error": f"SSO profile '{profile}' has no valid credentials. Run: aws sso login --profile {profile}"
        })

    try:
        _client = anthropic.AnthropicBedrock(aws_profile=profile, aws_region=region)
        _provider = "bedrock"
        _auth_method = "sso"
        _sso_profile = profile
        _auth_region = region
        _auth_error = None
        return jsonify({"success": True, "provider": "bedrock", "method": "sso", "profile": profile})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/auth-disconnect", methods=["POST"])
def auth_disconnect():
    """Reset authentication state."""
    global _provider, _client, _auth_method, _auth_error, _sso_profile, _auth_region

    _provider = None
    _client = None
    _auth_method = None
    _sso_profile = None
    _auth_region = DEFAULT_REGION
    _auth_error = "No authentication configured. Connect a provider to start chatting."

    return jsonify({"success": True, "method": None, "error": _auth_error})


@app.route("/api/profiles")
def list_profiles():
    """List AWS SSO profiles from ~/.aws/config."""
    aws_config_path = os.path.expanduser("~/.aws/config")
    if not os.path.exists(aws_config_path):
        return jsonify({"profiles": []})

    try:
        import configparser
        config = configparser.ConfigParser()
        config.read(aws_config_path)
        profiles = []
        for section in config.sections():
            if section.startswith("profile "):
                profiles.append(section.replace("profile ", ""))
            elif section == "default":
                profiles.append("default")
        return jsonify({"profiles": sorted(profiles)})
    except Exception:
        return jsonify({"profiles": []})


# ─── Data Endpoints ──────────────────────────────────────────────────────────


@app.route("/api/providers")
def get_providers():
    """Get all available providers and their models."""
    return jsonify(PROVIDERS)


@app.route("/api/models")
def list_models():
    """Get models for the currently active provider."""
    if _provider and _provider in PROVIDERS:
        return jsonify({"models": PROVIDERS[_provider]["models"]})
    return jsonify({"models": []})


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "provider": _provider,
        "authenticated": _client is not None,
    })


# ─── Conversation History ────────────────────────────────────────────────────


@app.route("/api/conversations")
def list_conversations():
    """List all saved conversations."""
    convos = []
    for filepath in glob.glob(os.path.join(CONVERSATIONS_DIR, "*.json")):
        try:
            with open(filepath) as f:
                data = json.load(f)
                convos.append({
                    "id": data["id"],
                    "title": data.get("title", "Untitled"),
                    "createdAt": data.get("createdAt"),
                    "updatedAt": data.get("updatedAt"),
                    "messageCount": len(data.get("messages", [])),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    convos.sort(key=lambda c: c.get("updatedAt", 0), reverse=True)
    return jsonify({"conversations": convos})


@app.route("/api/conversations/<conv_id>")
def get_conversation(conv_id):
    """Get a single conversation by ID."""
    safe_id = _sanitize_conv_id(conv_id)
    if not safe_id:
        return jsonify({"error": "Invalid conversation ID"}), 400
    filepath = os.path.join(CONVERSATIONS_DIR, f"{safe_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"error": "Conversation not found"}), 404
    with open(filepath) as f:
        return jsonify(json.load(f))


@app.route("/api/conversations", methods=["POST"])
def save_conversation():
    """Save or update a conversation."""
    data = request.json
    conv_id = data.get("id") or f"conv_{uuid.uuid4().hex[:12]}"
    safe_id = _sanitize_conv_id(conv_id)
    if not safe_id:
        return jsonify({"error": "Invalid conversation ID"}), 400
    data["id"] = safe_id
    filepath = os.path.join(CONVERSATIONS_DIR, f"{safe_id}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"id": safe_id, "title": data.get("title", "Untitled")})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    """Delete a conversation."""
    safe_id = _sanitize_conv_id(conv_id)
    if not safe_id:
        return jsonify({"error": "Invalid conversation ID"}), 400
    filepath = os.path.join(CONVERSATIONS_DIR, f"{safe_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return jsonify({"success": True})


# ─── Chat (SSE Streaming) ───────────────────────────────────────────────────


@app.route("/api/chat", methods=["POST"])
def chat():
    """Stream chat responses via Server-Sent Events."""
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model")
    max_tokens = data.get("max_tokens", 1024)
    temperature = data.get("temperature", 1.0)

    # Validate auth
    if _client is None:
        return Response(
            f"data: {json.dumps({'error': _auth_error or 'No provider configured'})}\n\n",
            mimetype="text/event-stream",
        )

    # Get default model if not specified
    if not model and _provider:
        default_models = [m for m in PROVIDERS[_provider]["models"] if m.get("default")]
        model = default_models[0]["id"] if default_models else PROVIDERS[_provider]["models"][0]["id"]

    def generate():
        try:
            if _provider == "bedrock":
                # Bedrock streaming
                guardrail_id = data.get("guardrail_id", "")
                guardrail_version = data.get("guardrail_version", "DRAFT")
                guardrail_headers = get_guardrail_headers(guardrail_id, guardrail_version)

                with _client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                    extra_headers=guardrail_headers if guardrail_headers else None,
                ) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'text': text})}\n\n"

                    final = stream.get_final_message()
                    if final.stop_reason == "guardrail_intervened":
                        yield f"data: {json.dumps({'guardrail': True})}\n\n"

                yield "data: [DONE]\n\n"

            elif _provider == "anthropic":
                # Anthropic streaming (same API as Bedrock, different client)
                with _client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'text': text})}\n\n"

                yield "data: [DONE]\n\n"

            elif _provider == "gemini":
                # Gemini streaming (different SDK)
                # Convert message format from [{role: "user", content: "..."}] to Gemini format
                contents = []
                for msg in messages:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(genai.types.Content(
                        role=role,
                        parts=[genai.types.Part(text=msg["content"])]
                    ))

                response = _client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )

                for chunk in response:
                    if chunk.text:
                        yield f"data: {json.dumps({'text': chunk.text})}\n\n"

                yield "data: [DONE]\n\n"

            elif _provider == "nvidia":
                # NVIDIA NIM streaming with fallback
                models_to_try = [model] + [m for m in NVIDIA_FALLBACK_ORDER if m != model]
                last_error = None

                for attempt_model in models_to_try:
                    try:
                        if attempt_model != model:
                            yield f"data: {json.dumps({'info': f'Switching to {attempt_model}...'})}\n\n"

                        stream = _client.chat.completions.create(
                            model=attempt_model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=True,
                        )

                        for chunk in stream:
                            if not getattr(chunk, "choices", None):
                                continue
                            if chunk.choices[0].delta.content is not None:
                                yield f"data: {json.dumps({'text': chunk.choices[0].delta.content})}\n\n"

                        yield "data: [DONE]\n\n"
                        last_error = None
                        break
                    except Exception as fallback_err:
                        last_error = fallback_err
                        continue

                if last_error:
                    yield f"data: {json.dumps({'error': f'All models failed. Last error: {last_error}'})}\n\n"

            else:
                yield f"data: {json.dumps({'error': f'Unknown provider: {_provider}'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# ─── Root Route ──────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve frontend or API info."""
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    index_path = os.path.join(frontend_dir, "index.html")

    if os.path.exists(index_path):
        return send_from_directory(frontend_dir, "index.html")

    # API info when frontend not available
    return jsonify({
        "name": "CloudChat API",
        "version": "1.0.0",
        "providers": list(PROVIDERS.keys()),
        "authenticated": _client is not None,
        "current_provider": _provider,
    })


# ─── Startup ─────────────────────────────────────────────────────────────────


os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
_auto_configure_from_env()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    print(f"CloudChat Backend v1.0.0")
    print(f"Provider: {_provider or 'NONE'}")
    print(f"Auth method: {_auth_method or 'NONE'}")
    if _auth_error:
        print(f"Auth error: {_auth_error}")
    print(f"Conversations dir: {CONVERSATIONS_DIR}")
    print(f"Listening on http://0.0.0.0:{PORT}")

    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
