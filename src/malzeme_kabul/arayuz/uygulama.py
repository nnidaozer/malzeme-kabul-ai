"""Streamlit ekranları: M&P, giriş kalite ve depo; basit giriş ve iki rol.

Çalıştırma (yerelde, internetsiz):

    streamlit run src/malzeme_kabul/arayuz/uygulama.py

Veritabanı `MALZEME_KABUL_DB` (varsayılan data/calisma/katalog.sqlite),
yüklenen dosyalar `MALZEME_KABUL_YUKLEME` (varsayılan data/calisma/yuklenen)
altına yazılır. İş kuralları `arayuz/ekran_verisi.py` ve alttaki katmanlardadır;
bu dosya yalnız gösterir.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st

from malzeme_kabul.arayuz import ekran_verisi as ev
from malzeme_kabul.arayuz.kimlik import EKRANLAR, giris, yetkili_mi
from malzeme_kabul.hat.hibrit_hat import HatHatasi, sertifika_hatti
from malzeme_kabul.hat.katalog_karari import karari_duzelt
from malzeme_kabul.hat.revizyon_etkisi import mp_bekleyenler, mp_incelemesini_kapat, yeni_revizyon_yukle
from malzeme_kabul.katalog.veritabani import PARTI_DURUMLARI, Katalog, KatalogHatasi
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi, sema_eksikleri

KOK = Path(__file__).resolve().parents[3]
DB = Path(os.environ.get("MALZEME_KABUL_DB", KOK / "data" / "calisma" / "katalog.sqlite"))
YUKLEME = Path(os.environ.get("MALZEME_KABUL_YUKLEME", KOK / "data" / "calisma" / "yuklenen"))


def baglan(katalog: Katalog) -> tuple[DenetimKaydi, list[str]]:
    """Defteri kurar; şemayı kurmadan önce denetim şemasında eksik olanları döner.

    Defterin kurulumu eksik tetikleyiciyi yeniden yaratır; eksik önce okunmazsa
    kenar çubuğu kurcalanmış veritabanını sağlam gösterirdi.
    """
    eksik = sema_eksikleri(katalog.baglanti)
    return DenetimKaydi(katalog.baglanti), eksik


MESGUL = "Veritabanı şu an başka bir işlemle meşgul; kaydedilmedi, yeniden deneyin"


def dosyayi_kaydet(yuklenen) -> Path:
    """Yüklenen dosyayı güvenli bir adla çalışma klasörüne yazar."""
    YUKLEME.mkdir(parents=True, exist_ok=True)
    ad = re.sub(r"[^A-Za-z0-9._-]", "_", Path(yuklenen.name).name) or "belge"
    yol = YUKLEME / ad
    yol.write_bytes(yuklenen.getvalue())
    return yol


# --- giriş -----------------------------------------------------------------------------


def giris_ekrani(katalog: Katalog) -> None:
    st.title("Malzeme kabul: giriş")
    with st.form("giris"):
        ad = st.text_input("Kullanıcı adı")
        parola = st.text_input("Parola", type="password")
        if st.form_submit_button("Giriş yap"):
            k = giris(katalog.baglanti, ad, parola)
            if k is None:
                st.error("Kullanıcı adı ya da parola yanlış.")
            else:
                st.session_state["kullanici"] = k
                st.rerun()


# --- M&P -----------------------------------------------------------------------------------


def standart_ekrani(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    st.header("Standart yükle")
    st.caption("Standart PDF'inden kural çıkarıcıyla kabul dokümanı taslağı üretilir. Test kümesindeki standartlar reddedilir.")
    pdf = st.file_uploader("Standart PDF'i (ör. MIL-PRF-23377K.pdf)", type=["pdf"], key="standart_pdf")
    if pdf is not None and st.button("Taslak üret"):
        try:
            with st.spinner("Çıkarılıyor..."):
                t = ev.standart_yukle(katalog, dosyayi_kaydet(pdf), kullanici.ad)
            st.success(f"{t.etiket} kaydedildi ({len(t.dokuman.testler)} test). 'Taslağı düzelt ve onayla' ekranından düzeltin.")
        except (KatalogHatasi, ValueError) as hata:
            st.error(str(hata))
    st.subheader("Kayıtlı taslaklar")
    st.dataframe([{"taslak": t.etiket, "durum": t.durum, "oluşturan": t.olusturan, "güncelleme": t.guncelleme}
                  for t in katalog.taslaklar()], width="stretch")


def taslak_ekrani(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    st.header("Taslağı düzelt ve onayla")
    acik = katalog.taslaklar(yalniz_acik=True)
    if not acik:
        st.info("Açık taslak yok. Önce 'Standart yükle' ekranından taslak üretin.")
        return
    secim = st.selectbox("Taslak", acik, format_func=lambda t: t.etiket)
    tablo = st.data_editor(
        ev.test_tablosu(secim.dokuman), key=f"tablo_{secim.id}", width="stretch", num_rows="fixed",
        disabled=["id"], column_order=ev.TABLO_SUTUNLARI,
    )
    satirlar = tablo.to_dict("records") if hasattr(tablo, "to_dict") else list(tablo)
    sol, sag = st.columns(2)
    if sol.button("Düzeltmeleri kaydet"):
        try:
            farklar = ev.taslak_duzelt(katalog, defter, secim.id, ev.tablodan_dokuman(secim.dokuman, satirlar), kullanici.ad)
            st.success(f"{len(farklar)} değişiklik kaydedildi." if farklar else "Değişiklik yok.")
            for f in farklar:
                st.write(f"- {f}")
        except (KatalogHatasi, ValueError) as hata:
            st.error(f"Kaydedilmedi: {hata}")
        except sqlite3.OperationalError as hata:
            st.error(f"{MESGUL} ({hata}).")
    not_ = sag.text_input("Onay notu", key=f"not_{secim.id}")
    if sag.button("Onayla (yeni değiştirilemez sürüm)"):
        try:
            s = ev.taslak_onayla(katalog, defter, secim.id, kullanici.ad, not_ or None)
            st.success(f"{s.etiket} onaylandı.")
        except (KatalogHatasi, ValueError) as hata:
            st.error(str(hata))
        except sqlite3.OperationalError as hata:
            st.error(f"{MESGUL} ({hata}).")
    with st.expander("Koşullar ve raf ömrü (salt okunur)"):
        st.json({"raf_omurleri": [r.model_dump(mode="json") for r in secim.dokuman.raf_omurleri],
                 "kosullar": [k.model_dump(mode="json") for k in secim.dokuman.kosullar]})


def revizyon_ekrani(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    st.header("Revizyon farkı ve M&P incelemesi")
    hazir = ev.hazir_revizyon_raporlari()
    sekme1, sekme2, sekme3 = st.tabs(["Hazır raporlar", "İki PDF karşılaştır", "M&P incelemesi"])
    with sekme1:
        if hazir:
            ad = st.selectbox("Rapor", list(hazir))
            st.markdown(hazir[ad].read_text(encoding="utf-8"))
        else:
            st.info("data/cikti altında hazır revizyon raporu yok.")
    with sekme2:
        eski = st.file_uploader("Eski revizyon PDF'i", type=["pdf"], key="eski")
        yeni = st.file_uploader("Yeni revizyon PDF'i", type=["pdf"], key="yeni")
        if eski and yeni and st.button("Karşılaştır"):
            # Test kümesi kilidi dosya kaydedilmeden önce denetlenir.
            try:
                izin, neden = ev.revizyon_izinli_mi(eski.name, yeni.name)
            except ValueError as hata:
                izin, neden = False, str(hata)
            if not izin:
                st.error(neden)
            else:
                try:
                    with st.spinner("Karşılaştırılıyor..."):
                        md, ozet = ev.revizyon_raporu(dosyayi_kaydet(eski), dosyayi_kaydet(yeni))
                    st.session_state["revizyon_ozet"] = ozet
                    st.json(ozet)
                    st.markdown(md)
                except (KatalogHatasi, ValueError) as hata:
                    st.error(str(hata))
        st.subheader("Yeni revizyonu kataloğa yükle")
        with st.form("revizyon_yukle"):
            belge_no = st.text_input("Belge no", "MIL-PRF-23377")
            rev = st.text_input("Yeni revizyon harfi")
            if st.form_submit_button("Yükle ve etkilenenleri işaretle") and rev.strip():
                try:
                    etki = yeni_revizyon_yukle(katalog, belge_no.strip(), rev.strip().upper(), kullanici.ad,
                                               fark_ozeti=st.session_state.get("revizyon_ozet"))
                    st.success(f"{etki.yeni_etiket}: {len(etki.etkilenen_malzemeler)} malzeme, "
                               f"{len(etki.etkilenen_partiler)} parti 'M&P incelemesi bekliyor' işaretlendi.")
                except (KatalogHatasi, ValueError) as hata:
                    st.error(str(hata))
                except sqlite3.OperationalError as hata:
                    st.error(f"{MESGUL} ({hata}).")
    with sekme3:
        bekleyen = mp_bekleyenler(katalog)
        if not bekleyen:
            st.info("M&P incelemesi bekleyen malzeme yok.")
            return
        kod = st.selectbox("Malzeme", bekleyen)
        st.write(katalog.malzeme(kod).mp_inceleme)
        karar = st.radio("Karar", ["gerek_yok", "yeni_revizyona_gec"],
                         format_func=lambda x: {"gerek_yok": "Gerek yok (eski revizyonda kal)",
                                                "yeni_revizyona_gec": "Yeni revizyona geç"}[x])
        yeni_rev = st.text_input("Yeni revizyon harfi (geçiş için)")
        not_ = st.text_input("Not")
        if st.button("İncelemeyi kapat"):
            try:
                mp_incelemesini_kapat(katalog, defter, kod, kullanici.ad, karar, not_ or None, yeni_rev.strip().upper() or None)
                st.success("Kapatıldı ve denetim kaydına yazıldı.")
            except (KatalogHatasi, ValueError) as hata:
                st.error(str(hata))
            except sqlite3.OperationalError as hata:
                st.error(f"{MESGUL} ({hata}).")


# --- giriş kalite --------------------------------------------------------------------------------


def giris_kalite_ekrani(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    st.header("Giriş kalite: CoC kontrolü")
    malzemeler = katalog.malzemeler()
    if not malzemeler:
        st.info("Katalogda malzeme yok.")
        return
    m = st.selectbox("Malzeme kodu", malzemeler, format_func=lambda x: f"{x.kod} ({x.standart_etiketi} Type {x.tip} Class {x.sinif})")
    try:
        surum = katalog.gecerli_dokuman(m.kod)
        st.caption(f"Kabul dokümanı: {surum.etiket} (onaylayan {surum.onaylayan})")
    except KatalogHatasi as hata:
        st.error(str(hata))
        return
    lotlar = [p.lot_no for p in katalog.partiler(m.kod)]
    lot = st.selectbox("Lot", ["(yeni lot)"] + lotlar)
    if lot == "(yeni lot)":
        with st.expander("Yeni lot bilgileri", expanded=True):
            yeni_lot = st.text_input("Lot no")
            tedarikci = st.selectbox("Tedarikçi (onaylı)", katalog.onayli_tedarikciler(m.kod))
            sip_rev = st.text_input("Sipariş revizyonu", m.revizyon)
            uretim = st.date_input("Üretim tarihi", date.today())
            kap = st.text_input("Kap türü (isteğe bağlı)")
    mod = st.radio("Okuma modu", ["kural", "hibrit"], horizontal=True,
                   help="hibrit: yerel dil modeli (yalnız localhost) okur, kanıt doğrulayıcı denetler; kararı her zaman kurallar verir.")
    dosya = st.file_uploader("CoC / test raporu (PDF ya da ham hücreli JSON)", type=["pdf", "json"], key="coc")
    if dosya is None or not st.button("Karar ver"):
        return
    try:
        if lot == "(yeni lot)":
            if not yeni_lot.strip() or not tedarikci:
                st.error("Lot no ve onaylı tedarikçi gerekli.")
                return
            lot = ev.parti_hazirla(katalog, m.kod, yeni_lot.strip(), tedarikci, sip_rev.strip(), uretim, kap.strip() or None).lot_no
        if dosya.name.lower().endswith(".json"):
            karar = ev.json_sertifika_karari(katalog, defter, m.kod, dosya.getvalue().decode("utf-8"), kullanici.ad, lot)
        else:
            karar, _ = sertifika_hatti(katalog, m.kod, dosyayi_kaydet(dosya), mod=mod, lot_no=lot, defter=defter, kullanici=kullanici.ad)
    except (KatalogHatasi, HatHatasi, ValueError) as hata:
        st.error(str(hata))
        return
    except sqlite3.OperationalError as hata:
        st.error(f"{MESGUL} ({hata}).")
        return
    st.subheader(f"Parti kararı: {ev.PARTI_ETIKETI[karar.parti_karari]}")
    if karar.hat and karar.hat.get("yedek"):
        st.warning(f"Dil modeli kullanılamadı, kural okumasıyla karar verildi: {karar.hat['yedek']}")
    st.dataframe(ev.karar_tablosu(karar), width="stretch")
    if karar.kontrol.eslesmeyen_satirlar:
        st.caption("Kabul dokümanında karşılığı olmayan sertifika satırları: " + ", ".join(karar.kontrol.eslesmeyen_satirlar))
    st.session_state["son_karar"] = (m.kod, lot)


def duzeltme_formu(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    son = st.session_state.get("son_karar")
    if not son or not son[1]:
        return
    with st.expander("Parti kararını düzelt (gerekçe zorunlu)"):
        durum = st.selectbox("Yeni durum", PARTI_DURUMLARI)
        neden = st.text_area("Gerekçe")
        if st.button("Düzeltmeyi kaydet"):
            try:
                karari_duzelt(katalog, defter, kullanici.ad, son[0], son[1], durum, neden)
                st.success("Düzeltme kaydedildi.")
            except (KatalogHatasi, ValueError) as hata:
                st.error(str(hata))
            except sqlite3.OperationalError as hata:
                st.error(f"{MESGUL} ({hata}).")


# --- depo --------------------------------------------------------------------------------------------


def depo_ekrani(katalog: Katalog, defter: DenetimKaydi, kullanici) -> None:
    st.header("Depo: partiler ve raf ömrü")
    esik = st.number_input("Uyarı eşiği (gün)", min_value=1, max_value=365, value=30)
    tablo = ev.depo_tablosu(katalog, date.today(), int(esik))
    uyarili = [s for s in tablo if s["raf"] in (ev.RAF_ETIKETI["yaklasiyor"], ev.RAF_ETIKETI["doldu"])]
    if uyarili:
        st.warning(f"{len(uyarili)} partide raf ömrü uyarısı var.")
    mp = [s for s in tablo if s["M&P"]]
    if mp:
        st.info(f"{len(mp)} parti M&P incelemesi bekliyor (kilit değildir).")
    st.dataframe(tablo, width="stretch")


EKRAN_FONKSIYONLARI = {
    "standart": standart_ekrani,
    "taslak": taslak_ekrani,
    "revizyon": revizyon_ekrani,
    "giris": giris_kalite_ekrani,
    "depo": depo_ekrani,
}


def main() -> None:
    st.set_page_config(page_title="Malzeme kabul", layout="wide")
    # Her çalıştırma kendi bağlantısını açar ve kapatır (st.rerun istisnasında ve defter kurulamazsa
    # da). Bağlantı oturumlar (iplikler) arasında paylaşılmaz; paylaşılsa işlemler birbirine karışırdı.
    with Katalog(DB) as katalog:
        defter, sema_eksik = baglan(katalog)
        _ekran(katalog, defter, sema_eksik)


def zincir_durumu(defter: DenetimKaydi, sema_eksik: list[str]) -> str:
    """Kenar çubuğundaki zincir yazısı; scripts/denetim_dogrula.py ile aynı şema ve zincir denetimi."""
    if sema_eksik:
        return f"Denetim zinciri: BOZUK (şema: eksik {', '.join(sema_eksik)})"
    s = defter.zinciri_dogrula()
    if s.gecerli:
        return f"Denetim zinciri: sağlam ({s.kayit_sayisi} kayıt)"
    yer = f"kayıt {s.bozuk_sira}" if s.bozuk_sira is not None else "zincir sonu"
    return f"Denetim zinciri: BOZUK ({yer}: {s.neden})"


def _ekran(katalog: Katalog, defter: DenetimKaydi, sema_eksik: list[str]) -> None:
    kullanici = st.session_state.get("kullanici")
    if kullanici is None:
        giris_ekrani(katalog)
        return
    st.sidebar.write(f"**{kullanici.ad}** ({kullanici.rol_adi})")
    if st.sidebar.button("Çıkış"):
        del st.session_state["kullanici"]
        st.rerun()
    ekran = st.sidebar.radio("Ekran", kullanici.ekranlar, format_func=EKRANLAR.get)
    if not yetkili_mi(kullanici, ekran):  # radyo yalnız yetkili ekranları gösterir; yine de denetlenir
        st.error("Bu ekran için yetkiniz yok.")
        return
    EKRAN_FONKSIYONLARI[ekran](katalog, defter, kullanici)
    if ekran == "giris":
        duzeltme_formu(katalog, defter, kullanici)
    st.sidebar.caption(zincir_durumu(defter, sema_eksik))


if __name__ == "__main__":
    main()
