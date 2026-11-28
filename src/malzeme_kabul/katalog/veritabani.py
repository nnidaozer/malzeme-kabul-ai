"""SQLite malzeme kataloğu (docs/mimari.md madde 2 ve 3).

Bağlar:

```
malzeme kodu ──► standart + revizyon + tip/sınıf ──► onaylı kabul dokümanı sürümü
      ├──────► onaylı tedarikçiler
      └──────► partiler (lot, tedarikçi, sipariş revizyonu, üretim tarihi, durum)
```

Kurallar:

- Onaylı kabul dokümanı sürümleri **değiştirilemez**. Bir standart + revizyon
  için sürümler 1'den başlayıp artar (v1, v2, ...). Düzeltme yeni sürümdür.
  Değiştirilemezlik veritabanında tetikleyicilerle (trigger) zorlanır:
  UPDATE ve DELETE reddedilir. Her sürüm içeriğinin SHA-256 özetini taşır.
- Örnek verinin onayı "demo onayı"dır: `demo_onayi` sütunu 1, onaylayan
  `ORNEK_ONAYLAYAN` ("ornek-veri"). Demo onaylı sürüm karar için onaylı sayılır
  ama ekranda ve kayıtta işaretlenir; işaret de sürümün parçasıdır, sonradan
  değiştirilemez. Demo işaretini yalnız tam `ORNEK_ONAYLAYAN` verebilir ve
  `ORNEK_ONAYLAYAN` yalnız demo onayı verebilir.
- Bir malzeme kodu tek bir standart + revizyon + tip/sınıf kombinasyonuna
  bağlıdır. Karar için o standart + revizyonun **en son onaylı** sürümü
  kullanılır (`gecerli_dokuman`).
- Parti yalnız o malzeme için onaylı bir tedarikçiden kaydedilebilir.
- Parti durumu: `serbest`, `karantina`, `bekliyor`; yeni parti `bekliyor`
  başlar. `durum_kaynagi` durumu en son kimin verdiğini tutar: boş (hiç karar
  verilmedi), `makine`, `insan` ya da `bilinmiyor` (sütundan önceki
  veritabanlarındaki partiler). Hangi geçişe izin verildiğine bu modül değil,
  karar hattı (`hat.katalog_karari`) bakar.

Bu modül karar vermez; yalnız saklar ve getirir.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from malzeme_kabul.sozlesme.sema import KabulDokumani

PartiDurumu = Literal["serbest", "karantina", "bekliyor"]
PARTI_DURUMLARI: tuple[str, ...] = ("serbest", "karantina", "bekliyor")
DurumKaynagi = Literal["makine", "insan"]
DURUM_KAYNAKLARI: tuple[str, ...] = ("makine", "insan")

# Örnek verinin (data/ornek/katalog.json) onaylayanı; bu adla verilen onay demo onayıdır.
# Ayrılmış addır: bu adla kullanıcı hesabı açılmaz (arayuz.kimlik).
ORNEK_ONAYLAYAN = "ornek-veri"
# Demo onaylı sürümün ekranda ve betik çıktısında görünen işareti (arayuz.ekran_verisi yeniden dışa verir).
DEMO_ETIKETI = "DEMO ONAYI (M&P onayı değil)"
# Kullanıcı rolleri ve ekran adları. Tek kaynak burasıdır: arayuz.kimlik.ROLLER bu sözlüğün
# kendisidir; hat (karari_duzelt) arayuz'a bağlanmadan aynı rolleri denetler.
ROLLER: dict[str, str] = {"mp": "M&P mühendisi", "giris_kalite": "Giriş kalite"}

DEMO_SUTUNU = "demo_onayi"
DEMO_SUTUN_TANIMI = "INTEGER NOT NULL DEFAULT 0 CHECK (demo_onayi IN (0, 1))"

# Değiştirilemezlik tetikleyicisi; SEMA ve demo_onayi göçü aynı metni kullanır.
DEGISTIRILEMEZ_TETIKLEYICI = "dokuman_surumu_degistirilemez"
_DEGISTIRILEMEZ_TETIKLEYICI_SQL = f"""CREATE TRIGGER IF NOT EXISTS {DEGISTIRILEMEZ_TETIKLEYICI}
BEFORE UPDATE ON dokuman_surumleri
BEGIN
    SELECT RAISE(ABORT, 'onaylı kabul dokümanı sürümü değiştirilemez; yeni sürüm ekleyin');
END;"""

SEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS standartlar (
    belge_no   TEXT NOT NULL,
    revizyon   TEXT NOT NULL,
    baslik     TEXT,
    tarih      TEXT,
    eklenme    TEXT NOT NULL,
    PRIMARY KEY (belge_no, revizyon)
);

CREATE TABLE IF NOT EXISTS malzemeler (
    kod        TEXT PRIMARY KEY,
    belge_no   TEXT NOT NULL,
    revizyon   TEXT NOT NULL,
    tip        TEXT,
    sinif      TEXT,
    aciklama   TEXT,
    mp_inceleme TEXT,
    FOREIGN KEY (belge_no, revizyon) REFERENCES standartlar (belge_no, revizyon)
);

CREATE TABLE IF NOT EXISTS dokuman_surumleri (
    belge_no     TEXT NOT NULL,
    revizyon     TEXT NOT NULL,
    surum        INTEGER NOT NULL CHECK (surum >= 1),
    icerik       TEXT NOT NULL,
    ozet         TEXT NOT NULL,
    onaylayan    TEXT NOT NULL,
    onay_zamani  TEXT NOT NULL,
    not_         TEXT,
    {DEMO_SUTUNU}   {DEMO_SUTUN_TANIMI},
    PRIMARY KEY (belge_no, revizyon, surum),
    FOREIGN KEY (belge_no, revizyon) REFERENCES standartlar (belge_no, revizyon)
);

{_DEGISTIRILEMEZ_TETIKLEYICI_SQL}

CREATE TRIGGER IF NOT EXISTS dokuman_surumu_silinemez
BEFORE DELETE ON dokuman_surumleri
BEGIN
    SELECT RAISE(ABORT, 'onaylı kabul dokümanı sürümü silinemez');
END;

CREATE TABLE IF NOT EXISTS tedarikciler (
    ad         TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS onayli_tedarikciler (
    malzeme_kodu  TEXT NOT NULL REFERENCES malzemeler (kod),
    tedarikci     TEXT NOT NULL REFERENCES tedarikciler (ad),
    PRIMARY KEY (malzeme_kodu, tedarikci)
);

CREATE TABLE IF NOT EXISTS partiler (
    lot_no             TEXT NOT NULL,
    malzeme_kodu       TEXT NOT NULL REFERENCES malzemeler (kod),
    tedarikci          TEXT NOT NULL REFERENCES tedarikciler (ad),
    siparis_revizyonu  TEXT NOT NULL,
    uretim_tarihi      TEXT NOT NULL,
    durum              TEXT NOT NULL DEFAULT 'bekliyor'
                       CHECK (durum IN ('serbest', 'karantina', 'bekliyor')),
    kap_turu           TEXT,
    mp_inceleme        TEXT,
    durum_kaynagi      TEXT CHECK (durum_kaynagi IS NULL OR durum_kaynagi IN ('makine', 'insan', 'bilinmiyor')),
    PRIMARY KEY (malzeme_kodu, lot_no)
);

CREATE TABLE IF NOT EXISTS taslaklar (
    id          INTEGER PRIMARY KEY,
    belge_no    TEXT NOT NULL,
    revizyon    TEXT NOT NULL,
    icerik      TEXT NOT NULL,
    olusturan   TEXT NOT NULL,
    guncelleme  TEXT NOT NULL,
    durum       TEXT NOT NULL DEFAULT 'taslak' CHECK (durum IN ('taslak', 'onaylandi')),
    surum       INTEGER
);
"""

# Eski veritabanlarına sonradan eklenen sütunlar: (tablo, sütun, tanım).
EK_SUTUNLAR: list[tuple[str, str, str]] = [
    ("partiler", "kap_turu", "TEXT"),
    ("partiler", "mp_inceleme", "TEXT"),
    ("malzemeler", "mp_inceleme", "TEXT"),
    ("partiler", "durum_kaynagi", "TEXT CHECK (durum_kaynagi IS NULL OR durum_kaynagi IN ('makine', 'insan', 'bilinmiyor'))"),
]

# Sütun eski bir veritabanına eklendiğinde mevcut satırlar için çalışan güvenli doldurma.
# Mevcut partilere daha önce kimin karar verdiği bilinmez; "hiç karar verilmedi" (NULL)
# sayılırsa makine onları serbest bırakabilirdi, bu yüzden "bilinmiyor" yazılır.
GOC_DOLDURMA: dict[tuple[str, str], str] = {
    ("partiler", "durum_kaynagi"): "UPDATE partiler SET durum_kaynagi = 'bilinmiyor' WHERE durum_kaynagi IS NULL",
}


class KatalogHatasi(ValueError):
    """Katalog kuralına aykırı işlem (onaysız tedarikçi, bilinmeyen kod...)."""


@dataclass(frozen=True)
class Malzeme:
    kod: str
    belge_no: str
    revizyon: str
    tip: str | None
    sinif: str | None
    aciklama: str | None
    mp_inceleme: str | None = None  # doluysa "M&P incelemesi bekliyor" ve nedeni

    @property
    def standart_etiketi(self) -> str:
        return f"{self.belge_no}{self.revizyon}"


@dataclass(frozen=True)
class DokumanSurumu:
    belge_no: str
    revizyon: str
    surum: int
    dokuman: KabulDokumani
    ozet: str
    onaylayan: str
    onay_zamani: str
    not_: str | None
    demo_onayi: bool = False  # örnek verinin demo onayı (M&P onayı değil)

    @property
    def etiket(self) -> str:
        return f"{self.belge_no}{self.revizyon} v{self.surum}"


@dataclass(frozen=True)
class Taslak:
    id: int
    dokuman: KabulDokumani
    olusturan: str
    guncelleme: str
    durum: str
    surum: int | None

    @property
    def etiket(self) -> str:
        std = self.dokuman.standart
        return f"taslak {self.id}: {std.belge_no}{std.revizyon}" + (f" (v{self.surum} olarak onaylandı)" if self.surum else "")


@dataclass(frozen=True)
class Parti:
    lot_no: str
    malzeme_kodu: str
    tedarikci: str
    siparis_revizyonu: str
    uretim_tarihi: date
    durum: str
    kap_turu: str | None = None
    mp_inceleme: str | None = None  # doluysa "M&P incelemesi bekliyor" ve nedeni
    durum_kaynagi: str | None = None  # None: hiç karar verilmedi; "makine" | "insan" | "bilinmiyor"

    @property
    def karar_verildi(self) -> bool:
        """Partiye daha önce (makine ya da insan) karar verildi mi? Bilinmiyorsa verildi sayılır."""
        return self.durum_kaynagi is not None


def icerik_ozeti(icerik: str) -> str:
    """Kabul dokümanı JSON metninin SHA-256 özeti."""
    return hashlib.sha256(icerik.encode("utf-8")).hexdigest()


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tarih(deger: date | str) -> date:
    if isinstance(deger, date):
        return deger
    try:
        return date.fromisoformat(deger)
    except ValueError as hata:
        raise KatalogHatasi(f"tarih YYYY-AA-GG biçiminde olmalı: {deger!r}") from hata


class Katalog:
    """SQLite katalog. `Katalog(":memory:")` testler için bellekte çalışır."""

    def __init__(self, yol: str | Path = ":memory:"):
        if str(yol) != ":memory:":
            Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self.yol = str(yol)
        self.baglanti = sqlite3.connect(self.yol, check_same_thread=False)
        self.baglanti.row_factory = sqlite3.Row
        try:
            self.baglanti.executescript(SEMA)
            self._sutunlari_tamamla()
            self._demo_gocu()
        except Exception:
            self.baglanti.close()
            raise

    def _sutunlari_tamamla(self) -> None:
        """Eski bir veritabanında eksik sütunları ekler (veri kaybı olmadan).

        Her sütun ekleme ve onun doldurması tek bir açık işlemdir (BEGIN ... COMMIT):
        doldurma düşerse ROLLBACK ile sütun da geri alınır, hata yukarı iletilir ve
        sonraki açılış göçü yeniden dener. Böylece eski satırlar hiçbir zaman
        doldurulmamış (ör. "hiç karar verilmedi") görünmez.
        """
        b = self.baglanti
        if b.in_transaction:
            b.commit()
        for tablo, sutun, tanim in EK_SUTUNLAR:
            var = {s["name"] for s in b.execute(f"PRAGMA table_info({tablo})")}
            if sutun in var:
                continue
            b.execute("BEGIN")
            try:
                b.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tanim}")
                if (doldurma := GOC_DOLDURMA.get((tablo, sutun))) is not None:
                    b.execute(doldurma)
                b.execute("COMMIT")
            except Exception:
                b.execute("ROLLBACK")
                raise

    def _demo_gocu(self) -> None:
        """demo_onayi sütunu olmayan eski veritabanına sütunu ekler ve örnek satırları işaretler.

        Değiştirilemezlik tetikleyicisi UPDATE'i reddettiğinden göç tek bir açık
        işlemdir (BEGIN IMMEDIATE ... COMMIT): sütun eklenir, tetikleyici düşürülür,
        `onaylayan = ORNEK_ONAYLAYAN` satırları demo işaretlenir, tetikleyici SEMA
        tanımıyla yeniden kurulur. Herhangi bir adım düşerse ROLLBACK (yalnız işlem
        hâlâ açıksa): sütun eklenmemiş, tetikleyici yerinde kalır, özgün hata yukarı
        iletilir ve sonraki açılış göçü yeniden dener. Sütun varsa göç çalışmaz.

        Yazma kilidi baştan alınır ve sütun işlem içinde yeniden denetlenir: aynı
        anda açan başka bir bağlantı göçü bitirdiyse bu çağrı hiçbir şey yapmaz.
        Bağlantıda açık bir işlem varsa onu bitirmez, KatalogHatasi verir. BEGIN
        IMMEDIATE kilit alamazsa `sqlite3.OperationalError` olduğu gibi iletilir.
        """
        b = self.baglanti
        if b.in_transaction:
            raise KatalogHatasi("demo onayı göçü açık bir işlemin içinde çalıştırılamaz")

        def sutun_var() -> bool:
            return DEMO_SUTUNU in {s["name"] for s in b.execute("PRAGMA table_info(dokuman_surumleri)")}

        if sutun_var():
            return
        b.execute("BEGIN IMMEDIATE")
        try:
            if not sutun_var():
                b.execute(f"ALTER TABLE dokuman_surumleri ADD COLUMN {DEMO_SUTUNU} {DEMO_SUTUN_TANIMI}")
                b.execute(f"DROP TRIGGER IF EXISTS {DEGISTIRILEMEZ_TETIKLEYICI}")
                b.execute(f"UPDATE dokuman_surumleri SET {DEMO_SUTUNU} = 1 WHERE onaylayan = ?", (ORNEK_ONAYLAYAN,))
                b.execute(_DEGISTIRILEMEZ_TETIKLEYICI_SQL)
            b.execute("COMMIT")
        except BaseException:
            if b.in_transaction:
                b.execute("ROLLBACK")
            raise

    def kapat(self) -> None:
        self.baglanti.close()

    def __enter__(self) -> Katalog:
        return self

    def __exit__(self, *_exc) -> None:
        self.kapat()

    @contextmanager
    def islem(self) -> Iterator[sqlite3.Connection]:
        """Tek bir işlem (transaction): hata olursa hepsi geri alınır.

        Bağlantıda açık bir işlem varsa (ör. dıştaki bir `islem()`), içteki
        işlem SAVEPOINT olarak ona katılır: hatada yalnız kendi yazdıklarını
        geri alır, başarıda dış işlemi bitirmez. Böylece bir durum değişikliği
        ile onun denetim kaydı dıştaki tek işlemde yazılır (denetim B1).

        Dış işlem BEGIN IMMEDIATE ile başlar: yazma kilidi baştan alınır, işlem
        içinde yapılan okuma (ör. parti durumu) yazılana kadar başka bir
        bağlantı tarafından değiştirilemez (K2 yarışı). Kilit alınamazsa
        `sqlite3.OperationalError` ("database is locked") yükselir.
        """
        b = self.baglanti
        if b.in_transaction:
            self._kayit_noktasi = getattr(self, "_kayit_noktasi", 0) + 1
            ad = f"katalog_islem_{self._kayit_noktasi}"
            b.execute(f"SAVEPOINT {ad}")
            try:
                yield b
            except BaseException:
                b.execute(f"ROLLBACK TO {ad}")
                b.execute(f"RELEASE {ad}")
                raise
            b.execute(f"RELEASE {ad}")
            return
        b.execute("BEGIN IMMEDIATE")
        try:
            yield b
        except BaseException:
            b.rollback()
            raise
        b.commit()

    # --- standart ---------------------------------------------------------

    def standart_ekle(self, belge_no: str, revizyon: str, baslik: str | None = None, tarih: str | None = None) -> None:
        with self.islem() as b:
            b.execute(
                "INSERT OR IGNORE INTO standartlar (belge_no, revizyon, baslik, tarih, eklenme) VALUES (?, ?, ?, ?, ?)",
                (belge_no, revizyon, baslik, tarih, _simdi()),
            )

    def standartlar(self) -> list[tuple[str, str, str | None]]:
        satirlar = self.baglanti.execute("SELECT belge_no, revizyon, baslik FROM standartlar ORDER BY belge_no, revizyon")
        return [(s["belge_no"], s["revizyon"], s["baslik"]) for s in satirlar]

    def standart_var_mi(self, belge_no: str, revizyon: str) -> bool:
        s = self.baglanti.execute(
            "SELECT 1 FROM standartlar WHERE belge_no = ? AND revizyon = ?", (belge_no, revizyon)
        ).fetchone()
        return s is not None

    # --- malzeme ----------------------------------------------------------

    def malzeme_ekle(
        self,
        kod: str,
        belge_no: str,
        revizyon: str,
        tip: str | None = None,
        sinif: str | None = None,
        aciklama: str | None = None,
    ) -> Malzeme:
        if not kod.strip():
            raise KatalogHatasi("malzeme kodu boş olamaz")
        if not self.standart_var_mi(belge_no, revizyon):
            raise KatalogHatasi(f"önce standart eklenmeli: {belge_no}{revizyon}")
        try:
            with self.islem() as b:
                b.execute(
                    "INSERT INTO malzemeler (kod, belge_no, revizyon, tip, sinif, aciklama) VALUES (?, ?, ?, ?, ?, ?)",
                    (kod, belge_no, revizyon, tip, sinif, aciklama),
                )
        except sqlite3.IntegrityError as hata:
            raise KatalogHatasi(f"malzeme kodu zaten var: {kod}") from hata
        return self.malzeme(kod)

    def malzeme(self, kod: str) -> Malzeme:
        s = self.baglanti.execute("SELECT * FROM malzemeler WHERE kod = ?", (kod,)).fetchone()
        if s is None:
            raise KatalogHatasi(f"bilinmeyen malzeme kodu: {kod}")
        return Malzeme(s["kod"], s["belge_no"], s["revizyon"], s["tip"], s["sinif"], s["aciklama"], s["mp_inceleme"])

    def malzemeler(self) -> list[Malzeme]:
        return [self.malzeme(s["kod"]) for s in self.baglanti.execute("SELECT kod FROM malzemeler ORDER BY kod")]

    # --- kabul dokümanı sürümleri ----------------------------------------

    def dokuman_onayla(
        self, dokuman: KabulDokumani, onaylayan: str, not_: str | None = None, *, demo_onayi: bool = False
    ) -> DokumanSurumu:
        """Dokümanı yeni ve değiştirilemez bir sürüm olarak kaydeder (v1, v2...).

        `demo_onayi=True` yalnız tam `ORNEK_ONAYLAYAN` ile verilir; `ORNEK_ONAYLAYAN`
        de yalnız demo onayı verebilir. Aksi KatalogHatasi, hiçbir şey yazılmaz.
        """
        if not onaylayan.strip():
            raise KatalogHatasi("onaylayan kullanıcı boş olamaz")
        if demo_onayi and onaylayan != ORNEK_ONAYLAYAN:
            raise KatalogHatasi(f"demo onayını yalnız {ORNEK_ONAYLAYAN!r} verebilir (onaylayan {onaylayan!r})")
        if not demo_onayi and onaylayan == ORNEK_ONAYLAYAN:
            raise KatalogHatasi(f"{ORNEK_ONAYLAYAN!r} ayrılmış addır; yalnız demo onayı verebilir")
        std = dokuman.standart
        self.standart_ekle(std.belge_no, std.revizyon, std.baslik, std.tarih)
        onayli = dokuman.model_copy(update={"durum": "onaylandi"})
        icerik = onayli.model_dump_json()
        with self.islem() as b:
            onceki = b.execute(
                "SELECT COALESCE(MAX(surum), 0) FROM dokuman_surumleri WHERE belge_no = ? AND revizyon = ?",
                (std.belge_no, std.revizyon),
            ).fetchone()[0]
            b.execute(
                "INSERT INTO dokuman_surumleri"
                " (belge_no, revizyon, surum, icerik, ozet, onaylayan, onay_zamani, not_, demo_onayi)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (std.belge_no, std.revizyon, onceki + 1, icerik, icerik_ozeti(icerik), onaylayan, _simdi(), not_,
                 1 if demo_onayi else 0),
            )
        return self.dokuman_surumu(std.belge_no, std.revizyon, onceki + 1)

    def _surum_satirindan(self, s: sqlite3.Row) -> DokumanSurumu:
        if icerik_ozeti(s["icerik"]) != s["ozet"]:
            raise KatalogHatasi(f"{s['belge_no']}{s['revizyon']} v{s['surum']}: içerik özeti tutmuyor (kurcalanmış)")
        return DokumanSurumu(
            s["belge_no"], s["revizyon"], s["surum"], KabulDokumani.model_validate_json(s["icerik"]),
            s["ozet"], s["onaylayan"], s["onay_zamani"], s["not_"], bool(s["demo_onayi"]),
        )

    def dokuman_surumu(self, belge_no: str, revizyon: str, surum: int) -> DokumanSurumu:
        s = self.baglanti.execute(
            "SELECT * FROM dokuman_surumleri WHERE belge_no = ? AND revizyon = ? AND surum = ?",
            (belge_no, revizyon, surum),
        ).fetchone()
        if s is None:
            raise KatalogHatasi(f"onaylı sürüm yok: {belge_no}{revizyon} v{surum}")
        return self._surum_satirindan(s)

    def dokuman_surumleri(self, belge_no: str, revizyon: str) -> list[DokumanSurumu]:
        satirlar = self.baglanti.execute(
            "SELECT * FROM dokuman_surumleri WHERE belge_no = ? AND revizyon = ? ORDER BY surum",
            (belge_no, revizyon),
        )
        return [self._surum_satirindan(s) for s in satirlar]

    def gecerli_dokuman(self, malzeme_kodu: str) -> DokumanSurumu:
        """Malzeme kodunun standart + revizyonu için en son onaylı sürüm."""
        m = self.malzeme(malzeme_kodu)
        surumler = self.dokuman_surumleri(m.belge_no, m.revizyon)
        if not surumler:
            raise KatalogHatasi(f"{malzeme_kodu}: {m.standart_etiketi} için onaylı kabul dokümanı yok")
        return surumler[-1]

    def mp_inceleme_ata(self, malzeme_kodu: str, neden: str | None, partiler_de: bool = True) -> None:
        """Malzemeyi (ve partilerini) "M&P incelemesi bekliyor" olarak işaretler; `neden` None ise kaldırır.

        Kilitlemez: parti durumu (serbest / karantina / bekliyor) değişmez.
        """
        self.malzeme(malzeme_kodu)
        with self.islem() as b:
            b.execute("UPDATE malzemeler SET mp_inceleme = ? WHERE kod = ?", (neden, malzeme_kodu))
            if partiler_de:
                b.execute("UPDATE partiler SET mp_inceleme = ? WHERE malzeme_kodu = ?", (neden, malzeme_kodu))

    def malzeme_revizyonu_ata(self, malzeme_kodu: str, revizyon: str) -> Malzeme:
        """Malzeme kodunu aynı standardın başka revizyonuna bağlar (M&P kararıyla).

        Yeni revizyonun geçerli (en son onaylı) sürümü demo onaylıysa reddeder:
        yalnız gerçek M&P onaylı sürüme geçilir (Nida, 28 Kasım). Denetim ve
        yazma kendi işlemindedir; dış işlem içinde çağrılırsa hata yalnız bu
        adımı geri alır.
        """
        with self.islem() as b:
            m = self.malzeme(malzeme_kodu)
            surumler = self.dokuman_surumleri(m.belge_no, revizyon)
            if not surumler:
                raise KatalogHatasi(f"{m.belge_no}{revizyon} için onaylı kabul dokümanı yok; önce onaylanmalı")
            if surumler[-1].demo_onayi:
                raise KatalogHatasi(
                    f"{surumler[-1].etiket} demo onaylı; yalnız gerçek M&P onaylı sürüme geçilir"
                )
            b.execute("UPDATE malzemeler SET revizyon = ? WHERE kod = ?", (revizyon, malzeme_kodu))
        return self.malzeme(malzeme_kodu)

    # --- taslaklar (M&P düzeltir, onaylayınca sürüm olur) -----------------

    def taslak_kaydet(self, dokuman: KabulDokumani, kullanici: str) -> Taslak:
        std = dokuman.standart
        with self.islem() as b:
            imlec = b.execute(
                "INSERT INTO taslaklar (belge_no, revizyon, icerik, olusturan, guncelleme) VALUES (?, ?, ?, ?, ?)",
                (std.belge_no, std.revizyon, dokuman.model_copy(update={"durum": "taslak"}).model_dump_json(), kullanici, _simdi()),
            )
        return self.taslak(imlec.lastrowid)

    def taslak(self, taslak_id: int) -> Taslak:
        s = self.baglanti.execute("SELECT * FROM taslaklar WHERE id = ?", (taslak_id,)).fetchone()
        if s is None:
            raise KatalogHatasi(f"bilinmeyen taslak: {taslak_id}")
        return Taslak(s["id"], KabulDokumani.model_validate_json(s["icerik"]), s["olusturan"], s["guncelleme"], s["durum"], s["surum"])

    def taslaklar(self, yalniz_acik: bool = False) -> list[Taslak]:
        nerede = " WHERE durum = 'taslak'" if yalniz_acik else ""
        return [self.taslak(s["id"]) for s in self.baglanti.execute(f"SELECT id FROM taslaklar{nerede} ORDER BY id")]

    def taslak_guncelle(self, taslak_id: int, dokuman: KabulDokumani) -> Taslak:
        t = self.taslak(taslak_id)
        if t.durum != "taslak":
            raise KatalogHatasi(f"taslak {taslak_id} onaylanmış; düzeltme yeni taslakla yapılır")
        if (dokuman.standart.belge_no, dokuman.standart.revizyon) != (t.dokuman.standart.belge_no, t.dokuman.standart.revizyon):
            raise KatalogHatasi("taslağın standardı ya da revizyonu değiştirilemez")
        with self.islem() as b:
            b.execute(
                "UPDATE taslaklar SET icerik = ?, guncelleme = ? WHERE id = ?",
                (dokuman.model_copy(update={"durum": "taslak"}).model_dump_json(), _simdi(), taslak_id),
            )
        return self.taslak(taslak_id)

    def taslagi_onayla(self, taslak_id: int, onaylayan: str, not_: str | None = None) -> DokumanSurumu:
        """Taslağı yeni onaylı sürüm yapar; taslak kapanır."""
        t = self.taslak(taslak_id)
        if t.durum != "taslak":
            raise KatalogHatasi(f"taslak {taslak_id} zaten onaylanmış (v{t.surum})")
        surum = self.dokuman_onayla(t.dokuman, onaylayan, not_)
        with self.islem() as b:
            b.execute("UPDATE taslaklar SET durum = 'onaylandi', surum = ? WHERE id = ?", (surum.surum, taslak_id))
        return surum

    # --- tedarikçiler -----------------------------------------------------

    def tedarikci_ekle(self, ad: str) -> None:
        if not ad.strip():
            raise KatalogHatasi("tedarikçi adı boş olamaz")
        with self.islem() as b:
            b.execute("INSERT OR IGNORE INTO tedarikciler (ad) VALUES (?)", (ad,))

    def tedarikci_onayla(self, malzeme_kodu: str, tedarikci: str) -> None:
        self.malzeme(malzeme_kodu)
        self.tedarikci_ekle(tedarikci)
        with self.islem() as b:
            b.execute(
                "INSERT OR IGNORE INTO onayli_tedarikciler (malzeme_kodu, tedarikci) VALUES (?, ?)",
                (malzeme_kodu, tedarikci),
            )

    def onayli_tedarikciler(self, malzeme_kodu: str) -> list[str]:
        satirlar = self.baglanti.execute(
            "SELECT tedarikci FROM onayli_tedarikciler WHERE malzeme_kodu = ? ORDER BY tedarikci", (malzeme_kodu,)
        )
        return [s["tedarikci"] for s in satirlar]

    # --- partiler ---------------------------------------------------------

    def parti_ekle(
        self,
        lot_no: str,
        malzeme_kodu: str,
        tedarikci: str,
        siparis_revizyonu: str,
        uretim_tarihi: date | str,
        durum: PartiDurumu = "bekliyor",
        kap_turu: str | None = None,
    ) -> Parti:
        self.malzeme(malzeme_kodu)
        if durum not in PARTI_DURUMLARI:
            raise KatalogHatasi(f"geçersiz parti durumu: {durum!r} ({', '.join(PARTI_DURUMLARI)})")
        if tedarikci not in self.onayli_tedarikciler(malzeme_kodu):
            raise KatalogHatasi(f"{tedarikci} {malzeme_kodu} için onaylı tedarikçi değil")
        if not siparis_revizyonu.strip():
            raise KatalogHatasi("sipariş revizyonu boş olamaz")
        uretim = _tarih(uretim_tarihi)
        try:
            with self.islem() as b:
                b.execute(
                    "INSERT INTO partiler (lot_no, malzeme_kodu, tedarikci, siparis_revizyonu, uretim_tarihi, durum, kap_turu)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (lot_no, malzeme_kodu, tedarikci, siparis_revizyonu, uretim.isoformat(), durum, kap_turu),
                )
        except sqlite3.IntegrityError as hata:
            raise KatalogHatasi(f"parti zaten var: {malzeme_kodu} / {lot_no}") from hata
        return self.parti(malzeme_kodu, lot_no)

    @staticmethod
    def _parti_satirindan(s: sqlite3.Row) -> Parti:
        return Parti(
            s["lot_no"], s["malzeme_kodu"], s["tedarikci"], s["siparis_revizyonu"],
            date.fromisoformat(s["uretim_tarihi"]), s["durum"], s["kap_turu"], s["mp_inceleme"],
            s["durum_kaynagi"],
        )

    def parti(self, malzeme_kodu: str, lot_no: str) -> Parti:
        s = self.baglanti.execute(
            "SELECT * FROM partiler WHERE malzeme_kodu = ? AND lot_no = ?", (malzeme_kodu, lot_no)
        ).fetchone()
        if s is None:
            raise KatalogHatasi(f"bilinmeyen parti: {malzeme_kodu} / {lot_no}")
        return self._parti_satirindan(s)

    def partiler(self, malzeme_kodu: str | None = None) -> list[Parti]:
        if malzeme_kodu is None:
            satirlar = self.baglanti.execute("SELECT * FROM partiler ORDER BY malzeme_kodu, lot_no")
        else:
            satirlar = self.baglanti.execute(
                "SELECT * FROM partiler WHERE malzeme_kodu = ? ORDER BY lot_no", (malzeme_kodu,)
            )
        return [self._parti_satirindan(s) for s in satirlar]

    def parti_durumu_ata(
        self, malzeme_kodu: str, lot_no: str, durum: PartiDurumu, *, kaynak: DurumKaynagi
    ) -> Parti:
        """Parti durumunu yazar ve durumu kimin verdiğini (`kaynak`, zorunlu) saklar.

        Geçiş kuralını denetlemez; makine kararları `hat.katalog_karari` üzerinden gelir.
        """
        if durum not in PARTI_DURUMLARI:
            raise KatalogHatasi(f"geçersiz parti durumu: {durum!r} ({', '.join(PARTI_DURUMLARI)})")
        if kaynak not in DURUM_KAYNAKLARI:
            raise KatalogHatasi(f"geçersiz durum kaynağı: {kaynak!r} ({', '.join(DURUM_KAYNAKLARI)})")
        self.parti(malzeme_kodu, lot_no)
        with self.islem() as b:
            b.execute(
                "UPDATE partiler SET durum = ?, durum_kaynagi = ? WHERE malzeme_kodu = ? AND lot_no = ?",
                (durum, kaynak, malzeme_kodu, lot_no),
            )
        return self.parti(malzeme_kodu, lot_no)


__all__ = [
    "DokumanSurumu",
    "Katalog",
    "KatalogHatasi",
    "Malzeme",
    "DURUM_KAYNAKLARI",
    "DEMO_ETIKETI",
    "ORNEK_ONAYLAYAN",
    "DurumKaynagi",
    "PARTI_DURUMLARI",
    "Parti",
    "ROLLER",
    "Taslak",
    "PartiDurumu",
    "icerik_ozeti",
]
