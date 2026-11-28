# Demo senaryosu: 2 dakikalık video

Bu senaryo `python scripts/demo.py` ile kurulan yerel demoyu baştan sona
gösterir: standart yükle, kabul dokümanı onayla, hatalı CoC yükle, karar ve
madde referansı, revizyon etkisi, denetim kaydı doğrulama. Ekran
dışı adımları (taslak, onay, karar, revizyon, inceleme kapatma, zincir)
`tests/test_demo.py` içindeki uçtan uca test sınar; ekran akışı 28 Kasım
2026'da temiz bir klonda tarayıcıyla (Playwright) baştan sona geçildi.

Demo verisi kurgusaldır: malzeme kodları, tedarikçiler ve lotlar uydurmadır,
CoC'ler `data/sentetik/` altındaki sentetik sertifikalardır. Örnek kabul
dokümanları **"DEMO ONAYI (M&P onayı değil)"** işaretlidir; gerçek onaylı
sürüm yalnız M&P mühendisinin ekranda verdiği onayla oluşur (adım 2).

## Kayıttan önce (videoya girmez)

1. Demoyu temiz kurun ve başlatın:

   ```bash
   python scripts/demo.py --sifirla      # Windows: py scripts\demo.py --sifirla
   ```

   İlk çalıştırma `.venv`'i kurar (ağ gerekir); sonrakiler ağsızdır. Betik
   adresi (`http://127.0.0.1:8501`), parola dosyasını
   (`data/calisma/demo/parolalar.txt`) ve demo dosyalarının klasörünü
   (`data/calisma/demo/dosyalar/`) yazar.
2. Tarayıcıda **iki sekme** açın; her sekme ayrı oturumdur:
   - Sekme 1: `mp` ile giriş (M&P mühendisi).
   - Sekme 2: `gk` ile giriş (giriş kalite).
   Parolaları `parolalar.txt`'den alın; parola ekranda görünmesin diye girişi
   kayıttan önce yapın.
3. Bir terminal penceresini depo kökünde hazır tutun (adım 6).
4. Ekranı 1440×900 ya da daha geniş kaydedin; tablolar yan yana sığar.

## Akış

### 1. Standart yükle (0:00–0:20)

- **Sekme 1 (mp)** → kenar çubuğu **Depo: partiler ve raf ömrü**. Mavi kutu:
  "8 partinin kabul dokümanı demo onaylı (DEMO ONAYI (M&P onayı değil))".
- **Standart yükle** → `dosyalar/MIL-PRF-23377K.pdf` → **Taslak üret**.
- Beklenen: "taslak 1: MIL-PRF-23377K kaydedildi (27 test)" (yaklaşık 2 s).
- Anlatım: "Sistem askeri standardı internetsiz okur ve test sınırlarını,
  her birinin madde numarasıyla bir kabul dokümanı taslağına çıkarır. Şu an
  depodaki dokümanlar yalnız demo onaylı."

### 2. Kabul dokümanı onayla (0:20–0:40)

- **Taslağı düzelt ve onayla** → tabloda `madde` ve `sayfa` sütunlarını
  gösterin (ör. Drying time, 3.7.2). Gerekirse bir hücre düzeltilip
  **Düzeltmeleri kaydet** denir; her düzeltme denetim kaydına yazılır.
- **Onay notu**: "Demo: M&P onayı" → **Onayla (yeni değiştirilemez sürüm)**.
- Beklenen: "MIL-PRF-23377K v2 onaylandı."
- Anlatım: "Kabul dokümanını mühendis onaylar. v1 örnek verinin DEMO ONAYI
  idi; v2 gerçek M&P onayıdır ve değiştirilemez. Bundan sonraki kararlar v2
  ile verilir."

### 3. Hatalı CoC yükle (0:40–0:55)

- **Sekme 2 (gk)** → **Giriş kalite: CoC kontrolü** (sekme önceden açıksa
  ekranı yeniden seçin).
- Malzeme kodu **AST-001**; altında "Kabul dokümanı: MIL-PRF-23377K v2
  (onaylayan mp)" yazar, demo uyarısı yoktur.
- Lot **B86447** → okuma modu **kural** → `dosyalar/hatali_CoC_B86447.pdf`
  → **Karar ver**.
- Anlatım: "Tedarikçinin CoC'si geldi. Belgede kuruma süresi gün cinsinden
  yazılmış: 0.25 day. Sayı küçük göründüğü için göz ya da dil modeli bunu
  kolayca geçer."

### 4. Karar ve madde referansı (0:55–1:15)

- Beklenen başlık: **"Parti kararı: ❌ RED (karantina)"**.
- Tabloda tek kırmızı satır: **Drying time**, madde **MIL-PRF-23377K, 3.7.2**,
  sayfa 7, gerekçe "0.25 day (= 6 hour), şart en çok 5 hour dışında".
  Tedarikçi, lot, revizyon ve tip/sınıf satırları ✅ uygun.
- Anlatım: "Kararı dil modeli değil, kesin kurallar verdi: birim dönüşümünü
  ve sınır karşılaştırmasını Python kodu yaptı ve dayandığı maddeyi
  gösterdi. Parti karantinaya alındı."
- İsteğe bağlı (süre varsa): lot **B80677** + `temiz_CoC_B80677.pdf` →
  "✅ KABUL (serbest)".

### 5. Revizyon etkisi (1:15–1:40)

- **Sekme 1 (mp)** → **Revizyon farkı ve M&P incelemesi** → **Hazır
  raporlar** → `MIL-PRF-23377_J-K`. Test tablosu satırını gösterin: "Drying
  time: Değişti (metot)", ASTM-D1640 → ASTM D5895.
- **İki PDF karşılaştır** sekmesinin altında **Yeni revizyonu kataloğa yükle**:
  belge no `MIL-PRF-23377`, yeni revizyon harfi `K` → **Yükle ve etkilenenleri
  işaretle**.
- Beklenen: "MIL-PRF-23377K: 1 malzeme, 1 parti 'M&P incelemesi bekliyor'
  işaretlendi." (AST-003 hâlâ J revizyonuna bağlı.)
- **M&P incelemesi** sekmesi → AST-003 → **Yeni revizyona geç**, harf `K` →
  **İncelemeyi kapat**. AST-003 artık MIL-PRF-23377K v2'ye bağlıdır.
- Anlatım: "Standardın yeni revizyonu gelince sistem eski revizyona bağlı
  malzemeleri ve partilerini bulur, mühendisin incelemesine düşürür. İşaret
  partiyi kilitlemez; karar mühendisindir ve kayda geçer."

### 6. Denetim kaydı doğrulama (1:40–2:00)

- Kenar çubuğunun altında: "Denetim zinciri: sağlam (N kayıt)".
- Terminalde:

  ```bash
  .venv/bin/python scripts/denetim_dogrula.py --db data/calisma/demo/katalog.sqlite
  # Windows: .venv\Scripts\python scripts\denetim_dogrula.py --db data\calisma\demo\katalog.sqlite
  ```

  Beklenen: `zincir sağlam: 7 kayıt, son özet …` ve çıkış kodu 0. (7 = dört
  demo onayı (23377K, 81733D, 85285E, 23377J), v2 onayı, hatalı CoC kararı,
  M&P incelemesinin kapatılması. Revizyon yüklemesi deftere yazılmaz.
  Adım 2'de düzeltme kaydedildiyse ya da adım 4'teki isteğe bağlı temiz CoC
  denendiyse her biri bir kayıt ekler; uçtan uca test temiz CoC'yi de
  denediği için 8 sayar.)
- Anlatım: "Her onay, düzeltme ve karar hash zincirli bir denetim kaydına
  yazılır. Kayıtlar değiştirilemez; biri veritabanını elle kurcalarsa zincir
  hangi kayıtta bozulduğunu söyler."

## Ek: video dışı gösterimler

**Kurcalanan kayıt yakalanır.** Demo veritabanının bir kopyasında tetikleyici
kaldırılıp bir karar elle "kabul"e çevrilir, tetikleyici geri konur; doğrulama
yine de yakalar (Linux/macOS):

```bash
cp data/calisma/demo/katalog.sqlite /tmp/kurcala.sqlite
.venv/bin/python - <<'EOF'
import sqlite3
b = sqlite3.connect("/tmp/kurcala.sqlite")
t = b.execute("SELECT sql FROM sqlite_master WHERE name = 'denetim_kaydi_degistirilemez'").fetchone()[0]
b.execute("DROP TRIGGER denetim_kaydi_degistirilemez")
b.execute("""UPDATE denetim_kaydi SET icerik = replace(icerik, '"parti_karari": "red"', '"parti_karari": "kabul"')
             WHERE tur = 'karar'""")
b.execute(t); b.commit()
EOF
.venv/bin/python scripts/denetim_dogrula.py --db /tmp/kurcala.sqlite
# ZİNCİR BOZUK (kayıt 6): kaydın özeti içeriğiyle tutmuyor (kayıt değiştirilmiş); ...
```

**Ağsız çalışma.** Kurulumdan sonra ağ kapatılıp `python scripts/demo.py`
yeniden çalıştırılabilir; pip yeniden çalışmaz, uygulama yalnız
`127.0.0.1`'den açılır. Docker'da ağın kapalı olduğu `scripts/ag_testi.sh`
ile gösterilir (README, "Ağsız Docker").

**Hibrit okuma.** Ollama'da yerel bir model çalışıyorsa uygulama
`MALZEME_KABUL_MODELI` ortam değişkeniyle başlatılıp (ör.
`MALZEME_KABUL_MODELI=qwen2.5:3b python scripts/demo.py`) adım 3'te okuma
modu **hibrit** seçilebilir; karar yine kurallardan gelir. Değişken yoksa
hibrit mod hata verir; model yanıt vermezse ekran "Dil modeli kullanılamadı,
kural okumasıyla karar verildi" der. Videoda **kural** modu kullanılır.

**Baştan almak.** `python scripts/demo.py --sifirla` demo veritabanını ve
parolaları yeniden kurar.
