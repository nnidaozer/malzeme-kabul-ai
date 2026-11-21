"""Claude Code PreToolUse hook'ları için ortak yazma analizi.

Bir araç çağrısının korunan bir klasöre (ör. data/gold/, tests/) yazıp
yazmayacağını tahmin eder. Dosya araçlarında (Write, Edit, NotebookEdit)
yol kesin olarak bilinir. Bash komutlarında ise sezgisel bir analiz yapılır:
yönlendirme hedefleri, yazan komutlar (cp, mv, rm, tee, sed -i ...), satır içi
kod (python -c, bash -c) ve korunan klasöre `cd` yakalanır.

Bash analizi her yolu yakalayamaz (ör. değişkenle oluşturulan yollar).
Bu yüzden data/gold için ikinci savunma hattı CI kontrolüdür.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

DOSYA_ARACLARI = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# Argümanlarından herhangi biri korunan yoldaysa yazma sayılan komutlar.
YAZAN_KOMUTLAR = {
    "rm", "rmdir", "mv", "touch", "tee", "mkdir", "truncate", "dd", "chmod",
    "chown", "unlink", "shred", "patch", "mkfifo",
}
# Yalnızca hedefi (son argüman ya da -t) korunan yoldaysa yazma sayılanlar.
HEDEFE_YAZAN_KOMUTLAR = {"cp", "rsync", "install", "ln", "scp"}
# PowerShell cmdlet'leri ve takma adları (küçük harfle karşılaştırılır).
PS_YAZAN_KOMUTLAR = {
    "set-content", "add-content", "out-file", "clear-content", "remove-item",
    "new-item", "rename-item", "move-item", "sc", "ac", "ri", "del", "erase",
    "rd", "ni", "rni", "mi", "move", "ren", "export-csv", "tee-object",
}
PS_HEDEFE_YAZAN_KOMUTLAR = {"copy-item", "copy", "cpi"}
WINDOWS = os.name == "nt"
# -i bayrağı ile dosyayı yerinde değiştirenler.
YERINDE_DEGISTIREN = {"sed", "perl", "ruby"}
# -c / -e ile satır içi kod çalıştıran yorumlayıcılar.
YORUMLAYICILAR = {
    "python", "python3", "py", "node", "ruby", "perl", "bash", "sh", "zsh",
    "dash", "pwsh", "powershell",
}
GIT_YAZAN_ALT_KOMUTLAR = {
    "checkout", "restore", "rm", "mv", "apply", "stash", "reset", "clean",
    "am", "cherry-pick", "revert", "merge", "pull", "switch",
}
# Komutun önüne gelip asıl komutu değiştirmeyen sarmalayıcılar.
SARMALAYICILAR = {"sudo", "command", "env", "nohup", "time", "exec", "nice", "xargs"}

YONLENDIRME = {">", ">>", ">|", "&>", "&>>", ">&"}
AYIRICILAR = {";", "&&", "||", "&", "(", ")", "\n"}


def yol_korunan_mi(yol: str, kok: str, korunan: str, cwd: str | None = None) -> bool:
    """`yol`, `kok/korunan` klasörünün içinde (ya da kendisi) mi?

    Yol göreliyse `cwd`ye (verilmezse `kok`e) göre çözülür. Sembolik bağlar
    da çözülür.
    """
    yol = os.path.expanduser(yol.replace("\\", "/"))
    p = Path(yol)
    if not p.is_absolute():
        p = Path(cwd or kok) / p
    # Windows'ta yollar büyük/küçük harf duyarsızdır.
    hedef = Path(os.path.normcase(os.path.realpath(p)))
    korunan_kok = Path(os.path.normcase(os.path.realpath(Path(kok) / korunan)))
    return hedef == korunan_kok or korunan_kok in hedef.parents


def _metinde_korunan_var(metin: str, korunan: str, kok: str | None = None) -> bool:
    """Bir metin (argüman ya da satır içi kod) korunan klasöre atıf yapıyor mu?

    Göreli yazım (`data/gold`, `./data/gold/x`) ve, `kok` verilirse, mutlak
    yazım (`/proje/data/gold`) aranır. `src/tests` gibi başka bir klasörün
    altındaki aynı adlı klasör eşleşmez.
    """
    metin = metin.replace("\\", "/")
    govde = r"/+(?:\./+)*".join(re.escape(p) for p in korunan.strip("/").split("/"))
    desen = r"(?:^|[\s'\"=:(,;])(?:\./+)*" + govde + r"(?:$|[/\s'\"),;])"
    bayrak = re.IGNORECASE if WINDOWS else 0
    if re.search(desen, metin, bayrak):
        return True
    if kok:
        mutlak = (Path(kok) / korunan).as_posix().rstrip("/")
        gercek = Path(os.path.realpath(Path(kok) / korunan)).as_posix()
        for m in {mutlak, gercek}:
            if re.search(re.escape(m) + r"(?:$|[/\s'\"),;])", metin, bayrak):
                return True
    return False


def _arguman_korunan_mi(arg: str, kok: str, korunan: str, cwd: str | None = None) -> bool:
    if _metinde_korunan_var(arg, korunan, kok):
        return True
    if arg.startswith("-") or not arg:
        return False
    try:
        return yol_korunan_mi(arg, kok, korunan, cwd)
    except (OSError, ValueError):
        return False


def _parcala(komut: str) -> list[str] | None:
    """Komutu kabuk belirteçlerine ayırır. Ayrıştırılamazsa None döner."""
    komut = komut.replace("`", " ; ").replace("$(", " ( ").replace("\n", " ; ")
    lex = shlex.shlex(komut, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def _ifadelere_bol(belirtecler: list[str]) -> list[list[list[str]]]:
    """Belirteçleri ifadelere (; && ||) ve her ifadeyi boru parçalarına (|) böler."""
    ifadeler: list[list[list[str]]] = []
    ifade: list[list[str]] = []
    parca: list[str] = []
    for b in belirtecler:
        if b in AYIRICILAR:
            if parca:
                ifade.append(parca)
            if ifade:
                ifadeler.append(ifade)
            ifade, parca = [], []
        elif b in {"|", "|&"}:
            if parca:
                ifade.append(parca)
            parca = []
        else:
            parca.append(b)
    if parca:
        ifade.append(parca)
    if ifade:
        ifadeler.append(ifade)
    return ifadeler


def _asil_komut(parca: list[str]) -> tuple[str, list[str], bool]:
    """Ortam atamalarını ve sarmalayıcıları atlayıp (komut, argümanlar, xargs_mi) döner."""
    i = 0
    xargs = False
    while i < len(parca):
        b = parca[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", b):
            i += 1
            continue
        ad = os.path.basename(b)
        if ad in SARMALAYICILAR:
            xargs = xargs or ad == "xargs"
            i += 1
            # sarmalayıcının seçeneklerini atla (ör. sudo -u kok, xargs -0)
            while i < len(parca) and parca[i].startswith("-"):
                i += 1
            continue
        break
    if i >= len(parca):
        return "", [], xargs
    ad = os.path.basename(parca[i])
    ad = re.sub(r"\.exe$", "", ad.lower() if WINDOWS else ad, flags=re.IGNORECASE)
    # python3.11 -> python3
    ad = re.sub(r"^(python\d?)(\.\d+)?$", r"\1", ad)
    return ad, parca[i + 1:], xargs


def _yonlendirme_hedefleri(parca: list[str]) -> list[str]:
    hedefler = []
    for i, b in enumerate(parca):
        if b in YONLENDIRME and i + 1 < len(parca):
            hedef = parca[i + 1]
            if not re.fullmatch(r"\d+|-", hedef):  # 2>&1, >&- gibi
                hedefler.append(hedef)
    return hedefler


def _yonlendirmeleri_cikar(parca: list[str]) -> list[str]:
    temiz, atla = [], False
    for b in parca:
        if atla:
            atla = False
            continue
        if b in YONLENDIRME or b in {"<", "<<", "<<<", "<&"}:
            atla = True
            continue
        temiz.append(b)
    return temiz



def _parca_yaziyor_mu(parca: list[str], korunan_mi, ifade_korunanli: bool) -> bool:
    """Tek bir basit komut (boru parçası) korunan yola yazıyor mu?

    `korunan_mi(arg)` bir argümanın korunan yola işaret edip etmediğini söyler.
    """
    for hedef in _yonlendirme_hedefleri(parca):
        if korunan_mi(hedef):
            return True

    komut, argumanlar, xargs = _asil_komut(_yonlendirmeleri_cikar(parca))
    # sondaki "2" gibi dosya tanımlayıcı artıkları
    argumanlar = [a for a in argumanlar if not re.fullmatch(r"\d+", a)]
    korunanli = any(korunan_mi(a) for a in argumanlar)
    # xargs girdisini borudan alır; yolu bu parçada görünmeyebilir.
    if xargs and ifade_korunanli:
        korunanli = True
    if not komut or not korunanli:
        return False

    if komut in {"cd", "pushd"}:
        return True  # sonraki göreli yazmalar izlenemez
    if komut in YAZAN_KOMUTLAR:
        return True
    if komut.lower() in PS_YAZAN_KOMUTLAR:
        return True
    if komut.lower() in PS_HEDEFE_YAZAN_KOMUTLAR:
        for i, a in enumerate(argumanlar):
            if a.lower() == "-destination" and i + 1 < len(argumanlar):
                return korunan_mi(argumanlar[i + 1])
        konumsal = [a for a in argumanlar if not a.startswith("-")]
        return bool(konumsal) and korunan_mi(konumsal[-1])
    if komut in HEDEFE_YAZAN_KOMUTLAR:
        for i, a in enumerate(argumanlar):
            if a in {"-t", "--target-directory"} and i + 1 < len(argumanlar):
                return korunan_mi(argumanlar[i + 1])
            if a.startswith("--target-directory="):
                return korunan_mi(a.split("=", 1)[1])
        if xargs:
            return True
        konumsal = [a for a in argumanlar if not a.startswith("-")]
        return bool(konumsal) and korunan_mi(konumsal[-1])
    if komut in YERINDE_DEGISTIREN and any(
        re.fullmatch(r"-[A-Za-z]*i.*|--in-place.*", a) for a in argumanlar
    ):
        return True
    if komut in YORUMLAYICILAR and any(a in {"-c", "-e", "-Command"} for a in argumanlar):
        return True
    if komut == "find" and any(
        a in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
        for a in argumanlar
    ):
        return True
    if komut == "git":
        alt = next((a for a in argumanlar if not a.startswith("-")), "")
        if alt in GIT_YAZAN_ALT_KOMUTLAR:
            return True
    return False


def bash_korunana_yaziyor_mu(komut: str, kok: str, korunan: str, cwd: str | None = None) -> bool:
    """Bash komutu `kok/korunan` klasörüne yazmaya çalışıyor gibi görünüyor mu?

    Korunan klasörden yalnızca okuyan komutlara (cat, ls, grep, pytest,
    python betik.py data/gold ...) izin verilir. Göreli yollar `cwd`ye göre
    çözülür.
    """

    def korunan_mi(arg: str) -> bool:
        return _arguman_korunan_mi(arg, kok, korunan, cwd)

    belirtecler = _parcala(komut)
    if belirtecler is None:
        # Ayrıştırılamayan komut korunan yola atıf yapıyorsa güvenli tarafta kal.
        return _metinde_korunan_var(komut, korunan, kok)
    for ifade in _ifadelere_bol(belirtecler):
        ifade_korunanli = any(korunan_mi(b) for parca in ifade for b in parca)
        for parca in ifade:
            if _parca_yaziyor_mu(parca, korunan_mi, ifade_korunanli):
                return True
    return False


def arac_korunana_yaziyor_mu(girdi: dict, korunan: str) -> bool:
    """Hook girdisindeki araç çağrısı proje kökündeki `korunan` klasörüne yazıyor mu?"""
    cwd = girdi.get("cwd") or os.getcwd()
    kok = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    arac = girdi.get("tool_name", "")
    arac_girdisi = girdi.get("tool_input") or {}
    if arac in DOSYA_ARACLARI:
        yol = arac_girdisi.get("file_path") or arac_girdisi.get("notebook_path") or ""
        return bool(yol) and yol_korunan_mi(yol, kok, korunan, cwd)
    if arac == "Bash":
        return bash_korunana_yaziyor_mu(arac_girdisi.get("command", ""), kok, korunan, cwd)
    if arac == "PowerShell":
        # PowerShell'de ters bölü yol ayırıcısıdır, kaçış karakteri değil.
        komut = arac_girdisi.get("command", "").replace("\\", "/")
        return bash_korunana_yaziyor_mu(komut, kok, korunan, cwd)
    return False
