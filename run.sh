#!/bin/bash
# Run from anywhere: script goes to project dir first
cd "$(dirname "$0")"
echo "Working directory: $(pwd)"
.venv/bin/python main.py
