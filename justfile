set dotenv-load := true

rss_dir := "services/rss"

# Dev-default ports for the python workers. Must match the INGEST_URL /
# SCRIPTGEN_URL defaults in workers/orchestrate/src/orchestrate/config.py.
ingest_port      := "8001"
scriptgen_port   := "8002"
orchestrate_port := "8003"
audiogen_port    := "8004"

# list all recipes
default:
    @just --list --unsorted

# pytest workers/ingest (set RUN_LIVE_TESTS=1 to also hit real r.jina.ai)
ingest-test:
    uv run --package ingest pytest workers/ingest

# pytest workers/orchestrate
orchestrate-test:
    uv run --package orchestrate pytest workers/orchestrate

# pytest workers/audiogen
audiogen-test:
    uv run --package audiogen pytest workers/audiogen

# pytest all python workers with tests
workers-test: ingest-test orchestrate-test audiogen-test

# check for llama.cpp's llama-tts binary (installed via Homebrew, not uv)
audiogen-check:
    @command -v "${LLAMA_TTS_BIN:-llama-tts}" >/dev/null || { echo "missing llama-tts. Install it with: brew install llama.cpp"; exit 1; }

# uvicorn workers/ingest with auto-reload
ingest-run:
    uv run --package ingest uvicorn ingest.app:app --reload --port {{ingest_port}}

# uvicorn workers/scriptgen with auto-reload
scriptgen-run:
    uv run --package scriptgen uvicorn scriptgen.app:app --reload --port {{scriptgen_port}}

# uvicorn workers/audiogen with auto-reload
audiogen-run: audiogen-check
    uv run --package audiogen uvicorn audiogen.app:app --reload --port {{audiogen_port}}

# uvicorn workers/orchestrate with auto-reload (needs rss-run + ingest-run + scriptgen-run + audiogen-run alongside)
orchestrate-run:
    uv run --package orchestrate uvicorn orchestrate.app:app --reload --port {{orchestrate_port}}

# quick e2e: POST a URL through orchestrate, print the resulting script
pipeline-smoke url="https://example.com":
    #!/usr/bin/env bash
    set -euo pipefail
    base="http://localhost:{{orchestrate_port}}"
    resp=$(curl -sS -w $'\n%{http_code}' -X POST "$base/orchestrate/generate" \
        -H 'Content-Type: application/json' \
        -d "{\"url\":\"{{url}}\"}")
    status="${resp##*$'\n'}"
    body="${resp%$'\n'*}"
    if [[ "$status" != 2* ]]; then
        printf '%s\n' "$body"
        exit 1
    fi
    printf '%s' "$body" | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"title: {d['title']}\");print(f\"url: {d['url']}\");print(f\"feed: {d['feed_url']}\");print(f\"episode audio: {d['episode_audio_url']}\");print(f\"local audio: {d['audio_path']} ({d['audio_format']})\");print();print('--- script ---');print(d['script'])"

# run the rss service locally (uses ./services/rss/data for sqlite + media)
rss-run:
    cd {{rss_dir}} && go run ./cmd/rss

# build a production binary to services/rss/bin/rss
rss-build:
    cd {{rss_dir}} && go build -trimpath -ldflags="-s -w" -o bin/rss ./cmd/rss

# go test ./...
rss-test:
    cd {{rss_dir}} && go test ./...

# go vet ./...
rss-vet:
    cd {{rss_dir}} && go vet ./...

# gofmt -s -w .
rss-fmt:
    cd {{rss_dir}} && gofmt -s -w .

# go mod tidy
rss-tidy:
    cd {{rss_dir}} && go mod tidy

# fmt + vet + test (run before committing)
rss-check: rss-fmt rss-vet rss-test

# docker build -t piratepod/rss:dev .
rss-docker-build:
    cd {{rss_dir}} && docker build -t piratepod/rss:dev .

# docker run with ./data mounted; passes PIRATEPOD_BASE_URL + PIRATEPOD_MEDIA_URL through from .env
rss-docker-run: rss-docker-build
    docker run --rm -it -p 8080:8080 \
        -v "$(pwd)/{{rss_dir}}/data:/data" \
        -e PIRATEPOD_BASE_URL \
        -e PIRATEPOD_MEDIA_URL \
        piratepod/rss:dev

# expose http://localhost:8080 via a Cloudflare quick-tunnel
rss-tunnel:
    @echo "--> copy the printed URL into .env as PIRATEPOD_BASE_URL and restart rss-run"
    cloudflared tunnel --url http://localhost:8080

# wipe local sqlite + uploaded media
rss-reset:
    rm -rf {{rss_dir}}/data

# quick e2e against a running server: creates a podcast, prints feed URL + XML preview
rss-smoke:
    #!/usr/bin/env bash
    set -euo pipefail
    base="${PIRATEPOD_BASE_URL:-http://localhost:8080}"
    resp=$(curl -sfX POST "$base/podcasts" \
        -H 'Content-Type: application/json' \
        -d '{"title":"Smoke Test","language":"en"}')
    slug=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin)['slug'])")
    echo "feed: $base/feeds/$slug"
    echo
    curl -s "$base/feeds/$slug" | head -20
