# MIL-PRF-23377K sentetik sertifikaları

`scripts/sertifika_uret.py` ile `data/cikti/MIL-PRF-23377K_kabul_dokumani.json`
içindeki kabul testlerinden üretildi (tohum 23377). Tedarikçiler kurgusaldır;
belgeler gerçek değildir.

- `json/`: sertifika tablosunun ham hücreleri (`Sertifika` şeması). Karar
  motoru bunları okur; yani ölçüm "kusursuz okuma" varsayar.
- `pdf/`: aynı sertifikaların PDF görünümü, 3 tedarikçi düzeni (A, B: İngilizce,
  farklı sütun sırası ve birim yazılışı; C: Türkçe, ondalık virgül).
- `dogru_kararlar.json`: her sertifikanın doğru belge kararı, revizyon kararı
  ve test bazında doğru kararlar. Üretici bunları karar motorunu çağırmadan,
  eklediği hatadan hesaplar.
- `ozet.csv`: sertifika, şablon, atıf, hata türü ve açıklaması, doğru karar.

## Dağılım (150 sertifika)

| Hata türü | Adet | Doğru belge kararı |
|---|---|---|
| temiz | 70 | kabul |
| sinir_disi | 14 | red |
| birim | 12 | 6 kabul, 4 red, 2 inceleme |
| eksik_test | 10 | inceleme |
| ad_farki | 10 | kabul |
| revizyon | 10 | inceleme |
| sinira_yakin | 14 | 10 kabul, 4 red |
| algilama_siniri | 10 | 6 kabul, 4 inceleme |

Toplam: 102 kabul, 22 red, 26 inceleme.

Belge kararı: bir satır uygun değilse red; değilse bir satır (ya da revizyon)
insan incelemeli ise inceleme; hepsi uygunsa kabul.

Doğru kararlar üretici tarafından yazıldı; Nida'nın elle etiketlediği gold
veri değildir. Kontrol için `ozet.csv` yeterlidir.
