FROM python:3.11-slim

WORKDIR /app

# aiortc needs these to build/run its native audio & SRTP bits.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libavdevice-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    libsrtp2-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
