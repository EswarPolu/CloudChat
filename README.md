# CloudChat

A premium, self-hosted AI chatbot with multi-provider support. Connect your own API keys and start chatting with Claude, Gemini, or AWS Bedrock models. Built for developers who want full control over their AI infrastructure.

## Overview

CloudChat is an open-source, production-ready AI chatbot application with a premium Material Design 3 interface. Unlike typical chat bubble UIs, CloudChat delivers an editorial-grade experience optimized for both desktop and mobile. Deploy your own instance with GitHub Pages and Render.com, or run it locally for development.

## Features

- **Multi-Provider Support**: AWS Bedrock (Claude via SSO or API keys), Anthropic Claude (direct API), and Google Gemini
- **Real-Time Streaming**: Server-Sent Events (SSE) for responsive, token-by-token streaming
- **Premium UI**: Material Design 3 with editorial-grade typography and layouts
- **Conversation History**: Persistent localStorage-based history with conversation switching
- **Configurable Parameters**: Model selection, temperature, max tokens, and AWS Bedrock Guardrails
- **Mobile-Responsive**: Optimized for all screen sizes
- **Zero Framework Dependencies**: Vanilla JavaScript with Tailwind CSS CDN
- **Self-Hosted**: Deploy to your own infrastructure with full data control
- **Privacy-First**: No server-side storage, conversations stay in your browser

## Supported Providers

| Provider | Auth Required | Models Available |
|----------|--------------|-----------------|
| AWS Bedrock | Access Key + Secret Key (or SSO locally) | Claude Sonnet 4.6, Opus 4.6, Haiku 4.5, 3.7 Sonnet |
| Anthropic Claude | API Key (sk-ant-...) | Claude Sonnet 4.6, Opus 4.6, Haiku 4.5 |
| Google Gemini | API Key | Gemini 2.5 Flash, 2.5 Pro |

## Project Structure

```
cloudchat/
├── docs/
│   └── index.html              # Single-page web app (GitHub Pages)
├── backend/
│   ├── server.py               # Flask API server
│   └── gunicorn.conf.py        # Gunicorn config for production
├── render.yaml                 # Render.com deployment blueprint
├── requirements.txt            # Python dependencies
├── DESIGN.md                   # UI design system reference
├── LICENSE                     # MIT
└── .gitignore
```

## Quick Start (Local)

```bash
# Clone the repository
git clone https://github.com/EeswarSunny/cloudchat.git
cd cloudchat

# Install Python dependencies
pip install -r requirements.txt

# Start the Flask development server
cd backend && python server.py

# Open http://localhost:5000 in your browser
```

The application will start on port 5000. Enter your API keys in the UI to begin chatting.

## Deployment

### Frontend (GitHub Pages)

1. Fork or clone this repository to your GitHub account
2. Navigate to **Settings** > **Pages** in your repository
3. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
4. Click **Save**
5. Your frontend will be live at `https://<username>.github.io/cloudchat`

### Backend (Render.com)

1. Create a new **Web Service** on [Render](https://render.com)
2. Connect your GitHub repository
3. Render will auto-detect configuration from `render.yaml`
4. Set environment variables in the Render dashboard (see table below)
5. Update `API_BASE_URL` in `docs/index.html` to your Render backend URL

**Important**: Render's free tier sleeps after 15 minutes of inactivity. The first request after sleep may take up to 30 seconds to respond.

## Architecture

```
┌──────────────────┐       HTTPS        ┌──────────────────┐
│                  │ ────────────────── │                  │
│  GitHub Pages    │   fetch + SSE      │  Render.com      │
│  (Static HTML)   │ ←──────────────── │  (Flask + CORS)  │
│                  │                    │                  │
│  index.html      │                    │  server.py       │
│  localStorage    │                    │  gunicorn        │
└──────────────────┘                    └────────┬─────────┘
                                                 │
                                    ┌────────────┼────────────┐
                                    │            │            │
                              ┌─────┴─────┐ ┌───┴───┐ ┌─────┴─────┐
                              │ AWS       │ │Claude │ │ Google    │
                              │ Bedrock   │ │ API   │ │ Gemini    │
                              └───────────┘ └───────┘ └───────────┘
```

The frontend is a static single-page application hosted on GitHub Pages. The backend is a Flask API server deployed on Render.com that proxies requests to AI providers. Communication uses standard HTTP and Server-Sent Events for streaming responses.

## Environment Variables

These variables are configured in the Render dashboard for pre-configuring providers (optional):

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Pre-configure Anthropic Claude provider |
| `GEMINI_API_KEY` | No | Pre-configure Google Gemini provider |
| `AWS_ACCESS_KEY_ID` | No | Pre-configure AWS Bedrock provider |
| `AWS_SECRET_ACCESS_KEY` | No | Pre-configure AWS Bedrock provider |
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `FLASK_DEBUG` | No | Enable debug mode (default: false on Render) |
| `PORT` | Auto | Set automatically by Render |

Users can also enter API keys directly in the frontend UI if environment variables are not set.

## Tech Stack

**Frontend:**
- Vanilla JavaScript (ES6+)
- Tailwind CSS (CDN)
- Material Design 3 principles
- LocalStorage API

**Backend:**
- Python 3.8+
- Flask (web framework)
- Gunicorn (production WSGI server)
- Anthropic Python SDK
- Google GenerativeAI SDK
- Boto3 (AWS SDK)

**Deployment:**
- GitHub Pages (frontend static hosting)
- Render.com (backend container hosting)

## Privacy and Security

- **No Server-Side Storage**: All conversations are stored in your browser's localStorage. The backend is stateless.
- **Ephemeral Backend**: Render.com provides ephemeral storage. No data persists between deployments.
- **API Key Handling**: API keys are transmitted over HTTPS to the backend but never logged or stored.
- **Proxy-Only Backend**: The server only proxies requests to AI providers. It does not inspect or retain message content.
- **Self-Hosted**: You control both frontend and backend infrastructure.

## Configuration

### Model Selection

Choose from available models in the Settings panel:
- **AWS Bedrock**: Claude Sonnet 4.6, Opus 4.6, Haiku 4.5, 3.7 Sonnet
- **Anthropic Claude**: Claude Sonnet 4.6, Opus 4.6, Haiku 4.5
- **Google Gemini**: Gemini 2.5 Flash, 2.5 Pro

### Inference Parameters

Adjust response generation behavior:
- **Temperature**: Controls randomness (0.0 - 1.0, default 0.7)
- **Max Tokens**: Maximum response length (default 4096)

### AWS Bedrock Guardrails (Optional)

Enable content filtering and safety controls by entering a Guardrail ID and Version in Settings. Leave empty to disable.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Flask development server
cd backend
python server.py

# The server will start on http://localhost:5000
# Open the URL in your browser to access the UI
```

For frontend-only changes, you can edit `docs/index.html` and refresh your browser. For backend changes, restart the Flask server.

## Troubleshooting

### SSO Profile Not Working (Local Development)

If using AWS SSO locally:
1. Check that the profile exists: `aws configure list-profiles`
2. Refresh credentials: `aws sso login --profile <profile-name>`
3. Verify Bedrock access: `aws bedrock list-foundation-models --profile <profile-name>`

### Connection Errors

- Ensure your API keys have the necessary permissions
- Verify the AWS region supports Bedrock services (us-east-1, us-west-2)
- Check network connectivity to AI provider APIs
- Review browser console and backend logs for detailed error messages

### Render Backend Sleeping

The free tier on Render sleeps after 15 minutes of inactivity. The first request will wake the service but may take 30 seconds. Upgrade to a paid tier for always-on service.

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Author

**Eeswar Polu**
- GitHub: [@EeswarSunny](https://github.com/EeswarSunny)
- Email: polunandeeswar2002@gmail.com

## Acknowledgments

Built with:
- [Anthropic Claude](https://www.anthropic.com/claude)
- [Google Gemini](https://deepmind.google/technologies/gemini/)
- [AWS Bedrock](https://aws.amazon.com/bedrock/)
- [Flask](https://flask.palletsprojects.com/)
- [Tailwind CSS](https://tailwindcss.com/)

---

**CloudChat** - Self-hosted AI chatting, your way.
