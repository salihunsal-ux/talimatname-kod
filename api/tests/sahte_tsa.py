"""Testlerin zaman damgası sunucusu: **gerçek** RFC 3161 damgası üretir.

Ağa çıkmadan, ama uydurma baytlarla da değil: kendi ürettiği bir
sertifikayla CMS SignedData imzalıyor. Böylece doğrulayıcı gerçek bir
damga üstünde sınanıyor — "bayt geldi" demek, damganın çözülüp
imzasının tutduğunu göstermez.

Sertifika ve anahtar test içinde üretiliyor; depoda anahtar
tutmuyoruz (ADR-0003 ruhunda: gerçek sır yok).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from asn1crypto import cms, core, tsp, x509
from cryptography import x509 as cx509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

POLITIKA = "1.3.6.1.4.1.99999.1"


class _RetYaniti(core.Sequence):
    """Damgasız `TimeStampResp`: gerçek sunucular reddederken böyle yanıtlar."""

    _fields = [("status", tsp.PKIStatusInfo)]  # noqa: RUF012 — asn1crypto spesifikasyonu


class SahteTsa:
    """Tek bir anahtar/sertifika çiftiyle damga üreten sunucu taklidi."""

    def __init__(self, *, ad: str = "Deneme TSA") -> None:
        self._anahtar = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        konu = cx509.Name([cx509.NameAttribute(NameOID.COMMON_NAME, ad)])
        self._sertifika = (
            cx509.CertificateBuilder()
            .subject_name(konu)
            .issuer_name(konu)
            .public_key(self._anahtar.public_key())
            .serial_number(cx509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .add_extension(
                cx509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True
            )
            .sign(self._anahtar, hashes.SHA256())
        )
        self.sayac = 0

    # --- sunucu davranışı ---------------------------------------------

    def yanitla(self, istek_der: bytes, *, durum: str = "granted") -> bytes:
        """İsteği okuyup `TimeStampResp` döner — sunucunun yaptığı iş."""
        istek = tsp.TimeStampReq.load(istek_der)
        self.sayac += 1
        if durum != "granted":
            # Gerçek sunucular reddederken damga **göndermez**; yanıt
            # yalnızca durumdan ibarettir (RFC 3161 2.4.2).
            return bytes(
                _RetYaniti({"status": {"status": durum, "fail_info": {"bad_request"}}}).dump()
            )
        ozet = bytes(istek["message_imprint"]["hashed_message"].native)
        nonce = istek["nonce"].native if istek["nonce"] else None
        return self.yanit(ozet, nonce=nonce)

    def yanit(
        self,
        digest: bytes,
        *,
        nonce: int | None = None,
        gen_time: datetime | None = None,
    ) -> bytes:
        token = self.damga(digest, nonce=nonce, gen_time=gen_time)
        return bytes(
            tsp.TimeStampResp(
                {
                    "status": {"status": "granted"},
                    "time_stamp_token": cms.ContentInfo.load(token),
                }
            ).dump()
        )

    def damga(
        self,
        digest: bytes,
        *,
        nonce: int | None = None,
        gen_time: datetime | None = None,
        imzayi_boz: bool = False,
        ozeti_boz: bool = False,
        ess_boz: bool = False,
    ) -> bytes:
        """Tek bir `TimeStampToken` (CMS SignedData) üretir."""
        an = gen_time or datetime.now(UTC)
        bilgi = tsp.TSTInfo(
            {
                "version": "v1",
                "policy": POLITIKA,
                "message_imprint": {
                    "hash_algorithm": {"algorithm": "sha256"},
                    "hashed_message": digest,
                },
                "serial_number": 1,
                "gen_time": an,
                **({"nonce": nonce} if nonce is not None else {}),
            }
        )
        govde = bytes(bilgi.dump())
        sertifika_der = self._sertifika.public_bytes(serialization.Encoding.DER)
        # RFC 3161 2.4.1: damga, imzalayan sertifikayı **isimle** taşır
        # (ESS signing-certificate). OpenSSL bu alan yoksa damgayı
        # doğrulamıyor; gerçek sunucular da gönderiyor.
        ess = tsp.SigningCertificateV2(
            {
                "certs": [
                    {
                        "hash_algorithm": {"algorithm": "sha256"},
                        "cert_hash": hashlib.sha256(
                            sertifika_der if not ess_boz else b"baska sertifika"
                        ).digest(),
                    }
                ]
            }
        )
        imzali_alanlar = cms.CMSAttributes(
            [
                cms.CMSAttribute({"type": "content_type", "values": ["tst_info"]}),
                cms.CMSAttribute({"type": "signing_time", "values": [cms.Time({"utc_time": an})]}),
                cms.CMSAttribute({"type": "signing_certificate_v2", "values": [ess]}),
                cms.CMSAttribute(
                    {
                        "type": "message_digest",
                        "values": [hashlib.sha256(govde if not ozeti_boz else b"baska").digest()],
                    }
                ),
            ]
        )
        imza = self._anahtar.sign(bytes(imzali_alanlar.dump()), padding.PKCS1v15(), hashes.SHA256())
        if imzayi_boz:
            imza = bytes([imza[0] ^ 0xFF]) + imza[1:]

        sertifika = x509.Certificate.load(self._sertifika.public_bytes(serialization.Encoding.DER))
        imzali = cms.SignedData(
            {
                "version": "v3",
                "digest_algorithms": [{"algorithm": "sha256"}],
                "encap_content_info": {
                    "content_type": "tst_info",
                    "content": cms.ParsableOctetString(govde),
                },
                "certificates": [sertifika],
                "signer_infos": [
                    {
                        "version": "v1",
                        "sid": cms.SignerIdentifier(
                            {
                                "issuer_and_serial_number": {
                                    "issuer": sertifika.subject,
                                    "serial_number": sertifika.serial_number,
                                }
                            }
                        ),
                        "digest_algorithm": {"algorithm": "sha256"},
                        "signed_attrs": imzali_alanlar,
                        "signature_algorithm": {"algorithm": "rsassa_pkcs1v15"},
                        "signature": imza,
                    }
                ],
            }
        )
        return bytes(cms.ContentInfo({"content_type": "signed_data", "content": imzali}).dump())
