# Demo kurulumu planı (yol haritası madde 6)

Amaç: tek komutla yerel kurulum ve 2 dakikalık video için hazır bir demo
veritabanı. Ürün kodu (`src/`) değişmez; yeni iş `scripts/demo.py`,
`data/demo/`, README ve `docs/demo_senaryosu.md`'dedir.

## Komut

```
python scripts/demo.py            # Windows: py scripts\demo.py
python scripts/demo.py --sifirla  # demo veritabanını silip baştan kurar
python scripts/demo.py --yalniz-kur   # kurar, uygulamayı başlatmaz
python scripts/demo.py --kurulum-yok  # sanal ortam/pip adımını atlar (geçerli Python kullanılır)
python scripts/demo.py --port 8502
```

## Adımlar ve fonksiyonlar (`scripts/demo.py`)

1. `python_uygun_mu(surum=sys.version_info) -> bool`: Python 3.11 ve üstü.
   Değilse betik 2 ile çıkar ve gereken sürümü yazar.
2. Sanal ortam: `venv_python(venv: Path, platform=sys.platform) -> Path`
   (`win32` ise `Scripts/python.exe`, değilse `bin/python`). Varsayılan
   sanal ortam depo kökünde `.venv` (zaten .gitignore'da).
   `kilit_ozeti(kok) -> str`: `requirements-arayuz.lock` ve `pyproject.toml`
   içeriğinin sha256'sı. Kurulum sonrası `.venv/.malzeme_kabul_kurulum`
   dosyasına yazılır; `kurulum_gerekli_mi(venv, kok) -> bool` özet aynıysa
   False döner (ikinci çalıştırmada pip ağa çıkmaz). Kurulum komutları
   `kurulum_komutlari(venv_py, kok) -> list[list[str]]`:
   `[venv_py, -m, pip, install, -r, requirements-arayuz.lock]` ve
   `[venv_py, -m, pip, install, --no-deps, -e, <kok>]`. Geçerli yorumlayıcı
   sanal ortamın kendisi değilse betik kurulumdan sonra kendini sanal
   ortamın Python'uyla aynı argümanlar + `--kurulum-yok` ile yeniden çalıştırır.
3. `demo_kur(klasor: Path, kok: Path, sifirla: bool=False) -> DemoKurulumu`
   (`DemoKurulumu`: `db`, `parola_dosyasi`, `dosyalar`, `yeni_kuruldu`).
   - Varsayılan klasör `data/calisma/demo/` (git'e girmez).
   - Veritabanı varsa ve `sifirla` değilse dokunulmaz (`yeni_kuruldu=False`);
     parolalar yeniden üretilmez.
   - Yeni kurulumda: `data/ornek/katalog.json` ve ardından
     `data/demo/katalog.json` örnek veri olarak yüklenir (ikisi de
     `ornek-veri` ile **demo onaylı**; onay kayıtları `"demo_onayi": true`).
     Bunun için `scripts/katalog_kur.py` içindeki yükleme döngüsü
     `ornek_kur(katalog, defter, dosya, kok) -> YuklemeOzeti` fonksiyonuna
     alınır (davranış aynı; katalog_kur bunu çağırır).
   - `data/demo/katalog.json` ekleri:
     - `data/demo/MIL-PRF-23377J_kabul_dokumani.json` (kural çıkarıcısının
       23377J taslağı; demo onaylı),
     - malzeme `AST-003`: MIL-PRF-23377 **J**, Type I Class N (revizyon
       etkisi adımı için),
     - AST-001 için onaylı tedarikçi `Ornek Aerospace Finishes Ltd. (kurgusal)`
       (sentetik B şablonunun tedarikçisi) ve bu tedarikçiden iki bekleyen
       lot: `B86447` (hatalı CoC S-089) ve `B80677` (temiz CoC S-032),
     - AST-003 için bir parti (revizyon etkisinde parti sayısı görünsün).
   - Kullanıcılar: `mp` (rol mp) ve `gk` (rol giris_kalite), parolaları
     `secrets` ile rastgele (en az 16 karakter). Parolalar ekrana yazılmaz;
     `parolalar.txt`'ye yazılır (POSIX'te izin 0600) ve betik yalnız dosyanın
     yolunu söyler.
   - Demo dosyaları `klasor/dosyalar/` altına kopyalanır:
     `MIL-PRF-23377K.pdf` (data/raw), `hatali_CoC_B86447.pdf` (sentetik S-089:
     kuruma süresi 0.25 day = 6 saat, şart en çok 5 saat, madde 3.7.2),
     `temiz_CoC_B80677.pdf` (S-032).
   - Test kümesi ve `data/raw/gercek_coc_havacilik` hiç okunmaz; `data/gold`
     okunmaz ve yazılmaz.
4. `streamlit_komutu(python, kok, port) -> list[str]` ve
   `streamlit_ortami(kurulum, ortam) -> dict`: `streamlit run
   src/malzeme_kabul/arayuz/uygulama.py --server.address 127.0.0.1
   --server.port PORT --server.headless true --browser.gatherUsageStats false --client.toolbarMode minimal`
   (Docker'daki gibi "Deploy" düğmesi gizli);
   ortamda `MALZEME_KABUL_DB`, `MALZEME_KABUL_YUKLEME`
   (`klasor/yuklenen`) demo klasörünü gösterir. Uygulama yalnız
   127.0.0.1'den açılır.
5. `main(argv) -> int`: yukarıdakileri sırayla yapar; sonunda adresi
   (`http://127.0.0.1:PORT`), parola dosyasının yolunu ve demo dosyalarının
   klasörünü yazar.

## Belgeler

- README: "Kurulum ve kullanım"ın başına "Tek komutla demo" bölümü (ilk
  çalıştırmada pip için ağ gerekir, sonra ağsız çalışır).
- `docs/demo_senaryosu.md`: 2 dakikalık video, altı adım ve süreleri:
  standart yükle → kabul dokümanı onayla (demo v1 yerine gerçek v2) → hatalı
  CoC yükle → karar ve madde referansı → revizyon etkisi → denetim kaydı
  doğrulama. Her adımda tıklanacak yer, beklenen ekran ve anlatım cümlesi.

## Testler (`tests/test_demo.py`)

Yukarıdaki her fonksiyon için davranış testleri; uçtan uca: demo kurulur,
23377K taslağı üretilip onaylanır, B86447 lotuyla hatalı CoC kural modunda
RED verir ve kuruma süresi `MIL-PRF-23377K, 3.7.2` ile "uygun değil" olur,
tedarikçi/lot satırları uygun; temiz CoC KABUL; K revizyonu yüklenince
AST-003 işaretlenir; zincir sağlam ve `denetim_dogrula.py` 0 döner.
README ve senaryo belgesi komutu ve altı adımı içerir.

## Gözden geçirmeden sonra eklenenler

- Klasör koruması: `--klasor` depo içindeyse yalnız `data/calisma/` altında
  (kendisi değil) olabilir; `--venv` depo içindeyse yalnız kökteki `.venv` ya
  da `data/calisma/` altı. Denetim ilk yazmadan ve pip'ten önce yapılır;
  aksi 2 çıkış kodu.
- `--sifirla` ve yeni kurulum SQLite günlük artıklarını (`-journal`, `-wal`,
  `-shm`) siler. Veritabanı silinemezse (Windows'ta uygulama açıkken) betik
  2 ile "uygulamayı kapatıp yeniden deneyin" der.
- Var olan demoda eksik demo dosyaları yeniden kopyalanır; `parolalar.txt`
  yoksa parola üretilmez, `--sifirla` önerilir.
- Streamlit `--client.toolbarMode minimal` ile açılır ("Deploy" düğmesi yok).
- Bilinen sınır: betik doğrudan `.venv` Python'uyla çalıştırılırsa kilit
  değişse bile pip adımı atlanır; `python scripts/demo.py` kullanın.
