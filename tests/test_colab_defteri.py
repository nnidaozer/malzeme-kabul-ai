"""Colab defterinin yapısal denetimi: açılır, kodu sözdizimsel olarak geçerli, kurallara uyar."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEFTER = KOK / "notebooks" / "colab_dil_modeli.ipynb"


def _hucreler(tur: str) -> list[str]:
    defter = json.loads(DEFTER.read_text(encoding="utf-8"))
    assert defter["nbformat"] == 4
    return ["".join(h["source"]) for h in defter["cells"] if h["cell_type"] == tur]


def test_kod_hucreleri_gecerli_python():
    for kaynak in _hucreler("code"):
        # "!komut" kabuk satırları Python değildir; yerine boş deyim konur.
        ast.parse(re.sub(r"^(\s*)!.*$", r"\1pass", kaynak, flags=re.M))


def test_defter_colabin_yalniz_gelistirme_icin_oldugunu_soyler():
    metin = "\n".join(_hucreler("markdown"))
    assert "yalnız geliştirme ve ölçüm içindir" in metin
    assert "internetsiz" in metin


def test_defter_yerel_istemciyi_kullanir_ve_golde_yazmaz():
    kod = "\n".join(_hucreler("code"))
    assert "YerelModelIstemcisi" in kod and "deney/uc_mod.py" in kod
    assert "127.0.0.1" in kod
    assert "data/gold/" not in kod  # yalnız data/gold_taslak okunur


def test_klonlama_belirteci_secretstan_alir_ve_sizdirmaz():
    kod = "\n".join(_hucreler("code"))
    assert 'userdata.get("GITHUB_TOKEN")' in kod
    assert "http.extraHeader" in kod  # belirteç adrese ve .git/config'e yazılmaz
    assert "@github.com" not in kod and ":{belirtec}@" not in kod
    assert not re.search(r"print\([^)]*belirtec", kod)
    assert 'replace(belirtec, "***")' in kod  # hata çıktısında maskelenir


def test_kurulum_dogrulama_hucresi_var():
    kod = "\n".join(_hucreler("code"))
    assert '"pip", "install", "-q", "-e", "."' in kod
    assert "sys.path.insert(0, SRC)" in kod  # çalışan çekirdek yeni kurulumu görsün
    assert "import malzeme_kabul" in kod and "Kurulum doğrulandı" in kod


def test_hucreler_istege_bagli_hucrelerin_importlarina_dayanmaz():
    """Ollama hücresini atlayıp llama.cpp yolunu seçen biri de NameError almasın.

    Her hücre kullandığı standart modülleri ya kendisi içe aktarır ya da her
    oturumda çalıştırılan kurulum hücrelerinden (2a–2c) alır.
    """
    hucreler = [re.sub(r"^(\s*)!.*$", r"\1pass", k, flags=re.M) for k in _hucreler("code")]

    def aktarilanlar(kaynak):
        adlar = set()
        for d in ast.walk(ast.parse(kaynak)):
            if isinstance(d, ast.Import):
                adlar |= {(a.asname or a.name).split(".")[0] for a in d.names}
            elif isinstance(d, ast.ImportFrom):
                adlar |= {a.asname or a.name for a in d.names}
        return adlar

    kurulum = set().union(*(aktarilanlar(k) for k in hucreler if k.lstrip().startswith("# 2")))
    moduller = {"json", "time", "urllib", "subprocess", "os", "sys", "glob", "pd"}
    eksik = {}
    for i, kaynak in enumerate(hucreler):
        kullanilan = {d.id for d in ast.walk(ast.parse(kaynak)) if isinstance(d, ast.Name) and d.id in moduller}
        yok = kullanilan - aktarilanlar(kaynak) - kurulum
        if yok:
            eksik[i] = sorted(yok)
    assert not eksik, f"başka hücrenin içe aktarmasına dayanan hücreler: {eksik}"


def test_defter_uc_modu_tek_modelle_uc_belgede_calistirir():
    kod = "\n".join(_hucreler("code"))
    assert "deney/dil_modeli_cikar.py" not in kod  # eski çok-adaylı döngü yerine uc_mod.py
    assert '"qwen3:8b"' in kod
    assert "--dusunme-kapali" in kod
    for belge in ("MIL-PRF-23377K.pdf", "MIL-PRF-81733D.pdf", "MIL-PRF-85285E.pdf"):
        assert f"data/raw/{belge}" in kod


def test_defter_markdownunda_tahmini_sure_yazar():
    metin = "\n".join(_hucreler("markdown"))
    assert "Tahmini süre" in metin
