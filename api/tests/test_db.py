"""PostgreSQL adaptörleri ve kiracı yalıtımı (TC-011, ADR-0014 md.4).

Bu testler **çalışan bir veritabanı ister**: `DATABASE_URL` yoksa sebebi
yazılarak atlanır (sessiz atlama yok). Kendi kiracısını açar, işini
yapar, sonra siler — paylaşılan geliştirme veritabanını kirletmez.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from talimatname.domain.answers import Answer
from talimatname.domain.audit import GENESIS, AuditEvent, SequenceTaken, sealed
from talimatname.domain.chain_anchor import ChainAnchor
from talimatname.domain.evidence import Evidence
from talimatname.domain.exports import ExportJob
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch, uniform_hours
from talimatname.domain.plans import Plan, Run
from talimatname.domain.templates import Item, Section, Template, TemplateVersion
from talimatname.domain.users import RoleAssignment, User
from talimatname.domain.window import WindowRule
from talimatname.settings import get_settings

pytestmark = pytest.mark.db

if get_settings().database_url is None:  # pragma: no cover - ortam bağımlı
    pytest.skip(
        "DATABASE_URL tanımlı değil: veritabanı testleri atlandı "
        "(bkz. infra/veritabani-kurulum.md)",
        allow_module_level=True,
    )

from talimatname.infra.db.adapters import (  # noqa: E402
    SqlAnchorRepository,
    SqlAnswerRepository,
    SqlAuditRepository,
    SqlEvidenceRepository,
    SqlExportJobRepository,
    SqlNotificationRepository,
    SqlOrganizationRepository,
    SqlPlanRepository,
    SqlTemplateRepository,
    SqlUserRepository,
)
from talimatname.infra.db.session import (  # noqa: E402
    APP_ROLE,
    create_db_engine,
    tenant_session,
)
from talimatname.seed import DEV_TENANT  # noqa: E402
from talimatname.services.audit import AuditService  # noqa: E402

AD_ALANI = UUID("9f2b7c41-5d6e-4a83-9c17-2e4b8a6d3f55")
A_KIRACI = uuid5(AD_ALANI, "test:kiraci-a")
B_KIRACI = uuid5(AD_ALANI, "test:kiraci-b")


def _kiraci_ac(kiraci: UUID, ad: str) -> None:
    motor = create_db_engine(as_owner=True)
    with motor.begin() as b:
        b.execute(
            text(
                "INSERT INTO tenant (id, name, default_timezone, created_at) "
                "VALUES (:id, :ad, 'Europe/Istanbul', :an) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": kiraci, "ad": ad, "an": datetime.now(UTC)},
        )


def _kiraci_sil(*kiracilar: UUID) -> None:
    motor = create_db_engine(as_owner=True)
    with motor.begin() as b:
        for kiraci in kiracilar:
            b.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": kiraci})


@pytest.fixture
def iki_kiraci() -> object:
    """İki test kiracısı: **önce de** silinir.

    Yalnızca sonda silmek yetmiyordu: bir test ortasında düşerse
    kiracı satırlarıyla kalıyor ve sıradaki testi kirletiyor. Baştaki
    silme, koşunun önceki koşudan bağımsız başlamasını garanti ediyor.
    """
    _kiraci_sil(A_KIRACI, B_KIRACI)
    _kiraci_ac(A_KIRACI, "Test A")
    _kiraci_ac(B_KIRACI, "Test B")
    yield
    _kiraci_sil(A_KIRACI, B_KIRACI)


def _sube(kod: str) -> Branch:
    return Branch(
        id=uuid4(),
        code=kod,
        name=f"{kod} şubesi",
        timezone="Europe/Istanbul",
        business_hours=uniform_hours(time(8, 0), time(23, 0)),
    ).validated()


def test_tc011_kiraci_yalitimi(iki_kiraci: object) -> None:
    """Bir kiracının deposu diğerinin satırını **göremez**.

    Yalıtım uygulama katmanında değil, veritabanında: adaptör hiçbir
    `WHERE tenant_id = ...` yazmıyor, kesen şey RLS politikası.
    """
    a = SqlOrganizationRepository(A_KIRACI)
    b = SqlOrganizationRepository(B_KIRACI)

    a.save_branch(_sube("AAA"))
    b.save_branch(_sube("BBB"))

    a_kodlari = {s.code for s in a.branches()}
    b_kodlari = {s.code for s in b.branches()}

    # İddia "A'da tam bir satır var" değil, **"A, B'nin satırını
    # görmüyor"**. Tam eşitlik yazmak testi ortamdaki artık satırlara
    # bağlıyordu ve ara sıra kırmızı yanıyordu; sızıntı olsaydı
    # aşağıdaki iki satır yine yakalardı.
    assert "AAA" in a_kodlari
    assert "BBB" not in a_kodlari
    assert "BBB" in b_kodlari
    assert "AAA" not in b_kodlari
    assert a.branch_by_code("BBB") is None
    assert b.branch_by_code("AAA") is None


def test_tc011_baska_kiracinin_kaydina_kimlikle_de_erisilemez(iki_kiraci: object) -> None:
    """Kimliği bilmek yetmez: satır başka kiracınınsa yok sayılır."""
    a = SqlOrganizationRepository(A_KIRACI)
    b = SqlOrganizationRepository(B_KIRACI)
    sube = _sube("AAA")
    a.save_branch(sube)

    assert a.branch(sube.id) is not None
    assert b.branch(sube.id) is None


def test_rls_kiraci_ayari_yoksa_hicbir_satir_gelmez() -> None:
    """Fail-closed: `app.tenant_id` ayarlanmazsa sorgu boş döner."""
    motor = create_db_engine()  # uygulama rolü, SET ROLE bağlantıda
    with motor.connect() as b:
        kullanici = b.execute(text("SELECT current_user")).scalar_one()
        bypass = b.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
        sayi = b.execute(text("SELECT count(*) FROM branch")).scalar_one()

    assert kullanici == APP_ROLE
    assert bypass is False  # uygulama rolü RLS'i atlayamaz
    assert sayi == 0


def test_tohum_verisi_okunabiliyor() -> None:
    """Geliştirme kiracısında tohum duruyor (seed idempotent)."""
    org = SqlOrganizationRepository(DEV_TENANT)
    kodlar = {s.code for s in org.branches()}

    assert {"KDK", "BSK", "ALS"} <= kodlar


def test_sablon_surumu_bolum_ve_maddeleriyle_donuyor() -> None:
    """Eşleme kaybı olmamalı: bölüm, madde, seçenek ve aralık geri gelmeli."""
    sablonlar = SqlTemplateRepository(DEV_TENANT)
    kapanis = next(t for t in sablonlar.templates() if t.name.startswith("Kapanış"))
    surum = next(s for s in sablonlar.versions(kapanis.id) if s.status == "published")

    assert len(surum.sections) == 2
    assert surum.scored_item_count == 7
    sicaklik = next(i for i in surum.items if i.type == "temperature")
    assert (sicaklik.min_value, sicaklik.max_value, sicaklik.unit) == (0.0, 4.0, "°C")
    secimli = next(i for i in surum.items if i.type == "choice")
    assert [o.label for o in secimli.options] == ["Evet", "Hayır", "Uygun değil"]
    assert surum.publish_issues() == []


def test_sube_kaydi_gidip_geliyor(iki_kiraci: object) -> None:
    """Çalışma saatleri JSON'a yazılıp alan nesnesine geri dönüyor."""
    a = SqlOrganizationRepository(A_KIRACI)
    sube = _sube("RND")
    a.save_branch(sube)

    geri = a.branch_by_code("RND")

    assert geri is not None
    assert geri.name == sube.name
    assert geri.open_days == 7
    assert geri.business_hours[0] is not None
    assert geri.business_hours[0].close_time == time(23, 0)


def _alici(kiraci: UUID) -> User:
    """Bildirimin alıcısı gerçek bir kullanıcı olmalı: tabloda yabancı anahtar var.

    Kuyrukta silinmiş kullanıcıya ait kayıt kalmasın diye konuldu;
    adlar uydurma (ADR-0003).
    """
    kisi = User(
        id=uuid4(),
        full_name="Test Alıcı",
        phone=f"+90532{uuid4().int % 10_000_000:07d}",
        assignments=(RoleAssignment("admin"),),
    ).validated()
    SqlUserRepository(kiraci).save_user(kisi)
    return kisi


def _bildirim(baslik: str, alici: User) -> Notification:
    an = datetime.now(UTC)
    return Notification(
        id=uuid4(),
        kind="run_opened",
        channel="push",
        user_id=alici.id,
        title=baslik,
        body="gövde",
        send_at=an,
        created_at=an,
    ).validated()


def test_bildirim_kuyrugu_da_kiracilar_arasinda_yalitik(iki_kiraci: object) -> None:
    """Yeni tablo da RLS altında: 0002 göçü yetkiyi ve politikayı kurdu.

    Bildirim kuyruğu kim neyi görecek bilgisini taşıyor; sızması
    yalnızca gürültü değil, başka zincirin operasyonunu göstermek olur.
    """
    a = SqlNotificationRepository(A_KIRACI)
    b = SqlNotificationRepository(B_KIRACI)

    kayit = _bildirim("A kiracısının hatırlatması", _alici(A_KIRACI))
    a.save_notification(kayit)

    assert [n.title for n in a.notifications()] == ["A kiracısının hatırlatması"]
    assert b.notifications() == []
    assert b.notification(kayit.id) is None


def test_bildirim_teslimat_izi_gidip_geliyor(iki_kiraci: object) -> None:
    """Hata kodu ve deneme sayısı kalıcı: destek bunlara bakacak (FR-1005)."""
    depo = SqlNotificationRepository(A_KIRACI)
    kayit = _bildirim("Gönderilemeyen", _alici(A_KIRACI))
    depo.save_notification(kayit)

    an = datetime.now(UTC)
    depo.save_notification(kayit.failed(an, "surucu-yok", "push sürücüsü bağlı değil"))

    geri = depo.notification(kayit.id)
    assert geri is not None
    assert (geri.status, geri.error_code, geri.attempts) == ("failed", "surucu-yok", 1)


def _calistirma(kiraci: UUID) -> Run:
    """Kanıt bir çalıştırmaya bağlı (yabancı anahtar): zinciri gerçekten kuruyoruz.

    Şube → şablon → sürüm → plan → çalıştırma. Uydurma bir UUID ile
    kestirme yapmak, şemanın bütünlük kuralını test dışında bırakırdı.
    """
    org = SqlOrganizationRepository(kiraci)
    sube = _sube(f"K{uuid4().hex[:2].upper()}")
    org.save_branch(sube)

    sablonlar = SqlTemplateRepository(kiraci)
    sablon = Template(id=uuid4(), name="Kanıt denemesi")
    sablonlar.save_template(sablon)
    madde = Item(id=uuid4(), order=1, type="confirm", title="Kapı kilidi")
    surum = TemplateVersion(
        id=uuid4(),
        template_id=sablon.id,
        version_no=1,
        status="published",
        sections=(Section(id=uuid4(), order=1, title="Açılış", items=(madde,)),),
    ).validated()
    sablonlar.save_version(surum)

    planlar = SqlPlanRepository(kiraci)
    an = datetime.now(UTC)
    plan = Plan(
        id=uuid4(),
        name="Kanıt planı",
        template_version_id=surum.id,
        branch_ids=(sube.id,),
        rule=WindowRule(
            recurrence="daily",
            starts_on=an.date(),
            duration_minutes=60,
            start_time=time(9, 0),
        ),
    ).validated()
    planlar.save_plan(plan)

    run = Run(
        id=uuid4(),
        plan_id=plan.id,
        template_version_id=surum.id,
        branch_id=sube.id,
        business_day=an.date(),
        window_start=an,
        window_end=an + timedelta(hours=1),
        tolerance_end=an + timedelta(hours=2),
    )
    planlar.save_run(run)
    return run


def _kanit(run: Run, ozet: str) -> Evidence:
    return Evidence(
        id=uuid4(),
        run_id=run.id,
        answer_id=uuid4(),
        item_id=uuid4(),
        branch_id=run.branch_id,
        user_id=None,
        sha256=ozet,
        content_type="image/jpeg",
        size_bytes=1234,
        storage_key=f"evidence/{run.id}/{uuid4()}.jpg",
        created_at=datetime.now(UTC),
    ).validated()


def test_yapilamadi_sebebi_gidip_geliyor(iki_kiraci: object) -> None:
    """Sebep **kod** olarak saklanıyor (BR-09, FR-0805).

    Etiket ("Malzeme yok") değişebilir; kod değişmez. Sebep dağılımı
    raporu dönemler arasında karşılaştırılabilir kalsın diye.
    """
    run = _calistirma(A_KIRACI)
    sablonlar = SqlTemplateRepository(A_KIRACI)
    surum = sablonlar.version(run.template_version_id)
    assert surum is not None
    madde = surum.items[0]

    depo = SqlAnswerRepository(A_KIRACI)
    cevap = Answer(
        id=uuid4(),
        run_id=run.id,
        item_id=madde.id,
        state="not_done",
        note="Tedarik gelmedi",
        answered_at=datetime.now(UTC),
        not_done_reason="no_material",
    ).validated()
    depo.save_answer(cevap)

    geri = depo.answer(cevap.id)
    assert geri is not None
    assert geri.not_done_reason == "no_material"
    assert geri.state == "not_done"


def test_fr0614_ayni_ozet_veritabaninda_da_engellenir(iki_kiraci: object) -> None:
    """Tekillik şemaya yazılı: servis denetimi yarışta kaçabilir, indeks kaçmaz.

    Ürünün tek iddiası "kanıt gerçek"; onu yalnızca uygulama koduna
    bağlamak, iki eşzamanlı yüklemede iddiayı kaybetmek demek.
    """
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    ozet = "a" * 64
    depo.save_evidence(_kanit(run, ozet))

    with pytest.raises(IntegrityError):
        depo.save_evidence(_kanit(run, ozet))


def test_ayni_ozet_baska_kiracida_serbest(iki_kiraci: object) -> None:
    """Tekillik **hesap içinde** (FR-0614): başka zincirin fotoğrafı bizi bağlamaz."""
    ozet = "b" * 64
    SqlEvidenceRepository(A_KIRACI).save_evidence(_kanit(_calistirma(A_KIRACI), ozet))
    SqlEvidenceRepository(B_KIRACI).save_evidence(_kanit(_calistirma(B_KIRACI), ozet))

    assert SqlEvidenceRepository(A_KIRACI).evidence_by_digest(ozet) is not None
    assert SqlEvidenceRepository(B_KIRACI).evidence_by_digest(ozet) is not None


def test_kanit_silinebiliyor(iki_kiraci: object) -> None:
    """Doğrulanmamış yükleme silinir; tekillik kilidi onunla birlikte kalkar."""
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    ozet = "c" * 64
    kanit = _kanit(run, ozet)
    depo.save_evidence(kanit)

    depo.delete_evidence(kanit.id)

    assert depo.evidence_by_digest(ozet) is None
    depo.save_evidence(_kanit(run, ozet))  # aynı kare yeniden yüklenebilir


def test_damga_anahtarlari_gidip_geliyor(iki_kiraci: object) -> None:
    """Damgalı kopya ve küçük resmin anahtarları kalıcı (ST-040, FR-0606).

    Ham dosyanın anahtarı ve özeti **değişmiyor**: damga bir kopyadır,
    kanıtın kendisi yerinde durur (BR-12).
    """
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    kanit = _kanit(run, "d" * 64)
    depo.save_evidence(kanit)

    an = datetime.now(UTC)
    depo.save_evidence(
        kanit.stored(an).stamped(
            an,
            stamped_key=f"evidence/{run.id}/{kanit.id}.stamp.jpg",
            thumbnail_key=f"evidence/{run.id}/{kanit.id}.thumb.jpg",
        )
    )

    geri = depo.evidence(kanit.id)
    assert geri is not None
    assert geri.status == "stamped"
    assert geri.stamped_at is not None
    assert geri.stamped_key == f"evidence/{run.id}/{kanit.id}.stamp.jpg"
    assert geri.thumbnail_key == f"evidence/{run.id}/{kanit.id}.thumb.jpg"
    assert geri.storage_key == kanit.storage_key
    assert geri.sha256 == kanit.sha256


def test_damga_bekleyenler_veritabaninda_suzuluyor(iki_kiraci: object) -> None:
    """İşçi tüm kanıt tablosunu okumaz: süzgeç sorguda (ST-040).

    Kanıt en hızlı büyüyen tablo; her turda tam tarama yapmak işçiyi
    birkaç ay sonra kullanılamaz hale getirirdi.
    """
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    an = datetime.now(UTC)
    bekleyen = _kanit(run, "e" * 64).stored(an)
    depo.save_evidence(bekleyen)
    depo.save_evidence(_kanit(run, "f" * 64))  # pending: işçinin işi değil
    depo.save_evidence(
        _kanit(run, "0" * 64)
        .stored(an)
        .stamped(an, stamped_key="a.jpg", thumbnail_key="b.jpg")  # bitmiş
    )

    gelen = depo.stored_evidences(10)

    assert [k.id for k in gelen] == [bekleyen.id]


def test_supurulecek_bekleyenler_veritabaninda_suzuluyor(iki_kiraci: object) -> None:
    """Süpürücü de tam tarama yapmaz: yaş süzgeci sorguda.

    `dataclasses.replace` ile eski tarihli bir kayıt bırakıyoruz:
    bekleyen kayıt baytı gelmediği için `created_at` dışında bir
    yaşlanma işareti taşımıyor.
    """
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    an = datetime.now(UTC)
    eski = replace(_kanit(run, "1" * 64), created_at=an - timedelta(days=10))
    depo.save_evidence(eski)
    depo.save_evidence(_kanit(run, "2" * 64))  # taze: dokunulmaz
    depo.save_evidence(_kanit(run, "3" * 64).stored(an))  # baytı gelmiş

    gelen = depo.pending_evidences(an - timedelta(days=7), 10)

    assert [k.id for k in gelen] == [eski.id]


# --- olay günlüğü (FR-1301; TC-100) -----------------------------------


def _olay(sira: int, prev: str, **ek: object) -> AuditEvent:
    temel = AuditEvent(
        id=uuid4(),
        sequence=sira,
        event_type="oturum.acildi",
        at=datetime.now(UTC),
        object_type="kullanici",
        prev_hash=prev,
    )
    return sealed(replace(temel, **ek))  # type: ignore[arg-type]


def test_olay_gunlugu_gidip_geliyor(iki_kiraci: object) -> None:
    depo = SqlAuditRepository(A_KIRACI)
    bir = _olay(1, GENESIS, ip="198.51.100.7", device="iPhone", after={"roller": "admin"})
    depo.append(bir)
    iki = _olay(2, bir.hash, event_type="kanit.alindi", object_type="kanit")
    depo.append(iki)

    gelen = depo.events(limit=10)

    assert [o.sequence for o in gelen] == [1, 2]
    assert gelen[0].ip == "198.51.100.7"
    assert gelen[0].after == {"roller": "admin"}
    assert depo.head() is not None
    assert depo.head().hash == iki.hash  # type: ignore[union-attr]
    assert AuditService(depo).verify().intact


def test_ayni_sira_veritabaninda_da_engelleniyor(iki_kiraci: object) -> None:
    """Zincir çatallanamaz: (kiracı, sıra) tekil.

    İki istek aynı anda yazarsa ikincisi burada durur ve servis
    yeni başı okuyup tekrar dener.
    """
    depo = SqlAuditRepository(A_KIRACI)
    depo.append(_olay(1, GENESIS))

    with pytest.raises(SequenceTaken):
        depo.append(_olay(1, GENESIS))


def test_tc100_uygulama_rolu_gunlugu_degistiremez(iki_kiraci: object) -> None:
    """TC-100: veritabanı rolünün UPDATE/DELETE yetkisi **yok**.

    Kodda silme yöntemi bulunmaması niyeti anlatır; yetkinin
    olmaması güvenceyi. Uygulamada bir açık bulan da günlüğü
    düzeltemesin diye ikisi birden var.
    """
    SqlAuditRepository(A_KIRACI).append(_olay(1, GENESIS))

    with tenant_session(A_KIRACI) as o, pytest.raises(ProgrammingError, match="permission denied"):
        o.execute(text("UPDATE audit_event SET hash = 'x'"))
    with tenant_session(A_KIRACI) as o, pytest.raises(ProgrammingError, match="permission denied"):
        o.execute(text("DELETE FROM audit_event"))


def test_cipa_gidip_geliyor_ve_degistirilemiyor(iki_kiraci: object) -> None:
    """Zincir kökünün dış damgası (FR-1302).

    Damga birkaç kilobayt ikili veri: gidip geldiğini bayt bayt
    sınıyoruz. Tablo günlükle aynı kurala tabi — bir çıpayı sonradan
    düzeltebilmek, çıpanın anlamını ortadan kaldırırdı.
    """
    depo = SqlAnchorRepository(A_KIRACI)
    an = datetime.now(UTC)
    damga = bytes(range(256)) * 8
    cipa = ChainAnchor(
        id=uuid4(),
        created_at=an,
        sequence=42,
        chain_hash="b" * 64,
        state="ok",
        token=damga,
        stamped_at=an,
        tsa_name="Deneme TSA",
        serial="7",
    )
    depo.save_anchor(cipa)

    geri = depo.anchors(limit=5)
    assert [c.id for c in geri] == [cipa.id]
    assert geri[0].token == damga
    assert (geri[0].sequence, geri[0].tsa_name, geri[0].serial) == (42, "Deneme TSA", "7")
    assert depo.anchors_since(an - timedelta(minutes=1))
    assert depo.anchors_since(an + timedelta(minutes=1)) == []

    # Başka hesabın çıpası görünmüyor.
    assert SqlAnchorRepository(B_KIRACI).anchors(limit=5) == []

    # Ekle-yalnız: uygulama rolü çıpayı değiştiremez (göç 0009).
    with tenant_session(A_KIRACI) as o, pytest.raises(ProgrammingError, match="permission denied"):
        o.execute(text("UPDATE audit_anchor SET chain_hash = 'x'"))
    with tenant_session(A_KIRACI) as o, pytest.raises(ProgrammingError, match="permission denied"):
        o.execute(text("DELETE FROM audit_anchor"))


def test_cikti_isi_gidip_geliyor_ve_kiraciya_bagli(iki_kiraci: object) -> None:
    """Arka plan çıktısının iş kaydı (FR-1217).

    Durum geçişi **aynı satırı** güncelliyor: her tur yeni satır
    açsaydı kullanıcı aynı raporu üç kez görürdü.
    """
    depo = SqlExportJobRepository(A_KIRACI)
    an = datetime.now(UTC)
    is_kaydi = ExportJob(
        id=uuid4(),
        kind="aylik-ozet",
        params={"year": "2026", "month": "11"},
        requested_by=uuid4(),
        requested_at=an,
        run_count=900,
    )
    depo.save_job(is_kaydi)

    assert [i.id for i in depo.queued_jobs(5)] == [is_kaydi.id]

    hazir = is_kaydi.claimed(an).completed(
        an, key="exports/x.pdf", size=1234, code="AAAA-BBBB-CCCC"
    )
    depo.save_job(hazir)

    geri = depo.job(is_kaydi.id)
    assert geri is not None
    assert (geri.state, geri.attempts, geri.size_bytes) == ("ready", 1, 1234)
    assert geri.params == {"year": "2026", "month": "11"}
    assert depo.queued_jobs(5) == []
    assert [i.id for i in depo.jobs_for_user(is_kaydi.requested_by)] == [is_kaydi.id]
    assert [i.id for i in depo.files_before(an + timedelta(days=8), 5)] == [is_kaydi.id]
    assert depo.files_before(an - timedelta(days=1), 5) == []

    # Başka hesabın çıktısı görünmüyor: RLS burada da geçerli.
    assert SqlExportJobRepository(B_KIRACI).job(is_kaydi.id) is None
    assert SqlExportJobRepository(B_KIRACI).queued_jobs(5) == []


def test_belge_kodu_kaydi_buluyor_ve_kiraciya_bagli(iki_kiraci: object) -> None:
    """Doğrulama sayfasının okuma yolu (FR-1218).

    İkinci iddia daha önemli: bir hesabın belge kodu **başka hesapta
    çözülmüyor**. Oturumsuz bir uç noktanın kiracı yalıtımını delmesi,
    elinde kod olan herkese başka şirketin kaydını açmak olurdu.
    """
    depo = SqlAuditRepository(A_KIRACI)
    olay = _olay(1, GENESIS, event_type="rapor.uretildi", object_type="rapor")
    depo.append(olay)
    onek = olay.hash[:12]

    assert [o.id for o in depo.by_hash_prefix(onek)] == [olay.id]
    geri = depo.at_sequence(1)
    assert geri is not None
    assert geri.hash == olay.hash
    assert SqlAuditRepository(B_KIRACI).by_hash_prefix(onek) == []


def test_belge_kodu_sorgusu_indeksi_kullanabiliyor(iki_kiraci: object) -> None:
    """Göç 0007'deki ifade ile sorgudaki ifade **aynı** mı (ST-101).

    Tarama kapatılıp plan okunuyor: küçük tabloda planlayıcı zaten
    tam tarama seçer, sınanan şey hız değil indeksin bu sorguyla
    kullanılabilir olması. İfadeler ayrışırsa indeks sessizce ölü
    kalır ve oturumsuz uç nokta tam tarama yapmaya başlar.
    """
    SqlAuditRepository(A_KIRACI).append(_olay(1, GENESIS, event_type="rapor.uretildi"))

    with tenant_session(A_KIRACI) as o:
        o.execute(text("SET LOCAL enable_seqscan = off"))
        satirlar = o.execute(
            text("EXPLAIN SELECT id FROM audit_event WHERE substr(hash, 1, 12) = :onek"),
            {"onek": "0" * 12},
        ).all()

    plan = "\n".join(str(r[0]) for r in satirlar)
    assert "ix_audit_kod" in plan, plan


def test_olay_gunlugu_kiracilar_arasinda_yalitik(iki_kiraci: object) -> None:
    SqlAuditRepository(A_KIRACI).append(_olay(1, GENESIS))
    SqlAuditRepository(B_KIRACI).append(_olay(1, GENESIS))

    assert len(SqlAuditRepository(A_KIRACI).events(limit=10)) == 1
    assert len(SqlAuditRepository(B_KIRACI).events(limit=10)) == 1
    # Aynı sıra numarası iki kiracıda serbest: zincir hesap başına.


def test_toplu_calistirma_yazma_tek_islemde(iki_kiraci: object) -> None:
    """Ufuk üretimi onlarca satır yazıyor; satır başına işlem pahalı.

    Ölçüm (Frankfurt, 56 kayıt): tek tek 14,0 sn — toplu 0,26 sn.
    Test hızı değil **davranışı** sabitliyor: toplu yazma ve toplu
    silme, tek tek olanla aynı sonucu vermeli.
    """
    run = _calistirma(A_KIRACI)
    depo = SqlPlanRepository(A_KIRACI)
    an = datetime.now(UTC)
    yeni = [
        replace(run, id=uuid4(), business_day=run.business_day + timedelta(days=gun))
        for gun in range(1, 6)
    ]

    depo.save_runs(yeni)

    kimlikler = {r.id for r in depo.runs()}
    assert {r.id for r in yeni} <= kimlikler

    # Aynı kayıtları ikinci kez yazmak güncelleme: kopya açmaz.
    depo.save_runs([replace(r, status="cancelled", cancel_reason="deneme") for r in yeni])
    geri = {r.id: r for r in depo.runs()}
    assert all(geri[r.id].status == "cancelled" for r in yeni)
    assert len(depo.runs()) == len(kimlikler)

    depo.delete_runs([r.id for r in yeni])
    assert {r.id for r in depo.runs()}.isdisjoint({r.id for r in yeni})
    assert an is not None
