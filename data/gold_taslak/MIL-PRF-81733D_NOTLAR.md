# MIL-PRF-81733D doğru cevap taslağı: kontrol notları

`MIL-PRF-81733D.json` standart metninden elle hazırlanmış **taslak** doğru
cevaptır; çıkarıcı çıktısından kopyalanmadı (çıkarıcı bu belgeden hiçbir test
çıkaramadı). Kontrol için `MIL-PRF-81733D_kontrol_listesi.md` dosyasını kullan.
Onaydan sonra `data/gold/` altına kendin taşıyacaksın.

Şema: raf ömrü `raf_omurleri` listesi olarak yazıldı (kap türüne göre birden
çok kayıt, 6 numaralı kararın).

## Belgenin yapısı (23377K'dan farkları)

- Malzeme bir sızdırmazlık macunu. Tip (I–IV, uygulama şekli), sınıf (1
  polisülfür, 2 politiyoeter), derece (A kromatlı, B kromatsız) ve tire
  numarası (saat cinsinden uygulama süresi, ör. Type II-1/2) var.
- Sınırların çoğu tip/sınıf/tire numarasına göre değişiyor ve tablolarda
  duruyor (TABLE I–IV).
- Yeterlilik testleri TABLE V'te, kabul testleri **ayrı bir tabloda** (TABLE
  VI) sayılıyor; "with the exception of" cümlesi yok.

## Kontrol etmeni istediğim kararlar

1. **Tip/sınıfa göre değişen sınırları ayrı test kaydı yaptım.** Örnek:
   uçucu olmayan madde 5 kayıt (Type I, II, III, IV-Class 1, IV-Class 2),
   sertlik 2 kayıt, özgül ağırlık 2 kayıt. Kayıt hangi tip/sınıfa geçerliyse
   `uygulanabilirlik` alanında yazıyor.
2. **Yapışmazlık süresi (tack-free, TABLE IV) 15 kayıt**, tip + sınıf + tire
   numarası başına. Tablonun metin katmanında üç tuhaflık var, PDF'te gözle
   bakmanı istiyorum (s. 8):
   - Type II-1/4 Class 2 = **1 saat**, Type II-1/2 Class 2 = **2 saat**:
     Class 1 değerlerinden (8 ve 16 saat) çok düşük. Metinde böyle yazıyor,
     ben de böyle yazdım.
   - Type II-4 Class 1 hücresi "—". 1.2.4'e göre Class 1'de -4 var; bu
     kombinasyon için kayıt yazmadım.
   - Type IV TABLE IV'te yok (4.8.5 de yalnız Type I, II, III diyor); Type IV
     için yapışmazlık kaydı yok.
3. **Uygulama süresi (application time):** sınır, tire numarasının gösterdiği
   süre sonunda ölçülen değerdir: Type I ≤ 2500 poise, Type II ≥ 15 g/dk,
   Type III ≤ 300 poise, Type IV Class 1 ≥ 30 g/dk, Class 2 ≥ 50 g/dk. Sürenin
   kendisi (tire numarası) test koşulu sayıldı ve "Uygulama süresi (tire
   numarası)" kullanım koşulu olarak yazıldı.
4. **Kabul testleri TABLE VI'ya göre:** uçucu olmayan madde, akış, uygulama
   ömrü (ilk viskozite + uygulama süresi), sertlik, özgül ağırlık, ısıl
   kararlılık, soyulma direnci, ankraj (Type III), ambalaj birimi, uyarı
   etiketi. Diğerleri yalnız yeterlilik.
   - TABLE VI soyulma için yalnız "initial (Adherend #1)" diyor. Soyulma
     kayıtlarını kabul + yeterlilik yaptım ve `adherend_1` numunesine
     bağladım; daldırma sonrası soyulma kabulde aranmıyor.
5. **Bir paragrafta iki kriter, iki kayıt** (23377K'daki kuralın aynısı):
   - 3.3.2.5 ısıl kararlılık: kabarma/çatlama yok (metinsel) + sertlik
     değişimi -5 ile +15 puan arası (`thermal_stability_hardness_change`).
     4.8.11'e göre Type III'te sertlik ölçülmüyor; bu kaydı Type I, II, IV
     ile sınırladım.
   - 3.3.2.8 soyulma: sınıfa göre en az 15 / 20 piw + %100 kohezif kopma.
   - 3.3.2.10 tamir edilebilirlik: metinsel + en az 10 piw (Type I, II, IV).
6. **Birimler (pint):** inch, poise, g/min, psi; "pounds per inch width (piw)"
   için `lbf/inch` yazdım. Sertlik (Shore A-2) ve özgül ağırlık birimsiz.
   Ankraj "1/8 inch'ten fazla genişleme olmayacak" → ≤ 0,125 inch.
7. **Raf ömrü:** belgede açık bir raf ömrü maddesi yok. 3.3.3 "Long-term
   storage" 9 ay depolamadan sonra şartları sağlamayı istiyor (yeterlilik
   testi); 23377K'daki depolama kararlılığı gibi bunu raf ömrü saydım: 9 ay,
   kap türü belirtilmemiş, koşul 4.8.17'deki 25 ± 3 °C (22–28 °C). Bu bir test
   koşulu olduğu için ayrıca "depolama sıcaklığı" koşulu yazmadım. Raf ömrü
   saymak istemezsen kaydı silmen yeter.
8. **Numune hazırlığı:** 23377K'daki gibi harfli panel tablosu yok. Yalnız
   soyulma testinin TABLE X adherendlerini (1–7) numune olarak yazdım; diğer
   testlerin numuneleri test maddesinin içinde tarif ediliyor.
9. **3.2.4 Skin contact warning labels:** madde numarasından sonra nokta var
   ("3.2.4."). Çıkarıcı bu maddeyi göremiyor; taslakta madde 3.2.4, sayfa 6.
10. **Sayfa numaraları:** değer bir tablodaysa tablonun sayfası (ör. uçucu
    olmayan madde 3.3.1.3 maddesi s. 6'da başlıyor, TABLE I s. 7'de; sayfa 7
    yazıldı). PDF'in 34. sayfası taranmış görüntü; içerik açısından önemli
    değil (son sayfa).
