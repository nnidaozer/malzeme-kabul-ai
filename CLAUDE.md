# CLAUDE.md

Bu proje, MIL-PRF-23377 askeri malzeme standardı ile tedarikçi sertifikasını karşılaştırıp her test için "uygun / uygun değil / insan incelemeli" kararı veren bir belge kontrol sistemidir. Belgeyi yerel bir dil modeli okur; kabul/red kararını yalnızca kesin kurallar verir. Hibrit yaklaşım, yalnız kural ve yalnız dil modeli yaklaşımlarıyla karşılaştırılır (alan bazında F1, yanlış kabul oranı, belge başına süre).

## Kurallar

1. **Birim dönüşümü ve sınır karşılaştırması asla dil modeline yaptırılmaz; kesin kurallarla yapılır.** Dil modeli yalnızca belgeden değer okur. Okunan değerin birimini çevirmek ve standart sınırıyla karşılaştırmak Python kodunun işidir.
2. **data/gold/ klasörüne asla yazılmaz.** Doğru cevapları proje sahibi elle etiketler. Bu kural `.claude/settings.json` içindeki izin kuralı ve `scripts/hooks/gold_koruma.py` hook'u ile zorlanır; CI da etiketsiz PR'larda data/gold/ değişikliğini reddeder.
3. **Her yeni fonksiyon testle gelir.**
4. **Sistemin içindeki dil modeli yerel çalışır; dış API kullanılmaz.** `src/` altında dış servis kütüphanesi içe aktarmak `tests/test_dis_servis_yok.py` tarafından yakalanır. Tek istisna ileride eklenecek, yalnızca localhost'a bağlanan yerel model istemcisidir.
5. **İş önce planlanır, onaydan sonra kodlanır.**

## Çalışma düzeni

- Her oturumun başında scripts/oturum_kurulum.sh çalıştırılır.
- Alt ajanlar `.claude/agents/` altındadır: `planlayici` → `test-yazari` → `uygulayici` → `gozden-geciren`. Metrikler için `degerlendirme-kosucusu`.
- `uygulayici` ajanı `tests/` klasörünü değiştiremez (`scripts/hooks/tests_kilidi.py`).

## Komutlar

```bash
pip install -e ".[dev]"   # kurulum
pytest                    # tüm testler
```

## Klasörler

- `src/malzeme_kabul/`: üretim kodu
- `tests/`: pytest testleri
- `scripts/`: yardımcı betikler, hook'lar ve CI kontrolleri
- `data/raw/`: ham belgeler
- `data/gold/`: elle etiketlenmiş doğru cevaplar (salt okunur)
