# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Bedrock application for AI/ML workloads.

## Project Structure

```
bedrock/
├── app.py           # Main application file
└── CLAUDE.md        # This file
```

## Development

### Running the Application

```bash
cd ~/Projects/active/bedrock/
python app.py
```

### Dependencies

If there's a requirements.txt file:
```bash
pip install -r requirements.txt
```

## AWS Bedrock

This project uses AWS Bedrock for AI/ML capabilities. Ensure AWS credentials are configured:
- AWS SSO profile: `eeswar` (default) or `sandbox`
- API keys stored in `~/.aws/bedrock-long-term-api-key.csv`

## Notes

- This is an experimental AWS Bedrock application
- Part of the active projects in `~/Projects/active/`
