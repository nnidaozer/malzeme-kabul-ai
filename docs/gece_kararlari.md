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
