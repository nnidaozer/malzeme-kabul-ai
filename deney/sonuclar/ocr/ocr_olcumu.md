# OCR ölçümü

- Motor: tesseract 5.3.4 (dil eng, dpi 300, psm 3)
- Makine: Linux-6.18.44-fc-v880-x86_64-with-glibc2.39, x86_64, 4 çekirdek, Python 3.13.18
- Tarih: 2026-11-28T12:55:27

## Metin tabanlı belgeler

Her sayfa resme çevrilip OCR'dan geçirildi ve PDF'in kendi metniyle karşılaştırıldı. Alan F1 gold'a göre DEĞİL, kural çıkarıcının PDF metninden çıkardığına göredir (OCR'ın çıkarımı ne kadar bozduğunu gösterir). OCR sayfalarında tablo okunmaz: bu ölçümde bütün sayfalar OCR'dan geçtiği için kural çıkarıcı test tablosunu (TABLE II) göremez; Alan F1 ve OCR tarafındaki test sayısı bu yüzden düşük çıkabilir. WER ve sayı ölçümünden önce iki tarafta glif kodları düzeltilir ve "Downloaded from" filigran satırları atılır.

| Belge | Sayfa | WER | Sayı kesinlik | Sayı duyarlılık | Sayı F1 | Ort. güven | s/sayfa | Alan F1 (PDF metnine göre) | Kural test (PDF / OCR) |
|---|---|---|---|---|---|---|---|---|---|
| MIL-PRF-23377H | 19 | 0.018 | 0.992 | 0.984 | 0.988 | 94.806 | 1.324 | 0.083 | 24 / 0 |
| MIL-PRF-23377J | 18 | 0.014 | 0.987 | 0.973 | 0.980 | 95.065 | 1.390 | 0.081 | 25 / 0 |
| MIL-PRF-23377K | 19 | 0.018 | 1.000 | 0.984 | 0.992 | 95.292 | 1.476 | 0.099 | 27 / 0 |

## Taranmış belgeler

Doğru metin yok; Tesseract güveni ve süre raporlanır. Düşük güvenli kelime: güven < 60. Hazır OCR katmanlı belgede katman uyumu WER'i, hazır katman referans alınarak hesaplandı (ikisi de doğru metin değildir). Alan F1 gold etiketi gelene kadar yok (proje sahibi etiketler). Hazır OCR katmanlı MIL-PRF-23377G bu tabloda gösterilir; bölünmedeki tür sayımı (turlere_ayir) ise onu metin tabanlı sayar.

| Belge | Tür | Sayfa | Ort. güven | Düşük güvenli oran | s/sayfa | Katman uyumu WER | Kural test (katman / OCR) |
|---|---|---|---|---|---|---|---|
| MIL-S-81733C | taranmış | 33 | 90.644 | 0.058 | 1.361 | - | - / 0 |
| MIL-PRF-23377G | ocr_katmanlı | 25 | 92.113 | 0.037 | 1.470 | 0.521 | 0 / 0 |

## Kural çıkarıcı hataları

Kural çıkarıcı bu belgelerde hata verdi; ilgili alanlar boş (-), OCR ölçümü sürdü.

- yok

## Atlananlar

- yok
