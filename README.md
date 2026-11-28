# malzeme-kabul-ai

Havacılıkta kimyasal malzeme kabulü için yapay zekâ destekli belge kontrolü.

Astar, boya, sızdırmazlık macunu ve yapıştırıcı gibi malzemeler teslim
alınmadan önce standartlara göre kontrol edilir. Bu iş bugün büyük ölçüde elle
yapılır: mühendis standarttan bir kabul dokümanı hazırlar, sonra tedarikçinin
uygunluk sertifikası ve test raporundaki (CoC/TR) her değeri bu dokümanla tek
tek karşılaştırır. Bu proje o süreci otomatikleştirir. Ayrıntılı tanım:
[docs/proje_tanimi.md](docs/proje_tanimi.md).

## Kapsam

1. **Kabul dokümanı üretimi.** Sistem askeri standartları okur; test
   sınırlarını, test metotlarını, raf ömrünü, depolama ve kullanım koşullarını,
   kupon/uygulama/kürlenme bilgilerini, kabul ve ömür uzatma testlerini
   çıkarır. Bunlardan kalite mühendisinin onaylayacağı bir kabul dokümanı
   (Markdown ve Word) üretir. Her şartın yanında standarttaki madde numarası
   bulunur.
2. **Çapraz kontrol.** Tedarikçinin CoC/TR belgesi kabul dokümanıyla
   karşılaştırılır. Her test için "uygun / uygun değil / insan incelemeli"
   kararı verilir ve dayandığı madde gösterilir.
3. **Revizyon takibi.** Standardın revizyonları (ör. MIL-PRF-23377 G → H → J →
   K) arasındaki farklar bulunur ve etkilenen kabul dokümanı için güncelleme
   önerilir.

Kullanılan standartlar (kaynaklar: [data/raw/KAYNAKLAR.md](data/raw/KAYNAKLAR.md)):

| Standart | Malzeme | Revizyonlar |
|---|---|---|
| MIL-PRF-23377 | Epoksi astar, yüksek katı | G, H, J, K |
| MIL-PRF-81733 | Sızdırmazlık ve kaplama macunu, korozyon önleyici | D |
| MIL-PRF-85285 | Poliüretan son kat | E |

## Tasarım ilkeleri

- Belgeyi yerel bir dil modeli okur; kabul/red kararını yalnızca kesin kurallar
  verir. Birim dönüşümü ve sınır karşılaştırması Python kodunda yapılır.
- Sistem emin olmadığında kararı insana bırakır ("insan incelemeli").
- Sistem internetsiz çalışır; `src/` altında dış servis kullanılmaz.
- Doğru cevaplar (`data/gold/`) elle etiketlenir; kod bu klasöre yazmaz.

## Değerlendirme

Üç yaklaşım karşılaştırılır: yalnız kural, yalnız dil modeli ve hibrit.
Ölçütler:

- alan bazında precision, recall ve F1,
- yanlış kabul oranı (uygun olmayan bir değerin "uygun" sayılması),
- belge başına süre.

## Kurulum ve kullanım

### Tek komutla demo

```bash
python scripts/demo.py      # Windows: py scripts\demo.py   (Python 3.11+)
```

Betik depo kökünde `.venv` sanal ortamını kurar, kilitli sürümleri
(`requirements-arayuz.lock`) yükler, `data/calisma/demo/` altına demo
veritabanını, demo dosyalarını ve `parolalar.txt`'yi (`mp` = M&P, `gk` = giriş
kalite; parolalar ekrana yazılmaz) hazırlar ve uygulamayı yalnız
`http://127.0.0.1:8501` adresinde açar. İlk çalıştırmada pip için ağ gerekir;
sonraki çalıştırmalar ağsızdır. Seçenekler: `--sifirla` (demoyu baştan kurar,
parolaları yeniler), `--yalniz-kur` (uygulamayı başlatmaz), `--port 8502`,
`--kurulum-yok` (`.venv`/pip adımını atlar), `--klasor` (depo içinde yalnız
`data/calisma/` altı).
Parola dosyası POSIX'te yalnız sahibince okunur (0600); Windows'ta erişimini
klasörün izinleri belirler. Örnek kabul dokümanları "DEMO ONAYI (M&P onayı
değil)" işaretlidir. 2 dakikalık video senaryosu: `docs/demo_senaryosu.md`.

### Geliştirme kurulumu

```bash
pip install -r requirements-dev.lock && pip install -e . --no-deps   # sabit sürümler (docs/bagimliliklar.md)
pytest
python scripts/pdf_tur_kontrol.py    # data/raw PDF'leri metin mi taranmış mı
python deney/bolunme.py --turler     # kümeler: metin tabanlı / taranmış (OCR gerekli)
python deney/coa_eslestirme.py       # gerçek CoA'ları şartnameyle eşleştir -> data/coa_eslesme/
python scripts/kabul_dokumani_uret.py data/raw/MIL-PRF-23377K.pdf   # kural tabanlı kabul dokümanı taslağı
python deney/degerlendir.py TAHMIN.json GOLD.json                  # alan bazında P/R/F1
python deney/dil_modeli_cikar.py data/raw/MIL-PRF-23377K.pdf --model qwen2.5:7b-instruct-q4_K_M   # yerel dil modeliyle çıkarma
```

Üretilen taslaklar `data/cikti/` altına JSON, Markdown ve Word olarak yazılır.

### Ağsız Docker

Varsayılan parola yoktur. İlk açılışta M&P ve giriş kalite hesaplarının
parolaları (en az 12 karakter, kullanıcı adıyla aynı olamaz) host'ta ortam
değişkeni olarak verilir; compose bunları Docker secrets olarak konteynere
dosya şeklinde aktarır. Parola yoksa compose başlamaz; boş ya da zayıfsa
`scripts/ilk_kurulum.py` hata verir ve Streamlit başlamaz. Kullanıcı adları
`MALZEME_KABUL_MP_KULLANICI` / `MALZEME_KABUL_GK_KULLANICI` (varsayılan `mp` /
`gk`). Hesaplar `veri` biriminde kurulduktan sonra parolalar kullanılmaz ve
değiştirilmez; ancak compose her `up`'ta secrets değişkenlerini yine ister.

Gereken sürüm: secrets'ın ortam değişkeninden okunması (`secrets.<ad>.environment`)
**Docker Compose v2.6.0** ve üstünü ister (`docker compose version`). Daha eski
sürümler bu alanı tanımaz.

Her açılışta mevcut hesaplar da denetlenir: bir hesap bilinen bir deneme
parolasıyla kurulmuşsa (bu düzeltmeden önce `--ornek-kullanicilar` ile açılmış
eski bir `veri` birimi), uygulama hesabın adını söyleyip başlamaz. Docker
imajında `katalog_kur.py --ornek-kullanicilar` de reddedilir
(`MALZEME_KABUL_DOCKER=1`).

```bash
read -rs MALZEME_KABUL_MP_PAROLASI; read -rs MALZEME_KABUL_GK_PAROLASI
export MALZEME_KABUL_MP_PAROLASI MALZEME_KABUL_GK_PAROLASI
docker compose up -d --build          # ekran: http://127.0.0.1:8501 (uygulama dış ağa çıkamaz)
docker compose --profile model up -d  # yerel model (Ollama) ile, model dosyaları önceden konmuş olmalı
scripts/ag_testi.sh                   # ağın kapalı olduğunu gösterir (0 = kapalı); parola yoksa rastgele üretir
```

#### Parola değiştirme

Ortam değişkenine yeni bir parola yazmak **mevcut bir hesabın parolasını
değiştirmez**: ilk kurulum yalnız hiç hesap yokken çalışır. Parola değiştirmek
için hesap silinip yeniden açılır (uygulama durdurulmuşken; deneme parolası
yüzünden yeniden başlayıp duruyorsa da bu yol çalışır):

```bash
docker compose stop uygulama
# 1. hesabı sil (örnekte "mp")
docker compose run --rm --entrypoint python uygulama -c \
  "import sqlite3; b = sqlite3.connect('/veri/katalog.sqlite'); b.execute(\"DELETE FROM kullanicilar WHERE ad = 'mp'\"); b.commit()"
# 2. aynı adla yeniden aç; parola sorulur (ekrana ve geçmişe yazılmaz)
docker compose run --rm -it --entrypoint python uygulama \
  /uygulama/scripts/kullanici_ekle.py --ad mp --rol mp --db /veri/katalog.sqlite
docker compose up -d
```

Bütün hesaplar silinirse bir sonraki `up`'ta ilk kurulum, hesapları yeniden
`MALZEME_KABUL_MP_PAROLASI` / `MALZEME_KABUL_GK_PAROLASI` ile açar. Veriye
ihtiyaç yoksa `docker compose down -v` birimi (katalog ve denetim kaydı dahil)
tamamen siler.

## Klasörler

- `src/malzeme_kabul/`: üretim kodu; katmanlar `sozlesme`, `belge`, `cikarim`,
  `kural`, `revizyon`, `katalog`, `kayit`, `hat`, `arayuz` (bkz.
  [docs/mimari.md](docs/mimari.md))
- `deney/`: yalnız dil modeli deneyi ve ölçüm (F1, yanlış kabul); ürünün parçası değil
- `tests/`: pytest testleri
- `scripts/`: ürün betikleri, hook'lar ve CI kontrolleri
- `docs/`: proje tanımı ve belgeler (dil modeli ortamı: [docs/dil_modeli_ortami.md](docs/dil_modeli_ortami.md))
- `notebooks/`: Colab defteri (yalnız geliştirme ve ölçüm)
- `data/raw/`: ham standart belgeleri
- `data/gold_taslak/`: doğru cevap taslakları (gözden geçirilmeyi bekler)
- `data/gold/`: elle etiketlenmiş doğru cevaplar (salt okunur)
- `data/bolunme.yaml`: standartların geliştirme / test bölünmesi (test kümesi kilitli)
- `data/calisma/`: yerel çalışma verisi; git'e girmez
