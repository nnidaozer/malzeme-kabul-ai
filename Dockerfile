# Malzeme kabul uygulaması (Streamlit). Bağımlılıklar imaj kurulurken sabit
# kilitten (requirements-arayuz.lock) kurulur; çalışırken ağ yoktur
# (docker-compose.yml: uygulama yalnız dışa kapalı "ic" ağında).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALZEME_KABUL_DB=/veri/katalog.sqlite \
    MALZEME_KABUL_YUKLEME=/veri/yuklenen \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_CLIENT_TOOLBAR_MODE=minimal \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /uygulama
COPY requirements-arayuz.lock ./
RUN pip install -r requirements-arayuz.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

# Örnek veri ve ürün betikleri (gold ve ham belgeler imaja girmez; .dockerignore).
COPY scripts ./scripts
COPY data/ornek ./data/ornek
COPY data/cikti ./data/cikti
COPY data/bolunme.yaml ./data/bolunme.yaml
COPY docker ./docker

RUN useradd --create-home --uid 10001 uygulama && mkdir -p /veri && chown uygulama /veri
USER uygulama
VOLUME ["/veri"]
EXPOSE 8501

ENTRYPOINT ["sh", "/uygulama/docker/baslat.sh"]
