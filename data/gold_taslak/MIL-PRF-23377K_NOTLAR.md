# MIL-PRF-23377K doğru cevap taslağı: kontrol notları

`MIL-PRF-23377K.json`, standart metninden elle hazırlanmış **taslak** doğru
cevaptır. Çıkarıcının çıktısından kopyalanmadı; her değer standarttaki maddeye
bakılarak yazıldı. Durum: 1–5 ve 7–9 onaylandı, 6 aşağıdaki gibi düzeltildi. Değerler henüz
kontrol edilmedi (`MIL-PRF-23377K_kontrol_listesi.md`). Nida kontrol edip düzelttikten sonra `data/gold/` altına
kendisi taşıyacak (o klasöre kod yazmaz).

Değerlendirme test kayıtlarını `id` ile, koşulları `kategori:ad` ile eşleştirir.
Bir `id` ya da koşul adını değiştirirsen çıkarıcı o kaydı bulamaz; o yüzden
adları değiştirirken iki tarafı birlikte düşün.

## Kontrol etmeni istediğim kararlar

1. **Bir paragrafta iki kriter varsa iki ayrı test yazdım.** Çıkarıcı yalnız
   ilkini alıyor, bu taslak ikisini de bekliyor:
   - 3.4: kadmiyum ≤ 1 ppm (`lead_and_cadmium_content`) ve kurşun ≤ %0,05
     (`lead_and_cadmium_content_lead`).
   - 3.7.2: yapışmazlık ≤ 5 saat (`drying_time`) ve sert kuruma ≤ 8 saat
     (`drying_time_dry_hard`).
   - 3.8.2.2: filiform ≤ 6,35 mm ve filamentlerin çoğu < 3,175 mm
     (`..._filament_length`, üst sınır dahil değil).
2. **4.3.2 "Visual inspection of filled containers"** TABLE II'de yok ama her
   partide yapılan bir kabul muayenesi; yalnız `kabul` türüyle ekledim.
3. **Kriter türleri:** "Kabarma olmayacak" türü şartları `metinsel`, sonucu
   geçti/kaldı olan şartları `gecti_kaldi` yaptım: depolama kararlılığı ve
   hızlandırılmış depolama ("bütün şartları sağlamalı"), solvent direnci
   (50 sürtmede alt malzemeye inmemeli), toksisite (HHA değerlendirmesi).
4. **Yapışma 4A:** ASTM D3359 derecesi; sayısal `alt = 4`, birimsiz yazdım.
   Harf (A: X-kesim yöntemi) birimde değil, orijinal metinde duruyor.
5. **Inceltik (Hegman) değeri** pint'te birim olmadığı için birimsiz.
6. **Raf ömrü:** Nida'nın kararıyla şema kap türüne göre birden çok kayda izin
   veriyor. Metal kap 1 yıl ve plastik kap 6 ay ayrı kayıtlar; ikisinde de
   depolama sıcaklığı 1,7–46 °C (3.5.3). Önceki "Plastik kaplarda raf ömrü"
   koşulu kaldırıldı.
7. **Test türleri:** 4.2'ye göre bütün testler `yeterlilik`; 4.3'te istisna
   sayılanlar (depolama kararlılığı, hızlandırılmış depolama, korozyon direnci
   yani tuz sisi ve filiform, toksisite, sökülebilirlik) yalnız `yeterlilik`,
   diğerleri `kabul` + `yeterlilik`.
8. **Panel bağlantıları:** 4.5.x'teki "panels designated X" ifadelerine göre.
   Kuruma süresi için TABLE II dipnotu (1/ "Use panels designated A") → A.
   Uygulama (4.5.11.2) ve sökülebilirlik (4.5.13) panel harfi vermiyor, boş.
9. **Serbest metin alanları** (uygulama yöntemi, kürlenme, orijinal metin)
   standarttaki İngilizce cümleyle aynen yazıldı. Değerlendirme orijinal
   metni ölçmüyor; uygulama yöntemi ve kürlenme metin olarak karşılaştırılıyor.

## İlk ölçüm (yalnız kural, bu taslağa göre)

`python deney/degerlendir.py data/cikti/MIL-PRF-23377K_kabul_dokumani.json data/gold_taslak/MIL-PRF-23377K.json`

Genel (mikro): P = 0,959, R = 0,835, F1 = 0,892. Ayrıntı:
`data/cikti/MIL-PRF-23377K_kural_degerlendirme.csv`. Kayıplar çoğunlukla
yukarıdaki 1. ve 2. maddelerdeki eksik testlerden, kriter türünden
(geçti/kaldı ↔ metinsel), kuruma süresinin panel bağlantısından ve raf
ömründen geliyor: çıkarıcı kap türü vermeden tek bir "1 yıl" kaydı üretiyor,
taslak ise metal ve plastik için iki kayıt bekliyor. Gold onaylanana kadar
çıkarıcı bu belgeye göre düzeltilmiyor.

## Nida'nın kontrolü (ilk 5 satır)

- 2–5. satırlar doğru.
- 1. satır: 3.4'teki ≤ 1 ppm şartı yalnızca kadmiyum içindir. Test adı
  "Cadmium content" yapıldı; tablodaki "Lead and cadmium content" adı yeni
  `kaynak_tablo_adi` alanında tutuluyor (kurşun satırında da). Çıkarıcı, tablo
  satırı "X and Y content" biçimindeyse adı şart cümlesinin andığı bileşenden
  alıyor; karar motoru sertifikada önce test adını, sonra tablo adını arıyor
  ve tablo adı birden çok teste uyuyorsa satırı insan incelemesine bırakıyor.
  Çıkarıcı hâlâ ayrı kurşun satırı üretmiyor; F1'deki küçük düşüş
  (0,893 → 0,892) bu satırın tablo adı alanından geliyor.
