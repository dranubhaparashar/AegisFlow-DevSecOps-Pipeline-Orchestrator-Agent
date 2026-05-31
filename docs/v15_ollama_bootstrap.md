# v15 Ollama Bootstrap

AegisFlow v15 adds a first-run local AI bootstrap flow for clients.

## Behavior

1. Check whether the `ollama` CLI exists locally.
2. If missing and automatic install is enabled, run the Linux/WSL installer.
3. Start the Ollama server if it is not responding.
4. Check local model cache using both the Ollama HTTP API and `ollama list`.
5. If the selected model is missing, run `ollama pull <model>`.
6. During long downloads, emit live dashboard updates every few seconds with elapsed time and latest output.
7. On later runs, skip download when the model already exists locally.

## Default model

`qwen2.5-coder:7b`

## Safety

If installation or download fails, deterministic DevSecOps reports still work. Only local AI recommendations are skipped.
