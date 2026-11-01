"""RFC 3161 zaman damgası istemcisi (ST-103; FR-1302).

`TimestampAuthority` portunun gerçek karşılığı. Burada üç iş var:
isteği kurmak, yanıtı çözmek ve damganın **bizim** özetimizi taşıdığını
doğrulamak.

Neden infra: HTTP ve ASN.1 bu katmanın işi (ADR-0014 md.2; servis
katmanında HTTP istemcisi yasak). Servis yalnızca "özeti tarihlet"
diyor.

**ASN.1'i elle yazmıyoruz.** İstek DER kodlaması ve özellikle damganın
(CMS SignedData) çözümlenmesi `asn1crypto` ile yapılıyor: damga
dışarıdan gelen veridir ve kendi ayrıştırıcımızı yazmak, güvenlik
işini en kırılgan yerde ev yapımı koda bırakmak olurdu.

**İki doğrulama ayrı.** `covers()` damganın içindeki `messageImprint`
ile beklenen özeti karşılaştırır — bu, damganın *hangi veriye* ait
olduğunu söyler. `signature_ok()` ise damganın imzasını otoritenin
kendi sertifikasıyla sınar. İkincisi **sertifika zincirini doğrulamaz**:
"bu damgayı imzalayan anahtar, damganın içindeki sertifikaya ait" der,
"bu sertifikaya güvenilir" demez. Güven kökü işletmecinin kararı ve
`openssl ts -verify -CAfile` ile yapılır; ürün bunu kendi bildiği gibi
sunmuyor çünkü güvenilecek kök listesi bizim seçimimiz değil.

**Sertifika damganın içinde adıyla da duruyor.** RFC 3161 2.4.1,
imzalı `signing-certificate` alanını şart koşuyor; doğrulayıcı bu
alanın elimizdeki sertifikayı gösterdiğini de sınıyor. Alanı atlayan
bir kontrol, imzası geçerli ama başka bir sertifika için üretilmiş
bir damgayı kabul ederdi (OpenSSL de bu yüzden reddediyor).

**Nonce her istekte yeni.** Otoritenin önceden hazırlanmış bir yanıtı
tekrar oynatmasına karşı; yanıttaki nonce istekle aynı değilse damga
kabul edilmiyor.
"""

from __future__ import annotations

import secrets
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import structlog
from asn1crypto import cms, core, tsp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import load_der_x509_certificate

from talimatname.services.anchors import Stamp, TimestampError

log = structlog.get_logger(__name__)

ISTEK_TURU = "application/timestamp-query"
YANIT_TURU = "application/timestamp-reply"

#: Yalnızca SHA-256. Daha zayıfını istemiyoruz; otorite desteklemiyorsa
#: damga alınmasın — zayıf özetli bir çıpa, çıpa olmayandan beter
#: (güvence veriyormuş gibi görünür).
HASH_OID = "sha256"
DIGEST_LENGTH = 32

#: PKIStatus (RFC 3161 2.4.2): 0 granted, 1 grantedWithMods; ötesi ret.
KABUL_EDILEN_DURUMLAR = frozenset({"granted", "granted_with_mods"})


class _Yanit(core.Sequence):  # type: ignore[misc]  # asn1crypto tipsiz
    """`TimeStampResp` — damga alanı **isteğe bağlı**.

    asn1crypto'nun kendi `tsp.TimeStampResp`i damgayı zorunlu sayıyor;
    oysa RFC 3161 2.4.2'de reddedilen yanıtta damga yoktur. Onun
    spesifikasyonuyla okursak gerçek bir ret, "yanıt çözülemedi" diye
    görünür ve işletmeci sebebi (ör. "politika desteklenmiyor") hiç
    öğrenemezdi. Alanların kendisi yine asn1crypto'nun: değiştirdiğimiz
    tek şey zorunluluk.
    """

    _fields = [  # noqa: RUF012 — asn1crypto spesifikasyonu
        ("status", tsp.PKIStatusInfo),
        ("time_stamp_token", cms.ContentInfo, {"optional": True}),
    ]


class Rfc3161Authority:
    """Tek bir zaman damgası sunucusuna konuşan istemci."""

    def __init__(
        self,
        url: str,
        *,
        policy_oid: str | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        self._url = url
        self._politika = policy_oid
        self._timeout = timeout_seconds

    # --- port ---------------------------------------------------------

    def stamp(self, digest: bytes) -> Stamp:
        if len(digest) != DIGEST_LENGTH:
            raise TimestampError(f"SHA-256 özeti {DIGEST_LENGTH} bayt olmalı")
        nonce = secrets.randbits(64)
        istek = self._istek(digest, nonce)
        ham = self._gonder(istek)
        return self._coz(ham, digest, nonce)

    def covers(self, token: bytes, digest: bytes) -> bool:
        """Damga bu özeti mi taşıyor?"""
        try:
            bilgi = _tst_info(token)
        except Exception:
            log.warning("tsa.damga_cozulemedi")
            return False
        return bytes(bilgi["message_imprint"]["hashed_message"].native) == digest

    # --- imza ----------------------------------------------------------

    def signature_ok(self, token: bytes) -> bool:
        """Damganın imzası içindeki sertifikayla tutuyor mu?

        **Zincir doğrulaması değildir** (bkz. modül başlığı): imzayı
        atanın, damgada duran sertifikanın sahibi olduğunu söyler.
        """
        try:
            return _imza_dogru(token)
        except Exception as hata:
            log.warning("tsa.imza_dogrulanamadi", sebep=type(hata).__name__)
            return False

    # --- iç ------------------------------------------------------------

    def _istek(self, digest: bytes, nonce: int) -> bytes:
        govde: dict[str, Any] = {
            "version": "v1",
            "message_imprint": {
                "hash_algorithm": {"algorithm": HASH_OID},
                "hashed_message": digest,
            },
            "nonce": nonce,
            # Sertifika istiyoruz: damga tek başına doğrulanabilsin.
            # İstemezsek imzayı sınamak için sertifikayı ayrıca
            # saklamamız gerekirdi ve damga taşınabilir olmazdı.
            "cert_req": True,
        }
        if self._politika:
            govde["req_policy"] = self._politika
        return bytes(tsp.TimeStampReq(govde).dump())

    def _gonder(self, istek: bytes) -> bytes:
        http = urllib.request.Request(
            self._url,
            data=istek,
            method="POST",
            headers={"Content-Type": ISTEK_TURU, "Accept": YANIT_TURU},
        )
        try:
            with urllib.request.urlopen(http, timeout=self._timeout) as yanit:
                return bytes(yanit.read())
        except urllib.error.HTTPError as hata:
            raise TimestampError(f"HTTP {hata.code}") from hata
        except Exception as hata:  # ağ, DNS, TLS
            raise TimestampError(f"{type(hata).__name__}") from hata

    def _coz(self, ham: bytes, digest: bytes, nonce: int) -> Stamp:
        try:
            yanit = _Yanit.load(ham)
            durum = yanit["status"]["status"].native
        except Exception as hata:
            raise TimestampError("Yanıt çözülemedi") from hata

        if durum not in KABUL_EDILEN_DURUMLAR:
            sebep = yanit["status"]["fail_info"].native if yanit["status"]["fail_info"] else "-"
            raise TimestampError(f"Sunucu reddetti: {durum} ({sebep})")

        damga_alani = yanit["time_stamp_token"]
        if isinstance(damga_alani, core.Void):
            raise TimestampError("Sunucu kabul etti ama damga göndermedi")
        token = bytes(damga_alani.dump())
        bilgi = _tst_info(token)

        if bytes(bilgi["message_imprint"]["hashed_message"].native) != digest:
            raise TimestampError("Damga başka bir özete ait")
        gelen_nonce = bilgi["nonce"].native if bilgi["nonce"] else None
        if gelen_nonce != nonce:
            # Tekrar oynatma: sunucunun hazır bir yanıtı iade etmesi.
            raise TimestampError("Nonce tutmuyor")

        return Stamp(
            token=token,
            stamped_at=_zaman(bilgi),
            tsa_name=_otorite_adi(bilgi),
            serial=str(bilgi["serial_number"].native),
        )


def _tst_info(token: bytes) -> Any:
    """Damganın içindeki TSTInfo. Bozuk damgada istisna atar."""
    icerik = cms.ContentInfo.load(token)
    imzali = icerik["content"]
    return imzali["encap_content_info"]["content"].parsed


def _zaman(bilgi: Any) -> datetime:
    an = bilgi["gen_time"].native
    if not isinstance(an, datetime):  # pragma: no cover - asn1crypto hep datetime verir
        raise TimestampError("Damga zamanı okunamadı")
    return an


def _otorite_adi(bilgi: Any) -> str | None:
    """Damgadaki TSA adı; alan isteğe bağlı olduğu için boş olabilir."""
    try:
        if bilgi["tsa"]:
            return str(bilgi["tsa"].native["value"])
    except Exception:  # pragma: no cover - biçim sunucudan sunucuya değişir
        return None
    return None


def _imza_dogru(token: bytes) -> bool:
    """SignerInfo imzasını damgadaki sertifikayla sınar.

    İmzalanan şey `signedAttrs`ın DER'i (RFC 5652 5.4) ve içindeki
    `messageDigest`, eContent'in özetine eşit olmalı — ikisini birden
    sınamazsak, geçerli imzalı ama **başka içerikli** bir damga kabul
    edilirdi.
    """
    icerik = cms.ContentInfo.load(token)
    imzali = icerik["content"]
    imzalayan = imzali["signer_infos"][0]

    sertifika = _sertifika(imzali, imzalayan)
    if sertifika is None:
        return False

    imzali_alanlar = imzalayan["signed_attrs"]
    if not imzali_alanlar:
        return False

    if not _ess_tutuyor(imzali_alanlar, sertifika):
        return False

    icerik_ozeti = _ozet_al(imzali_alanlar, "message_digest")
    # `.native` TSTInfo'yu sözlüğe çevirir; imzalanan şey ham
    # oktetlerdir (`.contents`).
    govde = bytes(imzali["encap_content_info"]["content"].contents)
    algoritma = imzalayan["digest_algorithm"]["algorithm"].native
    if icerik_ozeti != _hesapla(govde, algoritma):
        return False

    # RFC 5652 5.4: imza, signedAttrs'ın **SET OF** kodlaması üstünedir;
    # SignerInfo içinde alan IMPLICIT [0] ile etiketli durur. `untag()`
    # etiketi kaldırıp imzalanan baytları veriyor.
    imzalanan = bytes(imzali_alanlar.untag().dump())
    imza = bytes(imzalayan["signature"].native)
    acik_anahtar = load_der_x509_certificate(sertifika).public_key()
    kancali = _hash_nesnesi(algoritma)

    try:
        if isinstance(acik_anahtar, rsa.RSAPublicKey):
            acik_anahtar.verify(imza, imzalanan, padding.PKCS1v15(), kancali)
        elif isinstance(acik_anahtar, ec.EllipticCurvePublicKey):
            acik_anahtar.verify(imza, imzalanan, ec.ECDSA(kancali))
        else:  # pragma: no cover - başka anahtar türü beklenmiyor
            return False
    except InvalidSignature:
        return False
    return True


def _sertifika(imzali: Any, imzalayan: Any) -> bytes | None:
    """İmzalayanın sertifikası damganın içinde (cert_req=True sayesinde)."""
    sertifikalar = imzali["certificates"]
    if not sertifikalar:
        return None
    kimlik = imzalayan["sid"]
    for aday in sertifikalar:
        sert = aday.chosen
        if kimlik.name == "issuer_and_serial_number":
            ayni_seri = sert["tbs_certificate"]["serial_number"].native == (
                kimlik.chosen["serial_number"].native
            )
            if ayni_seri:
                return bytes(sert.dump())
        else:
            return bytes(sert.dump())
    return None


def _ess_tutuyor(imzali_alanlar: Any, sertifika_der: bytes) -> bool:
    """Damga, imzalayan sertifikayı adıyla taşıyor mu? (RFC 3161 2.4.1)

    `signing-certificate(-v2)` imzalı alanı, imzanın hangi sertifikaya
    ait olduğunu **imzanın içine** yazar. Alan yoksa damga eksik
    (OpenSSL de reddeder); varsa ve içindeki özet elimizdeki
    sertifikayı göstermiyorsa damga başka bir sertifika için
    üretilmiş demektir.
    """
    for alan in imzali_alanlar:
        tur = alan["type"].native
        if tur not in ("signing_certificate", "signing_certificate_v2"):
            continue
        for kayit in alan["values"][0]["certs"]:
            beklenen = bytes(kayit["cert_hash"].native)
            algoritma = (
                kayit["hash_algorithm"]["algorithm"].native
                if tur == "signing_certificate_v2"
                else "sha1"
            )
            if _hesapla(sertifika_der, algoritma) == beklenen:
                return True
        return False
    return False


def _ozet_al(imzali_alanlar: Any, ad: str) -> bytes | None:
    for alan in imzali_alanlar:
        if alan["type"].native == ad:
            return bytes(alan["values"][0].native)
    return None


def _hesapla(veri: bytes, algoritma: str) -> bytes:
    sayaç = hashes.Hash(_hash_nesnesi(algoritma))
    sayaç.update(veri)
    return sayaç.finalize()


def _hash_nesnesi(algoritma: str) -> hashes.HashAlgorithm:
    secenek = {
        "sha1": hashes.SHA1(),  # yalnızca eski ESS alanı için (imza değil)
        "sha256": hashes.SHA256(),
        "sha384": hashes.SHA384(),
        "sha512": hashes.SHA512(),
    }.get(algoritma)
    if secenek is None:
        raise TimestampError(f"Desteklenmeyen özet: {algoritma}")
    return secenek


__all__ = ["Rfc3161Authority"]
