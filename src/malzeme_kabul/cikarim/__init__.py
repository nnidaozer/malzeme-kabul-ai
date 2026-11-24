"""Çıkarım: standart ve sertifikadan değer okuma.

- `kural_cikarici`: yalnız kural (düzenli ifade, belge yapısı) taban çizgisi.
- `yerel_model`: yalnız localhost'a bağlanan yerel dil modeli istemcisi.

Dil modeli yalnız ham metin, kaynak konum ve sınır yönü döndürür
(`malzeme_kabul.sozlesme.okuma`); normalleştirme, birim dönüşümü ve karar
`malzeme_kabul.kural` içindedir (docs/mimari.md madde 6).
"""
