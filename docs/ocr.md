# Yerel OCR katmanı

Taranmış standartlar (bütün sayfaları resim) ve hazır OCR katmanlı taramalar
metin olarak okunamaz ya da bozuk okunur. Bu katman bu sayfaları **tamamen
yerel** olarak Tesseract ile okur: sayfa `pypdfium2` ile resme çevrilir,
`tesseract` ikili dosyası alt süreç olarak çalıştırılır. Ağ kullanılmaz, yeni
Python paketi eklenmez (pytesseract yok; kilit dosyaları değişmez).

Kurulum: `apt-get install tesseract-ocr tesseract-ocr-eng` (Docker imajında
ve CI'da kurulur). Windows: UB-Mannheim Tesseract kurulumu, `tesseract` PATH'te olmalı.

## Hangi belgeler

| Belge | Tür (data/raw/pdf_turleri.csv) | Küme | OCR |
|---|---|---|---|
| MIL-S-81733C | taranmış (33/33 sayfa) | geliştirme | evet |
| MIL-PRF-23377G | hazır OCR katmanlı (25/25) | geliştirme | evet, katman yeniden okunur |
| MIL-PRF-81733D | karma (yalnız 34. sayfa taranmış) | geliştirme | yalnız o sayfa |
| MIL-PRF-27617F | karma (1. sayfa OCR katmanlı) | geliştirme | yalnız o sayfa |
| MIL-A-46146B | taranmış (23/23) | **test** | kilit açılana kadar **hayır** |

MIL-A-46146B test kümesindedir. Test kilidi (`test_kumesi_acik: false`) OCR'dan
önce denetlenir; OCR katmanı onu açmaz ve ölçüme girmez. Kilit açılınca aynı
komutla okunur.

## Tasarım

1. `belge/ocr.py`
   - `tsv_coz(tsv) -> OcrSonucu`: Tesseract TSV çıktısını (seviye 5, kelime)
     satırlara dizer; her kelimenin güveni (0-100) tutulur.
   - `OcrSonucu.ortalama_guven`, `dusuk_guvenli_oran(esik)`; eşik
     `DUSUK_GUVEN_ESIGI = 60`.
   - `TesseractMotoru(dil="eng", psm=3, dpi=300, zaman_asimi_s=120, en_cok_piksel=100_000_000)`:
     `sayfa_oku(pdf_yolu, sayfa_no)`, `resim_oku(png)`, `surum()`.
     İkili dosya yoksa, hata koduyla biterse ya da süre aşılırsa `OcrKullanilamaz`.
   - **Piksel sınırı:** sayfanın `dpi`'daki boyutu (genişlik x yükseklik piksel)
     `en_cok_piksel`'i aşarsa sayfa render edilmeden ve tesseract çağrılmadan
     `OcrKullanilamaz` verilir; güvenilmeyen PDF'teki dev bir sayfa belleği tüketmez.
     Sınıra tam eşit sayfa okunur.
   - `surum()` Windows (UB-Mannheim) çıktısındaki baştaki `v`'yi atar ("v5.3.0..." -> "5.3.0...").
   - `tesseract_var_mi()`.
2. `belge/pdf_okuyucu.pdf_oku(..., ocr=None)`: motor verilirse yalnız
   `pdf_turu.sayfa_turu` "taranmış" ya da "ocr_katmanlı" diyen sayfalar OCR'dan
   geçer. Bu sayfalar `Sayfa.kaynak = "ocr"` ve `Sayfa.ocr_guveni` taşır.
   Motor verilmezse davranış değişmez.
   - **Tablolar:** hazır OCR katmanlı sayfada pdfplumber'ın katmandan bulduğu
     tablolar korunur (metin OCR'dan gelir); taranmış sayfada tablo yoktur (`[]`).
     OCR metninden tablo çıkarılmaz.
   - **Süre bütçesi:** `PdfSiniri.ocr_sayfa_basi_s` (varsayılan 30 s). Okuma
     bütçesi `en_cok_sure_s + ocr_sayfa_basi_s x (OCR'a giden sayfa sayısı)`;
     metin sayfaları ek bütçe almaz. Bütçe sayfa aralarında denetlenir, aşılırsa
     `PdfSiniriAsildi`.
3. `deney/bolunme.kullanima_izin_ver(etiket, ocr=False)` ve
   `betik_korumasi(..., ocr=False)`: `ocr=True` iken `ocr_gerekli` belgeler
   kabul edilir. Test kümesi kilidi önce gelir.
4. `kural_cikarici.cikar(..., belge=None)`: önceden okunmuş (OCR'lı) belge verilebilir.
   `deney/uc_mod.py --ocr` ve `deney/dil_modeli_cikar.py --ocr` taranmış belgeyi OCR ile okur.
   - **Belge denetimi** (`deney/bolunme.Bolunme.belgeyi_denetle`; `uc_mod.py`,
     `dil_modeli_cikar.py` ve `ocr_olcumu.py` aynı noktayı kullanır). Sıra:
     1. Yol kilidi: yol hem mutlak hem `resolve()` edilmiş hâliyle, klasör adları
        harf farkı gözetmeden (`casefold`) denetlenir; göreli yol, sembolik bağ
        ve "GERCEK_COC_HAVACILIK" gibi yazımlar kilidi atlatamaz.
     2. İçerik kilidi (`icerik_kilitli_mi`): test kilidi kapalıyken belgenin
        SHA-256 özeti, `data/raw` (her zaman) ve `--ham-klasor` ile verilen ek
        klasör (birleşim) altındaki (özyinelemeli) dosya adı etiketi test
        kümesinde olan ya da kilitli klasördeki PDF'lerin özetleriyle
        karşılaştırılır. Verilen ek klasör yoksa ya da klasör değilse `ValueError`;
        betikler bunu model istemcisi kurulmadan, klasör adıyla stderr'e yazıp
        2 koduyla bildirir. Yeniden adlandırılmış, kopyalanmış ya da bağlanmış
        test belgesi yakalanır. Yalnız bayt özeti alınır (boyutu aynı olan
        adaylar için, önbellekli); içerik çıkarılmaz. İçerik kilidi yalnız bayt
        bayt aynı kopyayı yakalar; değiştirilmiş ya da yeniden yazılmış (ör.
        yeniden kaydedilmiş, sayfası çıkarılmış) bir kopya yakalanmaz.
     3. Dosya adından çözülen etiket (`dosya_etiketi`: adın "_" öncesi,
        ör. `MIL-PRF-81309H_Amendment1.pdf` -> `MIL-PRF-81309H`) bölünmeden geçer;
        `--belge-no/--revizyon` ile verilen etiket test kümesindeki bir dosyayı
        gizleyemez.
     4. Verilen etiket bölünmeden geçer. İki etiket uyuşmazsa `ValueError`
        (betikte 2 kodu, mesajda iki etiket); ikisi de yoksa `ValueError`.
     Denetimler OCR ve model istemcisinden önce yapılır.
     Tür sayımı farkı: ölçüm raporunda hazır OCR katmanlı MIL-PRF-23377G
     "Taranmış belgeler" tablosunda gösterilir; bölünmedeki tür sayımı
     (`turlere_ayir`, yalnız `ocr_gerekli` listesine bakar) ise onu metin tabanlı sayar.
   - **Gold koruması** tek yerdedir (`deney/bolunme.gold_altinda_mi`: `resolve()`,
     sembolik bağ, harf farkı). Çıktı klasörü orada ise üç betik de hiçbir şey
     yazmadan reddeder (`dil_modeli_cikar.py` 2 döner, istemci kurulmaz).
   - `TesseractMotoru.sayfa_oku`: PDF açılamazsa, sayfa resme çevrilemezse ya da
     resim kaydedilemezse `OcrKullanilamaz` (sayfa numarası aralık dışıysa `ValueError`).
   - `ocr_olcumu.py`: kural çıkarıcı bir belgede hata verirse satıra
     `kural_hatasi` yazılır ve md'de "Kural çıkarıcı hataları" altında görünür; ölçüm sürer.
   - OCR hatası (`OcrKullanilamaz`, ör. dil paketi yok) iki betikte de yığın
     izi olmadan stderr'e yazılır ve 2 koduyla çıkılır.
5. Ölçüm: `python deney/ocr_olcumu.py` -> `deney/sonuclar/ocr/`.

## Ölçüm (taranmış ve metin tabanlı ayrı)

Taranmış belgelerin doğru metni yoktur; bu yüzden iki ayrı ölçüm yapılır:

WER ve sayı ölçümünden önce iki tarafa `karsilastirma_metni` uygulanır: glif
kodları `metni_normallestir` ile düzeltilir, "Downloaded from" filigran satırları
atılır. Sayılarda binlik virgülün iki yanındaki OCR boşluğu ("16 ,000",
"16, 000") tolere edilir; önünde rakam olmayan "-" ya da U+2212 eksi işaretidir
("100-500" ise aralıktır).

- **Metin tabanlı belgeler** (MIL-PRF-23377H, J, K): sayfa resme çevrilip
  OCR'dan geçirilir ve PDF'in kendi metniyle karşılaştırılır. Kelime hata oranı
  (WER), sayısal değerlerin kesinlik / duyarlılık / F1'i (sınır değerleri
  sayıdır, en önemli hata budur), sayfa başına süre. Ayrıca kural çıkarıcı hem
  PDF metninde hem OCR metninde çalıştırılır; alan bazında F1, PDF metninden
  çıkanlar referans alınarak ölçülür (gold değildir; OCR'ın çıkarımı ne kadar
  bozduğunu gösterir). OCR sayfalarında tablo okunmadığı için kural çıkarıcı
  OCR tarafında test tablosunu göremez; bu F1 OCR'ın metin hatalarını değil
  çoğunlukla tablo kaybını gösterir.
- **Taranmış belgeler** (MIL-S-81733C; hazır katmanlı MIL-PRF-23377G ayrı
  satırda): ortalama Tesseract güveni, düşük güvenli kelime oranı, sayfa başına
  süre. 23377G için hazır OCR katmanı ile yeni OCR arasındaki uyum (WER) ve iki
  okumadan kural çıkarıcının bulduğu test sayısı. Alan bazında F1 için gold
  etiketi gerekir (proje sahibi etiketler).

## Güvenlik notu

OCR bir rakamı yanlış okuyabilir ("16,000" -> "16 ,000", "II" -> "II]").
Kabul dokümanı mühendis onayından geçer; OCR'lı sayfadan gelen alanlar
`kaynak="ocr"` ile işaretlidir. Düşük güvenli sayfadan gelen okumanın karar
hattında insan incelemesine yönlendirilmesi sonraki adımdır.
