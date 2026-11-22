# Karar motoru ölçümü: MIL-PRF-23377K

150 sentetik sertifika; belge okuma kusursuz varsayıldı (ham hücreler JSON'dan).
Yanlış kabul yalnız motor "kabul" (satırda "uygun") dediğinde oluşur; "inceleme" kabul sayılmaz.

Belge başına süre: ortalama 10.58 ms, en çok 17.05 ms.

### Belge düzeyi (150)

| Ölçüt | Değer |
|---|---|
| Yanlış kabul oranı | %0.0 |
| Yakalama oranı (red olması gerekenlerde red) | %100.0 |
| Doğruluk | %100.0 |
| Otomasyon oranı (insana gitmeyen) | %82.7 |

Karışıklık matrisi (satır: doğru karar, sütun: motor):

| doğru \ motor | kabul | red | inceleme |
|---|---|---|---|
| kabul | 102 | 0 | 0 |
| red | 0 | 22 | 0 |
| inceleme | 0 | 0 | 26 |

### Test satırı düzeyi (2841)

| Ölçüt | Değer |
|---|---|
| Yanlış kabul oranı | %0.0 |
| Yakalama oranı (red olması gerekenlerde red) | %100.0 |
| Doğruluk | %100.0 |
| Otomasyon oranı (insana gitmeyen) | %99.4 |

Karışıklık matrisi (satır: doğru karar, sütun: motor):

| doğru \ motor | uygun | uygun_degil | insan_incelemeli |
|---|---|---|---|
| uygun | 2803 | 0 | 0 |
| uygun_degil | 0 | 22 | 0 |
| insan_incelemeli | 0 | 0 | 16 |

### Hata türüne göre

| Hata türü | Adet | Doğru karar | Yanlış kabul |
|---|---|---|---|
| ad_farki | 10 | 10 | 0 |
| algilama_siniri | 10 | 10 | 0 |
| birim | 12 | 12 | 0 |
| eksik_test | 10 | 10 | 0 |
| revizyon | 10 | 10 | 0 |
| sinir_disi | 14 | 14 | 0 |
| sinira_yakin | 14 | 14 | 0 |
| temiz | 70 | 70 | 0 |

### Doğru karardan ayrılan sertifikalar

Yok.

### Ek: test adı varyantlarının kapsamı

Üreticideki 32 ad varyantının 27 tanesi doğru teste eşleşiyor. Eşleşmeyenler insana gider (yanlış kabul oluşturmaz):

- 'Dry to touch' (drying_time)
- 'Hegman grind' (fineness_of_grind)
- 'Viscosity after 4 hours' (pot_life)
- 'Cross-cut adhesion' (adhesion)
- 'Pb/Cd content' (lead_and_cadmium_content)

### Sınırlar

- Sertifikalar ve karar motoru aynı ekip tarafından, aynı kabul dokümanından yazıldı; bu sonuç
  motorun kendi tasarım alanındaki üst sınırıdır. Gerçek CoC/TR'lerde oranlar düşebilir.
- Belge okuma ölçülmedi: motor ham hücreleri JSON'dan aldı. PDF'ten okuma (kural ya da yerel
  dil modeli) eklendiğinde okuma hataları da yanlış kabule yol açabilir.
- Kabul dokümanı çıkarıcının onaylanmamış taslağıdır; standarttan eksik çıkarılan bir şart
  (ör. kurşun sınırı) sertifikada da aranmaz.
