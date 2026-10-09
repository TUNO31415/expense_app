#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Virtual environment not found. Creating one with uv..."
  uv venv
fi

uv run streamlit run app.py
