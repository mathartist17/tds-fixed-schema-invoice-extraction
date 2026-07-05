## Notes

- To run the server
`uv run uvicorn main:app --reload`
- Build command in Render
`uv sync --frozen && uv cache prune --ci`
- Start command in Render
`uv run uvicorn main:app --host 0.0.0.0 --port $PORT --reload`
