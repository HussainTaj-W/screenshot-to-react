# Screenshot-to-React pipeline image.
#
# Bundles everything the pipeline needs:
#   - Python 3.11 + uv (the harness itself)
#   - Node.js 20 + npm (to scaffold/build the generated Vite app)
#   - Playwright Chromium + OS deps (screenshot capture)
#   - Netlify CLI is auto-installed at runtime by the preflight
#
# The image installs the package; the project directory is expected to be
# mounted at runtime (so inputs, outputs, .env, and skills come from the host).

# Playwright's Python image ships the browser + all OS dependencies.
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# --- Node.js 20 (for the generated Vite/React app + Netlify CLI) ---
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# --- uv (Python package/runtime manager) ---
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Install Python dependencies (cached layer) ---
# Copy only the lockfiles first so dependency installs are cached across
# source changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

# --- Install the project ---
COPY . .
RUN uv sync --frozen

# The Playwright base already has Chromium; ensure it's present for our venv.
RUN uv run playwright install chromium

# Run the pipeline. Pass flags/inputs via env (.env mounted) or `docker run` args.
ENTRYPOINT ["uv", "run", "screenshot-to-react"]
