"""docs/codex_inceleme_gorevi.md: Codex'in bağımsız gözden geçiren görev tanımı.

Bu testler dokümanın yapısal sözleşmesini denetler:
- Belirli `## ` bölümleri belirli sırada; "Kontrol listesi" altında belirli `### ` alt başlıklar.
- "İncelenecek PR'lar" bölümünde PR numarası ve konu içeren bir Markdown tablosu.
- Backtick içindeki depo yolları depoda gerçekten var (uydurma yol yok).
- "Raporlama" bulgu biçimini, "Sınırlar" Codex'in yetki sınırlarını tarif eder.
- Doküman arayüz sözleşmesinin "Bilinen açıklar" bölümüne atıf yapar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DOKUMAN = KOK / "docs" / "codex_inceleme_gorevi.md"
ARAYUZ_SOZLESMESI = KOK / "docs" / "arayuz_sozlesmesi.md"

BOLUMLER = ("Amaç ve rol", "İncelenecek PR'lar", "Kontrol listesi", "Raporlama", "Sınırlar")
KONTROL_ALT_BASLIKLARI = ("Mimariye uyum", "Güvenlik", "Testler", "Proje kuralları (CLAUDE.md)")
ZORUNLU_PRLAR = (49, 52, 53, 54, 55, 56, 57, 58, 59)
ONEM_DUZEYLERI = ("kritik", "önemli", "küçük")

YOL_ONEKLERI = ("src/", "docs/", "tests/", "scripts/", "data/", "docker/", ".github/")
KOK_DOSYALARI = ("Dockerfile", "docker-compose.yml", "CLAUDE.md")
# Henüz var olmayabilecek ama dokümanda geçmesi meşru yollar
YOKSA_KABUL = ("docs/inceleme",)
GLOB_KARAKTERLERI = set("*?[")

_BACKTICK = re.compile(r"`([^`\n]+)`")
# data/gold satırında aranan olumsuz (yasaklayıcı) fiil biçimleri; kelime sınırlı.
# "yazmalısın", "yazılabilir", "dokunulabilir" gibi olumlu biçimler eşleşmez.
_YASAK_FIIL = re.compile(
    r"\b(?:yaz(?:ma|maz|ılmaz|amaz|mayacak|mamalı|mayın)"
    r"|dokun(?:ma|maz|ulmaz|amaz|mayacak|mamalı|mayın))\b",
    re.IGNORECASE,
)
# Sınırlar'da onay yetkisinin olmadığını söyleyen dar kalıplar ("onay verir" eşleşmez)
_ONAY_YOK = re.compile(
    r"\bonay\s+(?:vermez|veremez|yetkisi\s+(?:yok|yoktur|bulunmaz|bulunmuyor|olmaz))\b"
    r"|\bonaylamaz\b",
    re.IGNORECASE,
)
DURUM_DEGERLERI = ("birleşti", "açık")


# --- yardımcılar ---------------------------------------------------------------------------


def _metin() -> str:
    if not DOKUMAN.exists():
        pytest.fail(f"{DOKUMAN.relative_to(KOK)} yok; Codex inceleme görevi yazılmalı.")
    return DOKUMAN.read_text(encoding="utf-8")


def _basliklar(metin: str, seviye: int) -> list[tuple[int, str]]:
    """(satır indeksi, başlık metni) listesi; yalnız tam bu seviyedeki başlıklar."""
    desen = re.compile(r"^" + "#" * seviye + r"\s+(.*?)\s*$")
    sonuc = []
    for i, satir in enumerate(metin.splitlines()):
        m = desen.match(satir)
        if m and not satir.startswith("#" * (seviye + 1)):
            sonuc.append((i, m.group(1)))
    return sonuc


def _bolum(metin: str, baslik: str) -> str:
    """`## baslik` bölümünün gövdesi (bir sonraki `## ` ya da `# ` başlığa kadar)."""
    satirlar = metin.splitlines()
    for i, ad in _basliklar(metin, 2):
        if ad == baslik:
            govde = []
            for s in satirlar[i + 1:]:
                if re.match(r"^#{1,2}\s", s):
                    break
                govde.append(s)
            return "\n".join(govde)
    pytest.fail(f"'## {baslik}' bölümü bulunamadı")


def _yol_adayi(ifade: str) -> str | None:
    """Backtick içindeki ifade depo yolu gibi görünüyorsa normalize edilmiş yolu döner."""
    ifade = ifade.strip()
    if not ifade or any(c.isspace() for c in ifade):
        return None
    if not (ifade.startswith(YOL_ONEKLERI) or ifade.split("/")[0] in KOK_DOSYALARI):
        return None
    ifade = ifade.split("::")[0]  # tests/x.py::test_y
    ifade = re.sub(r":\d+(-\d+)?$", "", ifade)  # src/x.py:12 ya da :12-20
    return ifade


def _yol_var_mi(yol: str) -> bool:
    if GLOB_KARAKTERLERI & set(yol):
        return any(KOK.glob(yol.rstrip("/")))
    return (KOK / yol).exists()


def yol_ihlalleri(metin: str) -> list[str]:
    """Dokümandaki uydurma/yanlış yolları ve yazma yasağı olmadan geçen data/gold'u listeler."""
    ihlaller = []
    for no, satir in enumerate(metin.splitlines(), start=1):
        for ifade in _BACKTICK.findall(satir):
            yol = _yol_adayi(ifade)
            if yol is None:
                continue
            temiz = yol.rstrip("/")
            if temiz == "data/gold" or temiz.startswith("data/gold/"):
                if not _YASAK_FIIL.search(satir):
                    ihlaller.append(
                        f"satır {no}: `{ifade}` yazma/dokunma yasağı olmadan geçiyor"
                    )
                continue
            if any(temiz == y or temiz.startswith(y + "/") for y in YOKSA_KABUL):
                continue
            if not _yol_var_mi(yol):
                ihlaller.append(f"satır {no}: `{ifade}` depoda yok")
    return ihlaller


# --- yardımcıların kendi davranışı (doküman olmadan da çalışır) --------------------------


def test_yol_denetimi_olmayan_dosyayi_yakalar_var_olani_gecirir():
    ornek = "\n".join(
        [
            "Bak: `src/malzeme_kabul/yok_boyle_bir_modul.py` ve `docs/mimari.md:12`.",
            "Ayrıca `tests/test_*.py`, `Dockerfile`, `pytest -q` ve `docs/inceleme/rapor.md`.",
        ]
    )
    ihlaller = yol_ihlalleri(ornek)
    assert len(ihlaller) == 1
    assert "yok_boyle_bir_modul.py" in ihlaller[0]


def test_yol_denetimi_data_gold_yasaksiz_gecince_yakalar():
    assert yol_ihlalleri("Gerekirse `data/gold/` güncellenir.")
    assert not yol_ihlalleri("`data/gold/` klasörüne asla yazma.")
    assert not yol_ihlalleri("`data/gold/` içeriğine dokunma.")
    assert not yol_ihlalleri("Codex `data/gold/` klasörüne yazmaz.")
    assert not yol_ihlalleri("`data/gold/` dokunulmaz.")


def test_yol_denetimi_data_gold_olumlu_fiili_yasak_saymaz():
    assert yol_ihlalleri("Bulguları `data/gold/` altına yazmalısın.")
    assert yol_ihlalleri("`data/gold/` dosyalarına dokunulabilir.")
    assert yol_ihlalleri("`data/gold/` yazılabilir.")


def test_onay_kalibi_yalniz_olumsuz_bicimi_kabul_eder():
    assert _ONAY_YOK.search("Codex onay vermez.")
    assert _ONAY_YOK.search("Codex'in onay yetkisi yok.")
    assert not _ONAY_YOK.search("Codex onay verir ve birleştirmez.")
    assert not _ONAY_YOK.search("Onay gerekir.")


# --- dokümanın sözleşmesi -------------------------------------------------------------------


def test_dokuman_zorunlu_bolumleri_sirayla_icerir():
    metin = _metin()
    adlar = [ad for _, ad in _basliklar(metin, 2)]
    eksik = [b for b in BOLUMLER if b not in adlar]
    assert not eksik, f"eksik `## ` bölümleri: {eksik}"
    sira = [adlar.index(b) for b in BOLUMLER]
    assert sira == sorted(sira), f"bölüm sırası yanlış: {adlar}"


def test_kontrol_listesi_dort_alt_basligi_sirayla_icerir():
    govde = _bolum(_metin(), "Kontrol listesi")
    adlar = [ad for _, ad in _basliklar(govde, 3)]
    eksik = [b for b in KONTROL_ALT_BASLIKLARI if b not in adlar]
    assert not eksik, f"'Kontrol listesi' altında eksik `### ` başlıklar: {eksik}"
    sira = [adlar.index(b) for b in KONTROL_ALT_BASLIKLARI]
    assert sira == sorted(sira), f"alt başlık sırası yanlış: {adlar}"


def _tablo(govde: str) -> tuple[list[str], list[list[str]]]:
    """(başlık hücreleri, veri satırları)."""
    satirlar = [s.strip() for s in govde.splitlines() if s.strip().startswith("|")]
    veri = []
    for s in satirlar:
        hucreler = [h.strip() for h in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", h) for h in hucreler if h):
            continue  # ayraç satırı
        veri.append(hucreler)
    if not veri:
        return [], []
    return veri[0], veri[1:]


def _tablo_satirlari(govde: str) -> list[list[str]]:
    return _tablo(govde)[1]


def _sade(hucre: str) -> str:
    return hucre.strip().strip("`*_ ").strip().lower()


def test_incelenecek_prlar_tablosunda_her_satir_pr_numarasi_ve_konu_tasir():
    satirlar = _tablo_satirlari(_bolum(_metin(), "İncelenecek PR'lar"))
    assert satirlar, "'İncelenecek PR'lar' bölümünde Markdown tablosu yok"
    for hucreler in satirlar:
        pr_hucreleri = [h for h in hucreler if re.search(r"#\d+\b", h)]
        assert pr_hucreleri, f"satırda #NN biçiminde PR numarası yok: {hucreler}"
        konu = [h for h in hucreler if h and h not in pr_hucreleri]
        assert konu, f"satırda konu yok: {hucreler}"


def test_incelenecek_prlar_tablosunda_durum_sutunu_birlesti_ya_da_acik_olur():
    baslik, satirlar = _tablo(_bolum(_metin(), "İncelenecek PR'lar"))
    adlar = [_sade(h) for h in baslik]
    assert "durum" in adlar, f"PR tablosunda 'Durum' sütunu yok: {baslik}"
    i = adlar.index("durum")
    for hucreler in satirlar:
        deger = _sade(hucreler[i]) if i < len(hucreler) else ""
        assert deger in DURUM_DEGERLERI, (
            f"Durum değeri {DURUM_DEGERLERI} dışında: {deger!r} (satır: {hucreler})"
        )


def test_gece_ve_sabah_birlesen_prlarin_hepsi_listelenir():
    satirlar = _tablo_satirlari(_bolum(_metin(), "İncelenecek PR'lar"))
    numaralar = {
        int(n) for hucreler in satirlar for h in hucreler for n in re.findall(r"#(\d+)\b", h)
    }
    eksik = sorted(set(ZORUNLU_PRLAR) - numaralar)
    assert not eksik, f"tabloda eksik PR'lar: {['#%d' % n for n in eksik]}"


def test_backtick_icindeki_depo_yollari_gercekten_vardir():
    ihlaller = yol_ihlalleri(_metin())
    assert not ihlaller, "dokümandaki yol sorunları:\n" + "\n".join(ihlaller)


def test_raporlama_bolumu_uc_onem_duzeyini_etiket_olarak_tanimlar():
    govde = _bolum(_metin(), "Raporlama")
    etiketler = set(_BACKTICK.findall(govde))
    eksik = [d for d in ONEM_DUZEYLERI if d not in etiketler]
    assert not eksik, f"'Raporlama' bölümünde backtick içinde eksik önem düzeyleri: {eksik}"


def test_raporlama_bolumu_bulgu_bicimini_tarif_eder():
    govde = _bolum(_metin(), "Raporlama").lower()
    eksik = [k for k in ("dosya:satır", "senaryo", "öneri") if k not in govde]
    assert not eksik, f"'Raporlama' bölümünde bulgu biçiminin eksik alanları: {eksik}"


def test_raporlama_bolumu_raporun_nereye_yazilacagini_belirtir():
    govde = _bolum(_metin(), "Raporlama")
    assert "PR yorumu" in govde or "docs/inceleme/" in govde, (
        "'Raporlama' bölümü raporun yerini söylemiyor (PR yorumu ya da `docs/inceleme/` altı)"
    )


def test_sinirlar_bolumu_birlestirme_ve_onay_yetkisi_olmadigini_yazar():
    govde = _bolum(_metin(), "Sınırlar").lower()
    assert "birleştirmez" in govde, "'Sınırlar' Codex'in PR birleştirmediğini yazmıyor"
    assert _ONAY_YOK.search(govde), (
        "'Sınırlar' Codex'in onay yetkisi olmadığını açıkça yazmıyor "
        "(ör. 'onay vermez' ya da 'onay yetkisi yok')"
    )


def test_sinirlar_bolumu_gold_ve_test_kumesine_dokunulmadigini_yazar():
    govde = _bolum(_metin(), "Sınırlar")
    assert "data/gold/" in govde, "'Sınırlar' `data/gold/` yasağını yazmıyor"
    assert "test kümesi" in govde.lower(), "'Sınırlar' test kümesine dokunulmayacağını yazmıyor"


def test_dokuman_arayuz_sozlesmesinin_bilinen_aciklarina_atif_yapar():
    metin = _metin()
    assert "docs/arayuz_sozlesmesi.md" in metin, "arayüz sözleşmesine atıf yok"
    assert "Bilinen açıklar" in metin, "arayüz sözleşmesinin 'Bilinen açıklar' bölümüne atıf yok"
    # Atıf yapılan bölüm gerçekten var olmalı (bayat atıf olmasın)
    if not ARAYUZ_SOZLESMESI.exists():
        pytest.fail(
            f"{ARAYUZ_SOZLESMESI.relative_to(KOK)} yok; Codex görevi var olmayan bir "
            "dokümana atıf yapıyor"
        )
    hedef = ARAYUZ_SOZLESMESI.read_text(encoding="utf-8")
    assert any(ad.startswith("Bilinen açıklar") for _, ad in _basliklar(hedef, 2)), (
        "docs/arayuz_sozlesmesi.md içinde 'Bilinen açıklar' başlıklı `## ` bölüm yok"
    )
