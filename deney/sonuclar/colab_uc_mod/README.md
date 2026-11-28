# Colab üç mod sonuçları (28 Kasım 2026)

`deney/uc_mod.py` ile Colab'da `qwen3:8b` (düşünme kapalı, Ollama) kullanılarak üç geliştirme
belgesinde üç mod koşuldu: **yalnız kural**, **yalnız dil modeli**, **hibrit**. Dosyalar Nida'nın
yüklediği zip'ten değiştirilmeden alındı. Bu klasör deney sonucudur; ürün (`src/`) bunu okumaz.

> **GEÇİCİ sonuçlar.** MIL-PRF-81733D ve MIL-PRF-85285E sayıları, Nida'nın kontrolünden
> geçmemiş `data/gold_taslak/` ve `data/gold_codex/` dosyalarıyla ölçüldü. Bu iki standardın her
> sayısı **GEÇİCİ**dir; istem ya da çıkarıcı bu sayılara bakılarak ayarlanmamalıdır.
> MIL-PRF-23377K, Nida'nın kontrol ettiği `data/gold_taslak/MIL-PRF-23377K.json` ile ölçüldü
> (dosya henüz `data/gold/` altına taşınmadı; `data/gold/` boş).

## Dosyalar

| Dosya | İçerik |
|---|---|
| `ETIKET_kural.json`, `ETIKET_dil_modeli.json`, `ETIKET_hibrit.json` | Her modun kabul dokümanı (KabulDokumani) |
| `ETIKET_uc_mod_rapor.json` | Model, süreler, test sayıları, sayfa raporu, hibrit raporu, anlaşmazlıklar, genel F1 |
| `ETIKET_uc_mod_olcum.csv` | Her mod × her gold için hizalı alan bazında P/R/F1 |
| `ETIKET_ara/` | Dil modelinin sayfa başına ara kaydı |
| `kanit_kontrolu/ETIKET_MOD.csv` | `deney/kanit_kontrol.py` çıktısı: her sayısal değerin sayfada bulunup bulunmadığı |
| `ozet_alan_f1.csv` | Üç standardın ölçüm CSV'lerinin tek tabloda özeti; `durum` sütunu `GECICI` ya da `kontrollu_taslak` |

## Doğrulama

- Bütün JSON'lar şemaya (KabulDokumani) uyuyor.
- Genel F1'ler bu depodaki kodla (`degerlendir` + `kaydi_eslestir`) yeniden hesaplandı; 15 sayının
  15'i Colab raporuyla birebir aynı.
- Kural çıktısı bu depodaki kodla yeniden üretildi: 23377K 27 test, 81733D 0 test, 85285E 0 test
  (1 raf ömrü). Colab'dakiyle aynı.
- Uydurma değer sayısı `deney/kanit_kontrol.py` ile her mod çıktısı için ayrıca çalıştırıldı.

## 1. Genel F1 (hizalı, mikro, bütün alanlar)

| Standart | Gold | Durum | Kural | Dil modeli | Hibrit |
|---|---|---|---|---|---|
| MIL-PRF-23377K | gold_taslak (31 test) | kontrollü | **0,892** | 0,369 | 0,735 |
| MIL-PRF-81733D | gold_taslak (55 test) | **GEÇİCİ** | 0,000 | **0,191** | 0,174 |
| MIL-PRF-81733D | gold_codex (239 test) | **GEÇİCİ** | 0,000 | **0,048** | 0,046 |
| MIL-PRF-85285E | gold_taslak (60 test) | **GEÇİCİ** | 0,000 | **0,228** | 0,221 |
| MIL-PRF-85285E | gold_codex (91 test) | **GEÇİCİ** | 0,000 | **0,164** | 0,161 |

P / R (gold_taslak): 23377K kural 0,96 / 0,83, dil modeli 0,39 / 0,35, hibrit 0,64 / 0,87.
81733D (**GEÇİCİ**) dil modeli 0,30 / 0,14, hibrit 0,29 / 0,13. 85285E (**GEÇİCİ**) dil modeli 0,25 / 0,21, hibrit 0,29 / 0,18.

## 2. Alan bazında F1 (test alanları)

Tam tablo `ozet_alan_f1.csv`'de (raf ömrü, koşul ve numune alanları dahil). Sıra: kural / dil modeli / hibrit.

| Alan | 23377K (kontrollü) | 81733D taslak (**GEÇİCİ**) | 85285E taslak (**GEÇİCİ**) |
|---|---|---|---|
| test.test_adi | 0,93 / 0,56 / 0,64 | 0 / 0,22 / 0,21 | 0 / 0,24 / 0,24 |
| test.kaynak.madde | 0,93 / 0,63 / 0,68 | 0 / 0,33 / 0,32 | 0 / 0,46 / 0,49 |
| test.test_turleri | 0,93 / 0,02 / 0,64 | 0 / 0 / 0 | 0 / 0 / 0 |
| test.sinir.kriter_turu | 0,79 / 0,40 / 0,57 | 0 / 0,29 / 0,26 | 0 / 0,27 / 0,22 |
| test.sinir.alt | 1,00 / 0,43 / 0,71 | 0 / 0,25 / 0,21 | 0 / 0,20 / 0,25 |
| test.sinir.ust | 0,86 / 0,19 / 0,69 | 0 / 0,29 / 0,22 | 0 / 0,19 / 0,12 |
| test.sinir.birim | 0,88 / 0,44 / 0,75 | 0 / 0,19 / 0,09 | 0 / 0,23 / 0,19 |
| test.test_metodu | 0,90 / 0 / 0,90 | 0 / 0 / 0 | 0 / 0 / 0 |
| test.metot_kaynagi.madde | 0,97 / 0 / 0,97 | 0 / 0 / 0 | 0 / 0 / 0 |
| test.numune_hazirlama_id | 0,86 / 0 / 0,86 | 0 / 0 / 0 | 0 / 0 / 0 |
| raf_omru.sure | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| **GENEL (mikro)** | **0,89 / 0,37 / 0,74** | **0 / 0,19 / 0,17** | **0 / 0,23 / 0,22** |

Dil modeli `test_metodu`, `metot_kaynagi`, `numune_hazirlama_id` alanlarını hiç doğru doldurmuyor (F1 0),
`test_turleri` alanını neredeyse hiç (23377K'da 0,02, diğerlerinde 0). Bu alanlar 23377K'da yalnız kuraldan geliyor; kuralın çalışmadığı iki belgede
hibritte de 0.

## 3. Anlaşmazlıklar ve insan incelemeli sınırlar

| Standart | Anlaşmazlık | Anlaşmazlıklı test | İnsan incelemeli sınır (kural / dil modeli / hibrit) | İşaretlenemeyen |
|---|---|---|---|---|
| 23377K | 10 | 10 | 0 / 1 / 8 | 2 |
| 81733D (**GEÇİCİ**) | 0 | 0 | 0 / 2 / 0 | 0 |
| 85285E (**GEÇİCİ**) | 0 | 0 | 0 / 2 / 0 | 0 |

23377K'daki 10 anlaşmazlığın 8'i `kriter_turu` (6'sında kural `sayisal`, model `metinsel`: kurşun-kadmiyum,
krom, VOC, öğütme inceliği, filiform, uygulama; 2'sinde tersi: depolama ve hızlandırılmış depolama),
1'i `yon` (drying_time: kural en çok 5 saat, model 5–8 saat aralığı), 1'i `birim` (adhesion: model "A").
81733D ve 85285E'de kural hiç test bulmadığı için karşılaştırılacak çift yok; anlaşmazlık 0 "uyum" değil,
**ölçülemedi** demek.

## 4. Belge başına süre (Colab, T4)

| Standart | Sayfa | Kural | Dil modeli | Dil modeli / sayfa | Hibrit |
|---|---|---|---|---|---|
| 23377K | 19 | 2,0 s | 579,1 s (9,7 dk) | 30,5 s | 581,2 s |
| 81733D | 34 | 2,9 s | 819,7 s (13,7 dk) | 24,1 s | 822,6 s |
| 85285E | 24 | 1,9 s | 965,8 s (16,1 dk) | 40,2 s | 967,7 s |

Hibrit süresi kural + dil modeli + birleştirmedir; birleştirmenin kendisi 0,1 saniyenin altında.
Ara kayıttan devam edilen sayfa yok (süreler tek koşudan).

## 5. Uydurma değerler

**Sayfada geçmeyen sayısal değer** (`deney/kanit_kontrol.py`, `bulunamadi`):

| Standart | Kural | Dil modeli | Hibrit |
|---|---|---|---|
| 23377K | 0 / 29 | **2** / 18 | 0 / 38 |
| 81733D (**GEÇİCİ**) | 0 / 0 | 0 / 15 | 0 / 13 |
| 85285E (**GEÇİCİ**) | 0 / 1 | **1** / 50 | 0 / 15 |

- 23377K, viscosity (s. 3, 3.5.1): alt 10, üst 30 s. PR #44'teki koşuda da aynı uydurma vardı; gerçek şart
  3.6.3'te en çok 40 s.
- 85285E, color (s. 8, 3.7.3): alt 0. Ayrıca 5 değer yalnız `X ± Y`'den türetilebiliyor, 1 değer yalnız
  sonraki sayfada geçiyor (elle bakılmalı).

**Özgün alıntısı sayfada olmayan test** (hibritin attığı "kanıtsız" kayıt): 23377K 1, 81733D 2, 85285E 13.
85285E'deki 13'ün 12'si sayfa 4'e bağlanmış; model bir içindekiler ya da tablo sayfasından alıntı uydurmuş görünüyor.

**Şemadan reddedilen test** (sayfa raporundaki hata): 23377K 1, 81733D 8, 85285E 13. En sık nedenler:
pint'in tanımadığı birim ("fluid ounce", "piw", "G.U.", "double rub", "Hegman scale") ve yönle uyuşmayan
sınır (85285E VOC tablosunda model alt = 0 ve "en çok" yazıyor).

Hibritte sıfır uydurma değer kalması tasarımın sonucu: sınır modelden alınmıyor, kural özgün metinden
yeniden çıkarıyor. Bedeli 85285E'de görülüyor: 20 testin sayısı kural tarafından çıkarılamadığı için atıldı
(`sayi_atildi`), dil modelinin 50 sayısal değeri hibritte 15'e iniyor.

## 6. Bulgular

1. **23377K'da hibrit kuraldan kötü (0,735 / 0,892).** Hibrit recall'u biraz artırıyor (0,83 → 0,87) ama
   precision 0,96'dan 0,64'e düşüyor. Eklenen 30 testin 15'i kuralda zaten olan bir maddeden geliyor; çoğu
   dil modelinin aynı testi iki kez yazması ("pot_life" ile "pot life", "drying_time" ile "drying time").
   Eşleştirme bire bir olduğu için ikinci kopya "eşleşmeyen" sayılıp ekleniyor. Bu 15 kayıt (kural testiyle aynı
   `kaynak.madde`'ye sahip eklenenler) atılınca hibrit F1 0,799'a çıkıyor (P 0,76, R 0,85; deneme hesabı,
   kod değişmedi, dosya olarak kaydedilmedi); geri kalan kayıp 4.x muayene maddelerinden ve
   gold'da olmayan kayıtlardan.
2. **Kuralın çalışmadığı iki belgede hibrit ≈ dil modeli (GEÇİCİ).** Kural 0 test bulduğu için hibrit dil
   modelinin kanıtlı kayıtlarına iniyor. F1 dil modelinden biraz düşük, precision biraz yüksek
   (85285E: 0,25 → 0,29). Kural eksenindeki 0, bu iki belgede hibritin değerini sınırlayan asıl etken.
3. **Hibrit uydurmayı sıfırlıyor.** Dil modelinin 3 uydurma değeri ve 16 kanıtsız testi hibrit çıktıya girmedi.
   Yanlış kabul riski açısından bu, F1'deki kayıptan daha önemli olabilir.
4. **İki gold birbirinden çok farklı (GEÇİCİ).** 81733D taslağı 55, Codex 239 test bekliyor; aynı çıktının
   F1'i 0,19 ile 0,05 arasında değişiyor. Bu iki standardın sayıları gold onaylanmadan yorumlanmamalı.
5. **Süre:** belge başına 10–16 dk, sayfa başına 24–40 s; sürenin tamamına yakını dil modelinde.
