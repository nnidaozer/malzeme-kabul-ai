"""Kabul dokümanı şeması.

Standarttan çıkarılan her şart burada tanımlı bir modele oturur. Her şart,
dayandığı standart maddesini (`Kaynak`) taşımak zorundadır; kabul dokümanında
her satırın yanında bu madde numarası gösterilir.

Her şart kendi kaynak belgesini ve revizyonunu taşır; böylece aynı kabul
dokümanında askeri standart ile müşteri şartnamesi birlikte bulunabilir ve
revizyon takibinde şartın hangi revizyondan geldiği bilinir.

Şema değeri, birimi (pint'in tanıdığı biçimde) ve standarttaki özgün metni
tutar. Birim dönüşümü ve sınır karşılaştırması ayrı modüllerde kesin
kurallarla yapılır (CLAUDE.md, kural 1).

Çapraz kontrolde tedarikçi sertifikası yalnızca kabul (conformance) testlerine
göre denetlenir (`KabulDokumani.kabul_testleri`); yeterlilik testleri aranmaz.

Ürün tanımı (tip, sınıf, kompozisyon; etiketleme kılavuzu K2) şart değildir,
`KabulDokumani.urun_tanimi` alanında durur. Her şart (test, koşul, raf ömrü,
numune hazırlığı) hangi tip/sınıf için geçerli olduğunu `uygulanabilirlik`
alanında taşır; ürün tanımı doluysa bu alandaki her değer orada tanımlı
olmalıdır. Bkz. docs/mimari.md.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from malzeme_kabul.kural.birimler import birimi_coz, zaman_birimi_mi

# "3.5.1", "4.6.12.3", ek maddeleri "A.3.1" ya da "TABLE I", "TABLE IV".
MADDE_KALIBI = re.compile(r"^(([A-Z]\.)?\d+(\.\d+)*|TABLE [IVXLC]+)$")

TestTuru = Literal["kabul", "omur_uzatma", "yeterlilik"]
"""kabul: her partide yapılan kabul (conformance) testi.
omur_uzatma: raf ömrü dolan malzemenin ömrünü uzatmak için tekrarlanan test.
yeterlilik: yalnızca ürün yeterliliğinde (qualification) yapılan test."""

KriterTuru = Literal["sayisal", "gecti_kaldi", "metinsel"]
"""sayisal: alt ve/veya üst sınırı olan ölçüm.
gecti_kaldi: sayısal değeri olmayan, geçti/kaldı sonucu veren test.
metinsel: "kabarma olmayacak" gibi sözel kriter."""
KosulKategorisi = Literal["depolama", "kullanim"]

SinirYonu = Literal["en_az", "en_cok", "aralik", "tam", "belirsiz"]
"""Sayısal sınırın yönü. en_az: yalnız alt; en_cok: yalnız üst; aralik: alt < üst;
tam: alt == üst. belirsiz: standart metninden "en az" mı "tam" mı olduğu
anlaşılmıyor (ör. MIL-PRF-23377K 3.11); karar motoru bu şartlara karar vermez,
insan incelemesine gönderir."""

SonucKaynagi = Literal["coc", "ic_laboratuvar"]
"""Test sonucunun nereden geldiği. coc: tedarikçinin CoC / test raporu
(varsayılan); ic_laboratuvar: sonuç iç laboratuvarda ölçülür ve ekrandan girilir."""

UYGULANABILIRLIK_ACIKLAMASI = (
    "Şartın geçerli olduğu tip/sınıf/kompozisyon kodları, ör. ['Class N'] "
    "('Chromium content (class N only)'). Boşsa bütün tip ve sınıflar için geçerlidir."
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Kaynak(_Model):
    """Şartın dayandığı standart maddesi."""

    belge_no: str = Field(min_length=1, examples=["MIL-PRF-23377", "MUSTERI-SPEC-001"])
    revizyon: str = Field(min_length=1, examples=["K"])
    madde: str = Field(min_length=1, examples=["3.5.1", "TABLE I"])
    sayfa: int | None = Field(default=None, ge=1)
    alinti: str | None = Field(default=None, description="Standarttaki özgün cümle.")

    @field_validator("madde")
    @classmethod
    def _madde_bicimi(cls, deger: str) -> str:
        if not MADDE_KALIBI.match(deger):
            raise ValueError(f"madde numarası '3.5.1' ya da 'TABLE I' biçiminde olmalı: {deger!r}")
        return deger

    @property
    def belge_etiketi(self) -> str:
        """MIL belgelerinde 'MIL-PRF-23377K', diğerlerinde 'X Rev. B'."""
        if self.belge_no.startswith("MIL-"):
            return f"{self.belge_no}{self.revizyon}"
        return f"{self.belge_no} Rev. {self.revizyon}"

    @property
    def etiket(self) -> str:
        return f"{self.belge_etiketi}, {self.madde}"


class Sinir(_Model):
    """Bir test ya da koşulun kabul kriteri.

    Sayısal kriterde alt ve üst sınır isteğe bağlıdır ama en az biri bulunur:
    yalnız alt "en az", yalnız üst "en çok", ikisi eşitse tam değer demektir.
    Birim pint'in tanıdığı biçimde yazılır ("°C", "g/L", "mil"; "mil" inç/1000 olarak
    okunur, bkz. `birimler.pint_ifadesi`). Geçti/kaldı ve
    metinsel kriterler sayı ya da birim almaz. Her durumda standarttaki özgün
    metin saklanır.
    """

    kriter_turu: KriterTuru
    alt: float | None = None
    ust: float | None = None
    alt_dahil: bool = True
    ust_dahil: bool = True
    birim: str | None = Field(default=None, description="pint biçiminde birim, ör. '°C', 'g/L'.")
    yon: SinirYonu | None = Field(
        default=None,
        description="Yalnız sayısal kriterde. Boşsa alt/üst sınırdan çıkarılır; 'belirsiz' insan incelemesi ister.",
    )
    orijinal_metin: str = Field(min_length=1, description="Standarttaki kriter metni.")

    @field_validator("birim")
    @classmethod
    def _pint_birimi(cls, deger: str | None) -> str | None:
        if deger is None or deger == "":
            return None
        birimi_coz(deger)  # tanınmazsa ValueError
        return deger

    @model_validator(mode="after")
    def _kriter_ile_tutarli(self) -> Sinir:
        if self.kriter_turu == "sayisal":
            if self.alt is None and self.ust is None:
                raise ValueError("sayısal kriter için alt ya da üst sınırdan en az biri gerekli")
            if self.alt is not None and self.ust is not None and self.alt > self.ust:
                raise ValueError(f"alt sınır üst sınırdan büyük: {self.alt} > {self.ust}")
            if self.yon not in (None, "belirsiz") and self.yon != self._turetilmis_yon():
                raise ValueError(
                    f"yön '{self.yon}' alt/üst sınırla uyuşmuyor (alt={self.alt}, üst={self.ust}); "
                    "emin değilsen 'belirsiz' yaz"
                )
        elif self.alt is not None or self.ust is not None or self.birim is not None:
            raise ValueError(f"'{self.kriter_turu}' kriteri sayı ya da birim almaz")
        elif self.yon is not None:
            raise ValueError(f"'{self.kriter_turu}' kriteri yön almaz")
        return self

    def _turetilmis_yon(self) -> SinirYonu:
        if self.alt is not None and self.ust is not None:
            return "tam" if self.alt == self.ust else "aralik"
        return "en_az" if self.alt is not None else "en_cok"

    @property
    def yonu(self) -> SinirYonu | None:
        """Sınırın yönü: açıkça yazılmışsa o, değilse alt/üst sınırdan çıkarılan. Sayısal değilse None."""
        if self.kriter_turu != "sayisal":
            return None
        return self.yon or self._turetilmis_yon()

    @property
    def yon_belirsiz(self) -> bool:
        return self.yon == "belirsiz"


class NumuneHazirlama(_Model):
    """Kupon, uygulama ve kürlenme bilgileri. Testler buna `id` ile bağlanır."""

    id: str = Field(min_length=1)
    kupon_malzemesi: str | None = None
    kupon_boyutu: str | None = None
    yuzey_hazirligi: str | None = None
    uygulama_yontemi: str | None = None
    kuru_film_kalinligi: Sinir | None = None
    kurlenme: str | None = Field(default=None, description="Süre ve koşul, ör. '7 gün, 77 °F, %50 BN'.")
    uygulanabilirlik: list[str] = Field(default_factory=list, description=UYGULANABILIRLIK_ACIKLAMASI)
    kaynak: Kaynak


class TestSarti(_Model):
    """Kabul dokümanındaki tek bir test satırı."""

    __test__ = False  # pytest bu sınıfı test sınıfı sanmasın

    id: str = Field(min_length=1, description="Belge içinde benzersiz kısa ad, ör. 'viskozite'.")
    test_adi: str = Field(min_length=1, description="Şartın gerçekten kapsadığı test, ör. 'Cadmium content'.")
    kaynak_tablo_adi: str | None = Field(
        default=None,
        description=(
            "Test tablosundaki satır adı, test adından farklıysa. Ör. 3.4'teki ≤ 1 ppm şartı yalnız "
            "kadmiyum içindir: test_adi 'Cadmium content', kaynak_tablo_adi 'Lead and cadmium content'."
        ),
    )
    test_metodu: str | None = Field(default=None, examples=["ASTM D 1200", "FED-STD-141 Method 4321"])
    metot_kaynagi: Kaynak | None = Field(default=None, description="Test metodunu anlatan madde, ör. 4.6.3.")
    sinir: Sinir
    kaynak: Kaynak = Field(description="Şartın yazdığı madde (3.x ya da tablo).")
    test_turleri: set[TestTuru] = Field(min_length=1)
    uygulanabilirlik: list[str] = Field(default_factory=list, description=UYGULANABILIRLIK_ACIKLAMASI)
    sonuc_kaynagi: SonucKaynagi = Field(
        default="coc", description="Sonuç CoC'den mi gelir, iç laboratuvarda mı ölçülür. Varsayılan CoC."
    )
    numune_hazirlama_id: str | None = None

    @model_validator(mode="after")
    def _tablo_adi_farkli(self) -> TestSarti:
        if self.kaynak_tablo_adi and self.kaynak_tablo_adi.casefold() == self.test_adi.casefold():
            self.kaynak_tablo_adi = None  # aynıysa tekrar tutulmaz
        return self

    @field_serializer("test_turleri")
    def _sirali_turler(self, turler: set[str]) -> list[str]:
        return sorted(turler)  # JSON çıktısı her çalıştırmada aynı olsun

    @property
    def kabul_testi(self) -> bool:
        return "kabul" in self.test_turleri

    @property
    def omur_uzatma_testi(self) -> bool:
        return "omur_uzatma" in self.test_turleri


class RafOmru(_Model):
    """Raf ömrü: süre, zaman birimi (pint) ve depolama koşulu (ör. 4–38 °C).

    Raf ömrü kap türüne göre değişebilir (ör. metal kap 1 yıl, plastik kap 6
    ay); her kap türü ayrı bir kayıttır. `kap_turu` boşsa kayıt bütün kaplar
    için geçerlidir.
    """

    kap_turu: str | None = Field(default=None, examples=["metal", "plastik"])
    sure: float = Field(gt=0)
    birim: str = Field(examples=["month", "day", "year"])
    kosul: Sinir | None = Field(default=None, description="Raf ömrünün geçerli olduğu koşul, ör. sıcaklık aralığı.")
    baslangic: str | None = Field(default=None, description="Ör. 'üretim tarihinden itibaren'.")
    uygulanabilirlik: list[str] = Field(default_factory=list, description=UYGULANABILIRLIK_ACIKLAMASI)
    kaynak: Kaynak

    @field_validator("birim")
    @classmethod
    def _zaman_birimi(cls, deger: str) -> str:
        if not zaman_birimi_mi(deger):
            raise ValueError(f"raf ömrü birimi pint'in tanıdığı bir zaman birimi olmalı: {deger!r}")
        return deger


class Kosul(_Model):
    """Depolama ya da kullanım koşulu (sıcaklık, kap ömrü, indüksiyon süresi...)."""

    kategori: KosulKategorisi
    ad: str = Field(min_length=1)
    sinir: Sinir | None = None
    aciklama: str | None = None
    uygulanabilirlik: list[str] = Field(default_factory=list, description=UYGULANABILIRLIK_ACIKLAMASI)
    kaynak: Kaynak

    @model_validator(mode="after")
    def _sinir_ya_da_aciklama(self) -> Kosul:
        if self.sinir is None and not self.aciklama:
            raise ValueError("koşul için 'sinir' ya da 'aciklama' gerekli")
        return self


def _kod_anahtari(kod: str) -> str:
    """'class  n' ve 'Class N' aynı koddur."""
    return " ".join(kod.split()).casefold()


class TanimKaydi(_Model):
    """Ürün tanımındaki tek bir tip, sınıf ya da kompozisyon."""

    kod: str = Field(min_length=1, examples=["Type I", "Class N"])
    aciklama: str | None = Field(default=None, examples=["Non-chromate inhibitors"])
    kaynak: Kaynak


class UrunTanimi(_Model):
    """Standardın tanımladığı tip, sınıf ve kompozisyonlar (şart değildir; K2).

    Şartların `uygulanabilirlik` alanı bu kodlara başvurur. Katalogda her
    malzeme kodu tek bir tip/sınıf kombinasyonuna bağlanır (docs/mimari.md).
    """

    tipler: list[TanimKaydi] = Field(default_factory=list)
    siniflar: list[TanimKaydi] = Field(default_factory=list)
    kompozisyonlar: list[TanimKaydi] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kodlar_benzersiz(self) -> UrunTanimi:
        anahtarlar = [_kod_anahtari(k.kod) for k in self.tipler + self.siniflar + self.kompozisyonlar]
        tekrar = sorted({a for a in anahtarlar if anahtarlar.count(a) > 1})
        if tekrar:
            raise ValueError(f"ürün tanımında tekrar eden kodlar: {tekrar}")
        return self

    def kod_tanimli_mi(self, kod: str) -> bool:
        return _kod_anahtari(kod) in {
            _kod_anahtari(k.kod) for k in self.tipler + self.siniflar + self.kompozisyonlar
        }


class StandartBilgisi(_Model):
    """Dokümanın üretildiği ana standart."""

    belge_no: str = Field(min_length=1)
    revizyon: str = Field(min_length=1)
    baslik: str | None = None
    tarih: str | None = None


class KabulDokumani(_Model):
    """Bir malzeme standardından üretilen kabul dokümanı."""

    standart: StandartBilgisi
    durum: Literal["taslak", "onaylandi"] = "taslak"
    urun_tanimi: UrunTanimi | None = Field(default=None, description="Tip, sınıf ve kompozisyon tanımları.")
    testler: list[TestSarti] = Field(default_factory=list)
    raf_omurleri: list[RafOmru] = Field(default_factory=list, description="Kap türüne göre raf ömrü kayıtları.")
    kosullar: list[Kosul] = Field(default_factory=list)
    numune_hazirlama: list[NumuneHazirlama] = Field(default_factory=list)

    @model_validator(mode="after")
    def _tutarlilik(self) -> KabulDokumani:
        idler = [t.id for t in self.testler]
        tekrar = sorted({i for i in idler if idler.count(i) > 1})
        if tekrar:
            raise ValueError(f"test kimlikleri benzersiz olmalı, tekrar edenler: {tekrar}")

        numune_idleri = {n.id for n in self.numune_hazirlama}
        for t in self.testler:
            if t.numune_hazirlama_id and t.numune_hazirlama_id not in numune_idleri:
                raise ValueError(f"{t.id}: bilinmeyen numune hazırlama kimliği {t.numune_hazirlama_id!r}")

        kaplar = [(r.kap_turu or "").casefold() for r in self.raf_omurleri]
        tekrar = sorted({k or "(genel)" for k in kaplar if kaplar.count(k) > 1})
        if tekrar:
            raise ValueError(f"her kap türü için tek raf ömrü kaydı olmalı, tekrar edenler: {tekrar}")

        if self.urun_tanimi is not None:
            sartlar = [
                *((f"test {t.id}", t.uygulanabilirlik) for t in self.testler),
                *((f"koşul {k.ad}", k.uygulanabilirlik) for k in self.kosullar),
                *((f"raf ömrü {r.kap_turu or '(genel)'}", r.uygulanabilirlik) for r in self.raf_omurleri),
                *((f"numune {n.id}", n.uygulanabilirlik) for n in self.numune_hazirlama),
            ]
            bilinmeyen = [
                f"{ad}: {kod!r}" for ad, kodlar in sartlar for kod in kodlar if not self.urun_tanimi.kod_tanimli_mi(kod)
            ]
            if bilinmeyen:
                raise ValueError(f"uygulanabilirlikte ürün tanımında olmayan kodlar: {bilinmeyen}")
        return self

    @property
    def kabul_testleri(self) -> list[TestSarti]:
        """Çapraz kontrolde sertifikada aranacak testler (yeterlilik testleri hariç)."""
        return [t for t in self.testler if t.kabul_testi]

    @property
    def omur_uzatma_testleri(self) -> list[TestSarti]:
        return [t for t in self.testler if t.omur_uzatma_testi]
