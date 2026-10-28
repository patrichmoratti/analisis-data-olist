# Proyek Analisis Data: E-Commerce Public Dataset (Olist)

Analisis data pesanan e-commerce Olist (Brasil) untuk pesanan berstatus delivered pada periode Januari 2017 sampai Agustus 2018. Proyek ini terdiri dari notebook analisis (`notebook.ipynb`) dan dashboard interaktif berbasis Streamlit yang menampilkan pendapatan, keterlambatan pengiriman, kepuasan pelanggan, dan segmen pelanggan RFM.

## Pertanyaan Bisnis

1. Kategori produk apa saja yang menjadi 10 penyumbang pendapatan terbesar, beserta persentase kontribusinya terhadap total pendapatan selama Januari 2017 sampai Agustus 2018?
2. Bagaimana tren pendapatan per bulan selama Januari 2017 sampai Agustus 2018, termasuk bulan puncak dan pertumbuhan persentasenya?
3. Negara bagian mana yang termasuk 10 teratas dengan persentase pesanan terlambat tertinggi selama Januari 2017 sampai Agustus 2018?
4. Berapa penurunan rata-rata skor ulasan pada pesanan yang terlambat 1 sampai 3 hari, 4 sampai 7 hari, atau lebih dari 7 hari dibandingkan pesanan tepat waktu selama Januari 2017 sampai Agustus 2018?
5. Segmen pelanggan RFM (recency, frequency, monetary) mana yang menyumbang pendapatan terbesar pada pembelian Januari 2017 sampai Agustus 2018?

## Struktur Folder

```
.
├── dashboard/
│   ├── dashboard.py                    # aplikasi Streamlit
│   ├── main_data.csv                   # data hasil wrangling dari notebook
│   └── brasil_negara_bagian.geojson    # batas negara bagian Brasil untuk peta
├── data/                               # dataset asli Olist (CSV)
├── .streamlit/
│   └── config.toml                     # tema dashboard
├── notebook.ipynb                      # notebook analisis
├── README.md
├── requirements.txt
└── url.txt                             # tautan dashboard yang sudah di-deploy
```

## Setup Environment (Windows, Python 3.13)

Buka Command Prompt atau PowerShell di folder proyek, lalu jalankan:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Jika PowerShell menolak menjalankan skrip aktivasi, jalankan dulu `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, lalu ulangi perintah aktivasi.

## Menjalankan Dashboard

Dari folder proyek (dengan environment aktif):

```
streamlit run dashboard/dashboard.py
```

Dashboard akan terbuka di browser pada alamat `http://localhost:8501`.

## Fitur Dashboard

- Filter periode pembelian, negara bagian pelanggan, kategori produk, dan segmen pelanggan (RFM), dengan tombol untuk mengembalikan semua filter.
- Enam kartu ringkasan: total pendapatan, jumlah pesanan, rata-rata nilai pesanan, persentase pesanan terlambat, rata-rata skor ulasan, dan persentase ulasan skor rendah.
- Tab Pendapatan: tren pendapatan bulanan dan pendapatan per kategori produk.
- Tab Pengiriman dan Ulasan: peta keterlambatan per negara bagian (klik peta untuk memilih negara bagian), 5 negara bagian paling terlambat, dan penurunan skor ulasan per kelompok keterlambatan.
- Tab Pelanggan (RFM): kartu segmen yang bisa dipilih serta porsi pelanggan dan porsi pendapatan per segmen.
- Setiap grafik dilengkapi insight singkat yang mengikuti filter.

## Tautan Dashboard

Tautan Streamlit Community Cloud: (https://olist-patrich.streamlit.app)
