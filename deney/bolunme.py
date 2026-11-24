"""Standartların geliştirme / test bölünmesi (data/bolunme.yaml).

Kurallar (docs/mimari.md madde 7):

- Geliştirme kümesindeki standartlar serbestçe kullanılır.
- Yeni indirilen standartlar (`yeni_standartlar`) sabit bir tohumla ikiye
  bölünür: rastgele yarısı (tek sayıda yukarı yuvarlanır) test kümesine, kalanı
  geliştirme kümesine gider. Bölme `python deney/bolunme.py --sec` ile yapılır
  ve dosyaya yazılır; aynı tohum her zaman aynı seçimi verir ve okuma sırasında
  bu denetlenir.
- Bölme yapılana kadar (`test_durumu: bekliyor`) yeni standartların hiçbiri
  kullanılamaz; seçimden sonra test kümesi, `test_kumesi_acik: true` yazana
  kadar kullanılamaz. Bölünmede hiç olmayan standart da reddedilir, böylece yeni
  bir belge sessizce geliştirme kümesine karışmaz.

Çıkarıcı ve taslak cevap betikleri bir standardı işlemeden önce
`betik_korumasi` çağırır.

Dosya YAML'ın küçük bir alt kümesiyle yazılır (yorum, `anahtar: değer` ve
`- öğe` listeleri); bağımlılık kilidine yeni paket eklememek için burada okunur.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

VARSAYILAN_YOL = Path(__file__).resolve().parents[1] / "data" / "bolunme.yaml"
BELGE_ETIKETI = re.compile(r"^[A-Z]+(-[A-Z]+)?-\d+[A-Z]$")
Kume = Literal["gelistirme", "test", "bekliyor"]
TestDurumu = Literal["bekliyor", "secildi"]
ANAHTARLAR = ("test_kumesi_acik", "test_durumu", "tohum", "gelistirme", "yeni_standartlar", "test")


class TestKumesiKilitli(PermissionError):
    """Test kümesindeki (ya da bölünmeyi bekleyen) bir standart kullanılmak istendi."""

    __test__ = False


def yariyi_sec(yeni: list[str], tohum: int) -> list[str]:
    """Yeni standartların rastgele yarısını (tekse yukarı yuvarlanır) sıralı döner. Girdi sırası önemsizdir."""
    aday = sorted(yeni)
    return sorted(random.Random(tohum).sample(aday, (len(aday) + 1) // 2))


@dataclass(frozen=True)
class Bolunme:
    gelistirme: list[str] = field(default_factory=list)
    yeni_standartlar: list[str] = field(default_factory=list)
    test: list[str] = field(default_factory=list)
    test_durumu: TestDurumu = "bekliyor"
    tohum: int = 0
    test_kumesi_acik: bool = False

    __test__ = False

    def kume(self, belge_etiketi: str) -> Kume | None:
        if belge_etiketi in self.test:
            return "test"
        if belge_etiketi in self.yeni_standartlar and self.test_durumu == "bekliyor":
            return "bekliyor"
        if belge_etiketi in self.gelistirme:
            return "gelistirme"
        return None

    def kullanima_izin_ver(self, belge_etiketi: str) -> Kume:
        """Standart kullanılabiliyorsa kümesini döner, değilse hata verir."""
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
    )
    if b.test_durumu not in ("bekliyor", "secildi"):
        raise ValueError(f"test_durumu 'bekliyor' ya da 'secildi' olmalı: {b.test_durumu!r}")
    hepsi = b.gelistirme + b.yeni_standartlar + b.test
    hatali = [x for x in hepsi if not BELGE_ETIKETI.match(x)]
    if hatali:
        raise ValueError(f"belge etiketi 'MIL-PRF-23377K' biçiminde olmalı: {hatali}")
    for ad, liste in (("gelistirme", b.gelistirme), ("yeni_standartlar", b.yeni_standartlar), ("test", b.test)):
        tekrar = sorted({x for x in liste if liste.count(x) > 1})
        if tekrar:
            raise ValueError(f"{ad} içinde tekrar edenler: {tekrar}")
    if b.test_durumu == "bekliyor":
        if b.test:
            raise ValueError("test_durumu bekliyor iken test listesi boş olmalı")
        cakisan = sorted(set(b.yeni_standartlar) & set(b.gelistirme))
        if cakisan:
            raise ValueError(f"bölünmeyi bekleyen standartlar geliştirme kümesinde olamaz: {cakisan}")
        if b.test_kumesi_acik:
            raise ValueError("test kümesi seçilmeden kilit açılamaz")
    else:
        beklenen = yariyi_sec(b.yeni_standartlar, b.tohum)
        if sorted(b.test) != beklenen:
            raise ValueError(f"test listesi tohum {b.tohum} ile yapılan seçimle uyuşmuyor; beklenen: {beklenen}")
        kalan = set(b.yeni_standartlar) - set(b.test)
        if not kalan <= set(b.gelistirme) or set(b.test) & set(b.gelistirme):
            raise ValueError("seçilmeyen yeni standartlar geliştirme kümesinde, seçilenler yalnız test kümesinde olmalı")
    return b


def bolunme_yaz(b: Bolunme, yol: str | Path) -> None:
    """Değerleri dosyada yerinde günceller; açıklama yorumlarına dokunmaz."""
    yol = Path(yol)
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    degerler = {
        "test_kumesi_acik": "true" if b.test_kumesi_acik else "false",
        "test_durumu": b.test_durumu,
        "tohum": str(b.tohum),
    }
    listeler = {"gelistirme": b.gelistirme, "yeni_standartlar": b.yeni_standartlar, "test": b.test}
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


def betik_korumasi(belge_etiketi: str, yol: str | Path = VARSAYILAN_YOL, betik: str = "") -> int | None:
    """Betikler için: standart kullanılamıyorsa nedenini stderr'e yazar ve 2 döner; kullanılabiliyorsa None."""
    try:
        bolunme_oku(yol).kullanima_izin_ver(belge_etiketi)
    except (TestKumesiKilitli, ValueError) as hata:
        print(f"{betik or 'bolunme'}: {hata}", file=sys.stderr)
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description="Geliştirme / test bölünmesini denetler ya da test kümesini seçer.")
    ayr.add_argument("--yol", default=str(VARSAYILAN_YOL))
    ayr.add_argument("--sec", action="store_true", help="Bekleyen yeni standartları tohumla böl ve dosyaya yaz")
    args = ayr.parse_args(argv)
    b = bolunme_oku(args.yol)
    if args.sec:
        b = b.secimi_yap()
        bolunme_yaz(b, args.yol)
        assert bolunme_oku(args.yol) == b
    print(f"geliştirme: {len(b.gelistirme)}, test: {len(b.test)} ({b.test_durumu}), "
          f"bekleyen yeni: {len(b.yeni_standartlar) if b.test_durumu == 'bekliyor' else 0}, "
          f"test kilidi: {'açık' if b.test_kumesi_acik else 'kapalı'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
