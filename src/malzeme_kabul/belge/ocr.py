"""Yerel OCR katmanı: taranmış PDF sayfalarını Tesseract ile okur (docs/ocr.md).

Tamamen yereldir: sayfa `pypdfium2` ile gri tonlu PNG'ye çevrilir, geçici bir
klasöre yazılır ve `tesseract` ikili dosyası alt süreç olarak çalıştırılır
(`tesseract <png> stdout -l <dil> --psm <psm> tsv`). Ağ kullanılmaz, Python
OCR paketi (pytesseract) yoktur.

Çıktı TSV'sindeki kelime satırları (seviye 5) blok / paragraf / satır
numarasına göre satırlara dizilir; her kelimenin Tesseract güveni (0-100)
tutulur. İkili dosya yoksa, hata koduyla biterse ya da süre aşılırsa
`OcrKullanilamaz` verilir.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pypdfium2

# Bu güvenin altındaki kelime "düşük güvenli" sayılır (eşiğe eşit olan sayılmaz).
DUSUK_GUVEN_ESIGI = 60.0
VARSAYILAN_KOMUT = "tesseract"


class OcrKullanilamaz(RuntimeError):
    """Tesseract bulunamadı, hata koduyla bitti ya da süre sınırını aştı."""


@dataclass(frozen=True)
class OcrKelime:
    metin: str
    guven: float


@dataclass(frozen=True)
class OcrSonucu:
    """Bir sayfanın (ya da resmin) OCR metni ve kelime güvenleri."""

    metin: str
    kelimeler: tuple[OcrKelime, ...] = ()

    @property
    def ortalama_guven(self) -> float | None:
        """Kelime güvenlerinin ortalaması; kelime yoksa None."""
        if not self.kelimeler:
            return None
        return sum(k.guven for k in self.kelimeler) / len(self.kelimeler)

    def dusuk_guvenli_oran(self, esik: float = DUSUK_GUVEN_ESIGI) -> float:
        """Güveni eşiğin altında kalan kelimelerin oranı; kelime yoksa 0."""
        if not self.kelimeler:
            return 0.0
        return sum(1 for k in self.kelimeler if k.guven < esik) / len(self.kelimeler)


class OcrMotoru(Protocol):
    """pdf_oku'nun beklediği arayüz: bir PDF sayfasını (1'den başlar) okur."""

    def sayfa_oku(self, pdf_yolu: Path, sayfa_no: int) -> OcrSonucu: ...


def tsv_coz(tsv: str) -> OcrSonucu:
    """Tesseract TSV çıktısını metne ve kelime listesine çevirir.

    Yalnız seviye 5 (kelime) satırları alınır; güveni -1 olan ya da metni boş
    olan kelimeler atlanır. Aynı (sayfa, blok, paragraf, satır) içindeki
    kelimeler tek boşlukla, satırlar görünüş sırasıyla yeni satırla birleşir.
    """
    satirlar: dict[tuple[str, str, str, str], list[str]] = {}
    kelimeler: list[OcrKelime] = []
    for satir in tsv.splitlines():
        alanlar = satir.rstrip("\r").split("\t")
        if len(alanlar) < 12 or alanlar[0] != "5":
            continue  # başlık, boş satır ya da üst seviye
        metin = alanlar[11].strip()
        try:
            guven = float(alanlar[10])
        except ValueError:
            continue
        if guven < 0 or not metin:
            continue
        anahtar = (alanlar[1], alanlar[2], alanlar[3], alanlar[4])
        satirlar.setdefault(anahtar, []).append(metin)
        kelimeler.append(OcrKelime(metin, guven))
    return OcrSonucu("\n".join(" ".join(k) for k in satirlar.values()), tuple(kelimeler))


def tesseract_var_mi(komut: str = VARSAYILAN_KOMUT) -> bool:
    """Tesseract ikili dosyası PATH'te (ya da verilen yolda) çalıştırılabilir mi."""
    return shutil.which(komut) is not None


@dataclass(frozen=True)
class TesseractMotoru:
    dil: str = "eng"
    psm: int = 3
    dpi: int = 300
    zaman_asimi_s: float = 120
    komut: str = VARSAYILAN_KOMUT
    # Render edilecek resmin en çok piksel sayısı (genişlik x yükseklik). Güvenilmeyen
    # PDF'teki dev bir sayfa belleği tüketmesin diye render'dan önce denetlenir.
    en_cok_piksel: int = 100_000_000

    def __post_init__(self):
        if self.zaman_asimi_s <= 0:
            raise ValueError(f"zaman_asimi_s pozitif olmalı: {self.zaman_asimi_s!r}")
        if self.dpi <= 0:
            raise ValueError(f"dpi pozitif olmalı: {self.dpi!r}")
        if self.en_cok_piksel <= 0:
            raise ValueError(f"en_cok_piksel pozitif olmalı: {self.en_cok_piksel!r}")

    def _calistir(self, argumanlar: list[str]) -> str:
        try:
            sonuc = subprocess.run(
                [self.komut, *argumanlar], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.zaman_asimi_s, check=True,
            )
        except FileNotFoundError as hata:
            raise OcrKullanilamaz(f"tesseract bulunamadı ({self.komut}); docs/ocr.md kurulum") from hata
        except subprocess.TimeoutExpired as hata:
            raise OcrKullanilamaz(f"tesseract {self.zaman_asimi_s:g} s içinde bitmedi") from hata
        except subprocess.CalledProcessError as hata:
            raise OcrKullanilamaz(
                f"tesseract hata koduyla bitti ({hata.returncode}): {(hata.stderr or '').strip()[:300]}"
            ) from hata
        except OSError as hata:  # izin yok, çalıştırılabilir değil
            raise OcrKullanilamaz(f"tesseract çalıştırılamadı ({self.komut}): {hata}") from hata
        return sonuc.stdout

    def surum(self) -> str:
        """Tesseract sürümü, ör. "5.3.4" (Windows'taki "v5.3.0..." önekindeki v atılır)."""
        ilk = self._calistir(["--version"]).strip().splitlines()
        if not ilk or not ilk[0].split():
            raise OcrKullanilamaz("tesseract sürümü okunamadı")
        surum = ilk[0].split()[-1]
        return surum[1:] if surum[:1] in ("v", "V") else surum

    def resim_oku(self, png: str | Path) -> OcrSonucu:
        """Bir resim dosyasını OCR'dan geçirir."""
        return tsv_coz(self._calistir([str(png), "stdout", "-l", self.dil, "--psm", str(self.psm), "tsv"]))

    def sayfa_oku(self, pdf_yolu: str | Path, sayfa_no: int) -> OcrSonucu:
        """PDF'in `sayfa_no`. sayfasını (1'den başlar) `dpi`'da resme çevirip okur.

        Sayfa numarası aralık dışındaysa ValueError; render edilecek resim
        `en_cok_piksel`'i aşıyorsa (render ve tesseract çağrılmadan), PDF
        açılamazsa, sayfa resme çevrilemezse ya da resim kaydedilemezse
        OcrKullanilamaz verir.
        """
        try:
            pdf = pypdfium2.PdfDocument(str(pdf_yolu))
        except (pypdfium2.PdfiumError, OSError) as hata:
            raise OcrKullanilamaz(f"PDF açılamadı: {pdf_yolu}: {hata}") from hata
        try:
            if not 1 <= sayfa_no <= len(pdf):
                raise ValueError(f"sayfa numarası 1..{len(pdf)} aralığında olmalı: {sayfa_no}")
            try:
                sayfa = pdf[sayfa_no - 1]
            except pypdfium2.PdfiumError as hata:
                raise OcrKullanilamaz(f"sayfa {sayfa_no} açılamadı: {pdf_yolu}: {hata}") from hata
            try:
                genislik, yukseklik = sayfa.get_size()
                olcek = self.dpi / 72
                piksel = round(genislik * olcek) * round(yukseklik * olcek)
                if piksel > self.en_cok_piksel:
                    raise OcrKullanilamaz(
                        f"sayfa {sayfa_no} {self.dpi} dpi'da {piksel} piksel; sınır {self.en_cok_piksel}"
                    )
                try:
                    resim = sayfa.render(scale=olcek, grayscale=True).to_pil()
                except (pypdfium2.PdfiumError, OSError, MemoryError) as hata:
                    raise OcrKullanilamaz(f"sayfa {sayfa_no} resme çevrilemedi: {pdf_yolu}: {hata}") from hata
            finally:
                sayfa.close()
        finally:
            pdf.close()
        with tempfile.TemporaryDirectory(prefix="ocr_") as klasor:
            png = Path(klasor) / f"sayfa_{sayfa_no}.png"
            try:
                resim.save(png, dpi=(self.dpi, self.dpi))
            except (OSError, ValueError) as hata:
                raise OcrKullanilamaz(f"sayfa {sayfa_no} resmi kaydedilemedi: {hata}") from hata
            return self.resim_oku(png)
