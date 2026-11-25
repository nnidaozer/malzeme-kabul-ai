# Codex inceleme görevi

Bu doküman Codex'e yazılmıştır. Bu projede bağımsız gözden geçiren sensin.

## Amaç ve rol

Görevin, aşağıdaki PR'ları bağımsız olarak incelemek ve bulgularını
raporlamak. Kod yazmazsın, PR birleştirmezsin. Yalnız bulgu raporlarsın.
Kararı proje sahibi (Nida) verir.

Sistem MIL-PRF-23377 gibi standartlarla tedarikçi sertifikasını
karşılaştırır ve her test için "uygun / uygun değil / insan incelemeli"
kararı verir. Belgeyi yerel bir dil modeli okur; kabul/red kararını yalnız
kesin kurallar verir. En pahalı hata **yanlış kabuldür**: uygun olmayan bir
partinin serbest bırakılması. İncelemeni bu gözle yap.

Başlamadan önce sırayla oku:

1. `CLAUDE.md`: proje kuralları.
2. `docs/mimari.md`: katmanlar, sınırları ve karar kuralları.
3. `docs/guvenlik.md`: tehdit modeli. Bu doküman güncel değil (bkz.
   "Güvenlik" kontrol listesi); güncel olmayan kısımlarını bulgu olarak
   raporla.
4. `docs/arayuz_sozlesmesi.md`: arayüzün çağırdığı fonksiyonlar. Özellikle
   "Bilinen açıklar ve bekleyen işler" bölümünü oku. Oradaki maddeleri yeni
   bulgu diye raporlama. Bunun yerine her madde için iki şeyi denetle:
   ilgili PR'la kapanmış mı, ve dokümanda doğru anlatılmış mı. Kodla çelişen
   ya da eksik anlatılan madde bir bulgudur. Biçim için bkz. "Raporlama".
5. `docs/gece_kararlari.md`: gece verilen ve proje sahibinin onayladığı ya
   da onay bekleyen kararlar.

Kurulum ve testler:

```bash
pip install -r requirements-dev.lock && pip install -e . --no-deps   # CLAUDE.md'deki kurulum
pip install -r requirements-arayuz.lock                              # Streamlit ekranı testleri için
pytest
```

## İncelenecek PR'lar

"Birleşti" durumundaki PR'ların numarasını ve konusunu
`git log origin/main --oneline` ile doğrula. "Açık" PR'lar henüz `main`'de
değildir; onları PR dalından (`gh pr checkout NN`) incele. Öncelik sırası:
yanlış kabul riski taşıyanlar önce.

| PR | Durum | Konu | Odak dosyalar | Öncelik |
|---|---|---|---|---|
| #52 | birleşti | Karar motoru katalog bağlantısı ve parti kuralı | `src/malzeme_kabul/kural/karar_motoru.py`, `src/malzeme_kabul/hat/katalog_karari.py` | 1 (yanlış kabul) |
| #56 | birleşti | Hibrit hat: kural / hibrit mod, localhost model, kanıt doğrulayıcı | `src/malzeme_kabul/hat/hibrit_hat.py`, `src/malzeme_kabul/kural/kanit_dogrulama.py`, `src/malzeme_kabul/cikarim/yerel_model.py`, `src/malzeme_kabul/cikarim/sertifika_okuyucu.py`, `src/malzeme_kabul/kural/yon_dogrulama.py`, `src/malzeme_kabul/sozlesme/okuma.py` | 1 (yanlış kabul) |
| #61 | birleşti | Kural ve model farklı okursa şart insan incelemeli (okuma anlaşmazlığı) | `src/malzeme_kabul/kural/okuma_karsilastirma.py`, `src/malzeme_kabul/hat/hibrit_hat.py` | 1 (yanlış kabul) |
| #49 | birleşti | Katalog veritabanı: SQLite, değiştirilemez doküman sürümleri, onaylı tedarikçiler, partiler | `src/malzeme_kabul/katalog/veritabani.py`, `src/malzeme_kabul/katalog/ornek_veri.py`, `scripts/katalog_kur.py` | 1 (katalog kararı) |
| #53 | birleşti | Denetim kaydı ve hash zinciri | `src/malzeme_kabul/kayit/denetim_kaydi.py`, `scripts/denetim_dogrula.py` | 2 |
| #57 | birleşti | Streamlit ekranları; giriş ve iki rol | `src/malzeme_kabul/arayuz/uygulama.py`, `src/malzeme_kabul/arayuz/ekran_verisi.py`, `src/malzeme_kabul/arayuz/kimlik.py`, `scripts/kullanici_ekle.py`, `requirements-arayuz.lock` | 2 |
| #58 | birleşti | Ağsız Docker | `Dockerfile`, `docker-compose.yml`, `docker/baslat.sh`, `docker/yerel_kapi.py`, `.dockerignore`, `scripts/ag_testi.sh`, `scripts/ag_kapali_mi.py` | 2 |
| #54 | birleşti | Raf ömrü | `src/malzeme_kabul/kural/raf_omru.py`, `src/malzeme_kabul/hat/raf_omru_raporu.py` | 3 |
| #55 | birleşti | Revizyon etkisi | `src/malzeme_kabul/hat/revizyon_etkisi.py` | 3 |
| #59 | birleşti | Arayüz sözleşmesi | `docs/arayuz_sozlesmesi.md`, `tests/test_arayuz_sozlesmesi.py` | 3 |

PR'a özgü kontroller:

- **#61:** Kural okuması ile model okuması anlaşmazsa hiçbir okuma sessizce
  karara girmemeli; şart "insan incelemeli" olmalı. Anlaşmazlıklar karar
  kaydında `hat.anlasmazliklar` ve `anlasmazlik_sayisi` olarak durmalı.
  Değer, birim, sınır ve yön farkının hepsini dene (sertifika tarafı değer/birim/satır,
  standart tarafı sınır/yön).
- **#58:** `tests/test_dis_servis_yok.py` yalnız `src/`'yi tarar.
  `docker/` ve `scripts/` altındaki dosyalarda dış servis bağlantısını elle
  kontrol et.

Sonra açılacaklar: karar motoru güvenlik düzeltmeleri, denetim kaydı
düzeltmeleri, hibrit hat kanıt düzeltmeleri, Docker parolası ve demo onayı.
Bunlar açıldıkça aynı tabloya "açık" durumuyla girer ve aynı kontrol
listesiyle incelenir.

## Kontrol listesi

### Mimariye uyum

`docs/arayuz_sozlesmesi.md` "Kapsam ve katman sınırı" bölümündeki sınırlar:

- Kabul/red kararını yalnız `src/malzeme_kabul/kural/karar_motoru.py`
  verir (satır kararları ve `parti_karari`). Başka bir katman karar
  üretmez ya da kararı değiştirmez.
- Görev dağılımı: katalogla bağlama `hat/katalog_karari`, belge → okuma →
  kanıt → karar akışı `hat/hibrit_hat`, revizyon işaretleme
  `hat/revizyon_etkisi`, saklama `katalog/veritabani`, zincirli kayıt
  `kayit/denetim_kaydi`.
- `src/malzeme_kabul/arayuz/uygulama.py` yalnız arayüz sözleşmesindeki
  adları çağırır. Ekranın arkasındaki işler
  `src/malzeme_kabul/arayuz/ekran_verisi.py`'de durur ve Streamlit olmadan
  test edilir; bu dosya `hat`, `katalog`, `kayit`, `cikarim`, `revizyon`, `belge` ve
  `sozlesme` katmanlarını içe aktarır (bkz. `docs/mimari.md` §1). Streamlit'e yalnız `uygulama.py` bağımlıdır.
- Birim dönüşümü ve sınır karşılaştırması yalnız `kural/` katmanındadır;
  arayüz de dil modeli de yapmaz.

`tests/test_katmanlar.py`'nin denetlediği kurallar:

- Bütün kod bir katmanda durur; paket kökünde yalnız `__init__.py` vardır.
- Ürün kodu (`src/`) `deney/` paketini hiçbir yerde içe aktarmaz.
- `kural` katmanı `malzeme_kabul.cikarim`'ı içe aktarmaz.
- `sozlesme` katmanı yalnız `malzeme_kabul.sozlesme.sema` ve
  `malzeme_kabul.kural.birimler`'e bağlıdır.
- "Yalnız dil modeli" çıkarımı (`belgeden_cikar` vb.) üründe değil,
  `deney/` altındadır.
- Göreli içe aktarma yoktur.

Testin kapsamadıkları elle kontrol edilir:

- Tip ve sınıf katalogdan gelir; sertifikadan ya da dil modelinin
  okumasından tahmin edilmez.
- Her karar, onay ve düzeltme denetim kaydına yazılır. Kayıtsız durum
  değişikliği (ör. parti durumunun kayıt olmadan değişmesi) var mı?

### Güvenlik

- **Yanlış kabul yolları.** Sistemin birincil ölçütü yanlış kabul oranıdır.
  Bir sertifikanın ya da partinin yanlışlıkla "uygun" / `serbest` olduğu
  her yolu ara: eksik test, boş test listesi, olumsuz sonuç metni, tanımsız
  tip/sınıf, karantinadan makineyle çıkış, eşleşmeyen lot veya tedarikçi.
- **Yedek yol.** Hibrit modda model yanıt vermezse, kanıt doğrulanamazsa ya
  da kural yedeğine düşülürse karar hâlâ ihtiyatlı mı ("insan incelemeli")?
  Yedekte bir denetimin "uygun" çıkması yanlış kabul yolu açıyor mu?
- **İstem enjeksiyonu ve kanıt doğrulama.** Dil modelinin okuduğu her değer
  belgedeki kanıtla kuralla doğrulanıyor mu? Belgeye gömülü talimatlar
  kararı etkileyebilir mi?
- **Dış servis yok.** `src/` dış servis kütüphanesi içe aktarmaz; dil modeli
  istemcisi yalnız localhost'a bağlanır (`tests/test_dis_servis_yok.py`).
- **Denetim kaydının bütünlüğü.** Hash zinciri, tetikleyiciler, durum
  değişikliği ile kaydın aynı işlemde yazılması.
- **Parolalar ve roller.** Varsayılan ya da kodda gömülü parola var mı? Rol
  denetimi yalnız arayüzde mi yapılıyor?
- **Docker ağ yalıtımı.** Konteyner gerçekten ağsız mı; model dosyası ve
  veri yolları doğru mu?
- **Dosya yükleme.** Yol temizliği, üzerine yazma, kötü niyetli PDF.
- **`docs/guvenlik.md` §3-§6 önlemleri** uygulanmış mı:
  - §3: bağımlılıklar sabit sürümlü mü (`requirements.lock`), CI'da
    `pip-audit` çalışıyor mu?
  - §4: Ollama yalnız `127.0.0.1`'e bağlanıyor mu?
  - §5: model dosyasının SHA-256 özeti tutulup yükleme öncesi doğrulanıyor
    mu?
  - §6: konteyner root olmayan kullanıcıyla, salt okunur kök dosya
    sistemiyle çalışıyor mu; temel imaj özetle (`@sha256:...`) sabit mi?
- **`docs/guvenlik.md` güncel değil.** "Konteyner kullanılmıyor" ve
  "kullanıcı arayüzü ya da ağ sunucusu yoktur" ifadeleri artık doğru değil
  (#57, #58). Bunları doküman tutarsızlığı olarak raporla.

### Testler

- Her yeni fonksiyonun testi var mı?
- Testler davranışı mı tarif ediyor, yoksa uygulamanın iç ayrıntısını mı
  kopyalıyor?
- Gevşetilmiş, atlanmış (`skip`, `xfail`) ya da beklentisi değiştirilmiş
  test var mı? Varsa gerekçesi yazılmış mı?
- Kenar durumlar: boş girdi, eksik alan, birim farkı, sınırın tam üstü,
  bilinmeyen kap türü.
- `pytest` sonucunu raporuna ekle (geçen / kalan / atlanan sayıları).

### Proje kuralları (CLAUDE.md)

1. Birim dönüşümü ve sınır karşılaştırması asla dil modeline yaptırılmaz;
   kesin kurallarla (Python kodu) yapılır.
2. `data/gold/` klasörüne yazma yasaktır; hiçbir PR bu klasöre dokunmamalı.
3. Her yeni fonksiyon testle gelir.
4. Sistemin dil modeli yerel çalışır; dış API kullanılmaz.
5. İş önce planlanır, onaydan sonra kodlanır.

Ayrıca: test kümesine (`data/bolunme.yaml`'daki test listesi) dokunulmaz;
hiçbir kod ya da deney o standartları açmamalı.

## Raporlama

Her bulgu için şunları yaz:

- **Önem:** `kritik` (yanlış kabul ya da kayıtsız durum değişikliği gibi),
  `önemli` (yanlış red, güvenlik zayıflığı, mimari ihlali, eksik test),
  `küçük` (okunabilirlik, doküman tutarsızlığı).
- **Yer:** dosya:satır (ör. `src/malzeme_kabul/kural/karar_motoru.py:120`).
- **Senaryo:** somut girdi → yanlış sonuç (ör. sonuç metni "did not pass"
  → satır "uygun").
- **Öneri:** düzeltme önerisi (kod yazmadan, kısaca).
- **Test:** bu hatayı yakalayacak testin tarifi.

"Bilinen açıklar ve bekleyen işler" maddelerinin durumunu ayrı bir tabloyla
ver:

| Madde | Durum | Kanıt |
|---|---|---|
| 1 | kapandı / açık / yanlış anlatılmış | dosya:satır, PR ya da test adı |

Rapor yeri: her PR için ayrı bir dosya, `docs/inceleme/PR-NN.md` (klasör
henüz yok; ilk raporla oluştur). Raporları ayrı bir dalda, tek bir PR olarak
aç; Nida birleştirir. PR yorumu yalnız dosya yazamıyorsan yedek yoldur.

Her raporun sonunda tek bir sonuç satırı olsun: `ONAY` ya da
`DÜZELTME GEREKLİ`. Bir `kritik` bulgu ya da bir veya daha fazla `önemli`
bulgu varsa sonuç `DÜZELTME GEREKLİ` olur; Nida aksini söyleyebilir.
Yalnız `küçük` bulgular varsa sonuç `ONAY` olabilir. Emin olmadığın
bulguları "Emin olunmayanlar" başlığı altında ayrıca listele; neyi
doğrulayamadığını yaz.

## Sınırlar

- Codex PR birleştirmez ve onay vermez. Sonuç satırı yalnız öneridir; onay
  yetkisi proje sahibindedir.
- Kod, test ya da doküman değiştirmez; yalnız `docs/inceleme/` altına rapor
  dosyası ekler.
- `data/gold/` klasörüne yazmaz ve içeriğine dokunmaz.
- Test kümesi (`data/bolunme.yaml`'daki test listesi ve kilitli klasörler)
  kullanılmaz; o belgeleri açmaz, üzerinde çıkarıcı çalıştırmaz.
- Dış servise veri göndermez; belgeleri, kodu ya da raporları depo dışına
  çıkarmaz.
