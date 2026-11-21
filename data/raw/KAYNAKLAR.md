# Ham belgeler

Bu klasöre konacak standart PDF'leri ve kaynakları. Dosya adları aşağıdaki gibi
olmalı; betikler bu adlara göre çalışır.

| Dosya adı | Standart | Revizyon / tarih | Kaynak |
|---|---|---|---|
| `MIL-PRF-23377G.pdf` | Epoksi astar (yüksek katı) | G, 30.09.1994 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-010000-29999/download.php?spec=MIL-PRF-23377G.029359.pdf) |
| `MIL-PRF-23377H.pdf` | Epoksi astar (yüksek katı) | H, 30.04.2002 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-010000-29999/download.php?spec=MIL-PRF-23377H.039154.pdf) |
| `MIL-PRF-23377J.pdf` | Epoksi astar (yüksek katı) | J, 15.04.2005 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-010000-29999/download.php?spec=MIL-PRF-23377J.039149.pdf) |
| `MIL-PRF-23377K.pdf` | Epoksi astar (yüksek katı) | K, 07.06.2012 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-010000-29999/download.php?spec=MIL-PRF-23377K.042191.pdf) |
| `MIL-PRF-81733D.pdf` | Sızdırmazlık ve kaplama macunu, korozyon önleyici | D, 15.05.1998 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-080000-99999/download.php?spec=MIL-PRF-81733D.054453.pdf) |
| `MIL-PRF-85285E.pdf` | Poliüretan son kat (uçak ve yer destek ekipmanı) | E, 12.01.2012 | [EverySpec](https://everyspec.com/MIL-PRF/MIL-PRF-080000-99999/download.php?spec=MIL-PRF-85285E.040303.pdf) |

Resmî kaynak ASSIST Quick Search'tür (https://quicksearch.dla.mil/). EverySpec
aynı belgelerin herkese açık kopyalarını sunar.

## Ek standartların seçim gerekçesi

Kriterler: herkese açık olması, test sınırları ve raf ömrü/depolama bölümü
içermesi, mümkünse metin tabanlı PDF olması.

- **MIL-PRF-81733D** (sızdırmazlık macunu): uygulama ömrü, yapışmazlık süresi,
  kürlenme, sertlik, akma gibi sayısal sınırlar ve raf ömrü/depolama şartı
  içerir. Epoksi astardan farklı bir malzeme sınıfıdır.
- **MIL-PRF-85285E** (poliüretan son kat): 23377 astarın üstüne uygulanan son
  kattır; parlaklık, renk, esneklik, sıvı direnci gibi test sınırları ve raf
  ömrü bölümü vardır. Astar + son kat birlikte kullanıldığı için çapraz
  kontrolde gerçekçi bir ikili oluşturur.

Henüz alınmayanlar: 23377 G ve J'nin değişiklik bildirimleri (Amendment 1/2)
ve 85285E Notice 1. Revizyon takibinde gerekirse eklenir.

## PDF türü kontrolü

```bash
python scripts/pdf_tur_kontrol.py      # sonuç: data/raw/pdf_turleri.csv
```

Taranmış PDF'ler atılmaz, listede `ocr_gerekli=evet` olarak işaretlenir.
