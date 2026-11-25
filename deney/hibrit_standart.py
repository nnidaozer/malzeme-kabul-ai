"""Deney: standart tarafında hibrit birleştirme (ürünün parçası değildir).

Ürün içindeki hibrit hat (`malzeme_kabul.hat.hibrit_hat`) yalnız sertifika
tarafındadır. Standart tarafı için hibrit, bu deneyde şöyle tanımlanır
(docs/mimari.md madde 6):

1. Kural öncelikli: kural çıkarıcısının bütün kayıtları (testler, raf ömrü,
   koşullar, numune hazırlama, ürün tanımı, standart bilgisi) aynen kalır.
2. Dil modeli tamamlar: kural testiyle eşleşmeyen dil modeli testi, özgün
   metni (`sinir.orijinal_metin`) modelin söylediği sayfada geçiyorsa eklenir;
   geçmiyorsa (ya da sayfa yoksa) kanıtsız sayılıp atılır.
3. Sınırı kural hesaplar: eklenen testin sınırı modelden alınmaz,
   `kural_cikarici.sinir_cikar` ile özgün metinden yeniden çıkarılır. Test adı,
   kaynak, test türleri ve uygulanabilirlik modelden gelir; numune bağlantısı boştur.
4. Anlaşmazlık sessiz geçmez: kuralla eşleşen, madde numarası aynı ve
   kanıtlı her dil modeli testinin sınırı kuralınkiyle karşılaştırılır. Tek
   hata tek kayıt: kriter türü farklıysa yalnız "kriter_turu"; değilse yön
   farklıysa yalnız "yon" (modelin "belirsiz" yönü yerine alt/üst'ten türetilen
   yön); değilse farklı olan her "alt", "ust", "birim" için bir kayıt. Madde
   numarası farklı çift eşleşmemiş sayılır, model testi kanıt yoluna gider.
   Güven skoru için birincil sayı `anlasmazlikli_test_sayisi`dır. Fark varsa kural
   testinin sayısal sınırı hibrit çıktıda `yon="belirsiz"` yapılır (sayılar
   korunur); karar motoru bunu insan incelemesine gönderir. Sayısal olmayan
   sınır işaretlenemez; test `isaretlenemeyen` listesine yazılır.

Karşılaştırma ve birim eşitliği kesin kurallarla yapılır (birimler pint ile
çözülür, sayılar küçük toleransla karşılaştırılır); dil modeline yaptırılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deney.degerlendirme import _Birim, degerler_esit
from deney.taslak_karsilastirma import kaydi_eslestir
from malzeme_kabul.belge.pdf_okuyucu import Belge
from malzeme_kabul.cikarim.kural_cikarici import metni_normallestir, sinir_cikar
from malzeme_kabul.kural.kanit_dogrulama import metin_sayfada_mi
from malzeme_kabul.sozlesme.sema import KabulDokumani, Sinir, TestSarti

SAYI_ALANLARI = ("alt", "ust", "birim")


@dataclass
class HibritRaporu:
    kural_test_sayisi: int = 0
    eklenen: list[str] = field(default_factory=list)
    kuralla_eslesen: list[str] = field(default_factory=list)  # dil modeli kimlikleri
    kanitsiz: list[tuple[str, str]] = field(default_factory=list)  # (dil modeli kimliği, neden)
    sayi_atildi: list[str] = field(default_factory=list)
    anlasmazliklar: list[dict[str, str]] = field(default_factory=list)
    isaretlenemeyen: list[str] = field(default_factory=list)  # anlaşmazlıklı ama sayısal olmayan kural testleri

    @property
    def anlasmazlik_sayisi(self) -> int:
        return len(self.anlasmazliklar)

    @property
    def anlasmazlikli_test_sayisi(self) -> int:
        return len({k["test_id"] for k in self.anlasmazliklar})

    def sozluk(self) -> dict[str, Any]:
        return {
            "kural_test_sayisi": self.kural_test_sayisi,
            "eklenen": list(self.eklenen),
            "kuralla_eslesen": list(self.kuralla_eslesen),
            "kanitsiz": [[id_, neden] for id_, neden in self.kanitsiz],
            "sayi_atildi": list(self.sayi_atildi),
            "anlasmazliklar": [dict(k) for k in self.anlasmazliklar],
            "anlasmazlik_sayisi": self.anlasmazlik_sayisi,
            "anlasmazlikli_test_sayisi": self.anlasmazlikli_test_sayisi,
            "isaretlenemeyen": list(self.isaretlenemeyen),
        }


def _kanit_nedeni(test: TestSarti, sayfalar: dict[int, str]) -> str | None:
    """Kanıt yoksa nedeni, varsa None. Özgün metin modelin söylediği sayfada aranır."""
    sayfa = test.kaynak.sayfa
    if sayfa is None:
        return "kaynak sayfası yok"
    metin = sayfalar.get(sayfa)
    if metin is None:
        return f"sayfa {sayfa} belgede yok"
    ozgun = test.sinir.orijinal_metin
    if metin_sayfada_mi(ozgun, metin) or metin_sayfada_mi(ozgun, metni_normallestir(metin)):
        return None
    return f"özgün metin sayfa {sayfa} metninde yok"


def _goster(deger: Any) -> str:
    if deger is None:
        return "-"
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger)


def _yon(s: Sinir) -> str | None:
    """Sınırın yönü; "belirsiz" ise (ör. yön doğrulamasının koyduğu) alt/üst'ten türetilen yön."""
    if s.kriter_turu != "sayisal":
        return None
    return s._turetilmis_yon() if s.yon == "belirsiz" else s.yonu


def _madde(madde: str) -> str:
    return " ".join(madde.split()).casefold()


def _esit(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return degerler_esit(a, b)


def _sinir_anlasmazliklari(kural: TestSarti, model: TestSarti) -> list[dict[str, str]]:
    """Tek hata tek kayıt: kriter türü farkı, yoksa yön farkı, yoksa alt/üst/birim farkları."""
    k, m = kural.sinir, model.sinir

    def kayit(alan: str, a: Any, b: Any) -> dict[str, str]:
        return {"test_id": kural.id, "model_id": model.id, "alan": alan, "kural": _goster(a),
                "model": _goster(b), "kural_madde": kural.kaynak.madde, "model_madde": model.kaynak.madde}

    if k.kriter_turu != m.kriter_turu:
        return [kayit("kriter_turu", k.kriter_turu, m.kriter_turu)]
    if _yon(k) != _yon(m):
        return [kayit("yon", _yon(k), _yon(m))]
    farklar = []
    for alan in SAYI_ALANLARI:
        a, b = getattr(k, alan), getattr(m, alan)
        if alan == "birim":
            a, b = (_Birim(x) if x is not None else None for x in (a, b))
        if not _esit(a, b):
            farklar.append(kayit(alan, a, b))
    return farklar


def hibrit_birlestir(
    kural: KabulDokumani, dil: KabulDokumani, belge: Belge
) -> tuple[KabulDokumani, HibritRaporu]:
    """Kural çıktısını temel alır, dil modelinin kanıtlı ek testleriyle tamamlar (modül açıklaması)."""
    rapor = HibritRaporu(kural_test_sayisi=len(kural.testler))
    sayfalar = {s.no: s.metin for s in belge.sayfalar}
    kural_testleri = {t.id: t for t in kural.testler}
    dil_testleri = {t.id: t for t in dil.testler}

    eslesen: dict[str, str] = {}  # dil modeli id -> kural id
    for e in kaydi_eslestir(kural, dil):
        if e.tur == "test" and e.a in kural_testleri and e.b in dil_testleri:
            # Madde numarası farklıysa aynı şart sayılmaz: eşleşmemiş gibi kanıt yoluna gider.
            if _madde(kural_testleri[e.a].kaynak.madde) == _madde(dil_testleri[e.b].kaynak.madde):
                eslesen[e.b] = e.a

    belirsiz: set[str] = set()
    eklenenler: list[TestSarti] = []
    kullanilan = set(kural_testleri)

    for t in dil.testler:
        neden = _kanit_nedeni(t, sayfalar)
        if t.id in eslesen:
            rapor.kuralla_eslesen.append(t.id)
            if neden is not None:
                rapor.kanitsiz.append((t.id, neden))
                continue
            kural_testi = kural_testleri[eslesen[t.id]]
            farklar = _sinir_anlasmazliklari(kural_testi, t)
            if farklar:
                rapor.anlasmazliklar.extend(farklar)
                if kural_testi.sinir.kriter_turu == "sayisal":
                    belirsiz.add(kural_testi.id)
                elif kural_testi.id not in rapor.isaretlenemeyen:
                    rapor.isaretlenemeyen.append(kural_testi.id)
            continue
        if neden is not None:
            rapor.kanitsiz.append((t.id, neden))
            continue

        sinir = sinir_cikar(t.sinir.orijinal_metin)
        if t.sinir.kriter_turu == "sayisal" and sinir.kriter_turu != "sayisal":
            rapor.sayi_atildi.append(t.id)
        yeni_id = t.id
        while yeni_id in kullanilan:
            yeni_id += "_dm"
        kullanilan.add(yeni_id)
        eklenenler.append(t.model_copy(update={"id": yeni_id, "sinir": sinir, "numune_hazirlama_id": None}))
        rapor.eklenen.append(yeni_id)

    testler = [
        t.model_copy(update={"sinir": t.sinir.model_copy(update={"yon": "belirsiz"})}) if t.id in belirsiz else t
        for t in kural.testler
    ]
    hibrit = kural.model_copy(update={"testler": testler + eklenenler})
    return KabulDokumani.model_validate(hibrit.model_dump()), rapor
