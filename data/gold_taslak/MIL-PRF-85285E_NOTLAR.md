# MIL-PRF-85285E doğru cevap taslağı: kontrol notları

`MIL-PRF-85285E.json` standart metninden elle hazırlanmış **taslak** doğru
cevaptır; çıkarıcı çıktısından kopyalanmadı (çıkarıcı bu belgeden yalnız metal
kap raf ömrünü çıkarabildi). Kontrol için `MIL-PRF-85285E_kontrol_listesi.md`
dosyasını kullan. Onaydan sonra `data/gold/` altına kendin taşıyacaksın.

Şema: raf ömrü `raf_omurleri` listesi (metal kap 1 yıl, plastik kap 6 ay).

## Belgenin yapısı (23377K'dan farkları)

- Poliüretan son kat boya. Tip I–IV (uçak, yer ekipmanı, düşük VOC, uzun
  hava dayanımı), sınıf H (yüksek katı) ve W (su bazlı). Bazı sınırlar renk
  türüne (parlak, yarı parlak, kamuflaj) ya da renk numarasına göre değişiyor.
- TABLE IV'te sütun sırası farklı: önce şart maddesi, sonra test adı, test
  maddesi ve iki ayrı metot sütunu (EPA, ASTM).
- Kabul kapsamı 4.4.1'de "except ..." ile veriliyor.

## Kontrol etmeni istediğim kararlar

1. **Renk türüne/tipe göre değişen sınırlar ayrı kayıt.** `uygulanabilirlik`
   alanına tip, sınıf ve renk türünü yazdım ("Gloss", "Semi-gloss",
   "Camouflage", "Color 34095" gibi). Örnek: VOC 3 kayıt, VOHAP 7 kayıt,
   parlaklık 4 kayıt (85° kamuflaj ayrı), hava dayanımı 8 kayıt.
2. **"composition (3.4)" kabul dışı.** 4.4.1 kabul dışı listesinde
   "composition (3.4)" var. Bunu yalnız 3.4 satırları (kurşun/kadmiyum,
   krom) olarak okudum; **VOC (3.4.1) ve VOHAP (3.4.2) kabul testi** kaldı.
   3.4'ün alt maddelerini de kapsıyor dersen bu 10 kayıt yalnız yeterlilik
   olur. Bu karar sertifika üreticisini ve karar motorunu etkiliyor.
3. **Kadmiyum ve altı değerli krom** "içermeyecek" diye yazılmış, sayı yok →
   metinsel. Kurşun ≤ %0,05 ayrı sayısal kayıt (`lead_and_cadmium_content_lead`).
4. **Viskozite ve kap ömrü (TABLE II):** üç kayıt: başlangıç ≤ 30 s, 4 saat
   ≤ 60 s, 5 saat jelleşme yok (metinsel).
5. **Kuruma süresi:** dokunma kuruluğu ≤ 6 saat ve sert kuruma ≤ 12 saat, iki
   kayıt. Panel bağlantısı yok (tabloda dipnot yok).
6. **"Less than" sınırları dahil değil:** renk farkı ΔE < 1 (3.7.3), hava
   dayanımındaki ΔE < 1,0 ve parlaklık değişimi < 20 / < 3 kayıtlarında
   `ust_dahil = false`. Isı dayanımı ΔE ≤ 1,0 (3.8.4 "less than or equal")
   dahil.
7. **Birimsiz değerler:** Hegman inceliği, parlaklık (G.U.), kontrast oranı,
   ΔE, ASTM D3359 derecesi (4A → 4). Kızılötesi yansıma (3.7.4) "not greater
   than 8" diyor, birim yazmıyor; birimsiz bıraktım (23377K'da %'ydi, bakmanı
   istiyorum).
8. **İnceltik (fineness of grind)** parlak ≥ 7, kamuflaj ≥ 5. Yarı parlak
   renkler için değer verilmemiş; kayıt yok.
9. **Hızlandırılmış depolama:** TABLE IV "(component B only)" diyor, 3.5.3
   ise "coating components" diyor. Tablodaki adı aldım, kabul + yeterlilik.
10. **TABLE IV'te olmayan şartlar:** 3.9.1 karıştırma ve 3.9.2 uygulama test
    olarak yazılmadı. 3.9.2'deki uygulama sıcaklığı (15,6–32,2 °C), bağıl nem
    (%20–80) ve kuru film kalınlığı (1,7–2,3 mil) kullanım koşulu olarak
    yazıldı. 4.4.1.1 dolu kap görsel muayenesi yalnız kabul testi.
11. **Bekleme (indüksiyon) süresi ≥ 30 dakika** 4.5.2.2'den (test paneli
    hazırlığı) alındı; önlem listesinde (3.10.3) yok. Kap ömrü ≤ 4 saat
    3.10.3 c'den.
12. **Numune hazırlığı:** iki panel: `panel_standart` (4.5–4.5.2: 2024-T3,
    MIL-DTL-5541 dönüşüm kaplama, astar + son kat, 14 gün kür) ve
    `panel_esneklik` (4.6.7: 2024-O, MIL-A-8625 type I anodize, astarsız).
    "4.5 through 4.5.2" diyen testler `panel_standart`'a, esneklik testleri
    `panel_esneklik`'e bağlandı.
13. **Sayfa numaraları:** değer bir tablodaysa tablonun sayfası (VOHAP s. 7);
    hava dayanımının Type IV kısmı s. 9'dan s. 10'a taşıyor, (b)–(d) kayıtları
    s. 10.
