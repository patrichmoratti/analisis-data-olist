# Proyek Analisis Data: E-Commerce Public Dataset (Olist)

Analisis data pesanan e-commerce Olist (Brasil) untuk pesanan berstatus delivered pada periode Januari 2017 sampai Agustus 2018. Proyek ini terdiri dari notebook analisis (`notebook.ipynb`) dan dashboard interaktif berbasis Streamlit yang menampilkan pendapatan, keterlambatan pengiriman, kepuasan pelanggan, dan segmen pelanggan RFM.

Tautan dashboard: https://olist-patrich.streamlit.app

## Ringkasan Temuan Utama

1. Sepuluh kategori teratas menyumbang 62,47% dari total pendapatan R$ 13.176.606,15, dan tiga kategori teratas saja menyumbang 25,92%.
2. Pendapatan tertinggi terjadi pada November 2017 sebesar R$ 987.648,07, naik 52,36% dibandingkan bulan sebelumnya.
3. AL (21,46%), MA (17,53%), SE (15,36%), PI (13,89%), dan CE (13,83%) memiliki persentase pesanan terlambat tertinggi, lebih dari dua kali rata-rata nasional 6,79%.
4. Rata-rata skor ulasan turun dari 4,29 pada pesanan tepat waktu menjadi 3,29, 2,10, dan 1,70 pada keterlambatan 1 sampai 3 hari, 4 sampai 7 hari, dan lebih dari 7 hari.
5. Segmen Aktif Bernilai Tinggi menyumbang pendapatan terbesar (42,17%), dan kedua segmen Bernilai Tinggi yang mencakup 50,01% pelanggan menyumbang 83,32% pendapatan.

## Pertanyaan Bisnis

1. Kategori produk apa saja yang menjadi 10 penyumbang pendapatan terbesar, beserta persentase kontribusinya terhadap total pendapatan selama Januari 2017 sampai Agustus 2018, sebagai dasar penentuan prioritas stok dan promosi?
2. Bagaimana tren pendapatan per bulan selama Januari 2017 sampai Agustus 2018, termasuk bulan puncak dan pertumbuhan persentasenya, sebagai dasar penentuan jadwal kampanye dan persiapan stok?
3. Negara bagian mana yang termasuk 5 teratas dengan persentase pesanan terlambat tertinggi selama Januari 2017 sampai Agustus 2018, sebagai dasar penentuan wilayah prioritas evaluasi pengiriman?
4. Berapa penurunan rata-rata skor ulasan pada pesanan yang terlambat 1 sampai 3 hari, 4 sampai 7 hari, atau lebih dari 7 hari dibandingkan pesanan tepat waktu selama Januari 2017 sampai Agustus 2018, sebagai dasar penentuan batas keterlambatan yang perlu ditangani lebih dulu?
5. Segmen pelanggan RFM (recency, frequency, monetary) mana yang menyumbang pendapatan terbesar pada pembelian Januari 2017 sampai Agustus 2018, sebagai dasar penentuan sasaran program loyalitas dan kampanye win-back?

## Struktur Folder

```
.
├── dashboard/
│   ├── dashboard.py                    # aplikasi Streamlit
│   ├── main_data.csv                   # data untuk dashboard, diekspor dari notebook (hanya kolom yang dipakai)
│   └── brasil_negara_bagian.geojson    # batas negara bagian Brasil untuk peta
├── data/                               # dataset asli Olist (CSV)
├── .streamlit/
│   └── config.toml                     # tema dashboard
├── notebook.ipynb                      # notebook analisis
├── README.md
├── requirements.txt                    # library untuk notebook dan dashboard
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

`requirements.txt` memuat semua library yang dipakai notebook dan dashboard. Untuk menjalankan notebook di Jupyter atau VS Code, pilih environment `.venv` sebagai kernel.

## Menjalankan Dashboard

Dari folder proyek (dengan environment aktif):

```
streamlit run dashboard/dashboard.py
```

Dashboard akan terbuka di browser pada alamat `http://localhost:8501`.

## Fitur Dashboard

- Tiga filter di sidebar: periode pembelian (bulan dan tahun), kategori produk, dan segmen pelanggan (RFM), ditambah tombol untuk mengembalikan semua filter.
- Ketiga filter memengaruhi seluruh visual: kartu ringkasan, tren pendapatan, pendapatan per kategori, peta keterlambatan, 5 negara bagian paling terlambat, skor ulasan per kelompok keterlambatan, kartu dan grafik segmen RFM, serta teks insight di bawah setiap grafik.
- Enam kartu ringkasan: total pendapatan, jumlah pesanan, rata-rata nilai pesanan, persentase pesanan terlambat, rata-rata skor ulasan, dan persentase ulasan skor rendah.
- Tab Pendapatan: tren pendapatan bulanan dan pendapatan per kategori produk.
- Tab Pengiriman dan Ulasan: peta keterlambatan per negara bagian, 5 negara bagian paling terlambat, dan penurunan skor ulasan per kelompok keterlambatan.
- Tab Pelanggan (RFM): kartu segmen yang bisa dipilih (ikut mengubah filter segmen) serta porsi pelanggan dan porsi pendapatan per segmen.
