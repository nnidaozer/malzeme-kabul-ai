# malzeme-kabul-ai

Havacılıkta kimyasal malzeme kabulü için yapay zekâ destekli belge kontrolü.

Astar, boya, sızdırmazlık macunu ve yapıştırıcı gibi malzemeler teslim
alınmadan önce standartlara göre kontrol edilir. Bu iş bugün büyük ölçüde elle
yapılır: mühendis standarttan bir kabul dokümanı hazırlar, sonra tedarikçinin
uygunluk sertifikası ve test raporundaki (CoC/TR) her değeri bu dokümanla tek
tek karşılaştırır. Bu proje o süreci otomatikleştirir. Ayrıntılı tanım:
[docs/proje_tanimi.md](docs/proje_tanimi.md).

## Kapsam

1. **Kabul dokümanı üretimi.** Sistem askeri standartları okur; test
   sınırlarını, test metotlarını, raf ömrünü, depolama ve kullanım koşullarını,
   kupon/uygulama/kürlenme bilgilerini, kabul ve ömür uzatma testlerini
   çıkarır. Bunlardan kalite mühendisinin onaylayacağı bir kabul dokümanı
   (Markdown ve Word) üretir. Her şartın yanında standarttaki madde numarası
   bulunur.
2. **Çapraz kontrol.** Tedarikçinin CoC/TR belgesi kabul dokümanıyla
   karşılaştırılır. Her test için "uygun / uygun değil / insan incelemeli"
   kararı verilir ve dayandığı madde gösterilir.
3. **Revizyon takibi.** Standardın revizyonları (ör. MIL-PRF-23377 G → H → J →
   K) arasındaki farklar bulunur ve etkilenen kabul dokümanı için güncelleme
   önerilir.

Kullanılan standartlar (kaynaklar: [data/raw/KAYNAKLAR.md](data/raw/KAYNAKLAR.md)):

| Standart | Malzeme | Revizyonlar |
|---|---|---|
| MIL-PRF-23377 | Epoksi astar, yüksek katı | G, H, J, K |
| MIL-PRF-81733 | Sızdırmazlık ve kaplama macunu, korozyon önleyici | D |
| MIL-PRF-85285 | Poliüretan son kat | E |

## Tasarım ilkeleri

- Belgeyi yerel bir dil modeli okur; kabul/red kararını yalnızca kesin kurallar
  verir. Birim dönüşümü ve sınır karşılaştırması Python kodunda yapılır.
- Sistem emin olmadığında kararı insana bırakır ("insan incelemeli").
- Sistem internetsiz çalışır; `src/` altında dış servis kullanılmaz.
- Doğru cevaplar (`data/gold/`) elle etiketlenir; kod bu klasöre yazmaz.

## Değerlendirme

Üç yaklaşım karşılaştırılır: yalnız kural, yalnız dil modeli ve hibrit.
Ölçütler:

- alan bazında precision, recall ve F1,
- yanlış kabul oranı (uygun olmayan bir değerin "uygun" sayılması),
- belge başına süre.

## Kurulum ve kullanım

```bash
pip install -e ".[dev]"
pytest
python scripts/pdf_tur_kontrol.py    # data/raw PDF'leri metin mi taranmış mı
```

## Klasörler

- `src/malzeme_kabul/`: üretim kodu
- `tests/`: pytest testleri
- `scripts/`: yardımcı betikler, hook'lar ve CI kontrolleri
- `docs/`: proje tanımı ve belgeler
- `data/raw/`: ham standart belgeleri
- `data/gold_taslak/`: doğru cevap taslakları (gözden geçirilmeyi bekler)
- `data/gold/`: elle etiketlenmiş doğru cevaplar (salt okunur)
