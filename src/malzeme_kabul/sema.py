"""Kabul dokümanı şeması.

Standarttan çıkarılan her şart burada tanımlı bir modele oturur. Her şart,
dayandığı standart maddesini (`Kaynak`) taşımak zorundadır; kabul dokümanında
her satırın yanında bu madde numarası gösterilir.

Şema yalnızca değeri ve birimi olduğu gibi tutar. Birim dönüşümü ve sınır
karşılaştırması ayrı modüllerde kesin kurallarla yapılır (CLAUDE.md, kural 1).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# "3.5.1", "4.6.12.3" gibi paragraf numaraları ya da "TABLE I", "TABLE IV".
MADDE_KALIBI = re.compile(r"^(\d+(\.\d+)*|TABLE [IVXLC]+)$")

TestTuru = Literal["kabul", "omur_uzatma", "yeterlilik"]
"""kabul: her partide yapılan kabul (conformance) testi.
omur_uzatma: raf ömrü dolan malzemenin ömrünü uzatmak için tekrarlanan test.
yeterlilik: yalnızca ürün yeterliliğinde (qualification) yapılan test."""

SinirTuru = Literal["aralik", "en_az", "en_cok", "esit", "nitel"]
KosulKategorisi = Literal["depolama", "kullanim"]
SureBirimi = Literal["gün", "ay", "yıl"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Kaynak(_Model):
    """Şartın dayandığı standart maddesi."""

    standart: str = Field(min_length=1, examples=["MIL-PRF-23377"])
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
    def etiket(self) -> str:
        return f"{self.standart}{self.revizyon}, {self.madde}"


class Sinir(_Model):
    """Bir test ya da koşulun sınırı.

    - aralik: alt ≤ değer ≤ ust
    - en_az: değer ≥ alt
    - en_cok: değer ≤ ust
    - esit: değer = alt (ust boş)
    - nitel: sayısal olmayan şart, ör. "kabarma ya da kalkma olmamalı"
    """

    tur: SinirTuru
    alt: float | None = None
    ust: float | None = None
    alt_dahil: bool = True
    ust_dahil: bool = True
    birim: str | None = Field(default=None, description="Standartta yazdığı gibi, ör. 'g/L', '°F'.")
    ifade: str | None = Field(default=None, description="Nitel şartın metni.")

    @model_validator(mode="after")
    def _tur_ile_tutarli(self) -> Sinir:
        var = (self.alt is not None, self.ust is not None)
        beklenen = {
            "aralik": (True, True),
            "en_az": (True, False),
            "esit": (True, False),
            "en_cok": (False, True),
            "nitel": (False, False),
        }[self.tur]
        if var != beklenen:
            raise ValueError(f"'{self.tur}' sınırı için alt/ust dolu olmalı mı: {beklenen}, gelen: {var}")
        if self.tur == "aralik" and self.alt > self.ust:
            raise ValueError(f"alt sınır üst sınırdan büyük: {self.alt} > {self.ust}")
        if self.tur == "nitel" and not self.ifade:
            raise ValueError("nitel sınır 'ifade' ister")
        return self


class NumuneHazirlama(_Model):
    """Kupon, uygulama ve kürlenme bilgileri. Testler buna `id` ile bağlanır."""

    id: str = Field(min_length=1)
    kupon_malzemesi: str | None = None
    kupon_boyutu: str | None = None
    yuzey_hazirligi: str | None = None
    uygulama_yontemi: str | None = None
    kuru_film_kalinligi: Sinir | None = None
    kurlenme: str | None = Field(default=None, description="Süre ve koşul, ör. '7 gün, 77 °F, %50 BN'.")
    kaynak: Kaynak


class TestSarti(_Model):
    """Kabul dokümanındaki tek bir test satırı."""

    __test__ = False  # pytest bu sınıfı test sınıfı sanmasın

    id: str = Field(min_length=1, description="Belge içinde benzersiz kısa ad, ör. 'viskozite'.")
    test_adi: str = Field(min_length=1)
    test_metodu: str | None = Field(default=None, examples=["ASTM D 1200", "FED-STD-141 Method 4321"])
    metot_kaynagi: Kaynak | None = Field(default=None, description="Test metodunu anlatan madde (4.x).")
    sinir: Sinir
    kaynak: Kaynak = Field(description="Şartın yazdığı madde (3.x ya da tablo).")
    test_turleri: set[TestTuru] = Field(min_length=1)
    uygulanabilirlik: list[str] = Field(
        default_factory=list, description="Geçerli tip/sınıflar, ör. ['Type I', 'Class C2']. Boşsa hepsi."
    )
    numune_hazirlama_id: str | None = None

    @property
    def kabul_testi(self) -> bool:
        return "kabul" in self.test_turleri

    @property
    def omur_uzatma_testi(self) -> bool:
        return "omur_uzatma" in self.test_turleri


class RafOmru(_Model):
    sure: float = Field(gt=0)
    birim: SureBirimi
    baslangic: str | None = Field(default=None, description="Ör. 'üretim tarihinden itibaren'.")
    kaynak: Kaynak


class Kosul(_Model):
    """Depolama ya da kullanım koşulu (sıcaklık, kap ömrü, indüksiyon süresi...)."""

    kategori: KosulKategorisi
    ad: str = Field(min_length=1)
    sinir: Sinir | None = None
    aciklama: str | None = None
    kaynak: Kaynak

    @model_validator(mode="after")
    def _sinir_ya_da_aciklama(self) -> Kosul:
        if self.sinir is None and not self.aciklama:
            raise ValueError("koşul için 'sinir' ya da 'aciklama' gerekli")
        return self


class StandartBilgisi(_Model):
    standart: str = Field(min_length=1)
    revizyon: str = Field(min_length=1)
    baslik: str | None = None
    tarih: str | None = None


class KabulDokumani(_Model):
    """Bir malzeme standardından üretilen kabul dokümanı."""

    standart: StandartBilgisi
    durum: Literal["taslak", "onaylandi"] = "taslak"
    testler: list[TestSarti] = Field(default_factory=list)
    raf_omru: RafOmru | None = None
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

        std = self.standart.standart
        kaynaklar = [t.kaynak for t in self.testler] + [k.kaynak for k in self.kosullar]
        kaynaklar += [n.kaynak for n in self.numune_hazirlama]
        if self.raf_omru:
            kaynaklar.append(self.raf_omru.kaynak)
        yabanci = sorted({k.etiket for k in kaynaklar if k.standart != std})
        if yabanci:
            raise ValueError(f"başka standarda dayanan şartlar var ({std} bekleniyordu): {yabanci}")
        return self

    @property
    def kabul_testleri(self) -> list[TestSarti]:
        return [t for t in self.testler if t.kabul_testi]

    @property
    def omur_uzatma_testleri(self) -> list[TestSarti]:
        return [t for t in self.testler if t.omur_uzatma_testi]
