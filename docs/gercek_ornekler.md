# Gerçek belgelerden örnek vakalar

Gerçek tedarikçi belgelerinde karşılaşılan ve bir kuralı somutlaştıran durumlar.
Kaynak dosyalar `data/raw/gercek_coa/` altındadır; eşleştirme listesi proje
dosyalarında (`gercek_coa_eslesme/`).

## 1. İki kaynak çakışınca daha sıkı şart: Acetone su sınırı

**Kural** (docs/proje_tanimi.md): İki kaynak aynı özellik için farklı sınır
verirse daha sıkı olan alınır.

**Vaka.** Thermo Fisher, Acetone 99+% (katalog L10407.0F):

| Kaynak | Test | Sınır |
|---|---|---|
| Ürün şartnamesi (`L10407.0F_spec.pdf`) | Water Content (Karl Fischer Titration) | ≤0.75% |
| ABD lotlarının CoA'ları (T08M005, X07M023, Y17M052) | Water Content (Karl Fischer Titration) | ≤0.5% |
| ABD dışı lotların CoA'ları (10262526, 10263738, 10263802, 10263803, 2684713) | Water Content (Karl Fischer Titration) | ≤0.75% |

Aynı ürün, aynı test, iki kaynakta iki farklı üst sınır. Şartname bazı
satırlarda ABD ve ABD dışı malzemeyi ayırıyor ("Specification differs for U.S.
and non-U.S. material where indicated"), ama su satırında böyle bir ayrım yok.
ABD lotlarının CoA'sı ise daha dar bir sınır beyan ediyor.

**Kuralın sonucu.** ABD lotu için geçerli sınır ≤0.5%'tir (daha sıkı olan).
Ölçülen değerler (<0.2) her iki sınırın da altında olduğu için bu üç lotta karar
değişmiyor. Ama 0.5 ile 0.75 arasında bir değer gelseydi:

- yalnız şartnameye bakan bir sistem "uygun" derdi,
- daha sıkı şartı alan sistem "uygun değil" der.

Bu, yanlış kabul oranını doğrudan etkileyen türden bir fark: gevşek sınırı
seçmek yanlış kabul üretir.

**Uygulama için notlar.**

- Sınırların karşılaştırılması ve hangisinin daha sıkı olduğunun seçimi kesin
  kurallarla yapılır (birim dönüşümünden sonra); dil modeli yalnız iki sınırı
  okur.
- Karar satırında iki kaynak da gösterilmeli: hangi sınırın neden seçildiği
  (ör. "≤0.5% (CoA, ABD lotu) şartnamedeki ≤0.75%'ten sıkı").
- Öneri (henüz karar değil): sınırlar farklı türdeyse (biri aralık, biri tek
  yönlü) ya da biri yalnız "Report" diyorsa hangisinin daha sıkı olduğu her
  zaman belirlenemez; böyle satırlar insan incelemesine gidebilir.
