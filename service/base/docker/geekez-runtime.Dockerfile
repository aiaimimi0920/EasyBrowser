FROM node:20-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    npm_config_loglevel=warn

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    dbus-x11 \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnotify4 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libxss1 \
    libxtst6 \
    python3 \
    python3-pip \
    python-is-python3 \
    xauth \
    xvfb \
    xdg-utils \
 && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --break-system-packages --no-cache-dir playwright

WORKDIR /opt/geekez-browser

COPY upstreams/geekez-browser/package.json /opt/geekez-browser/package.json
COPY upstreams/geekez-browser/package-lock.json /opt/geekez-browser/package-lock.json
COPY upstreams/geekez-browser/setup.js /opt/geekez-browser/setup.js
COPY upstreams/geekez-browser/.puppeteerrc.cjs /opt/geekez-browser/.puppeteerrc.cjs
COPY upstreams/geekez-browser/electron.vite.config.mjs /opt/geekez-browser/electron.vite.config.mjs
COPY upstreams/geekez-browser/src /opt/geekez-browser/src
COPY upstreams/geekez-browser/resources /opt/geekez-browser/resources

RUN npm ci --ignore-scripts \
 && node node_modules/electron/install.js \
 && npm run build

COPY service/base/providers/geekez/runtime.py /opt/easybrowser/providers/geekez/runtime.py

WORKDIR /opt/easybrowser

CMD ["python", "/opt/easybrowser/providers/geekez/runtime.py", "--provider", "geekez", "--runtime-id", "manual"]
