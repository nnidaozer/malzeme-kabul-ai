# 6. Deneyler

> Durum: deney düzeneği yazıldı; sonuçlar ve yorum **boş**. Sayılar 7. bölüme,
> yorum bu bölümün "Yorum" alt başlıklarına Colab üç mod sonuçları, dizüstü
> ölçümü ve test kümesi ölçümü geldikten sonra yazılacak.

## 6.1 Deney 1: Kabul dokümanı çıkarımı (üç mod)

**Soru.** Yalnız kural, yalnız dil modeli ve hibrit yaklaşım standarttan
şartları ne kadar doğru çıkarıyor?

**Düzenek.**

- Betik: `deney/uc_mod.py` (Colab defteri `notebooks/colab_dil_modeli.ipynb`).
- Belgeler: geliştirme kümesinde MIL-PRF-23377K, MIL-PRF-81733D,
  MIL-PRF-85285E; dil modeli çıkarıcısı dondurulduktan sonra test kümesi.
- Model: Colab'da `qwen3:8b` (düşünme kapalı), Ollama, bağlam 8192, sıcaklık 0.
- Ölçüt: alan bazında P/R/F1 (genel ve bölüm bazında), uydurma değer sayısı,
  anlaşmazlık sayısı, insan incelemeli sınır sayısı, belge başına süre.
- Doğru cevap: onaylandığında `data/gold/`; o zamana kadar yalnız geçici
  karşılaştırma için `data/gold_taslak/` ve `data/gold_codex/`.

**Sonuç.** <!-- Boş: 7.1'e yazılacak. -->

**Yorum.** <!-- Boş. -->

## 6.2 Deney 2: Çapraz kontrol (yanlış kabul)

**Soru.** Karar motoru sertifikalarda ne sıklıkla yanlış kabul veriyor ve ne
kadarını insana bırakıyor?

**Düzenek.**

- Betik: `deney/karar_olc.py`.
- Veri: 150 sentetik sertifika ve 10 istem enjeksiyonlu sertifika
  (`data/sentetik/sertifikalar/MIL-PRF-23377K/`).
- Bugünkü betik ham hücreleri (`json/`) okur; yani karar motorunu "kusursuz
  okuma" varsayımıyla ölçer, belge okumayı ölçmez. PDF'i yerel modelin
  okuduğu hibrit sertifika ölçümü için betik henüz yok.
  <!-- Teslim öncesi: hibrit sertifika ölçümü eklendiyse burayı güncelle. -->
- Ölçüt: parti ve parametre düzeyinde yanlış kabul oranı (%95 Wilson
  aralığı), yakalama oranı, doğruluk, otomasyon oranı; hata türüne göre döküm.

**Sonuç.** <!-- Boş: 7.2'ye yazılacak. -->

**Yorum.** <!-- Boş. -->

## 6.3 Deney 3: Dizüstünde süre ve doğruluk

**Soru.** Sistem hedef dizüstünde (7,7 GB RAM, GPU yok sayılabilir), ağ
kapalıyken çalışıyor mu; belge başına süre ve F1 ne?

**Düzenek.**

- Modeller: Ollama ile `qwen2.5:1.5b` ve `qwen2.5:3b` (4 bit).
- Ağ kapalıyken tek komutla çalışan ölçüm betiği (ayrı iş olarak
  geliştiriliyor; adı ve komutu teslimden önce buraya yazılacak).
- Ölçüt: belge başına süre, sayfa başına süre, alan bazında F1.

**Sonuç.** <!-- Boş: 7.3'e yazılacak. -->

**Yorum.** <!-- Boş. -->

## 6.4 Deney 4: Revizyon farkları

**Soru.** Revizyon karşılaştırıcı MIL-PRF-23377 revizyonları arasındaki şart
değişikliklerini buluyor mu?

**Düzenek.**

- Betik: `scripts/revizyon_karsilastir.py`; çıktılar
  `data/cikti/MIL-PRF-23377_H-J_revizyon_farklari.*` ve `..._J-K_...`.
- Ölçüt: <!-- Doğru cevabı olan bir revizyon farkı listesi hazırlanırsa
  bulunan / kaçırılan / yanlış değişiklik sayısı. Henüz tanımlanmadı. -->

**Sonuç.** <!-- Boş: 7.4'e yazılacak. -->

**Yorum.** <!-- Boş. -->

## 6.5 Deney 5: Taranmış belgeler

**Soru.** Yerel OCR katmanıyla taranmış standartlarda çıkarım ne kadar
başarılı; metin tabanlı belgelerden ne kadar farklı?

**Düzenek.**

- Belgeler: 5.8'deki kapsam. Geliştirme kümesinde MIL-S-81733C ve
  MIL-PRF-23377G; test kümesindeki MIL-A-46146B kilit açılana kadar
  kullanılmaz.
- OCR katmanı ayrı iş olarak geliştiriliyor; ayrıntı teslimden önce
  eklenecek.

**Sonuç.** <!-- Boş: 7.5'e yazılacak. -->

**Yorum.** <!-- Boş. -->

## 6.6 Deney 6: Gerçek havacılık belgesi

**Soru.** Sistem geliştirme sırasında hiç görülmemiş gerçek bir havacılık
CoC'sinde nasıl davranıyor?

**Düzenek.** `data/raw/gercek_coc_havacilik/` altındaki belgeler kilitlidir
ve test kümesi açıldığında bir kez çalıştırılır.

**Sonuç.** <!-- Boş. -->

**Yorum.** <!-- Boş. -->
