# Sınıra yakınlık politikası

Kaynak: Codex incelemesi, `docs/inceleme/codex_raporu.md` (PR #52 bulgusu:
"Sınırın dışındaki değer dönüştürme sırasında sınıra yuvarlanıyor"). Eski
`birimi_cevir` sonucu 12 anlamlı basamağa yuvarlıyordu; "en çok 1 s" şartına
karşı 1.0000000000004 s okunan değer 1 s olup **uygun** çıkabiliyordu
(yanlış kabul).

Proje sahibinin kuralı: karşılaştırma, standarttaki ve sertifikadaki değerler
yuvarlanmadan yapılır; sınıra çok yakın değerler insan incelemesine gider.

## Kural

Uygulama: `src/malzeme_kabul/kural/karar_motoru.py` (`birimi_cevir`, `_degerlendir`).

1. `birimi_cevir` yuvarlamaz; pint'in verdiği değer aynen kullanılır. Standart
   sınırı da olduğu gibi kullanılır.
2. Birime çevrilmiş okumanın her uç noktası `e` ve şartın her sınırı `b` için
   `math.isclose(e, b, rel_tol=SINIR_YAKINLIK_BAGIL, abs_tol=SINIR_YAKINLIK_MUTLAK)`
   doğruysa karar **insan incelemeli** olur. Gerekçede "sınıra çok yakın" ve
   değerin yuvarlanmamış hali (`repr`) yazılır.
3. İstisna: üç koşul birlikte sağlanırsa bu çift atlanır ve dahil/hariç
   kuralı karar verir ("5 hour" ile "en çok 5 hour" uygun):
   - birim dönüşümü yok (ikisi de birimsiz ya da aynı birim, ör. "saat" ile
     "hour"),
   - uç sınıra tam eşit,
   - sertifikadaki sayı metni float'a kayıpsız sığıyor:
     `Decimal(sayi_metni.replace(",", ".")) == Decimal(repr(float))`.
     "<"/">" önekli metinlerde ve "ND (<0.5 ppm)" gibi algılama sınırlı
     sonuçlarda denetim sayı kısmına uygulanır (`Sonuc.sayi_metni`).
     "1.00000000000000001" float'ta 1.0 olur ama gerçek değer 1'in
     üstündedir; bu yüzden kayıpsız sayılmaz, bant içinde kalır ve insana
     gider. "0.1" float'ta tam değildir ama repr'i "0.1" olduğu için kayıpsız
     sayılır. Birim dönüşümü
   yapıldıysa tam eşitlik de bant içindedir, çünkü dönüşümden çıkan değerin
   tam eşitliği kayan nokta hatasına bağlıdır.
4. Bandın dışı eskisi gibi: açıkça içeride uygun, açıkça dışarıda uygun değil.

Bu denetim yön belirsizliği, sayı okunamadı, birim çelişkisi ve çevrilemeyen
birim denetimlerinden sonra yapılır.

## Eşikler

| Sabit | Değer | Anlamı |
|---|---|---|
| `SINIR_YAKINLIK_BAGIL` | 1e-6 | bağıl tolerans |
| `SINIR_YAKINLIK_MUTLAK` | 1e-12 | mutlak tolerans, sınır birimi cinsinden (sıfır sınır için) |

Gerekçe: 1e-6, pint dönüşümündeki kayan nokta hatasının (~1e-15) çok
üstünde, gerçek CoC ölçüm çözünürlüğünün (genelde 3-4 anlamlı basamak) çok
altındadır. Böylece yalnız "sınırda" sayılabilecek değerler yakalanır.
Bunun bir bedeli var: birim dönüşümü gerektiren ve sınıra tam eşit gerçekçi
değerler de artık insana gidiyor ("300 dk" ile "en çok 5 saat", "60 s" ile
"en çok 1 dk"). Eskiden bunlar uygun çıkıyordu. Aynı birimde yazılan tam
sınır değerlerinin kararı değişmez. Mutlak tolerans yalnız sınırın 0 olduğu
durumda (bağıl tolerans orada işe yaramaz) devreye girer.

**Eşik değerleri proje sahibinin onayına açık bir karardır.** Değiştirilirse
`tests/test_sinir_yakinligi.py` ile birlikte güncellenmelidir.

## Örnekler

| Şart | Sertifika | Karar | Neden |
|---|---|---|---|
| en çok 1 s | 1.0000000000004 s | insan incelemeli | aynı birim, sınıra çok yakın (eskiden yuvarlanıp uygun çıkıyordu) |
| en çok 1 s | 1000.0000000004 ms | insan incelemeli | çevrilmiş değer 1.0000000000004 s, sınıra çok yakın |
| en çok 1 s | 1 s | uygun | aynı birim, tam eşit: dahil kuralı |
| en çok 1 s | 1.00000000000000001 s | insan incelemeli | metin float'a kayıplı (1.0 olur), istisna uygulanmaz |
| en az 1 s | >0.99999999999999999 s | insan incelemeli | metin float'a kayıplı, istisna uygulanmaz |
| en çok 1 dk | 60 s | insan incelemeli | birim dönüşümü var, tam eşitlik bant içinde |
| en çok 5 saat | 300 dk | insan incelemeli | birim dönüşümü var, tam eşitlik bant içinde |
| en çok 1 s | 999.9 ms | uygun | bağıl fark 1e-4, bandın dışında |
| en çok 340 g/L | 340.001 g/L | uygun değil | bağıl fark ~2.9e-6, bandın dışında |
