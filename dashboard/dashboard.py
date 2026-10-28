"""
Dashboard Analisis E-Commerce (Olist).

Dashboard ini adalah kelanjutan dari notebook.ipynb. Semua angka dihitung dari
dashboard/main_data.csv dengan definisi yang sama seperti di notebook:
- pendapatan = jumlah price pada level item
- pesanan terlambat = delay_days > 0 (kolom is_late)
- skor rendah = review_score 1 atau 2
- segmen RFM sudah tersedia di kolom segment (dihitung dari seluruh periode)
"""

import html
import json
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------
FOLDER = Path(__file__).parent
FILE_DATA = FOLDER / "main_data.csv"
FILE_PETA = FOLDER / "brasil_negara_bagian.geojson"
# URL yang sama dengan variabel url_peta di notebook
URL_PETA = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"

URUTAN_KELOMPOK = ["Tepat waktu", "Terlambat 1-3 hari", "Terlambat 4-7 hari", "Terlambat > 7 hari"]
URUTAN_SEGMEN = ["Aktif Bernilai Tinggi", "Pasif Bernilai Tinggi", "Aktif Bernilai Rendah", "Pasif Bernilai Rendah"]
MIN_PESANAN = 100  # minimal pesanan per negara bagian agar ikut diperingkat (sama dengan Q3)
PESAN_KOSONG = "Tidak ada data untuk kombinasi filter ini."

BULAN_PENDEK = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
                 "Agustus", "September", "Oktober", "November", "Desember"]

FONT = "DM Sans, system-ui, sans-serif"
KONFIG_GRAFIK = {"displayModeBar": False, "scrollZoom": False}

# palet warna dashboard (tema terang)
WARNA = {
    "latar": "#F4F6FB", "kartu": "#FFFFFF", "teks": "#1B1F2A", "redup": "#566070",
    "garis": "#E3E7EF", "biru": "#1565C0", "ungu": "#6A1B9A", "takarir": "#EAF2FD",
    "biru_redup": "#A9C5EC", "ungu_gradasi": ["#B58AD0", "#8E44B5", "#6A1B9A"],
    "tepi_peta": "#8A94A6",
}


# ---------------------------------------------------------------------------
# Fungsi format angka (gaya Indonesia: titik untuk ribuan, koma untuk desimal)
# ---------------------------------------------------------------------------
def format_angka(nilai, desimal=0):
    teks = f"{nilai:,.{desimal}f}"
    return teks.replace(",", "#").replace(".", ",").replace("#", ".")


def format_persen(nilai, desimal=2):
    return format_angka(nilai, desimal) + "%"


def format_ringkas(nilai):
    """Contoh: 13176606,15 -> 13,18 jt dan 987648,07 -> 987,6 rb."""
    if abs(nilai) >= 1_000_000:
        return format_angka(nilai / 1_000_000, 2) + " jt"
    if abs(nilai) >= 1_000:
        return format_angka(nilai / 1_000, 1) + " rb"
    return format_angka(nilai, 2)


def format_rp(nilai):
    return "R$ " + format_ringkas(nilai)


def label_bulan(kode, panjang=False):
    """Mengubah '2017-11' menjadi 'Nov 2017' (atau 'November 2017')."""
    tahun, bulan = kode.split("-")
    nama = BULAN_PANJANG if panjang else BULAN_PENDEK
    return f"{nama[int(bulan) - 1]} {tahun}"


def format_tick(nilai):
    """Label sumbu ringkas tanpa nol berlebih, contoh: 0, 200 rb, 1 jt, 1,2 jt."""
    if nilai >= 1_000_000:
        angka, satuan = nilai / 1_000_000, " jt"
    elif nilai >= 1_000:
        angka, satuan = nilai / 1_000, " rb"
    else:
        angka, satuan = nilai, ""
    teks = f"{angka:.2f}".rstrip("0").rstrip(".")
    return teks.replace(".", ",") + satuan


def buat_tick(nilai_maks, jumlah=5):
    """Membuat posisi dan label tick yang rapi dari 0 sampai sedikit di atas nilai_maks."""
    if nilai_maks <= 0:
        return [0], ["0"]
    kasar = nilai_maks / jumlah
    pangkat = 10 ** np.floor(np.log10(kasar))
    langkah = next(k * pangkat for k in [1, 2, 2.5, 5, 10] if k * pangkat >= kasar)
    posisi = np.arange(0, nilai_maks + langkah, langkah)
    return posisi.tolist(), [format_tick(p) for p in posisi]


def warna_transparan(kode_hex, alfa):
    r, g, b = (int(kode_hex[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alfa})"


# ---------------------------------------------------------------------------
# Memuat data
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Memuat data...")
def muat_data():
    """Membaca main_data.csv sekali dan hanya mengambil kolom yang dipakai dashboard."""
    kolom = ["order_id", "customer_unique_id", "order_purchase_timestamp", "price",
             "product_category_name_english", "customer_state", "is_late", "delay_status",
             "review_score", "segment"]
    df = pd.read_csv(FILE_DATA, usecols=kolom)

    # bulan pembelian dalam format "YYYY-MM", contoh "2017-11"
    df["bulan"] = df["order_purchase_timestamp"].str[:7]
    # nama kategori Title Case tanpa underscore, sama seperti grafik di notebook
    df["kategori"] = df["product_category_name_english"].str.replace("_", " ").str.title()
    df = df.drop(columns=["order_purchase_timestamp", "product_category_name_english"])

    for kolom_teks in ["customer_state", "kategori", "delay_status", "segment"]:
        df[kolom_teks] = df[kolom_teks].astype("category")
    df["is_late"] = df["is_late"].astype("int8")
    df["review_score"] = df["review_score"].astype("float32")
    return df


@st.cache_data(show_spinner="Memuat peta...")
def muat_peta():
    """Membaca GeoJSON lokal. Jika belum ada, unduh sekali dari URL notebook lalu simpan."""
    if not FILE_PETA.exists():
        try:
            with urllib.request.urlopen(URL_PETA, timeout=30) as respons:
                FILE_PETA.write_bytes(respons.read())
        except urllib.error.URLError:
            return None
    return json.loads(FILE_PETA.read_text(encoding="utf-8"))


def nama_negara_bagian(peta):
    """Kamus kode ke nama negara bagian, diambil dari GeoJSON (kolom sigla dan name)."""
    if peta is None:
        return {}
    return {f["properties"]["sigla"]: f["properties"]["name"] for f in peta["features"]}


@st.cache_data
def daftar_bulan():
    return sorted(muat_data()["bulan"].unique())


@st.cache_data
def kategori_teratas():
    """10 kategori dengan pendapatan terbesar pada seluruh data (sama dengan Q1)."""
    pendapatan = muat_data().groupby("kategori", observed=True)["price"].sum()
    return pendapatan.sort_values(ascending=False).head(10).index.tolist()


# ---------------------------------------------------------------------------
# Filter dan perhitungan
# ---------------------------------------------------------------------------
def terapkan_filter(df, dari, sampai, negara="Semua", kategori="Semua"):
    hasil = df[(df["bulan"] >= dari) & (df["bulan"] <= sampai)]
    if negara != "Semua":
        hasil = hasil[hasil["customer_state"] == negara]
    if kategori == "Lainnya":
        hasil = hasil[~hasil["kategori"].isin(kategori_teratas())]
    elif kategori != "Semua":
        hasil = hasil[hasil["kategori"] == kategori]
    return hasil


def ke_level_pesanan(df):
    """Satu baris per pesanan, karena main_data.csv berada pada level item."""
    return df.drop_duplicates(subset="order_id")


@st.cache_data
def hitung_kpi(dari, sampai, negara, kategori):
    item_df = terapkan_filter(muat_data(), dari, sampai, negara)
    pesanan_df = ke_level_pesanan(item_df)
    ulasan = pesanan_df["review_score"].dropna()
    jumlah_pesanan = len(pesanan_df)
    ada_pesanan = jumlah_pesanan > 0

    return {
        # kategori hanya memengaruhi pendapatan
        "pendapatan": terapkan_filter(muat_data(), dari, sampai, negara, kategori)["price"].sum(),
        "jumlah_pesanan": jumlah_pesanan,
        "nilai_rata": item_df["price"].sum() / jumlah_pesanan if ada_pesanan else None,
        "jumlah_terlambat": int(pesanan_df["is_late"].sum()),
        "persen_terlambat": pesanan_df["is_late"].mean() * 100 if ada_pesanan else None,
        "jumlah_ulasan": len(ulasan),
        "skor_rata": ulasan.mean() if len(ulasan) else None,
        "persen_skor_rendah": (ulasan <= 2).mean() * 100 if len(ulasan) else None,
    }


@st.cache_data
def hitung_tren(dari, sampai, negara, kategori):
    """Pendapatan per bulan. Bulan tanpa penjualan tetap muncul dengan nilai 0."""
    item_df = terapkan_filter(muat_data(), dari, sampai, negara, kategori)
    semua_bulan = [b for b in daftar_bulan() if dari <= b <= sampai]
    tren = item_df.groupby("bulan")["price"].sum().reindex(semua_bulan, fill_value=0)
    return pd.DataFrame({"bulan": tren.index, "pendapatan": tren.values})


@st.cache_data
def hitung_kategori(dari, sampai, negara):
    item_df = terapkan_filter(muat_data(), dari, sampai, negara)
    kategori_df = (item_df.groupby("kategori", observed=True)["price"].sum()
                   .sort_values(ascending=False).reset_index())
    kategori_df.columns = ["kategori", "pendapatan"]
    kategori_df["kategori"] = kategori_df["kategori"].astype(str)
    kategori_df["persen"] = kategori_df["pendapatan"] / kategori_df["pendapatan"].sum() * 100
    return kategori_df


@st.cache_data
def hitung_keterlambatan_negara(dari, sampai):
    """Persen terlambat per negara bagian (mengikuti periode, tidak mengikuti filter negara bagian)."""
    pesanan_df = ke_level_pesanan(terapkan_filter(muat_data(), dari, sampai))
    negara_df = pesanan_df.groupby("customer_state", observed=True).agg(
        order_count=("order_id", "nunique"), late_count=("is_late", "sum")).reset_index()
    negara_df["customer_state"] = negara_df["customer_state"].astype(str)
    negara_df["late_pct"] = negara_df["late_count"] / negara_df["order_count"] * 100

    total_pesanan = negara_df["order_count"].sum()
    rata_nasional = negara_df["late_count"].sum() / total_pesanan * 100 if total_pesanan else None
    return negara_df, rata_nasional


@st.cache_data
def hitung_skor_ulasan(dari, sampai, negara):
    pesanan_df = ke_level_pesanan(terapkan_filter(muat_data(), dari, sampai, negara))
    ulasan_df = pesanan_df.dropna(subset=["review_score"])
    skor_df = ulasan_df.groupby("delay_status", observed=True)["review_score"].agg(["mean", "count"])
    skor_df.index = skor_df.index.astype(str)
    skor_df = skor_df.reindex(URUTAN_KELOMPOK)
    skor_df.columns = ["skor_rata", "jumlah_ulasan"]

    # penurunan skor dibanding pesanan tepat waktu
    skor_tepat_waktu = skor_df.loc["Tepat waktu", "skor_rata"]
    skor_df["turun"] = skor_tepat_waktu - skor_df["skor_rata"]
    skor_df["turun_persen"] = skor_df["turun"] / skor_tepat_waktu * 100
    return skor_df.rename_axis("kelompok").reset_index()


@st.cache_data
def hitung_segmen(negara):
    """Porsi pelanggan dan pendapatan per segmen RFM dari seluruh periode."""
    item_df = muat_data()
    if negara != "Semua":
        item_df = item_df[item_df["customer_state"] == negara]
    segmen_df = item_df.groupby("segment", observed=True).agg(
        jumlah_pelanggan=("customer_unique_id", "nunique"), pendapatan=("price", "sum"))
    segmen_df.index = segmen_df.index.astype(str)
    segmen_df = segmen_df.reindex(URUTAN_SEGMEN, fill_value=0)

    total_pelanggan = segmen_df["jumlah_pelanggan"].sum()
    total_pendapatan = segmen_df["pendapatan"].sum()
    segmen_df["persen_pelanggan"] = segmen_df["jumlah_pelanggan"] / total_pelanggan * 100 if total_pelanggan else 0
    segmen_df["persen_pendapatan"] = segmen_df["pendapatan"] / total_pendapatan * 100 if total_pendapatan else 0
    return segmen_df.rename_axis("segmen").reset_index()


# ---------------------------------------------------------------------------
# Grafik (Plotly)
# ---------------------------------------------------------------------------
def tata_letak_dasar(fig, warna, tinggi):
    fig.update_layout(
        height=tinggi, margin=dict(l=8, r=16, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=warna["teks"], size=13),
        hoverlabel=dict(bgcolor=warna["kartu"], bordercolor=warna["garis"],
                        font=dict(family=FONT, color=warna["teks"], size=13)),
        separators=",.", showlegend=False,
    )
    sumbu = dict(gridcolor=warna["garis"], linecolor=warna["garis"], zeroline=False, automargin=True,
                 tickfont=dict(color=warna["redup"]), title_font=dict(color=warna["redup"], size=12))
    fig.update_xaxes(**sumbu)
    fig.update_yaxes(**sumbu)
    return fig


def buat_grafik_tren(tren, warna):
    posisi = list(range(len(tren)))
    # label sumbu x: bila lebih dari 12 bulan, cukup tampilkan Jan, Apr, Jul, Okt agar tidak berdesakan
    tampil = [i for i, b in enumerate(tren["bulan"]) if len(tren) <= 12 or i == 0 or int(b[5:]) in (1, 4, 7, 10)]
    # tahun ditulis di bawah Januari dan di bawah label pertama
    label_x = [BULAN_PENDEK[int(tren["bulan"][i][5:]) - 1]
               + (f"<br>{tren['bulan'][i][:4]}" if tren["bulan"][i].endswith("-01") or i == 0 else "")
               for i in tampil]
    teks_hover = [[label_bulan(b, panjang=True), "R$ " + format_angka(v, 2)]
                  for b, v in zip(tren["bulan"], tren["pendapatan"])]

    fig = go.Figure(go.Scatter(
        x=posisi, y=tren["pendapatan"], mode="lines+markers",
        line=dict(color=warna["biru"], width=3),
        marker=dict(size=7, color=warna["biru"], line=dict(color=warna["kartu"], width=1.5)),
        fill="tozeroy", fillcolor=warna_transparan(warna["biru"], 0.10),
        customdata=teks_hover, hovertemplate="<b>%{customdata[0]}</b><br>Pendapatan: %{customdata[1]}<extra></extra>",
    ))

    # titik puncak berwarna ungu
    i_puncak = int(tren["pendapatan"].idxmax())
    nilai_puncak = tren["pendapatan"][i_puncak]
    fig.add_trace(go.Scatter(
        x=[i_puncak], y=[nilai_puncak], mode="markers", hoverinfo="skip",
        marker=dict(size=15, color=warna["ungu"], line=dict(color=warna["kartu"], width=2.5)),
    ))
    fig.add_annotation(
        x=i_puncak, y=nilai_puncak, ax=-60 if i_puncak > len(tren) * 0.6 else 60, ay=-34,
        text=f"<b>Puncak: {label_bulan(tren['bulan'][i_puncak])}</b><br>{format_rp(nilai_puncak)}",
        font=dict(color=warna["ungu"], size=12), arrowcolor=warna["ungu"], arrowwidth=1.5,
        bgcolor=warna["kartu"], bordercolor=warna["ungu"], borderwidth=1, borderpad=4,
    )

    tick_y, label_y = buat_tick(nilai_puncak * 1.15)
    tata_letak_dasar(fig, warna, tinggi=390)
    fig.update_xaxes(tickvals=tampil, ticktext=label_x, tickangle=0, showgrid=False, title_text="Bulan pembelian",
                     range=[-0.5, len(tren) - 0.5])
    fig.update_yaxes(tickvals=tick_y, ticktext=label_y, range=[0, tick_y[-1]], title_text="Pendapatan (R$)")
    return fig


def buat_grafik_kategori(kategori_df, kategori_terpilih, warna):
    top10 = kategori_df.head(10)
    # sorot kategori terpilih, atau tiga teratas bila tidak ada kategori tertentu yang dipilih
    if kategori_terpilih in top10["kategori"].tolist():
        disorot = [k == kategori_terpilih for k in top10["kategori"]]
    else:
        disorot = [i < 3 for i in range(len(top10))]
    warna_batang = [warna["biru"] if s else warna["biru_redup"] for s in disorot]
    teks = [f"{format_rp(p)} ({format_persen(pc, 1)})" for p, pc in zip(top10["pendapatan"], top10["persen"])]
    hover = [["R$ " + format_angka(p, 2), format_persen(pc)] for p, pc in zip(top10["pendapatan"], top10["persen"])]

    fig = go.Figure(go.Bar(
        x=top10["pendapatan"], y=top10["kategori"], orientation="h",
        marker=dict(color=warna_batang), text=teks, textposition="outside", cliponaxis=False,
        textfont=dict(color=warna["teks"], size=12), customdata=hover,
        hovertemplate="<b>%{y}</b><br>Pendapatan: %{customdata[0]}<br>Kontribusi: %{customdata[1]}<extra></extra>",
    ))
    tick_x, label_x = buat_tick(top10["pendapatan"].max(), jumlah=4)
    tata_letak_dasar(fig, warna, tinggi=390)
    fig.update_layout(margin=dict(l=8, r=24, t=16, b=8), bargap=0.3)
    fig.update_xaxes(tickvals=tick_x, ticktext=label_x, range=[0, top10["pendapatan"].max() * 1.5],
                     title_text="Pendapatan (R$)")
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=warna["teks"]))
    return fig


def buat_grafik_peta(peta, negara_df, negara_terpilih, nama, warna):
    semua_kode = [f["properties"]["sigla"] for f in peta["features"]]
    data = negara_df[negara_df["customer_state"].isin(semua_kode)]
    hover = [[nama.get(k, k), format_persen(p), format_angka(t), format_angka(n),
              "" if n >= MIN_PESANAN else f"<br><i>Kurang dari {MIN_PESANAN} pesanan, tidak diperingkat</i>"]
             for k, p, t, n in zip(data["customer_state"], data["late_pct"], data["late_count"], data["order_count"])]

    fig = go.Figure()
    # lapisan dasar agar semua negara bagian tetap tergambar walau tanpa pesanan
    fig.add_trace(go.Choropleth(
        geojson=peta, featureidkey="properties.sigla", locations=semua_kode, z=[0] * len(semua_kode),
        colorscale=[[0, warna["garis"]], [1, warna["garis"]]], showscale=False,
        marker=dict(line=dict(color=warna["tepi_peta"], width=0.6)), hoverinfo="skip",
    ))
    fig.add_trace(go.Choropleth(
        geojson=peta, featureidkey="properties.sigla", locations=data["customer_state"], z=data["late_pct"],
        colorscale="Purples", zmin=0, zmax=max(data["late_pct"].max(), 1),
        marker=dict(line=dict(color=warna["tepi_peta"], width=0.6)), customdata=hover,
        hovertemplate=("<b>%{location} · %{customdata[0]}</b><br>Terlambat: %{customdata[1]}"
                       "<br>%{customdata[2]} dari %{customdata[3]} pesanan%{customdata[4]}<extra></extra>"),
        colorbar=dict(title=dict(text="Terlambat", font=dict(color=warna["redup"], size=12)),
                      ticksuffix="%", tickfont=dict(color=warna["redup"]), thickness=12, len=0.75, outlinewidth=0),
    ))
    # garis tepi tebal untuk negara bagian terpilih
    if negara_terpilih != "Semua":
        fig.add_trace(go.Choropleth(
            geojson=peta, featureidkey="properties.sigla", locations=[negara_terpilih], z=[1],
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker=dict(line=dict(color=warna["biru"], width=3.5)), hoverinfo="skip",
        ))

    tata_letak_dasar(fig, warna, tinggi=440)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), clickmode="event+select", dragmode=False)
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)", projection_type="mercator")
    return fig


def buat_grafik_top5(top5, rata_nasional, negara_terpilih, nama, warna):
    label_y = [f"{k} · {nama.get(k, k)}" for k in top5["customer_state"]]
    tepi = [3 if k == negara_terpilih else 0 for k in top5["customer_state"]]
    hover = [[format_persen(p), format_angka(t), format_angka(n)]
             for p, t, n in zip(top5["late_pct"], top5["late_count"], top5["order_count"])]

    fig = go.Figure(go.Bar(
        x=top5["late_pct"], y=label_y, orientation="h",
        marker=dict(color=warna["ungu"], line=dict(color=warna["biru"], width=tepi)),
        text=[format_persen(p) for p in top5["late_pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=warna["teks"], size=12), customdata=hover,
        hovertemplate="<b>%{y}</b><br>Terlambat: %{customdata[0]}<br>%{customdata[1]} dari %{customdata[2]} pesanan<extra></extra>",
    ))
    fig.add_vline(x=rata_nasional, line=dict(color=warna["redup"], dash="dash", width=1.5))
    fig.add_annotation(x=rata_nasional, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                       text=f"Rata-rata nasional {format_persen(rata_nasional)}",
                       font=dict(color=warna["redup"], size=12))

    batas = max(top5["late_pct"].max(), rata_nasional) * 1.25
    tata_letak_dasar(fig, warna, tinggi=440)
    fig.update_layout(margin=dict(l=8, r=24, t=40, b=8), bargap=0.35)
    fig.update_xaxes(range=[0, batas], ticksuffix="%", title_text="Pesanan terlambat (%)")
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=warna["teks"]))
    return fig


def buat_grafik_skor(skor_df, warna):
    data = skor_df.dropna(subset=["skor_rata"])
    warna_kelompok = dict(zip(URUTAN_KELOMPOK, [warna["biru"]] + warna["ungu_gradasi"]))
    teks = []
    for baris in data.itertuples():
        label = f"<b>{format_angka(baris.skor_rata, 2)}</b>"
        if baris.kelompok != "Tepat waktu" and pd.notna(baris.turun):
            label += f"<br>turun {format_angka(baris.turun, 2)} poin ({format_persen(baris.turun_persen, 1)})"
        teks.append(label)
    label_x = [f"{k}<br>(n = {format_angka(n)})" for k, n in zip(data["kelompok"], data["jumlah_ulasan"])]

    fig = go.Figure(go.Bar(
        x=label_x, y=data["skor_rata"], marker=dict(color=[warna_kelompok[k] for k in data["kelompok"]]),
        text=teks, textposition="outside", cliponaxis=False, textfont=dict(color=warna["teks"], size=12),
        customdata=[[format_angka(s, 2), format_angka(n)] for s, n in zip(data["skor_rata"], data["jumlah_ulasan"])],
        hovertemplate="<b>%{x}</b><br>Rata-rata skor: %{customdata[0]}<extra></extra>",
    ))
    tata_letak_dasar(fig, warna, tinggi=400)
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(showgrid=False, tickfont=dict(color=warna["teks"]))
    fig.update_yaxes(range=[0, 6], tickvals=[0, 1, 2, 3, 4, 5], title_text="Rata-rata skor ulasan (1 sampai 5)")
    return fig


def buat_grafik_segmen(segmen_df, segmen_terpilih, warna):
    redup = [1 if segmen_terpilih in ("Semua", s) else 0.35 for s in segmen_df["segmen"]]
    fig = go.Figure()
    for kolom, judul, kode_warna in [("persen_pelanggan", "Porsi pelanggan", warna["biru"]),
                                     ("persen_pendapatan", "Porsi pendapatan", warna["ungu"])]:
        fig.add_trace(go.Bar(
            name=judul, x=segmen_df["segmen"], y=segmen_df[kolom], marker=dict(color=kode_warna, opacity=redup),
            text=[format_persen(v, 1) for v in segmen_df[kolom]], textposition="outside", cliponaxis=False,
            textfont=dict(color=warna["teks"], size=12),
            customdata=[format_persen(v) for v in segmen_df[kolom]],
            hovertemplate=f"<b>%{{x}}</b><br>{judul}: %{{customdata}}<extra></extra>",
        ))
    batas = max(segmen_df[["persen_pelanggan", "persen_pendapatan"]].max().max(), 1) * 1.2
    tata_letak_dasar(fig, warna, tinggi=400)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08, showlegend=True,
                      legend=dict(orientation="h", y=1.08, x=0, font=dict(color=warna["teks"])),
                      margin=dict(l=8, r=16, t=40, b=8))
    fig.update_xaxes(showgrid=False, tickfont=dict(color=warna["teks"]))
    fig.update_yaxes(range=[0, batas], ticksuffix="%", title_text="Persentase dari total (%)")
    return fig


# ---------------------------------------------------------------------------
# Takarir insight (dihitung dari data terfilter)
# ---------------------------------------------------------------------------
def kotak_takarir(lead, penjelas, aksi=None):
    baris_aksi = f'<div class="aksi">{aksi}</div>' if aksi else ""
    return f'<div class="takarir"><span class="lead">{lead}</span> {penjelas}{baris_aksi}</div>'


def buat_takarir_tren(tren):
    if tren.empty or tren["pendapatan"].sum() == 0:
        return kotak_takarir("Tidak ada data.", "Tidak ada pendapatan pada kombinasi filter ini.")
    i = int(tren["pendapatan"].idxmax())
    puncak = tren["pendapatan"][i]
    lead = f"Puncak pada {label_bulan(tren['bulan'][i], panjang=True)}: {format_rp(puncak)}."
    if i == 0 or tren["pendapatan"][i - 1] == 0:
        penjelas = "Tidak ada bulan sebelumnya pada filter ini sebagai pembanding."
    else:
        tumbuh = (puncak / tren["pendapatan"][i - 1] - 1) * 100
        arah = "Naik" if tumbuh >= 0 else "Turun"
        penjelas = f"{arah} {format_persen(abs(tumbuh), 1)} dibanding bulan sebelumnya."
    return kotak_takarir(lead, penjelas, "Aksi: siapkan stok dan kampanye menjelang bulan dengan permintaan tertinggi.")


def buat_takarir_kategori(kategori_df, kategori_terpilih):
    if kategori_df.empty:
        return kotak_takarir("Tidak ada data.", "Tidak ada pendapatan pada kombinasi filter ini.")
    top3 = kategori_df.head(3)
    lead = f"Tiga kategori teratas ({html.escape(', '.join(top3['kategori']))})"
    penjelas = f"menyumbang {format_persen(top3['persen'].sum(), 1)} dari pendapatan pada filter ini."

    if kategori_terpilih == "Lainnya":
        persen = kategori_df[~kategori_df["kategori"].isin(kategori_teratas())]["persen"].sum()
        penjelas += f" Kategori Lainnya (di luar 10 kategori teratas) menyumbang {format_persen(persen, 1)}."
    elif kategori_terpilih != "Semua":
        baris = kategori_df[kategori_df["kategori"] == kategori_terpilih]
        if baris.empty:
            penjelas += f" Kategori {html.escape(kategori_terpilih)} tidak memiliki penjualan pada filter ini."
        else:
            penjelas += (f" Kategori {html.escape(kategori_terpilih)} menyumbang "
                         f"{format_persen(baris['persen'].iloc[0], 1)} ({format_rp(baris['pendapatan'].iloc[0])}).")
    return kotak_takarir(lead, penjelas, "Aksi: prioritaskan stok dan promosi untuk kategori ini.")


def buat_takarir_peta(negara_df, rata_nasional, nama):
    layak = negara_df[negara_df["order_count"] >= MIN_PESANAN]
    if layak.empty:
        return kotak_takarir("Tidak ada data.", f"Belum ada negara bagian dengan minimal {MIN_PESANAN} pesanan pada periode ini.")
    teratas = layak.sort_values(by="late_pct", ascending=False).iloc[0]
    kode = teratas["customer_state"]
    lead = f"{kode} ({html.escape(nama.get(kode, kode))}) paling sering terlambat: {format_persen(teratas['late_pct'])}."
    penjelas = f"Rata-rata nasional {format_persen(rata_nasional)}; warna paling gelap menandai keterlambatan tertinggi."
    aksi = "Aksi: evaluasi rute dan mitra pengiriman, atau sesuaikan estimasi tiba, di wilayah berwarna gelap."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_top5(top5, rata_nasional):
    if top5.empty:
        return kotak_takarir("Tidak ada data.", f"Belum ada negara bagian dengan minimal {MIN_PESANAN} pesanan pada periode ini.")
    kode = top5["customer_state"].tolist()
    daftar = ", ".join(kode[:-1]) + (f", dan {kode[-1]}" if len(kode) > 1 else kode[-1])
    selisih = top5["late_pct"] - rata_nasional

    def bertanda(nilai):
        return ("+" if nilai >= 0 else "-") + format_angka(abs(nilai), 2)

    lead = f"{len(kode)} negara bagian teratas: {daftar}."
    penjelas = (f"Persentase terlambatnya {format_persen(top5['late_pct'].min())} sampai "
                f"{format_persen(top5['late_pct'].max())}, atau {bertanda(selisih.min())} sampai "
                f"{bertanda(selisih.max())} poin persen dibanding rata-rata nasional ({format_persen(rata_nasional)}).")
    aksi = "Aksi: dahulukan evaluasi rute dan mitra pengiriman, atau sesuaikan estimasi tiba, di negara bagian ini."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_skor(skor_df):
    data = skor_df.set_index("kelompok")
    tepat, lambat = data.loc["Tepat waktu"], data.loc["Terlambat > 7 hari"]
    if pd.isna(tepat["skor_rata"]) or pd.isna(lambat["skor_rata"]):
        return kotak_takarir("Data ulasan tidak cukup.",
                             "Kelompok tepat waktu atau terlambat lebih dari 7 hari tidak memiliki ulasan pada filter ini.")
    if lambat["turun"] >= 0:
        lead = (f"Terlambat lebih dari 7 hari menurunkan skor {format_angka(lambat['turun'], 2)} poin "
                f"({format_persen(lambat['turun_persen'], 1)}).")
    else:
        lead = "Terlambat lebih dari 7 hari tidak menurunkan skor pada filter ini."
    penjelas = (f"Skor rata-rata pesanan tepat waktu {format_angka(tepat['skor_rata'], 2)}, sedangkan pada kelompok "
                f"terlambat lebih dari 7 hari {format_angka(lambat['skor_rata'], 2)}. Ini asosiasi, bukan bukti sebab-akibat.")
    aksi = "Aksi: beri pemberitahuan proaktif atau kompensasi pada pesanan yang diperkirakan sangat terlambat."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_rfm(segmen_df, segmen_terpilih):
    if segmen_df["jumlah_pelanggan"].sum() == 0:
        return kotak_takarir("Tidak ada data.", "Tidak ada pelanggan pada kombinasi filter ini.")
    tinggi = segmen_df[segmen_df["segmen"].str.contains("Tinggi")]
    rendah = segmen_df[segmen_df["segmen"].str.contains("Rendah")]
    lead = (f"Segmen Bernilai Tinggi: {format_persen(tinggi['persen_pelanggan'].sum(), 1)} pelanggan, "
            f"{format_persen(tinggi['persen_pendapatan'].sum(), 1)} pendapatan.")

    if tinggi["jumlah_pelanggan"].sum() and rendah["jumlah_pelanggan"].sum():
        rata_tinggi = tinggi["pendapatan"].sum() / tinggi["jumlah_pelanggan"].sum()
        rata_rendah = rendah["pendapatan"].sum() / rendah["jumlah_pelanggan"].sum()
        penjelas = (f"Rata-rata belanja pelanggan Bernilai Tinggi ({format_rp(rata_tinggi)}) jauh di atas "
                    f"Bernilai Rendah ({format_rp(rata_rendah)}).")
    else:
        penjelas = "Salah satu kelompok segmen tidak memiliki pelanggan pada filter ini."

    if segmen_terpilih != "Semua":
        baris = segmen_df[segmen_df["segmen"] == segmen_terpilih].iloc[0]
        penjelas += (f" Segmen {segmen_terpilih} yang dipilih: {format_angka(baris['jumlah_pelanggan'])} pelanggan "
                     f"({format_persen(baris['persen_pelanggan'], 1)}) dengan {format_persen(baris['persen_pendapatan'], 1)} pendapatan.")
    aksi = ("Aksi: pertahankan segmen Aktif dengan program loyalitas dan aktifkan kembali segmen Pasif "
            "lewat kampanye win-back.")
    return kotak_takarir(lead, penjelas, aksi)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def buat_css(w):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
[data-testid="stMainBlockContainer"] {{ padding: 3.5rem 2.5rem 3rem; max-width: 1500px; }}
.olist, .kpi, .takarir, .chip, .judul-kartu {{ font-family: {FONT}; }}

/* judul halaman */
[data-testid="stMarkdownContainer"] h1.judul-halaman {{ font-size: 1.85rem; font-weight: 700; color: {w["teks"]};
        margin: 0; padding: 0; line-height: 1.2; }}
.subjudul-halaman {{ color: {w["redup"]}; margin: 4px 0 14px; font-size: 1rem; }}

/* chip filter aktif */
.baris-chip {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 16px; }}
.baris-chip .label {{ color: {w["redup"]}; font-size: .85rem; font-weight: 600; margin-right: 2px; }}
.chip {{ background: {w["takarir"]}; color: {w["biru"]}; border-radius: 999px; padding: 4px 12px;
         font-size: .82rem; font-weight: 600; }}

/* kartu KPI */
.kpi-grid {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }}
@media (max-width: 1150px) {{ .kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 640px) {{ .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.kpi {{ background: {w["kartu"]}; border: 1px solid {w["garis"]}; border-radius: 16px; padding: 16px 16px 14px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, .04); min-width: 0; }}
.kpi .judul {{ color: {w["redup"]}; font-size: .8rem; font-weight: 600; line-height: 1.3; min-height: 2.6em; }}
.kpi .nilai {{ color: {w["teks"]}; font-size: 1.45rem; font-weight: 700; margin: 6px 0 2px;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kpi .nilai.ungu {{ color: {w["ungu"]}; }}
.kpi .sub {{ color: {w["redup"]}; font-size: .78rem; overflow-wrap: anywhere; }}

/* kartu grafik dan kartu segmen (container dengan key berawalan "kartu") */
div[class*="st-key-kartu"] {{ background: {w["kartu"]}; border: 1px solid {w["garis"]}; border-radius: 16px;
        padding: 18px 20px; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
div[class*="st-key-kartu_seg"][class*="aktif"] {{ border: 2px solid {w["biru"]}; }}
/* Streamlit memberi margin bawah negatif pada markdown; dinolkan agar jarak di dalam kartu rata */
div[class*="st-key-kartu"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
/* kartu yang bersebelahan dibuat sama tinggi, dan elemen terakhir (takarir atau tombol) rata bawah */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-kartu"]) {{ align-items: stretch; }}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-kartu"]) > div[data-testid="stColumn"] > div {{ height: 100%; }}
div[data-testid="stColumn"] div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-kartu"]) {{ flex-grow: 1; }}
div[class*="st-key-kartu"] {{ flex-grow: 1; }}
div[class*="st-key-kartu"] > div[data-testid="stElementContainer"]:last-child {{ margin-top: auto; }}
/* sisa ruang diberikan ke kotak takarir, sehingga takarir kartu yang bersebelahan sejajar atas dan bawah */
div[class*="st-key-kartu"] > div[data-testid="stElementContainer"]:last-child:has(.takarir) {{ margin-top: 0; flex-grow: 1; }}
div[class*="st-key-kartu"] > div[data-testid="stElementContainer"]:last-child:has(.takarir)
    :is([data-testid="stMarkdown"], [data-testid="stMarkdown"] > div, [data-testid="stMarkdownContainer"], .takarir) {{ height: 100%; }}
.takarir {{ box-sizing: border-box; }}
[data-testid="stMarkdownContainer"] h2.judul-kartu {{ font-size: 1.1rem; font-weight: 700; color: {w["teks"]};
        margin: 0 0 2px; padding: 0; line-height: 1.35; }}

/* isi kartu segmen */
.seg-nama {{ font-weight: 700; color: {w["teks"]}; font-size: .98rem; }}
.seg-nilai {{ font-weight: 700; color: {w["biru"]}; font-size: 1.35rem; margin: 4px 0 2px; }}
.seg-detail {{ color: {w["redup"]}; font-size: .82rem; line-height: 1.5; }}

/* takarir insight */
.takarir {{ background: {w["takarir"]}; color: {w["teks"]}; border-radius: 12px; padding: 12px 14px;
            font-size: .92rem; line-height: 1.55; }}
.takarir .lead {{ color: {w["biru"]}; font-weight: 700; }}
.takarir .aksi {{ font-weight: 600; margin-top: 6px; }}

/* sidebar */
.logo {{ display: flex; align-items: center; gap: 10px; margin: 0 0 18px; }}
.logo .ikon {{ width: 38px; height: 38px; border-radius: 10px; background: {w["biru"]};
               display: flex; align-items: center; justify-content: center; }}
.logo .nama {{ font-weight: 700; font-size: 1.05rem; color: {w["teks"]}; line-height: 1.2; }}
.logo .sub {{ font-size: .8rem; color: {w["redup"]}; }}
.label-filter {{ font-size: .72rem; font-weight: 700; letter-spacing: .08em; color: {w["redup"]}; margin: 4px 0 8px; }}
.label-periode {{ font-size: .875rem; font-weight: 600; color: {w["teks"]}; margin-bottom: 2px; }}
.st-key-tombol_reset button {{ border: 1.5px solid {w["biru"]}; color: {w["biru"]}; background: transparent; font-weight: 600; }}
.st-key-tombol_reset button:hover {{ background: {w["takarir"]}; border-color: {w["biru"]}; color: {w["biru"]}; }}
</style>
"""


IKON_LOGO = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
<rect x="4" y="12" width="4" height="8" rx="1" fill="white"/><rect x="10" y="7" width="4" height="13" rx="1" fill="white"/>
<rect x="16" y="3" width="4" height="17" rx="1" fill="white"/></svg>"""


# ---------------------------------------------------------------------------
# Session state dan callback filter
# ---------------------------------------------------------------------------
def nilai_default():
    bulan = daftar_bulan()
    return {"dari": bulan[0], "sampai": bulan[-1], "negara": "Semua", "kategori": "Semua", "segmen": "Semua"}


def siapkan_session_state():
    for kunci, nilai in nilai_default().items():
        st.session_state.setdefault(kunci, nilai)


def reset_filter():
    for kunci, nilai in nilai_default().items():
        st.session_state[kunci] = nilai


def cek_urutan_periode():
    """Tukar otomatis bila 'Dari' lebih besar dari 'Sampai'."""
    if st.session_state.dari > st.session_state.sampai:
        st.session_state.dari, st.session_state.sampai = st.session_state.sampai, st.session_state.dari
        st.session_state.periode_ditukar = True


def saat_peta_diklik():
    """Klik pada peta mengatur filter negara bagian."""
    pilihan = st.session_state[st.session_state.kunci_peta]["selection"]
    lokasi = [titik.get("location") for titik in pilihan["points"] if titik.get("location")]
    if lokasi:
        st.session_state.negara = lokasi[0]


def pilih_segmen(nama):
    """Klik kartu segmen memilih segmen itu; klik lagi untuk membatalkan."""
    st.session_state.segmen = "Semua" if st.session_state.segmen == nama else nama


# ---------------------------------------------------------------------------
# Tampilan
# ---------------------------------------------------------------------------
def tampilkan_sidebar(nama):
    sb = st.sidebar
    sb.markdown(f'<div class="logo olist"><div class="ikon">{IKON_LOGO}</div><div><div class="nama">Olist Insights</div>'
                f'<div class="sub">Analisis pesanan terkirim</div></div></div>', unsafe_allow_html=True)
    sb.markdown('<div class="label-filter olist">FILTER</div>', unsafe_allow_html=True)

    sb.markdown('<div class="label-periode olist">Periode pembelian</div>', unsafe_allow_html=True)
    kiri, kanan = sb.columns(2)
    kiri.selectbox("Dari", daftar_bulan(), key="dari", format_func=label_bulan, on_change=cek_urutan_periode)
    kanan.selectbox("Sampai", daftar_bulan(), key="sampai", format_func=label_bulan, on_change=cek_urutan_periode)
    if st.session_state.pop("periode_ditukar", False):
        sb.warning("Bulan \"Dari\" lebih besar dari \"Sampai\", jadi keduanya ditukar otomatis.")

    daftar_negara = sorted(muat_data()["customer_state"].astype(str).unique())
    sb.selectbox("Negara bagian pelanggan", ["Semua"] + daftar_negara, key="negara",
                 format_func=lambda k: k if k == "Semua" or k not in nama else f"{k} · {nama[k]}")
    sb.selectbox("Kategori produk", ["Semua"] + kategori_teratas() + ["Lainnya"], key="kategori")
    sb.selectbox("Segmen pelanggan (RFM)", ["Semua"] + URUTAN_SEGMEN, key="segmen")
    sb.button("Reset semua filter", key="tombol_reset", on_click=reset_filter, width="stretch")


def tampilkan_chip(f, nama):
    chip = []
    if (f["dari"], f["sampai"]) != (daftar_bulan()[0], daftar_bulan()[-1]):
        chip.append(f"Periode: {label_bulan(f['dari'])} sampai {label_bulan(f['sampai'])}")
    if f["negara"] != "Semua":
        chip.append(f"Negara bagian: {f['negara']} · {nama.get(f['negara'], f['negara'])}")
    if f["kategori"] != "Semua":
        chip.append(f"Kategori: {f['kategori']}")
    if f["segmen"] != "Semua":
        chip.append(f"Segmen: {f['segmen']}")
    isi = "".join(f'<span class="chip">{html.escape(c)}</span>' for c in (chip or ["Semua data"]))
    st.markdown(f'<div class="baris-chip olist"><span class="label">Filter aktif:</span>{isi}</div>',
                unsafe_allow_html=True)


def hitung_kartu_kpi(kpi, kategori):
    """Menyusun judul, nilai, dan keterangan enam kartu KPI. Nilai '-' bila data kosong."""
    ada = kpi["jumlah_pesanan"] > 0
    sub_pendapatan = f"Kategori {kategori}" if kategori != "Semua" else "Total harga item terjual"
    return [
        ("Total pendapatan", format_rp(kpi["pendapatan"]) if ada else "-", sub_pendapatan, False),
        ("Jumlah pesanan", format_angka(kpi["jumlah_pesanan"]) if ada else "-", "Pesanan unik terkirim", False),
        ("Rata-rata nilai pesanan", "R$ " + format_angka(kpi["nilai_rata"], 2) if ada else "-",
         "Pendapatan dibagi pesanan", False),
        ("Pesanan terlambat", format_persen(kpi["persen_terlambat"]) if ada else "-",
         f"{format_angka(kpi['jumlah_terlambat'])} pesanan terlambat" if ada else "Tidak ada pesanan", True),
        ("Rata-rata skor ulasan", format_angka(kpi["skor_rata"], 2) if kpi["skor_rata"] is not None else "-",
         f"Dari {format_angka(kpi['jumlah_ulasan'])} ulasan", False),
        ("Ulasan skor rendah", format_persen(kpi["persen_skor_rendah"]) if kpi["persen_skor_rendah"] is not None else "-",
         "Skor 1 atau 2", False),
    ]


def tampilkan_kpi(kpi, kategori):
    kartu = ""
    for judul, nilai, sub, ungu in hitung_kartu_kpi(kpi, kategori):
        kelas = "nilai ungu" if ungu else "nilai"
        kartu += (f'<div class="kpi"><div class="judul">{judul}</div><div class="{kelas}">{nilai}</div>'
                  f'<div class="sub">{html.escape(sub)}</div></div>')
    st.markdown(f'<div class="kpi-grid">{kartu}</div>', unsafe_allow_html=True)


def judul_kartu(teks):
    st.markdown(f'<h2 class="judul-kartu">{teks}</h2>', unsafe_allow_html=True)


def takarir(isi_html):
    st.markdown(isi_html, unsafe_allow_html=True)


def tampilkan_tab_pendapatan(f, warna):
    kiri, kanan = st.columns([1.1, 1], gap="medium")

    with kiri.container(key="kartu_tren"):
        judul_kartu("Tren Pendapatan Bulanan")
        tren = hitung_tren(f["dari"], f["sampai"], f["negara"], f["kategori"])
        if tren["pendapatan"].sum() == 0:
            st.info(PESAN_KOSONG)
        else:
            st.plotly_chart(buat_grafik_tren(tren, warna), width="stretch", theme=None,
                            config=KONFIG_GRAFIK, key="grafik_tren")
        takarir(buat_takarir_tren(tren))

    with kanan.container(key="kartu_kategori"):
        judul_kartu("Pendapatan per Kategori Produk")
        kategori_df = hitung_kategori(f["dari"], f["sampai"], f["negara"])
        if kategori_df.empty:
            st.info(PESAN_KOSONG)
        else:
            st.plotly_chart(buat_grafik_kategori(kategori_df, f["kategori"], warna), width="stretch",
                            theme=None, config=KONFIG_GRAFIK, key="grafik_kategori")
        takarir(buat_takarir_kategori(kategori_df, f["kategori"]))


def tampilkan_tab_pengiriman(f, peta, nama, warna):
    negara_df, rata_nasional = hitung_keterlambatan_negara(f["dari"], f["sampai"])
    kiri, kanan = st.columns([1.15, 1], gap="medium")

    with kiri.container(key="kartu_peta"):
        judul_kartu("Peta Keterlambatan per Negara Bagian")
        if peta is None:
            st.warning("File peta tidak ditemukan dan gagal diunduh. Periksa koneksi internet lalu muat ulang halaman.")
        elif negara_df.empty:
            st.info(PESAN_KOSONG)
        else:
            # key berganti setiap negara bagian berubah, agar pilihan lama di peta tidak menempel
            st.session_state.kunci_peta = f"peta_{f['negara']}"
            st.plotly_chart(buat_grafik_peta(peta, negara_df, f["negara"], nama, warna), width="stretch",
                            theme=None, config=KONFIG_GRAFIK, key=st.session_state.kunci_peta,
                            on_select=saat_peta_diklik, selection_mode="points")
        takarir(buat_takarir_peta(negara_df, rata_nasional, nama))

    top5 = (negara_df[negara_df["order_count"] >= MIN_PESANAN]
            .sort_values(by="late_pct", ascending=False).head(5))
    with kanan.container(key="kartu_top5"):
        judul_kartu("5 Negara Bagian Paling Terlambat")
        if top5.empty:
            st.info(PESAN_KOSONG)
        else:
            st.plotly_chart(buat_grafik_top5(top5, rata_nasional, f["negara"], nama, warna), width="stretch",
                            theme=None, config=KONFIG_GRAFIK, key="grafik_top5")
        takarir(buat_takarir_top5(top5, rata_nasional))

    with st.container(key="kartu_skor"):
        judul_kartu("Penurunan Skor Ulasan pada Pesanan Terlambat")
        skor_df = hitung_skor_ulasan(f["dari"], f["sampai"], f["negara"])
        if skor_df["skor_rata"].isna().all():
            st.info(PESAN_KOSONG)
        else:
            st.plotly_chart(buat_grafik_skor(skor_df, warna), width="stretch", theme=None,
                            config=KONFIG_GRAFIK, key="grafik_skor")
        takarir(buat_takarir_skor(skor_df))


def tampilkan_tab_pelanggan(f, warna):
    segmen_df = hitung_segmen(f["negara"])

    kolom = st.columns(4, gap="small")
    for i, baris in enumerate(segmen_df.itertuples()):
        aktif = baris.segmen == f["segmen"]
        with kolom[i].container(key=f"kartu_seg_{i}" + ("_aktif" if aktif else "")):
            st.markdown(
                f'<div class="olist"><div class="seg-nama">{baris.segmen}</div>'
                f'<div class="seg-nilai">{format_rp(baris.pendapatan)}</div>'
                f'<div class="seg-detail">{format_angka(baris.jumlah_pelanggan)} pelanggan<br>'
                f'{format_persen(baris.persen_pendapatan)} pendapatan</div></div>', unsafe_allow_html=True)
            st.button("Segmen terpilih" if aktif else "Pilih segmen", key=f"tombol_seg_{i}",
                      type="primary" if aktif else "secondary", icon=":material/check:" if aktif else None,
                      on_click=pilih_segmen, args=(baris.segmen,), width="stretch")

    with st.container(key="kartu_rfm"):
        judul_kartu("Porsi Pelanggan dan Porsi Pendapatan per Segmen")
        if segmen_df["jumlah_pelanggan"].sum() == 0:
            st.info(PESAN_KOSONG)
        else:
            st.plotly_chart(buat_grafik_segmen(segmen_df, f["segmen"], warna), width="stretch", theme=None,
                            config=KONFIG_GRAFIK, key="grafik_segmen")
        takarir(buat_takarir_rfm(segmen_df, f["segmen"]))


def main():
    st.set_page_config(page_title="Dashboard Olist", page_icon="📊", layout="wide")
    warna = WARNA
    st.markdown(buat_css(warna), unsafe_allow_html=True)

    peta = muat_peta()
    nama = nama_negara_bagian(peta)
    siapkan_session_state()
    tampilkan_sidebar(nama)
    f = {k: st.session_state[k] for k in ["dari", "sampai", "negara", "kategori", "segmen"]}

    st.markdown('<div class="olist"><h1 class="judul-halaman">Dashboard Analisis E-Commerce</h1>'
                '<p class="subjudul-halaman">Pendapatan, pengiriman, kepuasan, dan segmen pelanggan dalam satu tampilan.</p></div>',
                unsafe_allow_html=True)
    tampilkan_chip(f, nama)

    kpi = hitung_kpi(f["dari"], f["sampai"], f["negara"], f["kategori"])
    tampilkan_kpi(kpi, f["kategori"])
    if kpi["jumlah_pesanan"] == 0:
        st.info(PESAN_KOSONG)

    tab_pendapatan, tab_pengiriman, tab_pelanggan = st.tabs(
        ["Pendapatan", "Pengiriman dan Ulasan", "Pelanggan (RFM)"], key="tab_aktif")
    with tab_pendapatan:
        tampilkan_tab_pendapatan(f, warna)
    with tab_pengiriman:
        tampilkan_tab_pengiriman(f, peta, nama, warna)
    with tab_pelanggan:
        tampilkan_tab_pelanggan(f, warna)


if __name__ == "__main__":
    main()
