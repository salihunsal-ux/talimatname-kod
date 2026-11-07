# Talimatname API ve zamanlayıcı (ADR-0012 md.4: her şey compose ile kalkar).
#
# Tek imaj, iki süreç: API (uvicorn) ve zamanlayıcı aynı koddan koşar,
# ayrı kapsayıcı olurlar. Mimaride de ayrı süreçler (01-teknik-mimari
# `SCH`): web trafiği zamanlayıcıyı geciktirmesin, tersi de olmasın.
#
# Derleme bağlamı **depo kökü** (compose'da `context: .`).

FROM python:3.12-slim

# Yazı tipi **gerçekten gerekli**: kanıt damgası Türkçe harf çiziyor
# (ST-040) ve Pillow'un gömülü yazı tipinde ş, ğ, İ yok — "Kadıköy"
# kutu kutu çıkardı. CI'da da aynı paket kuruluyor.
# curl: kapsayıcı sağlık kontrolü için.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /uygulama

# Bağımlılıklar önce: kod değişince katman yeniden kurulmasın.
COPY api/pyproject.toml ./
COPY api/src ./src
RUN pip install --no-cache-dir .

# Göçler `src/` içinde (alembic.ini `script_location` oradan okur):
# aynı imaj hem göç hem servis koşsun, dağıtımda ikinci bir dosya
# kopyalamak gerekmesin.
COPY api/alembic.ini ./

# Kök olmayan kullanıcı: kapsayıcıdan kaçış bir basamak zorlaşsın.
RUN useradd --create-home --uid 10001 talimatname \
    && mkdir -p /veri/kanit \
    && chown -R talimatname:talimatname /uygulama /veri
USER talimatname

ENV EVIDENCE_DIR=/veri/kanit

EXPOSE 8000

# API'ye özel: `curl :8000`. Bu imajı farklı bir `command` ile koşan her
# servis (zamanlayıcı, göç, tohum) kendi `healthcheck`ini yazmalı, yoksa
# geçemeyeceği bir kontrolü miras alır ve hep kırmızı görünür.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# Varsayılan: API. Zamanlayıcı aynı imajı farklı komutla koşar
# (compose'da `command:` ile).
CMD ["uvicorn", "talimatname.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
