# Gece kararları

Nida'nın 25 Kasım 2026 gece talimatı: belirsiz noktada makul karar ver, gerekçesiyle buraya yaz, devam et.
Her karar sabah onaylanmak üzere; yanlışsa geri alınır.

## Alfa Aesar / Spectrum eşleştirmesi ve OCR işareti

1. **MIL-S-81733C de "OCR gerekli" listesinde.** İstenen yalnız MIL-A-46146B idi; ama 81733C de bütün
   sayfaları taranmış (data/raw/pdf_turleri.csv) ve metni okunamıyor. Liste pdf_turleri.csv'deki
   "taranmış" belgelerle aynı tutulsun diye ekledim (test bunu denetliyor). 81733C geliştirme kümesinde
   kalıyor; yalnız çıkarıcılar onu "OCR gerekli" diye reddediyor.
2. **Kısmen taranmış belgeler metin tabanlı sayıldı.** MIL-PRF-23377G (hazır OCR katmanlı), MIL-PRF-27617F
   ve MIL-PRF-81733D (bir sayfası taranmış) şu an kullanılıyor; bunları engellemek mevcut işleri bozardı.
3. **Thermo Fisher de yeni betikle yeniden eşleştirildi.** Tek yöntem olsun diye `deney/coa_eslestirme.py`
   üç tedarikçiyi birden işliyor; Thermo sonucu PR #43'teki ile birebir aynı (259 satır, 223 / 6 / 30) ve
   test bunu sabitliyor.
4. **Sigma-Aldrich eşleştirilmedi.** Tek şartnamesi başka bir düzende ve sertifikası tek lot ("eksik");
   ölçüme girmiyor.
5. **Yeni durum: "var; şartnamede sınır yok".** Spectrum şartnamesinde APPEARANCE gibi sınırı boş kalemler
   var; bunları "sınır farklı" saymak yanıltıcı olurdu.
6. **Birim çevrimi yalnız %, ppm, ppb arasında, kesin oranla.** `10 ppm max` ile `≤0.001%` aynı sayılıyor ve
   "birim çevrilerek" notu düşülüyor. Başka birimler metin olarak karşılaştırılıyor.
7. **044227 Sodium nitrite'in ICP ızgarası şartnamenin "Total Metal Impurities" kalemine bağlandı**
   (`eslesme=toplam`). Şartname elementleri tek tek sınırlamıyor; kontrol listesinde tek soru olarak duruyor.
8. **014103'te "On 18 mesh" ile şartnamenin "+16 screen" kalemi eşlenmedi**: elek farklı, aynı ölçüm değil.

## 81733D / 85285E etiketleme kararlarının uygulanması

Nida'nın 25 Kasım kararları (soyulma tablosu satır satır, etiketleme/ambalaj "muayene", bölme düzeyi)
etiketleme kılavuzuna K8–K10 olarak, bağımsız etiketleme istemine Kapsam 8–9 olarak yazıldı.

1. **`muayene` tek başına bir test türü.** Kabul ya da yeterlilikle birleşemez; şema birleşimi reddeder.
   Böylece `kabul_testleri` muayene şartlarını kendiliğinden dışarıda bırakıyor: CoC'de aranmıyor,
   sentetik sertifikaya ve doğru karara girmiyor, yani FAR ölçümüne girmiyor. Karar motorunda kod
   değişikliği gerekmedi. Parti düzeyinde iç muayenenin karara nasıl bağlanacağı (ör. muayene
   girilmeden parti "bekliyor") parti kuralı işine bırakıldı.
2. **"İç muayene" yeni bir sonuç kaynağı (`ic_muayene`).** `muayene` şartında sonuç kaynağı boş
   bırakılırsa şema `ic_muayene` koyuyor; `ic_laboratuvar` verilirse ya da `ic_muayene` başka bir türde
   kullanılırsa hata veriyor.
3. **"Koşul alanı" = yeni `TestSarti.test_kosulu` (serbest metin).** Mevcut `kosullar` listesi depolama
   ve kullanım koşulları içindir; testin uygulandığı sıcaklık/süre/ortam için ayrı bir alan açtım.
   Serbest metin olduğu için alan bazında F1'e girmiyor (`orijinal_metin` gibi); ölçmek istersen sonra
   yapılandırılmış alanlara bölünebilir.
4. **Bölüm = kaydın şart maddesi (`kaynak.madde`).** Bölüm ortalaması her maddenin P/R/F1'inin
   aritmetik ortalaması. Gold'daki kayıt gold'un maddesine, yalnız tahminde olan kayıt tahminin
   maddesine yazılıyor. Bir tablo hem "TABLE I" hem "3.3.1.3" diye kaynaklanabildiği için iki taslak
   aynı şartı farklı bölümlere koyabilir; doğru cevapta hangisinin kullanılacağı kılavuzda zaten
   "şartın yazdığı madde (3.x ya da tablo)" diye tanımlı.
5. **`deney/degerlendir.py` tablosunun sonuna "GENEL (bölüm ortalaması)" satırı eklendi**
   (dp/yp/yn sütunları boş). `--bolumler` bölüm tablosunu da yazıyor. Mevcut bir test son satırın
   "GENEL (mikro)" olduğunu denetliyordu; son iki satırı denetleyecek biçimde güncellendi.
6. **Dil modeli çıkarıcısının istemi (`deney/yalniz_dil_modeli.py`) bu işte değiştirilmedi.** Şemadan
   türeyen JSON şeması `muayene` ve `test_kosulu`'nu kendiliğinden içeriyor; istem metnine kural
   eklemek istem sürümünü değiştirir ve Colab ölçümünü etkiler. Colab işine bırakıldı.
7. **Taslaklar yeni kurallara göre yeniden etiketlenmedi.** Claude taslakları (`data/gold_taslak/`)
   ve Codex dosyaları (`data/gold_codex/`) olduğu gibi kaldı; Codex'i güncel istemle yeniden
   çalıştırmak ve Claude taslağını K8–K10'a göre düzeltmek ayrı iş. Karşılaştırma mevcut dosyalarla
   yeniden çalıştırıldı.
8. **Kanıt kontrolünde tolerans kalıbı X ile ± arasında en çok üç rakamsız sözcüğe izin veriyor**
   ("6 fluid ounces ± 1/8"). Daha uzun aralar yanlış eşleşme riski taşıdığı için alınmadı.

## Gece işi 1: katalog veritabanı

- **Örnek kabul dokümanları `data/cikti/` taslaklarından yüklendi, `data/gold_taslak/`
  kullanılmadı.** Gold taslakları doğru cevap adayıdır; ürünün verisine
  karışırsa ölçüm kirlenir. Sonuç: 81733D ve 85285E çıktılarında kural
  çıkarıcının bulduğu test yok (0 test), yalnız 23377K'da 27 test var. Ekran
  ve karar gösterimi 23377K ile anlamlı.
- **Örnek dokümanlar v1 olarak "onaylı" kaydedildi, onaylayan `ornek-veri`.**
  Giriş kalite yalnız onaylı sürümle karar verebildiği için örnek akışın
  çalışması buna bağlı. Not alanında "M&P onayı değildir" yazar.
- **Onaylı sürümler ayrı tabloda, değiştirilemez.** Taslaklar bu tabloya girmez;
  düzeltme yeni sürümdür. SQLite tetikleyicileri UPDATE ve DELETE'i reddeder,
  içerik okunurken SHA-256 özetiyle denetlenir.
- **Malzeme kodu belirli bir sürüme değil, standart + revizyona bağlı;** karar
  en son onaylı sürümle verilir. Böylece M&P yeni sürüm onaylayınca malzeme
  kaydı değişmeden yeni sürüm geçerli olur.
- **Parti yalnız o malzeme için onaylı tedarikçiden kaydedilebilir;** onaysız
  tedarikçi hata verir (sessizce karantinaya almak yerine).
- **Malzeme kodları, tedarikçiler ve lotlar uydurmadır** (`AST-001`,
  `Örnek Tedarikçi A` ...). Sınıflar: AST-001 Type I Class N, AST-002 Type I
  Class C2, SZD-001 (81733D) Type I Class 1, PUB-001 (85285E) Type I Class H.

## Gece işi 2: karar motoru katalogdan

- **Tip/sınıf katalogdan alınır; sertifikadaki atıf yalnız çelişki için okunur.**
  Çelişirse (`tip_sinif` satırı) insan incelemeli; red değil, çünkü yanlış
  malzeme mi geldi yoksa sertifika mı yanlış yazıldı, insan karar verir.
- **Parti kararı katalogdaki durumlara şöyle eşlendi:** kabul → `serbest`,
  red → `karantina`, inceleme → `bekliyor`. Katalogda "red" diye ayrı durum
  istenmediği için reddedilen parti karantinada tutulur.
- **İki ek denetim:** sertifikadaki tedarikçi onaylı listede yoksa ve partinin
  sipariş revizyonu kabul dokümanının revizyonundan farklıysa insan
  incelemeli. Tedarikçi adı büyük/küçük harf ve boşluk farkını yok sayar;
  başka yazım farkları insana gider.
