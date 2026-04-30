FROM python:3.11-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libu2f-udev \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
 && rm -rf /var/lib/apt/lists/*

COPY runtimes/chrome/requirements.txt /tmp/chrome-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/chrome-requirements.txt

COPY runtimes/chrome /opt/easybrowser/runtimes/chrome

ENV PYTHONPATH=/opt/easybrowser/runtimes/chrome/src \
    BROWSER_BINARY_PATH=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    HEADLESS=1 \
    USE_UNDETECTED_CHROMEDRIVER=0

WORKDIR /opt/easybrowser/runtimes/chrome

CMD ["python", "/opt/easybrowser/runtimes/chrome/src/browser_runtime/runtime_entry.py", "--provider", "chrome", "--runtime-id", "manual"]
