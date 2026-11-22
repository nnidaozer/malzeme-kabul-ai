# Bağımlılıklar ve sabit sürümler

`pyproject.toml` hangi paketlerin gerektiğini ve kabul edilen sürüm aralığını
söyler. Kurulumda gelen tam sürümler ise iki kilit dosyasında sabittir
(docs/guvenlik.md, tehdit 3):

- `requirements.lock`: çalışma zamanı paketleri ve onların bağımlılıkları.
- `requirements-dev.lock`: bunlara ek olarak test paketleri (pytest,
  reportlab, pillow).

Kilitler Python 3.11 içindir (CI ile aynı). CI testleri kilitten kurar ve
ayrı bir işte `pip-audit` ile bilinen açıkları tarar; açık bulunursa ya da bir
paket taranamazsa CI kırmızı olur.

## Kurulum (sabit sürümlerle)

```bash
pip install -r requirements-dev.lock
pip install -e . --no-deps
```

`pip install -e ".[dev]"` hâlâ çalışır, ama aralıktaki en yeni sürümleri
getirir; ölçümü tekrarlamak için kilitten kurmak gerekir.

## Kilidi güncelleme

Bir paketi güncellemek (ya da pip-audit bir açık bulduğunda düzeltmek) ayrı
bir PR ile yapılır:

```bash
python3.11 -m venv /tmp/kilit && . /tmp/kilit/bin/activate
pip install --upgrade pip
pip install .                                   # yalnız çalışma zamanı
pip freeze --exclude malzeme-kabul > govde.txt  # -> requirements.lock
pip install pytest reportlab pillow             # pyproject'teki dev listesi
pip freeze --exclude malzeme-kabul > govde-dev.txt  # -> requirements-dev.lock
pip install pip-audit && pip-audit -r govde-dev.txt
```

Çıkan listeleri, ilk iki açıklama satırını koruyarak kilit dosyalarına yaz ve
`pytest` çalıştır. `tests/test_bagimlilik_kilidi.py` her satırın `ad==sürüm`
olduğunu, `pyproject.toml` içindeki her paketin kilitte ve aralık içinde
olduğunu ve CI'ın kilitten kurup pip-audit çalıştırdığını denetler.
