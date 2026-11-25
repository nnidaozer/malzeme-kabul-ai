# Colab dil modeli çıktıları

`notebooks/colab_dil_modeli.ipynb` ile Colab'da (Tesla T4, Ollama 0.40.18, bağlam 8192)
üretilen "yalnız dil modeli" çıktıları. 25 Kasım 2026'da PR #44 ile geldi.
Yalnız MIL-PRF-23377K çalıştırıldı; 81733D ve 85285E henüz çalıştırılmadı.

| Model | Kabul dokümanı | Sayfa raporu (süre, hata, tekrar) |
|---|---|---|
| qwen3:8b (düşünme kapalı) | `MIL-PRF-23377K_dil_modeli_qwen3_8b.json` | `MIL-PRF-23377K_dil_modeli_qwen3_8b_rapor.json` |
| llama3.1:8b-instruct-q4_K_M | `MIL-PRF-23377K_dil_modeli_llama3.json` | `MIL-PRF-23377K_dil_modeli_llama3.1_8b-instruct-q4_K_M_rapor.json` |
| qwen2.5:7b-instruct-q4_K_M | `MIL-PRF-23377K_dil_modeli_qwen2.json` | `MIL-PRF-23377K_dil_modeli_qwen2.5_7b-instruct-q4_K_M_rapor.json` |

Değerlendirme (geçici: onaylanmamış `data/gold_taslak` ile): `degerlendirme.md`.
Bu klasör deney sonucudur; ürün (`src/`) bunu okumaz.
