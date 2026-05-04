set dotenv-load := true

rss_dir := "services/rss"

# Dev-default ports for the python workers. Must match the INGEST_URL /
# SCRIPTGEN_URL defaults in workers/orchestrate/src/orchestrate/config.py.
ingest_port      := "8001"
scriptgen_port   := "8002"
orchestrate_port := "8003"
audiogen_port    := "8004"
api_port         := "8000"
web_port         := "5173"
llm_port         := "8010"

# list all recipes
default:
    @just --list --unsorted

# pytest shared python core
core-test:
    uv run --package piratepod-core pytest libs/py/piratepod_core

# pytest workers/ingest (set RUN_LIVE_TESTS=1 to also hit real r.jina.ai)
ingest-test:
    uv run --package ingest pytest workers/ingest

# pytest workers/orchestrate
orchestrate-test:
    uv run --package orchestrate pytest workers/orchestrate

# pytest workers/scriptgen
scriptgen-test:
    uv run --package scriptgen pytest workers/scriptgen

# pytest workers/audiogen
audiogen-test:
    uv run --package audiogen pytest workers/audiogen

# pytest all python workers with tests
workers-test: ingest-test scriptgen-test orchestrate-test audiogen-test

# pytest all python packages
python-test: core-test workers-test

# check for llama.cpp's llama-tts binary (installed via Homebrew, not uv)
audiogen-check:
    @command -v "${LLAMA_TTS_BIN:-llama-tts}" >/dev/null || { echo "missing llama-tts. Install it with: brew install llama.cpp"; exit 1; }

# check for llama.cpp's llama-server binary (installed via Homebrew, not uv)
scriptgen-llm-check:
    @command -v "${LLAMA_SERVER_BIN:-llama-server}" >/dev/null || { echo "missing llama-server. Install it with: brew install llama.cpp"; exit 1; }

# llama.cpp OpenAI-compatible chat server for scriptgen
scriptgen-llm-run: scriptgen-llm-check
    "${LLAMA_SERVER_BIN:-llama-server}" -hf "${SCRIPTGEN_LLM_MODEL:-ggml-org/gemma-4-E4B-it-GGUF}" --port {{llm_port}}

# uvicorn workers/ingest with auto-reload
ingest-run:
    uv run --package ingest uvicorn ingest.app:app --reload --port {{ingest_port}}

# uvicorn workers/scriptgen with auto-reload
scriptgen-run:
    uv run --package scriptgen uvicorn scriptgen.app:app --reload --port {{scriptgen_port}}

# uvicorn workers/audiogen with auto-reload
audiogen-run: audiogen-check
    uv run --package audiogen uvicorn audiogen.app:app --reload --port {{audiogen_port}}

# uvicorn workers/orchestrate with auto-reload (needs rss-run + scriptgen-llm-run + ingest-run + scriptgen-run + audiogen-run alongside)
orchestrate-run:
    ORCHESTRATE_SQLITE_PATH=services/api/data/piratepod-api.db uv run --package orchestrate uvicorn orchestrate.app:app --reload --port {{orchestrate_port}}

# start all local backend services; Ctrl+C stops everything it started
backend-run: scriptgen-llm-check audiogen-check
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .piratepod/logs .piratepod/pids
    echo "$$" > .piratepod/pids/backend-run.pid

    names=(rss scriptgen-llm ingest scriptgen audiogen orchestrate)
    cleanup_started=0

    kill_tree() {
        local pid="$1"
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
        kill "$pid" 2>/dev/null || true
    }

    kill_port() {
        local port="$1"
        for pid in $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true); do
            kill_tree "$pid"
        done
    }

    cleanup() {
        local exit_code="${1:-0}"
        set +e
        trap - EXIT INT TERM
        if [[ "$cleanup_started" -eq 1 ]]; then
            exit "$exit_code"
        fi
        cleanup_started=1
        echo
        echo "stopping backend..."
        for name in "${names[@]}"; do
            pid_file=".piratepod/pids/${name}.pid"
            if [[ -f "$pid_file" ]]; then
                pid="$(cat "$pid_file")"
                if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                    kill_tree "$pid"
                fi
                rm -f "$pid_file"
            fi
        done
        for port in {{orchestrate_port}} {{audiogen_port}} {{scriptgen_port}} {{ingest_port}} {{llm_port}} 8080; do
            kill_port "$port"
        done
        rm -f .piratepod/pids/backend-run.pid
        exit "$exit_code"
    }
    trap 'cleanup 130' INT TERM
    trap 'cleanup $?' EXIT

    start() {
        local name="$1"
        shift
        local log=".piratepod/logs/${name}.log"
        local pid_file=".piratepod/pids/${name}.pid"
        if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
            echo "$name already running with pid $(cat "$pid_file")"
            exit 1
        fi
        echo "starting $name -> $log"
        "$@" >"$log" 2>&1 &
        echo "$!" > "$pid_file"
    }

    wait_http() {
        local name="$1"
        local url="$2"
        local tries="${3:-180}"
        local pid_file=".piratepod/pids/${name}.pid"
        for _ in $(seq 1 "$tries"); do
            if curl -fsS "$url" >/dev/null 2>&1; then
                echo "$name ready"
                return 0
            fi
            if [[ -f "$pid_file" ]]; then
                pid="$(cat "$pid_file")"
                if ! kill -0 "$pid" 2>/dev/null; then
                    echo "$name exited early; log:"
                    tail -40 ".piratepod/logs/${name}.log" || true
                    exit 1
                fi
            fi
            sleep 1
        done
        echo "$name did not become ready at $url; log:"
        tail -40 ".piratepod/logs/${name}.log" || true
        exit 1
    }

    start rss bash -c 'cd services/rss && exec go run ./cmd/rss'
    wait_http rss "http://127.0.0.1:8080/healthz" 60

    start scriptgen-llm "${LLAMA_SERVER_BIN:-llama-server}" -hf "${SCRIPTGEN_LLM_MODEL:-ggml-org/gemma-4-E4B-it-GGUF}" --port {{llm_port}}
    wait_http scriptgen-llm "http://127.0.0.1:{{llm_port}}/v1/models" 600

    start ingest uv run --package ingest uvicorn ingest.app:app --host 127.0.0.1 --port {{ingest_port}}
    wait_http ingest "http://127.0.0.1:{{ingest_port}}/healthz" 60

    start scriptgen uv run --package scriptgen uvicorn scriptgen.app:app --host 127.0.0.1 --port {{scriptgen_port}}
    wait_http scriptgen "http://127.0.0.1:{{scriptgen_port}}/healthz" 60

    start audiogen uv run --package audiogen uvicorn audiogen.app:app --host 127.0.0.1 --port {{audiogen_port}}
    wait_http audiogen "http://127.0.0.1:{{audiogen_port}}/healthz" 60

    start orchestrate env INGEST_URL=http://127.0.0.1:{{ingest_port}} SCRIPTGEN_URL=http://127.0.0.1:{{scriptgen_port}} AUDIOGEN_URL=http://127.0.0.1:{{audiogen_port}} RSS_URL=http://127.0.0.1:8080 ORCHESTRATE_SQLITE_PATH=services/api/data/piratepod-api.db uv run --package orchestrate uvicorn orchestrate.app:app --host 127.0.0.1 --port {{orchestrate_port}}
    wait_http orchestrate "http://127.0.0.1:{{orchestrate_port}}/healthz" 60

    echo
    echo "backend ready"
    echo "orchestrate: http://127.0.0.1:{{orchestrate_port}}"
    echo "rss:         http://127.0.0.1:8080"
    echo "llm:         http://127.0.0.1:{{llm_port}}/v1"
    echo "smoke:       just pipeline-smoke https://example.com"
    echo "logs:        .piratepod/logs"
    echo
    echo "Press Ctrl+C to stop."
    while true; do sleep 3600; done

# start backend services, API, and web app; Ctrl+C stops everything it started
app-run-web: scriptgen-llm-check audiogen-check
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .piratepod/logs .piratepod/pids
    echo "$$" > .piratepod/pids/app-run-web.pid

    names=(web api app-backend)
    cleanup_started=0

    kill_tree() {
        local pid="$1"
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
        kill "$pid" 2>/dev/null || true
    }

    kill_port() {
        local port="$1"
        for pid in $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true); do
            kill_tree "$pid"
        done
    }

    cleanup() {
        local exit_code="${1:-0}"
        set +e
        trap - EXIT INT TERM
        if [[ "$cleanup_started" -eq 1 ]]; then
            exit "$exit_code"
        fi
        cleanup_started=1
        echo
        echo "stopping web app stack..."
        for name in "${names[@]}"; do
            pid_file=".piratepod/pids/${name}.pid"
            if [[ -f "$pid_file" ]]; then
                pid="$(cat "$pid_file")"
                if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                    kill_tree "$pid"
                fi
                rm -f "$pid_file"
            fi
        done
        for name in backend-run rss scriptgen-llm ingest scriptgen audiogen orchestrate; do
            pid_file=".piratepod/pids/${name}.pid"
            if [[ -f "$pid_file" ]]; then
                pid="$(cat "$pid_file")"
                if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                    kill_tree "$pid"
                fi
                rm -f "$pid_file"
            fi
        done
        for port in {{web_port}} {{api_port}} {{orchestrate_port}} {{audiogen_port}} {{scriptgen_port}} {{ingest_port}} {{llm_port}} 8080; do
            kill_port "$port"
        done
        rm -f .piratepod/pids/app-run-web.pid
        exit "$exit_code"
    }
    trap 'cleanup 130' INT TERM
    trap 'cleanup $?' EXIT

    start() {
        local name="$1"
        shift
        local log=".piratepod/logs/${name}.log"
        local pid_file=".piratepod/pids/${name}.pid"
        if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
            echo "$name already running with pid $(cat "$pid_file")"
            exit 1
        fi
        echo "starting $name -> $log"
        "$@" >"$log" 2>&1 &
        echo "$!" > "$pid_file"
    }

    wait_http() {
        local name="$1"
        local url="$2"
        local tries="${3:-180}"
        local pid_file=".piratepod/pids/${name}.pid"
        for _ in $(seq 1 "$tries"); do
            if curl -fsS "$url" >/dev/null 2>&1; then
                echo "$name ready"
                return 0
            fi
            if [[ -f "$pid_file" ]]; then
                pid="$(cat "$pid_file")"
                if ! kill -0 "$pid" 2>/dev/null; then
                    echo "$name exited early; log:"
                    tail -40 ".piratepod/logs/${name}.log" || true
                    exit 1
                fi
            fi
            sleep 1
        done
        echo "$name did not become ready at $url; log:"
        tail -40 ".piratepod/logs/${name}.log" || true
        exit 1
    }

    start app-backend just backend-run
    wait_http app-backend "http://127.0.0.1:{{orchestrate_port}}/healthz" 720

    start api bash -c 'workspace="$PWD"; cd services/api && exec env PIRATEPOD_WORKSPACE_DIR="$workspace" PIRATEPOD_API_PORT={{api_port}} PIRATEPOD_WEB_ORIGIN=http://127.0.0.1:{{web_port}},http://localhost:{{web_port}} ORCHESTRATE_URL=http://127.0.0.1:{{orchestrate_port}} INGEST_URL=http://127.0.0.1:{{ingest_port}} SCRIPTGEN_URL=http://127.0.0.1:{{scriptgen_port}} AUDIOGEN_URL=http://127.0.0.1:{{audiogen_port}} RSS_URL=http://127.0.0.1:8080 go run ./cmd/api'
    wait_http api "http://127.0.0.1:{{api_port}}/healthz" 60

    start web env VITE_API_URL=http://127.0.0.1:{{api_port}} npm --prefix clients/web run dev -- --host 127.0.0.1 --port {{web_port}}
    wait_http web "http://127.0.0.1:{{web_port}}" 60

    echo
    echo "web app stack ready"
    echo "web:         http://127.0.0.1:{{web_port}}"
    echo "api:         http://127.0.0.1:{{api_port}}"
    echo "orchestrate: http://127.0.0.1:{{orchestrate_port}}"
    echo "rss:         http://127.0.0.1:8080"
    echo "logs:        .piratepod/logs"
    echo
    echo "Press Ctrl+C to stop."
    while true; do sleep 3600; done

# stop backend services started by backend-run
backend-stop:
    #!/usr/bin/env bash
    set -euo pipefail
    names=(orchestrate audiogen scriptgen ingest scriptgen-llm rss)

    kill_tree() {
        local pid="$1"
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
        kill "$pid" 2>/dev/null || true
    }

    kill_port() {
        local port="$1"
        for pid in $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true); do
            echo "stopping listener on :$port ($pid)"
            kill_tree "$pid"
        done
    }

    for name in "${names[@]}"; do
        pid_file=".piratepod/pids/${name}.pid"
        if [[ ! -f "$pid_file" ]]; then
            echo "$name: no pid file"
            continue
        fi
        pid="$(cat "$pid_file")"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "stopping $name ($pid)"
            kill_tree "$pid"
        else
            echo "$name: not running"
        fi
        rm -f "$pid_file"
    done
    for port in {{orchestrate_port}} {{audiogen_port}} {{scriptgen_port}} {{ingest_port}} {{llm_port}} 8080; do
        kill_port "$port"
    done
    backend_pid_file=".piratepod/pids/backend-run.pid"
    if [[ -f "$backend_pid_file" ]]; then
        backend_pid="$(cat "$backend_pid_file")"
        if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
            echo "stopping backend-run ($backend_pid)"
            kill "$backend_pid" 2>/dev/null || true
        fi
        rm -f "$backend_pid_file"
    fi

# show local backend service health
backend-status:
    #!/usr/bin/env bash
    set -euo pipefail

    check() {
        local name="$1"
        local url="$2"
        if curl -fsS "$url" >/dev/null 2>&1; then
            printf '%-14s %s\n' "$name" "up"
        else
            printf '%-14s %s\n' "$name" "down"
        fi
    }

    check rss "http://127.0.0.1:8080/healthz"
    check scriptgen-llm "http://127.0.0.1:{{llm_port}}/v1/models"
    check ingest "http://127.0.0.1:{{ingest_port}}/healthz"
    check scriptgen "http://127.0.0.1:{{scriptgen_port}}/healthz"
    check audiogen "http://127.0.0.1:{{audiogen_port}}/healthz"
    check orchestrate "http://127.0.0.1:{{orchestrate_port}}/healthz"

# run the self-host web API locally
api-run:
    workspace="$PWD"; cd services/api && PIRATEPOD_WORKSPACE_DIR="$workspace" PIRATEPOD_API_PORT={{api_port}} go run ./cmd/api

# gofmt -s -w services/api
api-fmt:
    cd services/api && gofmt -s -w .

# go vet ./... for services/api
api-vet:
    cd services/api && go vet ./...

# go test ./... for services/api
api-test:
    cd services/api && go test ./...

# build the API service
api-build:
    cd services/api && go build -trimpath -ldflags="-s -w" -o bin/api ./cmd/api

# fmt + vet + test for services/api
api-check: api-fmt api-vet api-test

# run the web app locally
web-run:
    cd clients/web && npm run dev -- --host 127.0.0.1 --port {{web_port}}

# typecheck and build the web app
web-check:
    cd clients/web && npm run typecheck && npm run build

# quick e2e: POST one or more URLs through orchestrate, print the resulting script
pipeline-smoke urls="https://example.com":
    #!/usr/bin/env bash
    set -euo pipefail
    base="http://localhost:{{orchestrate_port}}"
    payload=$(URLS="{{urls}}" python3 -c 'import json, os, shlex; urls = shlex.split(os.environ["URLS"]); print(json.dumps({"urls": urls}))')
    resp=$(curl -sS -w $'\n%{http_code}' -X POST "$base/orchestrate/generate" \
        -H 'Content-Type: application/json' \
        -d "$payload")
    status="${resp##*$'\n'}"
    body="${resp%$'\n'*}"
    if [[ "$status" != 2* ]]; then
        printf '%s\n' "$body"
        exit 1
    fi
    printf '%s' "$body" | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"title: {d['title']}\");print('sources:');[print(f\"- {s['title']}: {s['url']}\") for s in d['sources']];print(f\"feed: {d['feed_url']}\");print(f\"episode audio: {d['episode_audio_url']}\");print(f\"local audio: {d['audio_path']} ({d['audio_format']})\");print();print('--- script ---');print(d['script'])"

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
