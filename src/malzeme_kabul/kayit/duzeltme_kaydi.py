"""Mühendis düzeltme olayları, etiket adayı ve düzeltme panosu.

Tasarım: docs/muhendis_duzeltmeleri_tasarimi.md, plan: docs/plan_duzeltme_dongusu.md.

Katalogla aynı SQLite bağlantısında iki tablo vardır; ikisi de yalnız eklenir
(UPDATE, DELETE ve üzerine yazma tetikleyicilerle reddedilir):

- `duzeltme_tabanlari`: taslağın sistem çıktısı (taban), taslak başına bir satır.
  Tabanı olmayan eski bir taslakta ilk düzeltme (ya da onay) anındaki içerik
  taban olur ve üreten `{"yaklasim": "bilinmiyor"}` yazılır.
- `duzeltme_olaylari`: alan düzeyinde olaylar (`degistir`, `ekle`, `sil`,
  `onayla`). Alan adları `duzeltme_alanlari` anahtarlarıdır: F1 ölçümünün
  alanları (`sozlesme.alanlar`) ve tablodan düzenlenen ama F1'de olmayan ek
  test alanları (`EK_ALANLAR`: sayfa, sınırın orijinal metni, sonuç kaynağı).

Onayda, tabanla son doküman arasında net değişmemiş her alan için `onayla`
olayı yazılır: doğru okunmuş alanlar da görünür ve oran şişmez.

Bu modül değer karşılaştırmasını `degerler_esit` ile yapar; birim çevirmez.
Katalog katmanını içe aktarmaz: `etiket_adayi_yaz` katalog nesnesinin
`taslak(id)` metodunu kullanır, pano yalnız `taslaklar` ve `dokuman_surumleri`
tablolarını okur.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from malzeme_kabul.sozlesme.alanlar import Anahtar, alanlari_duzlestir, degerler_esit
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak

ISLEMLER: tuple[str, ...] = ("degistir", "ekle", "sil", "onayla")
YAKLASIMLAR: tuple[str, ...] = ("kural", "dil_modeli", "hibrit", "bilinmiyor")
BILINMIYOR: dict[str, Any] = {"yaklasim": "bilinmiyor"}

# Tablodan düzenlenen ama F1 düzleştirmesinde (`alanlari_duzlestir`) olmayan test alanları.
# Düzeltme olaylarına ve panonun paydasına girer; F1 ölçümüne girmez.
EK_ALANLAR: tuple[str, ...] = ("test.kaynak.sayfa", "test.sinir.orijinal_metin", "test.sonuc_kaynagi")

SEMA = """
CREATE TABLE IF NOT EXISTS duzeltme_tabanlari (
    taslak_id  INTEGER PRIMARY KEY,
    belge      TEXT NOT NULL,
    icerik     TEXT NOT NULL,
    ozet       TEXT NOT NULL,
    ureten     TEXT NOT NULL,
    zaman      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duzeltme_olaylari (
    olay_id         INTEGER PRIMARY KEY,
    zaman           TEXT NOT NULL,
    muhendis        TEXT NOT NULL,
    taslak_id       INTEGER NOT NULL,
    belge           TEXT NOT NULL,
    dokuman_surumu  TEXT NOT NULL,
    kayit_turu      TEXT NOT NULL,
    kayit           TEXT NOT NULL,
    alan            TEXT NOT NULL,
    eski_deger      TEXT NOT NULL,
    yeni_deger      TEXT NOT NULL,
    islem           TEXT NOT NULL CHECK (islem IN ('degistir', 'ekle', 'sil', 'onayla')),
    kaynak          TEXT,
    gerekce         TEXT,
    ureten          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS duzeltme_olaylari_taslak ON duzeltme_olaylari (taslak_id, olay_id);

CREATE TRIGGER IF NOT EXISTS duzeltme_tabanlari_degistirilemez
BEFORE UPDATE ON duzeltme_tabanlari
BEGIN
    SELECT RAISE(ABORT, 'düzeltme tabanı değiştirilemez');
END;

CREATE TRIGGER IF NOT EXISTS duzeltme_tabanlari_silinemez
BEFORE DELETE ON duzeltme_tabanlari
BEGIN
    SELECT RAISE(ABORT, 'düzeltme tabanı silinemez');
END;

-- INSERT OR REPLACE çakışan satırı DELETE tetikleyicisi olmadan silerdi (denetim_kaydi.py ile aynı önlem).
CREATE TRIGGER IF NOT EXISTS duzeltme_tabanlari_uzerine_yazilamaz
BEFORE INSERT ON duzeltme_tabanlari
WHEN EXISTS (SELECT 1 FROM duzeltme_tabanlari WHERE taslak_id = NEW.taslak_id)
BEGIN
    SELECT RAISE(ABORT, 'taslağın düzeltme tabanı zaten var');
END;

CREATE TRIGGER IF NOT EXISTS duzeltme_olaylari_degistirilemez
BEFORE UPDATE ON duzeltme_olaylari
BEGIN
    SELECT RAISE(ABORT, 'düzeltme olayı değiştirilemez');
END;

CREATE TRIGGER IF NOT EXISTS duzeltme_olaylari_silinemez
BEFORE DELETE ON duzeltme_olaylari
BEGIN
    SELECT RAISE(ABORT, 'düzeltme olayı silinemez');
END;

CREATE TRIGGER IF NOT EXISTS duzeltme_olaylari_uzerine_yazilamaz
BEFORE INSERT ON duzeltme_olaylari
WHEN EXISTS (SELECT 1 FROM duzeltme_olaylari WHERE olay_id = NEW.olay_id)
BEGIN
    SELECT RAISE(ABORT, 'düzeltme olayının üzerine yazılamaz');
END;
"""

_OLAY_SUTUNLARI = (
    "olay_id", "zaman", "muhendis", "taslak_id", "belge", "dokuman_surumu", "kayit_turu", "kayit",
    "alan", "eski_deger", "yeni_deger", "islem", "kaynak", "gerekce", "ureten",
)


@dataclass(frozen=True)
class AlanFarki:
    """İki doküman arasındaki tek bir alan farkı; değerler JSON'a yazılabilir biçimdedir."""

    kayit_turu: str
    kayit: str
    alan: str
    eski_deger: Any
    yeni_deger: Any
    islem: str


@dataclass(frozen=True)
class Olay:
    olay_id: int
    zaman: str
    muhendis: str
    taslak_id: int
    belge: str
    dokuman_surumu: str
    kayit_turu: str
    kayit: str
    alan: str
    eski_deger: Any
    yeni_deger: Any
    islem: str
    kaynak: str | None
    gerekce: str | None
    ureten: dict[str, Any]


# --- yardımcılar -------------------------------------------------------------------------------


def _simdi() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json(deger: Any) -> str:
    return json.dumps(deger, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _json_degeri(deger: Any) -> Any:
    """Düz görünüm değerini JSON'a yazılabilir yapar: demet → liste, str alt sınıfı (birim) → str."""
    if isinstance(deger, (tuple, list)):
        return [_json_degeri(d) for d in deger]
    if isinstance(deger, str):
        return str(deger)
    return deger


def _belge(dokuman: KabulDokumani) -> str:
    return f"{dokuman.standart.belge_no}{dokuman.standart.revizyon}"


def _dokuman_ozeti(dokuman: KabulDokumani) -> str:
    return hashlib.sha256(dokuman.model_dump_json(exclude={"durum"}).encode("utf-8")).hexdigest()


def _kayit_kaynaklari(dokuman: KabulDokumani) -> dict[tuple[str, str], Kaynak]:
    """{(kayıt türü, kayıt): kaynak}; kayıt adları `alanlari_duzlestir` ile aynı."""
    kaynaklar: dict[tuple[str, str], Kaynak] = {}
    for t in dokuman.testler:
        kaynaklar[("test", t.id)] = t.kaynak
    for r in dokuman.raf_omurleri:
        kayit = " ".join(r.kap_turu.casefold().split()) if r.kap_turu else "genel"
        kaynaklar[("raf_omru", kayit)] = r.kaynak
    for k in dokuman.kosullar:
        kaynaklar[("kosul", f"{k.kategori}:{' '.join(k.ad.casefold().split())}")] = k.kaynak
    for n in dokuman.numune_hazirlama:
        kaynaklar[("numune", n.id)] = n.kaynak
    return kaynaklar


def _kaynak_metni(kaynak: Kaynak | None) -> str | None:
    if kaynak is None:
        return None
    sayfa = f", sayfa {kaynak.sayfa}" if kaynak.sayfa is not None else ""
    return f"{kaynak.belge_no} {kaynak.revizyon} {kaynak.madde}{sayfa}"


def _muhendis_denetle(muhendis: Any) -> str:
    if not isinstance(muhendis, str) or not muhendis.strip():
        raise ValueError("mühendis (kullanıcı adı) boş olamaz")
    return muhendis


def duzeltme_alanlari(dokuman: KabulDokumani) -> dict[Anahtar, Any]:
    """Düzeltme döngüsünün saydığı alanlar: {(alan, kayıt): değer}.

    `alanlari_duzlestir` (F1 alanları) ve her testin dolu (None olmayan)
    `EK_ALANLAR` değerleri. F1 değerleri aynen kalır.
    """
    alanlar = alanlari_duzlestir(dokuman)
    for t in dokuman.testler:
        for alan, deger in zip(EK_ALANLAR, (t.kaynak.sayfa, t.sinir.orijinal_metin, t.sonuc_kaynagi)):
            if deger is not None:
                alanlar[(alan, t.id)] = deger
    return alanlar


def alan_farklari(eski: KabulDokumani, yeni: KabulDokumani) -> list[AlanFarki]:
    """İki doküman arasındaki alan farkları (`duzeltme_alanlari` anahtarları, anahtar sırasıyla).

    Eskide yok → `ekle`, yenide yok → `sil`, ikisinde de var ve `degerler_esit`
    değil → `degistir`. Birim çevrilmez: 30 s ile 30 min yalnız birim farkıdır.
    """
    e, y = duzeltme_alanlari(eski), duzeltme_alanlari(yeni)
    farklar = []
    for anahtar in sorted(e.keys() | y.keys()):
        alan, kayit = anahtar
        if anahtar not in e:
            islem = "ekle"
        elif anahtar not in y:
            islem = "sil"
        elif degerler_esit(e[anahtar], y[anahtar]):
            continue
        else:
            islem = "degistir"
        farklar.append(AlanFarki(alan.split(".", 1)[0], kayit, alan, _json_degeri(e.get(anahtar)),
                                 _json_degeri(y.get(anahtar)), islem))
    return farklar


# --- depo -----------------------------------------------------------------------------------------


class DuzeltmeKaydi:
    """Düzeltme tabanları ve olayları. Katalogla aynı SQLite bağlantısını paylaşır.

    Yazan metotlar bağlantıda açık bir işlem varsa ona SAVEPOINT ile katılır
    (dış işlem geri alınırsa olaylar da gider), yoksa kendi işlemini açar.
    """

    def __init__(self, baglanti: sqlite3.Connection):
        """Açık işlemdeki bir bağlantıyla kurulamaz: şema betiği (executescript) o işlemi bitirirdi."""
        if baglanti.in_transaction:
            raise ValueError("bağlantıda açık işlem var; düzeltme kaydı işlem dışında kurulmalı")
        self.baglanti = baglanti
        baglanti.executescript(SEMA)

    def _yaz(self, is_):
        b = self.baglanti
        ic_islem = b.in_transaction
        b.execute("SAVEPOINT duzeltme_yaz" if ic_islem else "BEGIN IMMEDIATE")
        try:
            sonuc = is_(b)
            b.execute("RELEASE duzeltme_yaz" if ic_islem else "COMMIT")
        except BaseException:
            if ic_islem:
                b.execute("ROLLBACK TO duzeltme_yaz")
                b.execute("RELEASE duzeltme_yaz")
            else:
                b.execute("ROLLBACK")
            raise
        return sonuc

    # --- taban ---

    def _taban_ekle(self, b: sqlite3.Connection, taslak_id: int, dokuman: KabulDokumani, ureten: dict) -> None:
        icerik = dokuman.model_dump_json()
        b.execute(
            "INSERT INTO duzeltme_tabanlari (taslak_id, belge, icerik, ozet, ureten, zaman) VALUES (?, ?, ?, ?, ?, ?)",
            (taslak_id, _belge(dokuman), icerik, hashlib.sha256(icerik.encode("utf-8")).hexdigest(), _json(ureten), _simdi()),
        )

    def taban_kaydet(self, taslak_id: int, dokuman: KabulDokumani, ureten: dict[str, Any]) -> None:
        """Taslağın sistem çıktısını taban olarak kaydeder; ikinci taban reddedilir (ValueError)."""
        if not isinstance(ureten, dict) or ureten.get("yaklasim") not in YAKLASIMLAR:
            raise ValueError(f"üreten bir sözlük olmalı ve yaklaşımı {', '.join(YAKLASIMLAR)} olmalı: {ureten!r}")
        if self.taban(taslak_id) is not None:
            raise ValueError(f"taslak {taslak_id} için taban zaten kayıtlı")
        self._yaz(lambda b: self._taban_ekle(b, taslak_id, dokuman, ureten))

    def taban(self, taslak_id: int) -> KabulDokumani | None:
        s = self.baglanti.execute("SELECT icerik FROM duzeltme_tabanlari WHERE taslak_id = ?", (taslak_id,)).fetchone()
        return None if s is None else KabulDokumani.model_validate_json(s[0])

    def ureten(self, taslak_id: int) -> dict[str, Any] | None:
        s = self.baglanti.execute("SELECT ureten FROM duzeltme_tabanlari WHERE taslak_id = ?", (taslak_id,)).fetchone()
        return None if s is None else json.loads(s[0])

    # --- olaylar ---

    def _olay_ekle(self, b: sqlite3.Connection, taslak_id: int, dokuman: KabulDokumani, muhendis: str,
                   fark: AlanFarki, kaynaklar: dict, gerekce: str | None, ureten: dict, zaman: str) -> int:
        imlec = b.execute(
            "INSERT INTO duzeltme_olaylari (zaman, muhendis, taslak_id, belge, dokuman_surumu, kayit_turu, kayit,"
            " alan, eski_deger, yeni_deger, islem, kaynak, gerekce, ureten) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (zaman, muhendis, taslak_id, _belge(dokuman), _dokuman_ozeti(dokuman), fark.kayit_turu, fark.kayit,
             fark.alan, _json(fark.eski_deger), _json(fark.yeni_deger), fark.islem,
             _kaynak_metni(kaynaklar.get((fark.kayit_turu, fark.kayit))), gerekce, _json(ureten)),
        )
        return imlec.lastrowid

    def _olaylari_yaz(self, taslak_id: int, taban_adayi: KabulDokumani, dokuman: KabulDokumani, muhendis: str,
                      farklar_fn, kaynaklar: dict, gerekce: str | None) -> list[Olay]:
        def is_(b):
            if self.ureten(taslak_id) is None:
                self._taban_ekle(b, taslak_id, taban_adayi, BILINMIYOR)
            ureten = self.ureten(taslak_id)
            zaman = _simdi()
            return [self._olay_ekle(b, taslak_id, dokuman, muhendis, f, kaynaklar, gerekce, ureten, zaman)
                    for f in farklar_fn()]

        kimlikler = self._yaz(is_)
        return self._olaylar_kimlikle(kimlikler)

    def duzeltmeleri_kaydet(self, taslak_id: int, eski: KabulDokumani, yeni: KabulDokumani, muhendis: str,
                            gerekce: str | None = None) -> list[Olay]:
        """Bir kaydetmenin alan farklarını olay olarak yazar ve yazılan olayları döner.

        Taslağın tabanı yoksa `eski` taban olur (üreten `bilinmiyor`). Fark yoksa
        hiçbir şey yazılmaz.
        """
        _muhendis_denetle(muhendis)
        farklar = alan_farklari(eski, yeni)
        if not farklar:
            return []
        kaynaklar = {**_kayit_kaynaklari(eski), **_kayit_kaynaklari(yeni)}
        return self._olaylari_yaz(taslak_id, eski, yeni, muhendis, lambda: farklar, kaynaklar, gerekce)

    def onaylari_kaydet(self, taslak_id: int, son: KabulDokumani, muhendis: str) -> list[Olay]:
        """Onayda tabanla `son` arasında net değişmemiş her alan için `onayla` olayı yazar.

        Değiştirilip geri alınan alan net değişmemiştir ve `onayla` alır. Taban
        yoksa `son` taban olur (üreten `bilinmiyor`).
        """
        _muhendis_denetle(muhendis)
        kaynaklar = _kayit_kaynaklari(son)

        def farklar():
            taban = self.taban(taslak_id) or son
            t, s = duzeltme_alanlari(taban), duzeltme_alanlari(son)
            return [
                AlanFarki(alan.split(".", 1)[0], kayit, alan, _json_degeri(s[(alan, kayit)]),
                          _json_degeri(s[(alan, kayit)]), "onayla")
                for alan, kayit in sorted(t.keys() & s.keys())
                if degerler_esit(t[(alan, kayit)], s[(alan, kayit)])
            ]

        return self._olaylari_yaz(taslak_id, son, son, muhendis, farklar, kaynaklar, None)

    @staticmethod
    def _olay(satir) -> Olay:
        d = dict(zip(_OLAY_SUTUNLARI, satir))
        for ad in ("eski_deger", "yeni_deger", "ureten"):
            d[ad] = json.loads(d[ad])
        return Olay(**d)

    def _olaylar_kimlikle(self, kimlikler: list[int]) -> list[Olay]:
        if not kimlikler:
            return []
        yer = ", ".join("?" * len(kimlikler))
        satirlar = self.baglanti.execute(
            f"SELECT {', '.join(_OLAY_SUTUNLARI)} FROM duzeltme_olaylari WHERE olay_id IN ({yer}) ORDER BY olay_id",
            kimlikler,
        )
        return [self._olay(s) for s in satirlar]

    def olaylar(self, taslak_id: int | None = None) -> list[Olay]:
        """Olaylar, ekleme sırasıyla; `taslak_id` verilirse yalnız o taslağınkiler."""
        nerede, deger = ("WHERE taslak_id = ?", (taslak_id,)) if taslak_id is not None else ("", ())
        satirlar = self.baglanti.execute(
            f"SELECT {', '.join(_OLAY_SUTUNLARI)} FROM duzeltme_olaylari {nerede} ORDER BY olay_id", deger)
        return [self._olay(s) for s in satirlar]


# --- etiket adayı ----------------------------------------------------------------------------------


def gold_yolu_mu(yol: str | Path) -> bool:
    """Yolun bir parçası `gold` mu? Verilen (mutlak) ve bağlantıları çözülmüş yol denetlenir.

    Parçalar büyük/küçük harfe duyarsız ve sondaki nokta/boşluklar atılarak
    karşılaştırılır (`GOLD`, `Gold`, `gold.`, `gold ` gold sayılır; bazı dosya
    sistemleri bunları aynı klasöre çözer). `goldsmith` gibi adlar gold değildir.
    """
    yol = Path(yol)
    yollar = (yol.absolute(), yol.resolve())
    return any(p.rstrip(". ").casefold() == "gold" for y in yollar for p in y.parts)


_IZINSIZ = re.compile(r"[^A-Za-z0-9._-]")


def _gold_reddi(yol: Path) -> ValueError:
    return ValueError(f"etiket adayı data/gold/ altına yazılmaz (gold'a proje sahibi taşır): {yol}")


def _atomik_yaz(hedef: Path, metin: str) -> None:
    """Aynı klasörde geçici dosyaya yazar, `os.replace` ile taşır (hedef bağlantıysa bağlantının yerine geçer)."""
    fd, gecici = tempfile.mkstemp(dir=hedef.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(metin)
        os.replace(gecici, hedef)
    except BaseException:
        Path(gecici).unlink(missing_ok=True)
        raise


def etiket_adayi_yaz(katalog: Any, taslak_id: int, klasor: str | Path, uzerine_yaz: bool = True) -> list[Path]:
    """Onaylı taslağın son dokümanını ve olaylarını etiket adayı olarak yazar.

    `<belge>_taslak<id>.json` (KabulDokumani) ve `<belge>_taslak<id>.olaylar.jsonl`
    yazılır, yolları (`klasor` altında) döner. Dosya adında [A-Za-z0-9._-]
    dışındaki karakterler `_` olur (belge numarası yol kaçışı yapamaz).
    `katalog`, `taslak(id)` ve `baglanti` sağlayan katalog nesnesidir.

    Reddedilenler (ValueError, hiçbir şey yazılmaz): onaylanmamış taslak,
    `gold_yolu_mu` olan klasör (klasör oluşturulduktan sonra yeniden denetlenir),
    klasör dışına ya da gold'a çözülen dosya yolu. Yazma geçici dosya +
    `os.replace` ile yapılır: hedefteki dosya bağlantısı izlenmez.
    `uzerine_yaz=False` iken iki dosyadan biri varsa FileExistsError (hiçbir şey yazılmaz).
    """
    klasor = Path(klasor)
    if gold_yolu_mu(klasor):
        raise _gold_reddi(klasor)
    taslak = katalog.taslak(taslak_id)
    if taslak.durum != "onaylandi":
        raise ValueError(f"taslak {taslak_id} onaylanmamış; etiket adayı yalnız onaylı taslaktan yazılır")
    olaylar = DuzeltmeKaydi(katalog.baglanti).olaylar(taslak_id)
    dokuman = taslak.dokuman
    ad = _IZINSIZ.sub("_", f"{_belge(dokuman)}_taslak{taslak_id}")
    adlar = (f"{ad}.json", f"{ad}.olaylar.jsonl")
    klasor.mkdir(parents=True, exist_ok=True)
    if gold_yolu_mu(klasor):  # oluşturma sırasında bir bağlantıya dönüşmüş olabilir
        raise _gold_reddi(klasor)
    gercek = klasor.resolve()
    for a in adlar:
        yol = klasor / a
        if (gercek / a).parent != gercek:
            raise ValueError(f"etiket adayı klasör dışına yazılmaz: {yol}")
        if gold_yolu_mu(yol):  # gold'daki bir dosyaya işaret eden bağlantı
            raise _gold_reddi(yol)
    if not uzerine_yaz:
        var = [a for a in adlar if os.path.lexists(klasor / a)]
        if var:
            raise FileExistsError(f"etiket adayı zaten var: {', '.join(var)}")
    json_yolu, olay_yolu = klasor / adlar[0], klasor / adlar[1]
    _atomik_yaz(gercek / adlar[0], dokuman.model_dump_json(indent=2))
    _atomik_yaz(gercek / adlar[1], "".join(json.dumps(asdict(o), ensure_ascii=False) + "\n" for o in olaylar))
    return [json_yolu, olay_yolu]


# --- pano ----------------------------------------------------------------------------------------------


@dataclass
class PanoOzeti:
    """Düzeltme panosu. Oran yalnız onaylı ve tabanı bilinen taslaklar üzerindendir.

    Onay bekleyenler `onay_bekleyen_duzeltme`, tabanı `bilinmiyor` olan onaylı
    taslaklar `tabani_bilinmeyen_taslak` olarak ayrı sayılır.
    """

    toplam_alan: int = 0
    duzeltilen_alan: int = 0
    oran: float = 0.0
    onay_bekleyen_duzeltme: int = 0
    tabani_bilinmeyen_taslak: int = 0
    belge_bazinda: list[dict[str, Any]] = field(default_factory=list)
    alan_bazinda: list[dict[str, Any]] = field(default_factory=list)
    kayit_turu_bazinda: list[dict[str, Any]] = field(default_factory=list)
    yaklasim_bazinda: list[dict[str, Any]] = field(default_factory=list)
    muhendis_bazinda: list[dict[str, Any]] = field(default_factory=list)
    gun_bazinda: dict[str, float] = field(default_factory=dict)


def _kirilim(sayac: dict[str, list[int]], ad: str) -> list[dict[str, Any]]:
    return [
        {ad: anahtar, "toplam": t, "duzeltilen": d, "oran": d / t if t else 0.0}
        for anahtar, (t, d) in sorted(sayac.items())
    ]


def _onay_bilgisi(baglanti: sqlite3.Connection, tablolar: set[str], taslak_id: int, belge_no: str, revizyon: str,
                  surum: int | None) -> tuple[str, str]:
    """(onaylayan, onay günü): önce katalogdaki onaylı sürümden, yoksa taslağın son onay olayından."""
    if "dokuman_surumleri" in tablolar and surum is not None:
        s = baglanti.execute(
            "SELECT onaylayan, onay_zamani FROM dokuman_surumleri WHERE belge_no = ? AND revizyon = ? AND surum = ?",
            (belge_no, revizyon, surum),
        ).fetchone()
        if s is not None:
            return s[0], s[1][:10]
    s = baglanti.execute(
        "SELECT muhendis, zaman FROM duzeltme_olaylari WHERE taslak_id = ? AND islem = 'onayla'"
        " ORDER BY olay_id DESC LIMIT 1", (taslak_id,),
    ).fetchone()
    return (s[0], s[1][:10]) if s is not None else ("bilinmiyor", "bilinmiyor")


def duzeltme_panosu(baglanti: sqlite3.Connection) -> PanoOzeti:
    """Düzeltme oranı ve kırılımları.

    Onaylı ve tabanı olan her taslakta alanlar tabanla son dokümanın
    `duzeltme_alanlari` birleşimidir (F1 alanları + dolu ek alanlar); düzeltilen
    alan, tabanla son doküman arasında net değişen alandır (aynı alan için
    birden çok olay tek sayılır, geri alınan sayılmaz). Aynı belgenin her
    taslağı ayrı sayılır.

    Tabanı `bilinmiyor` olan (sistem çıktısı bilinmeyen) onaylı taslaklar ana
    orana ve belge/alan/kayıt türü/mühendis/gün kırılımlarına girmez; yalnız
    yaklaşım kırılımında (`bilinmiyor`) görünür ve `tabani_bilinmeyen_taslak`
    olarak sayılır.

    Mühendis atfı: net düzeltilen alan o alanı son düzelten mühendise,
    düzeltilmeyen alan onaylayana sayılır. Gün: taslağın onay günü (UTC).
    Onaylayan ve onay zamanı katalogdaki onaylı sürümden okunur. Onay bekleyen
    taslakların net düzeltilmiş alanları `onay_bekleyen_duzeltme` olarak ayrı
    sayılır ve orana girmez.
    """
    tablolar = {s[0] for s in baglanti.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    ozet = PanoOzeti()
    if not {"duzeltme_tabanlari", "duzeltme_olaylari", "taslaklar"} <= tablolar:
        return ozet
    satirlar = baglanti.execute(
        "SELECT t.id, t.durum, t.icerik, t.belge_no, t.revizyon, t.surum, d.icerik, d.ureten, d.belge"
        " FROM taslaklar t JOIN duzeltme_tabanlari d ON d.taslak_id = t.id ORDER BY t.id"
    ).fetchall()
    kirilimlar: dict[str, dict[str, list[int]]] = {ad: defaultdict(lambda: [0, 0]) for ad in
                                                    ("belge", "alan", "kayit_turu", "yaklasim", "muhendis", "gun")}
    for taslak_id, durum, son_icerik, belge_no, revizyon, surum, taban_icerik, ureten, belge in satirlar:
        son = KabulDokumani.model_validate_json(son_icerik)
        taban = KabulDokumani.model_validate_json(taban_icerik)
        duzeltilen: set[Anahtar] = {(f.alan, f.kayit) for f in alan_farklari(taban, son)}
        if durum != "onaylandi":
            ozet.onay_bekleyen_duzeltme += len(duzeltilen)
            continue
        alanlar = set(duzeltme_alanlari(taban)) | set(duzeltme_alanlari(son))
        yaklasim = json.loads(ureten).get("yaklasim", "bilinmiyor")
        yaklasim_sayaci = kirilimlar["yaklasim"][yaklasim]
        yaklasim_sayaci[0] += len(alanlar)
        yaklasim_sayaci[1] += len(duzeltilen & alanlar)
        if yaklasim == "bilinmiyor":
            ozet.tabani_bilinmeyen_taslak += 1
            continue
        onaylayan, gun = _onay_bilgisi(baglanti, tablolar, taslak_id, belge_no, revizyon, surum)
        son_duzelten: dict[Anahtar, str] = {
            (alan, kayit): muhendis for alan, kayit, muhendis in baglanti.execute(
                "SELECT alan, kayit, muhendis FROM duzeltme_olaylari WHERE taslak_id = ? AND islem != 'onayla'"
                " ORDER BY olay_id", (taslak_id,))
        }
        for anahtar in alanlar:
            alan = anahtar[0]
            d = int(anahtar in duzeltilen)
            muhendis = son_duzelten.get(anahtar, onaylayan) if d else onaylayan
            for ad, deger in (("belge", belge), ("alan", alan), ("kayit_turu", alan.split(".", 1)[0]),
                              ("muhendis", muhendis), ("gun", gun)):
                kirilimlar[ad][deger][0] += 1
                kirilimlar[ad][deger][1] += d
        ozet.toplam_alan += len(alanlar)
        ozet.duzeltilen_alan += len(duzeltilen & alanlar)
    ozet.oran = ozet.duzeltilen_alan / ozet.toplam_alan if ozet.toplam_alan else 0.0
    ozet.belge_bazinda = _kirilim(kirilimlar["belge"], "belge")
    ozet.alan_bazinda = _kirilim(kirilimlar["alan"], "alan")
    ozet.kayit_turu_bazinda = _kirilim(kirilimlar["kayit_turu"], "kayit_turu")
    ozet.yaklasim_bazinda = _kirilim(kirilimlar["yaklasim"], "yaklasim")
    ozet.muhendis_bazinda = _kirilim(kirilimlar["muhendis"], "muhendis")
    ozet.gun_bazinda = {g: d / t for g, (t, d) in sorted(kirilimlar["gun"].items())}
    return ozet


__all__ = [
    "BILINMIYOR",
    "EK_ALANLAR",
    "ISLEMLER",
    "SEMA",
    "YAKLASIMLAR",
    "AlanFarki",
    "DuzeltmeKaydi",
    "Olay",
    "PanoOzeti",
    "alan_farklari",
    "duzeltme_alanlari",
    "duzeltme_panosu",
    "etiket_adayi_yaz",
    "gold_yolu_mu",
]
