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


## Colab çıktıları ve sınır yönü kuralı

1. **Colab çıktılarının yeri.** 6 dosya `deney/sonuclar/colab/` altına `git mv` ile
   taşındı (içerik aynı). Klasöre README ve geçici değerlendirme raporu
   (`degerlendirme.md`) da kondu; ürün bu klasörü okumaz. Ayrı PR (#46).
2. **"6. kör nokta" adı.** Depoda numaralı bir kör nokta listesi bulunamadı. Bunu
   mimarideki dil modeli sınırının (docs/mimari.md madde 6) kör noktası olarak
   okudum: madde 6'ya kısa bir paragraf, ayrıntılar ve örnekler için
   `docs/sinir_yonu_hatasi.md` eklendi. Listen başka bir yerdeyse numarayı oraya taşı.
3. **Plan onayı (CLAUDE.md kural 5).** Gece soru sorulmaması istendiği için plan
   ayrıca onaya sunulmadı; aşağıdaki tasarım buraya yazılıp uygulandı. Test önce
   yazıldı (kural 3); alt ajan zinciri yerine aynı sırayla (test → kod) elle çalışıldı.
4. **Çelişkide ne olur?** Red değil, insan incelemesi: sınır `yon="belirsiz"` yapılır,
   sayılar korunur. Gerekçe: kural da metni yanlış okuyabilir; en kötü durumda yanlış
   alarm üretsin, yanlış kabul ya da yanlış red üretmesin.
5. **Metin yön söylemiyorsa ya da karışıksa** (iki yön, ya da aralık ile tek yön
   birlikte) kural karar vermez, model yönü kalır. Bunları da insana göndermek
   şartların büyük kısmını incelemeye düşürürdü; amaç açık çelişkiyi yakalamak.
6. **Koşul aralıkları.** nm, °C ve °F ile yazılan aralıklar test koşulu sayıldı (kural
   çıkarıcısı da °C aralıklarını atlıyor). Kalınlık aralıkları (mil, µm) sayılmadı,
   çünkü numune şartında asıl sınır onlar olabilir; bunlar "karışık" kuralına düşüyor.
7. **Nereye bağlandı?** `deney/yalniz_dil_modeli.belgeden_cikar` (çelişkiler
   `_rapor.json` içinde `yon_celiskileri`) ve ürün sözleşmesi için
   `okuma_yonu_dogrula(HamOkuma)`. Ürün içi dil modeli hattı henüz yok; hibrit hat işi
   bu fonksiyonu çağırmalı.
8. **Yanlış alarm denetimi** `data/gold_taslak` ve `data/gold_codex` ile yapıldı (yalnız
   okundu, ikisi de onaysız): 476 testte 0 çelişki.

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
