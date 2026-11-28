"""Standartların geliştirme / test bölünmesi (data/bolunme.yaml).

Kurallar (docs/mimari.md madde 7):

- Geliştirme kümesindeki standartlar serbestçe kullanılır.
- Yeni indirilen standartlar (`yeni_standartlar`) sabit bir tohumla ikiye
  bölünür. Bölme birimi revizyon ailesidir (aynı numaralı standardın
  revizyonları, ör. MIL-S-81733C ile MIL-PRF-81733D): ailelerin rastgele yarısı
  (tek sayıda yukarı yuvarlanır) bütün revizyonlarıyla test kümesine, kalanı
  geliştirme kümesine gider. Aynı aile iki kümede birden bulunamaz; böylece bir
  revizyonun metni öbürü üzerinden sızmaz. Bölme `python deney/bolunme.py --sec` ile yapılır
  ve dosyaya yazılır; aynı tohum her zaman aynı seçimi verir ve okuma sırasında
  bu denetlenir.
- Bölme yapılana kadar (`test_durumu: bekliyor`) yeni standartların hiçbiri
  kullanılamaz; seçimden sonra test kümesi, `test_kumesi_acik: true` yazana
  kadar kullanılamaz. Bölünmede hiç olmayan standart da reddedilir, böylece yeni
  bir belge sessizce geliştirme kümesine karışmaz.

Standart dışı belgeler (ör. gerçek havacılık CoC'leri) klasör olarak kilitlenir:
`kilitli_klasorler` altındaki adlarla eşleşen bir klasörün içindeki dosyalar test
kümesindedir ve `test_kumesi_acik: true` yazana kadar açılmaz
(`yol_kullanima_izin_ver`).

Taranmış belgeler (`ocr_gerekli`): bütün sayfaları resim olan standartlar
kümelerinden çıkarılmaz, "OCR gerekli" diye işaretlenir. Çıkarıcı ve ölçüm
betikleri bunları OCR'sız reddeder (`OcrGerekli`); `--ocr` ile (yerel
Tesseract, docs/ocr.md) okunurlar (`kullanima_izin_ver(etiket, ocr=True)`).
Test kümesi kilidi OCR'dan önce denetlenir: OCR kilitli belgeyi açmaz. Sonuçlar
raporlanırken taranmış ve metin tabanlı belgeler ayrı gösterilir
(`turlere_ayir`). Liste `scripts/pdf_tur_kontrol.py` çıktısındaki (data/raw/pdf_turleri.csv)
"taranmış" belgelerle aynı olmalıdır; test bunu denetler.

Çıkarıcı ve taslak cevap betikleri bir standardı işlemeden önce
`betik_korumasi` çağırır.

Dosya YAML'ın küçük bir alt kümesiyle yazılır (yorum, `anahtar: değer` ve
`- öğe` listeleri); bağımlılık kilidine yeni paket eklememek için burada okunur.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

KOK = Path(__file__).resolve().parents[1]
VARSAYILAN_YOL = KOK / "data" / "bolunme.yaml"
VARSAYILAN_HAM = KOK / "data" / "raw"
GOLD = KOK / "data" / "gold"
BELGE_ETIKETI = re.compile(r"^[A-Z]+(-[A-Z]+)?-\d+[A-Z]$")
Kume = Literal["gelistirme", "test", "bekliyor"]
TestDurumu = Literal["bekliyor", "secildi"]
ANAHTARLAR = (
    "test_kumesi_acik", "test_durumu", "tohum", "gelistirme", "yeni_standartlar", "test", "kilitli_klasorler",
    "ocr_gerekli",
)
METIN = "metin"
TARANMIS = "taranmış"
OCR_GEREKLI = "OCR gerekli"
KLASOR_ADI = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class TestKumesiKilitli(PermissionError):
    """Test kümesindeki (ya da bölünmeyi bekleyen) bir standart kullanılmak istendi."""

    __test__ = False


class OcrGerekli(ValueError):
    """Standart taranmış bir PDF; OCR'sız (``ocr=False``) çıkarıcı çalıştırılmaz."""


def dosya_etiketi(yol: str | Path) -> str | None:
    """Dosya adından belge etiketi: 'MIL-PRF-81309H_Amendment1.pdf' -> 'MIL-PRF-81309H'; çözülemezse None."""
    aday = Path(yol).stem.split("_")[0]
    return aday if BELGE_ETIKETI.match(aday) else None


def _ham_klasorleri(ham_klasor: str | Path | None) -> list[Path]:
    """İçerik kilidi için taranacak klasörler: data/raw (varsa) ve verilen ek klasör (yinelenmeden)."""
    klasorler: list[Path] = []
    if VARSAYILAN_HAM.is_dir():
        klasorler.append(VARSAYILAN_HAM.resolve())
    if ham_klasor is not None:
        ek = Path(ham_klasor)
        if not ek.is_dir():
            raise ValueError(f"ham klasör yok ya da klasör değil: {ek}")
        if ek.resolve() not in klasorler:
            klasorler.append(ek.resolve())
    return klasorler


_OZET_ONBELLEGI: dict[tuple[str, int, int], str] = {}


def _dosya_ozeti(yol: Path) -> str:
    """Dosyanın SHA-256 özeti; (gerçek yol, boyut, değişme zamanı) ile önbelleklenir."""
    gercek = Path(yol).resolve()
    bilgi = gercek.stat()
    anahtar = (str(gercek), bilgi.st_size, bilgi.st_mtime_ns)
    if anahtar not in _OZET_ONBELLEGI:
        h = hashlib.sha256()
        with open(gercek, "rb") as f:
            for parca in iter(lambda: f.read(1 << 20), b""):
                h.update(parca)
        _OZET_ONBELLEGI[anahtar] = h.hexdigest()
    return _OZET_ONBELLEGI[anahtar]


def gold_altinda_mi(yol: str | Path) -> bool:
    """Yol data/gold ya da altındaysa True (tek koruma noktası).

    Yol `resolve()` edilir (göreli yol, "..", sembolik bağ); ayrıca herhangi bir
    yerde ardışık "data/gold" parçaları harf farkı gözetmeden aranır.
    """
    gold = GOLD.resolve()
    for aday in (Path(yol).absolute(), Path(yol).resolve()):
        if aday == gold or gold in aday.parents:
            return True
        parcalar = [p.casefold() for p in aday.parts]
        if any(a == "data" and b == "gold" for a, b in zip(parcalar, parcalar[1:])):
            return True
    return False


def aile(belge_etiketi: str) -> str:
    """Revizyon ailesi: standart numarası. Ön ek (MIL-S, MIL-PRF) ve revizyon harfi yok sayılır."""
    m = re.fullmatch(r".*-(\d+)[A-Z]", belge_etiketi)
    if not m:
        raise ValueError(f"belge etiketi 'MIL-PRF-23377K' biçiminde olmalı: {belge_etiketi!r}")
    return m.group(1)


def yariyi_sec(yeni: list[str], tohum: int) -> list[str]:
    """Yeni standartların ailelerinin rastgele yarısını (tekse yukarı yuvarlanır) seçer.

    Seçilen ailelerin bütün revizyonlarını sıralı döner. Girdi sırası önemsizdir.
    """
    aileler = sorted({aile(s) for s in yeni})
    secilen = set(random.Random(tohum).sample(aileler, (len(aileler) + 1) // 2))
    return sorted(s for s in yeni if aile(s) in secilen)


@dataclass(frozen=True)
class Bolunme:
    gelistirme: list[str] = field(default_factory=list)
    yeni_standartlar: list[str] = field(default_factory=list)
    test: list[str] = field(default_factory=list)
    test_durumu: TestDurumu = "bekliyor"
    tohum: int = 0
    test_kumesi_acik: bool = False
    kilitli_klasorler: list[str] = field(default_factory=list)
    ocr_gerekli: list[str] = field(default_factory=list)

    __test__ = False

    def belge_turu(self, belge_etiketi: str) -> str:
        """"taranmış" (OCR gerekli) ya da "metin"."""
        return TARANMIS if belge_etiketi in self.ocr_gerekli else METIN

    def turlere_ayir(self, belge_etiketleri) -> dict[str, list[str]]:
        """Raporlama için belgeleri metin tabanlı ve taranmış diye ayırır; sıra korunur.

        Taranmış belgeler sonuç tablolarına karışmaz; ayrı bir grupta
        "OCR gerekli" diye gösterilir.
        """
        gruplar: dict[str, list[str]] = {METIN: [], TARANMIS: []}
        for etiket in belge_etiketleri:
            gruplar[self.belge_turu(etiket)].append(etiket)
        return gruplar

    def yol_kilitli_mi(self, yol: str | Path) -> bool:
        """Yol kilitli bir klasörün içindeyse ve test kümesi kapalıysa True.

        Yol hem olduğu gibi (mutlak) hem `resolve()` edilmiş hâliyle denetlenir;
        göreli yol, sembolik bağ ve harf farkı ("GERCEK_COC_HAVACILIK") kilidi atlatamaz.
        """
        if self.test_kumesi_acik:
            return False
        kilitli = {k.casefold() for k in self.kilitli_klasorler}
        yol = Path(yol)
        parcalar = {p.casefold() for y in (yol.absolute(), yol.resolve()) for p in y.parent.parts}
        return bool(kilitli & parcalar)

    def _kilitli_ham_dosya_mi(self, dosya: Path, ham_klasor: Path) -> bool:
        etiket = dosya_etiketi(dosya)
        if etiket is not None and self.kume(etiket) in ("test", "bekliyor"):
            return True
        kilitli = {k.casefold() for k in self.kilitli_klasorler}
        try:
            goreli = dosya.relative_to(ham_klasor)
        except ValueError:
            return False
        return any(p.casefold() in kilitli for p in goreli.parent.parts)

    def icerik_kilitli_mi(self, yol: str | Path, ham_klasor: str | Path | None = None) -> bool:
        """Belgenin baytları test kümesindeki ya da kilitli klasördeki bir PDF'le aynıysa True.

        `VARSAYILAN_HAM` (data/raw) her zaman taranır; `ham_klasor` verilirse
        yalnız ek klasördür (ikisinin birleşimi). Verilen ek klasör yoksa ya da
        klasör değilse ValueError. Taranan klasörlerin altındaki (özyinelemeli)
        PDF'lerden dosya adı etiketi test kümesinde (ya da bölünmeyi bekleyen)
        olanlar ve kilitli klasördekiler aday alınır. Yalnız boyutu aynı olan
        adayların SHA-256 özeti hesaplanır (önbelleklenir); içerik çıkarılmaz.
        Yalnız bayt bayt aynı kopya yakalanır. Test kilidi açıkken hep False.
        """
        klasorler = _ham_klasorleri(ham_klasor)
        if self.test_kumesi_acik:
            return False
        yol = Path(yol)
        if not yol.is_file():
            return False
        boyut = yol.stat().st_size
        ozet = None
        for ham in klasorler:
            for aday in ham.rglob("*"):
                if aday.suffix.casefold() != ".pdf" or not aday.is_file():
                    continue
                if aday.stat().st_size != boyut or not self._kilitli_ham_dosya_mi(aday, ham):
                    continue
                ozet = ozet or _dosya_ozeti(yol)
                if _dosya_ozeti(aday) == ozet:
                    return True
        return False

    def belgeyi_denetle(self, yol: str | Path, verilen_etiket: str | None = None, ocr: bool = False,
                        ham_klasor: str | Path | None = None) -> str:
        """Belgenin kullanılabileceğini denetler ve etiketini döner.

        Sıra: yol kilidi, içerik kilidi (test belgesinin kopyası / bağı), dosya
        adından çözülen etiket, verilen etiket. Verilen etiket dosya adındakiyle
        uyuşmazsa ya da ikisi de yoksa ValueError; kilitlerde TestKumesiKilitli,
        taranmış belgede (`ocr=False`) OcrGerekli. İçerik kilidi data/raw'ı her
        zaman, `ham_klasor`'ü ek olarak tarar; ek klasör yoksa ValueError.
        """
        _ham_klasorleri(ham_klasor)  # ek klasör geçersizse kilit denetiminden önce bildir
        self.yol_kullanima_izin_ver(yol)
        if self.icerik_kilitli_mi(yol, ham_klasor):
            raise TestKumesiKilitli(
                f"{yol} içeriği test kümesindeki (ya da kilitli klasördeki) bir belgeyle aynı; "
                "dil modeli çıkarıcısı dondurulana kadar açılmaz (data/bolunme.yaml, test_kumesi_acik: false)"
            )
        dosyadaki = dosya_etiketi(yol)
        if dosyadaki is not None:
            self.kullanima_izin_ver(dosyadaki, ocr=ocr)
        if verilen_etiket is not None:
            self.kullanima_izin_ver(verilen_etiket, ocr=ocr)
        if dosyadaki is not None and verilen_etiket is not None and dosyadaki != verilen_etiket:
            raise ValueError(f"dosya adındaki etiket ({dosyadaki}) verilen etiketle ({verilen_etiket}) uyuşmuyor")
        etiket = verilen_etiket or dosyadaki
        if etiket is None:
            raise ValueError(f"dosya adından etiket çözülemedi ve etiket verilmedi: {yol}")
        return etiket

    def yol_kullanima_izin_ver(self, yol: str | Path) -> None:
        """Kilitli klasördeki belge kullanılmak istenirse hata verir."""
        if self.yol_kilitli_mi(yol):
            raise TestKumesiKilitli(
                f"{yol} test kümesinde (kilitli klasör); dil modeli çıkarıcısı dondurulana kadar açılmaz "
                "(data/bolunme.yaml, test_kumesi_acik: false)"
            )

    def kume(self, belge_etiketi: str) -> Kume | None:
        if belge_etiketi in self.test:
            return "test"
        if belge_etiketi in self.yeni_standartlar and self.test_durumu == "bekliyor":
            return "bekliyor"
        if belge_etiketi in self.gelistirme:
            return "gelistirme"
        return None

    def kullanima_izin_ver(self, belge_etiketi: str, ocr: bool = False) -> Kume:
        """Standart kullanılabiliyorsa kümesini döner, değilse hata verir.

        `ocr=True` iken taranmış (`ocr_gerekli`) belgeler kabul edilir; test
        kümesi kilidi bundan önce denetlenir.
        """
        kume = self.kume(belge_etiketi)
        if kume is None:
            raise ValueError(f"{belge_etiketi} data/bolunme.yaml içinde yok; önce yeni_standartlar ya da gelistirme listesine ekle")
        if kume == "bekliyor":
            raise TestKumesiKilitli(
                f"{belge_etiketi} yeni standart; test kümesi seçilene kadar bakılmaz (python deney/bolunme.py --sec)"
            )
        if kume == "test" and not self.test_kumesi_acik:
            raise TestKumesiKilitli(
                f"{belge_etiketi} test kümesinde; dil modeli çıkarıcısı dondurulana kadar çıkarıcı çalıştırılmaz, "
                "taslak cevap hazırlanmaz (data/bolunme.yaml, test_kumesi_acik: false)"
            )
        if belge_etiketi in self.ocr_gerekli and not ocr:
            raise OcrGerekli(
                f"{belge_etiketi} taranmış bir PDF ({OCR_GEREKLI}); OCR'sız çıkarıcı çalıştırılmaz, "
                "--ocr ile okunur (data/bolunme.yaml, ocr_gerekli)"
            )
        return kume

    def secimi_yap(self) -> Bolunme:
        """Bekleyen yeni standartları tohumla böler: yarısı teste, kalanı geliştirmeye."""
        if self.test_durumu != "bekliyor":
            raise ValueError("test kümesi zaten seçilmiş")
        if not self.yeni_standartlar:
            raise ValueError("yeni_standartlar boş; bölünecek standart yok")
        test = yariyi_sec(self.yeni_standartlar, self.tohum)
        kalan = [b for b in sorted(self.yeni_standartlar) if b not in test]
        return replace(self, gelistirme=self.gelistirme + kalan, test=test, test_durumu="secildi")


def _ayristir(metin: str) -> dict[str, object]:
    veri: dict[str, object] = {}
    liste: list[str] | None = None
    for no, satir in enumerate(metin.splitlines(), 1):
        satir = satir.split("#", 1)[0].rstrip()
        if not satir.strip():
            continue
        if m := re.fullmatch(r"\s+-\s+(\S+)", satir):
            if liste is None:
                raise ValueError(f"satır {no}: liste öğesi bir liste anahtarının altında olmalı")
            liste.append(m.group(1))
            continue
        m = re.fullmatch(r"([a-z_]+):\s*(\S*)", satir)
        if not m:
            raise ValueError(f"satır {no}: tanınmayan satır: {satir!r}")
        anahtar, deger = m.groups()
        if anahtar in veri:
            raise ValueError(f"satır {no}: {anahtar} iki kez yazılmış")
        liste = None
        if deger == "":
            liste = []
            veri[anahtar] = liste
        elif deger in ("true", "false"):
            veri[anahtar] = deger == "true"
        elif re.fullmatch(r"\d+", deger):
            veri[anahtar] = int(deger)
        elif re.fullmatch(r"[a-z_]+", deger):
            veri[anahtar] = deger
        else:
            raise ValueError(f"satır {no}: {anahtar} için tanınmayan değer: {deger!r}")
    return veri


def _tur(veri: dict, anahtar: str, tur: type, varsayilan):
    deger = veri.get(anahtar, varsayilan)
    if type(deger) is not tur:
        raise ValueError(f"{anahtar} {tur.__name__} olmalı: {deger!r}")
    return deger


def bolunme_oku(yol: str | Path = VARSAYILAN_YOL) -> Bolunme:
    veri = _ayristir(Path(yol).read_text(encoding="utf-8"))
    bilinmeyen = set(veri) - set(ANAHTARLAR)
    if bilinmeyen:
        raise ValueError(f"bilinmeyen anahtarlar: {sorted(bilinmeyen)}")
    b = Bolunme(
        gelistirme=list(_tur(veri, "gelistirme", list, [])),
        yeni_standartlar=list(_tur(veri, "yeni_standartlar", list, [])),
        test=list(_tur(veri, "test", list, [])),
        test_durumu=_tur(veri, "test_durumu", str, "bekliyor"),
        tohum=_tur(veri, "tohum", int, 0),
        test_kumesi_acik=_tur(veri, "test_kumesi_acik", bool, False),
        kilitli_klasorler=list(_tur(veri, "kilitli_klasorler", list, [])),
        ocr_gerekli=list(_tur(veri, "ocr_gerekli", list, [])),
    )
    hatali_klasor = [k for k in b.kilitli_klasorler if not KLASOR_ADI.match(k) or k in (".", "..")]
    if hatali_klasor:
        raise ValueError(f"kilitli_klasorler yalnız klasör adı içermeli (yol değil): {hatali_klasor}")
    if b.test_durumu not in ("bekliyor", "secildi"):
        raise ValueError(f"test_durumu 'bekliyor' ya da 'secildi' olmalı: {b.test_durumu!r}")
    hepsi = b.gelistirme + b.yeni_standartlar + b.test
    hatali = [x for x in hepsi + b.ocr_gerekli if not BELGE_ETIKETI.match(x)]
    if hatali:
        raise ValueError(f"belge etiketi 'MIL-PRF-23377K' biçiminde olmalı: {hatali}")
    bolunmede_yok = sorted(set(b.ocr_gerekli) - set(hepsi))
    if bolunmede_yok:
        raise ValueError(f"ocr_gerekli içindekiler bir kümede olmalı (taranmış belge kümeden çıkarılmaz): {bolunmede_yok}")
    for ad, liste in (("gelistirme", b.gelistirme), ("yeni_standartlar", b.yeni_standartlar), ("test", b.test),
                      ("ocr_gerekli", b.ocr_gerekli)):
        tekrar = sorted({x for x in liste if liste.count(x) > 1})
        if tekrar:
            raise ValueError(f"{ad} içinde tekrar edenler: {tekrar}")
    if b.test_durumu == "bekliyor":
        if b.test:
            raise ValueError("test_durumu bekliyor iken test listesi boş olmalı")
        cakisan = sorted(set(b.yeni_standartlar) & set(b.gelistirme))
        if cakisan:
            raise ValueError(f"bölünmeyi bekleyen standartlar geliştirme kümesinde olamaz: {cakisan}")
        _aile_ortak_mi(b.yeni_standartlar, b.gelistirme, "bölünmeyi bekleyen")
        if b.test_kumesi_acik:
            raise ValueError("test kümesi seçilmeden kilit açılamaz")
    else:
        beklenen = yariyi_sec(b.yeni_standartlar, b.tohum)
        if sorted(b.test) != beklenen:
            raise ValueError(f"test listesi tohum {b.tohum} ile yapılan seçimle uyuşmuyor; beklenen: {beklenen}")
        kalan = set(b.yeni_standartlar) - set(b.test)
        if not kalan <= set(b.gelistirme) or set(b.test) & set(b.gelistirme):
            raise ValueError("seçilmeyen yeni standartlar geliştirme kümesinde, seçilenler yalnız test kümesinde olmalı")
        _aile_ortak_mi(b.test, b.gelistirme, "test kümesindeki")
    return b


def _aile_ortak_mi(liste: list[str], gelistirme: list[str], ad: str) -> None:
    ortak = sorted({aile(s) for s in liste} & {aile(s) for s in gelistirme})
    if ortak:
        raise ValueError(f"{ad} standartlar geliştirme kümesindekilerle aynı ailede olamaz (revizyonlar birlikte bölünür): {ortak}")


def bolunme_yaz(b: Bolunme, yol: str | Path) -> None:
    """Değerleri dosyada yerinde günceller; açıklama yorumlarına dokunmaz."""
    yol = Path(yol)
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    degerler = {
        "test_kumesi_acik": "true" if b.test_kumesi_acik else "false",
        "test_durumu": b.test_durumu,
        "tohum": str(b.tohum),
    }
    listeler = {"gelistirme": b.gelistirme, "yeni_standartlar": b.yeni_standartlar, "test": b.test,
                "kilitli_klasorler": b.kilitli_klasorler, "ocr_gerekli": b.ocr_gerekli}
    cikti: list[str] = []
    atla = False
    for satir in satirlar:
        govde = satir.split("#", 1)[0]
        if atla and re.fullmatch(r"\s+-\s+\S+\s*", govde):
            continue
        atla = False
        m = re.fullmatch(r"([a-z_]+):\s*(\S*)\s*", govde)
        if m and m.group(1) in degerler:
            cikti.append(f"{m.group(1)}: {degerler[m.group(1)]}")
        elif m and m.group(1) in listeler:
            cikti.append(f"{m.group(1)}:")
            cikti += [f"  - {x}" for x in listeler[m.group(1)]]
            atla = True
        else:
            cikti.append(satir)
    yol.write_text("\n".join(cikti) + "\n", encoding="utf-8")


def betik_korumasi(belge_etiketi: str, yol: str | Path = VARSAYILAN_YOL, betik: str = "",
                   ocr: bool = False) -> int | None:
    """Betikler için: standart kullanılamıyorsa nedenini stderr'e yazar ve 2 döner; kullanılabiliyorsa None.

    `ocr=True` taranmış belgeleri geçirir; test kümesi kilidi yine önce gelir.
    """
    try:
        bolunme_oku(yol).kullanima_izin_ver(belge_etiketi, ocr=ocr)
    except (TestKumesiKilitli, ValueError) as hata:  # OcrGerekli de ValueError'dır
        print(f"{betik or 'bolunme'}: {hata}", file=sys.stderr)
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description="Geliştirme / test bölünmesini denetler ya da test kümesini seçer.")
    ayr.add_argument("--yol", default=str(VARSAYILAN_YOL))
    ayr.add_argument("--sec", action="store_true", help="Bekleyen yeni standartları tohumla böl ve dosyaya yaz")
    ayr.add_argument("--turler", action="store_true", help="Kümeleri metin tabanlı / taranmış diye ayrı listele")
    args = ayr.parse_args(argv)
    b = bolunme_oku(args.yol)
    if args.sec:
        b = b.secimi_yap()
        bolunme_yaz(b, args.yol)
        assert bolunme_oku(args.yol) == b
    print(f"geliştirme: {len(b.gelistirme)}, test: {len(b.test)} ({b.test_durumu}), "
          f"bekleyen yeni: {len(b.yeni_standartlar) if b.test_durumu == 'bekliyor' else 0}, "
          f"test kilidi: {'açık' if b.test_kumesi_acik else 'kapalı'}")
    if b.ocr_gerekli:
        print(f"{OCR_GEREKLI} (taranmış): {', '.join(b.ocr_gerekli)}")
    if args.turler:
        print(turler_tablosu(b))
    return 0


def turler_tablosu(b: Bolunme) -> str:
    """Her küme için metin tabanlı ve taranmış belgeleri ayrı satırlarda gösteren Markdown tablosu."""
    satirlar = ["| Küme | Tür | Sayı | Belgeler |", "|---|---|---|---|"]
    for kume, liste in (("geliştirme", b.gelistirme), ("test", b.test)):
        for tur, belgeler in b.turlere_ayir(liste).items():
            ad = f"{tur} ({OCR_GEREKLI})" if tur == TARANMIS else "metin tabanlı"
            satirlar.append(f"| {kume} | {ad} | {len(belgeler)} | {', '.join(belgeler) or '-'} |")
    return "\n".join(satirlar)


if __name__ == "__main__":
    sys.exit(main())
