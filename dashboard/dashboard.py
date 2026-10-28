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

KOLOM_DATA = ["order_id", "customer_unique_id", "order_purchase_timestamp", "price",
              "product_category_name_english", "customer_state", "is_late", "delay_status",
              "review_score", "segment"]
URUTAN_KELOMPOK = ["Tepat waktu", "Terlambat 1-3 hari", "Terlambat 4-7 hari", "Terlambat > 7 hari"]
URUTAN_SEGMEN = ["Aktif Bernilai Tinggi", "Pasif Bernilai Tinggi", "Aktif Bernilai Rendah", "Pasif Bernilai Rendah"]
MIN_PESANAN = 100  # minimal pesanan per negara bagian agar ikut diperingkat (sama dengan Q3)
BATAS_WARNA_PETA = 22  # skala warna peta 0 sampai 22 persen (sama dengan peta di notebook)
PESAN_KOSONG = "Tidak ada data untuk kombinasi filter ini."

BULAN_PENDEK = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
                 "Agustus", "September", "Oktober", "November", "Desember"]
ANGKA_KATA = {1: "Satu", 2: "Dua", 3: "Tiga", 4: "Empat", 5: "Lima"}

FONT = "DM Sans, system-ui, sans-serif"
KONFIG_GRAFIK = {"displayModeBar": False, "scrollZoom": False}

# palet warna dashboard (tema terang)
WARNA = {
    "latar": "#F4F6FB", "kartu": "#FFFFFF", "teks": "#1B1F2A", "redup": "#566070",
    "garis": "#E3E7EF", "biru": "#1565C0", "ungu": "#6A1B9A", "takarir": "#EAF2FD",
    "biru_redup": "#A9C5EC", "ungu_gradasi": ["#B58AD0", "#8E44B5", "#6A1B9A"],
    "tepi_peta": "#8A94A6", "tanpa_data": "#E9ECF2",
}

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


def gabung_daftar(daftar):
    """['AL', 'MA', 'SE'] -> 'AL, MA, dan SE'."""
    if len(daftar) <= 1:
        return "".join(daftar)
    return ", ".join(daftar[:-1]) + f", dan {daftar[-1]}"


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
def siapkan_data(df):
    """Menambah kolom bulan dan nama kategori, lalu mengubah tipe data agar hemat memori."""
    df = df.copy()
    df["bulan"] = df["order_purchase_timestamp"].str[:7]  # contoh: "2017-11"
    # nama kategori Title Case tanpa underscore, sama seperti grafik di notebook
    df["kategori"] = df["product_category_name_english"].str.replace("_", " ").str.title()
    df = df.drop(columns=["order_purchase_timestamp", "product_category_name_english"])
    for kolom in ["customer_state", "kategori", "delay_status", "segment"]:
        df[kolom] = df[kolom].astype("category")
    df["is_late"] = df["is_late"].astype("int8")
    df["review_score"] = df["review_score"].astype("float32")
    return df


@st.cache_data(show_spinner="Memuat data...")
def muat_data():
    """Membaca main_data.csv sekali dan hanya mengambil kolom yang dipakai dashboard."""
    return siapkan_data(pd.read_csv(FILE_DATA, usecols=KOLOM_DATA))


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


def daftar_bulan(df):
    return sorted(df["bulan"].unique())


def kategori_teratas(df):
    """10 kategori dengan pendapatan terbesar pada seluruh data (sama dengan Q1)."""
    pendapatan = df.groupby("kategori", observed=True)["price"].sum()
    return pendapatan.sort_values(ascending=False).head(10).index.tolist()


def terapkan_filter(df, dari, sampai, kategori="Semua", segmen="Semua"):
    """Satu-satunya tempat filter diterapkan. df harus berisi seluruh data."""
    hasil = df[(df["bulan"] >= dari) & (df["bulan"] <= sampai)]
    if kategori == "Lainnya":
        hasil = hasil[~hasil["kategori"].isin(kategori_teratas(df))]
    elif kategori != "Semua":
        hasil = hasil[hasil["kategori"] == kategori]
    if segmen != "Semua":
        hasil = hasil[hasil["segment"] == segmen]
    return hasil


def ke_level_pesanan(df):
    """Satu baris per pesanan, karena main_data.csv berada pada level item."""
    return df.drop_duplicates(subset="order_id")


def hitung_kpi(df):
    pesanan_df = ke_level_pesanan(df)
    ulasan = pesanan_df["review_score"].dropna()
    jumlah_pesanan = len(pesanan_df)
    ada_pesanan = jumlah_pesanan > 0
    pendapatan = df["price"].sum()
    return {
        "pendapatan": pendapatan,
        "jumlah_pesanan": jumlah_pesanan,
        "nilai_rata": pendapatan / jumlah_pesanan if ada_pesanan else None,
        "jumlah_terlambat": int(pesanan_df["is_late"].sum()),
        "persen_terlambat": pesanan_df["is_late"].mean() * 100 if ada_pesanan else None,
        "jumlah_ulasan": len(ulasan),
        "skor_rata": ulasan.mean() if len(ulasan) else None,
        "persen_skor_rendah": (ulasan <= 2).mean() * 100 if len(ulasan) else None,
    }


def hitung_tren(df, dari, sampai):
    """Pendapatan per bulan dalam rentang terpilih. Bulan tanpa penjualan bernilai 0."""
    semua_bulan = pd.period_range(dari, sampai, freq="M").strftime("%Y-%m").tolist()
    tren = df.groupby("bulan")["price"].sum().reindex(semua_bulan, fill_value=0)
    return pd.DataFrame({"bulan": tren.index, "pendapatan": tren.values})


def hitung_kategori(df, total_pembanding):
    """10 kategori teratas pada data terfilter.

    Persentase dihitung terhadap total_pembanding, yaitu pendapatan pada filter periode
    dan segmen tanpa filter kategori, agar kategori yang dipilih tidak selalu 100%.
    """
    kategori_df = (df.groupby("kategori", observed=True)["price"].sum()
                   .sort_values(ascending=False).reset_index())
    kategori_df.columns = ["kategori", "pendapatan"]
    kategori_df["kategori"] = kategori_df["kategori"].astype(str)
    kategori_df["persen"] = kategori_df["pendapatan"] / total_pembanding * 100 if total_pembanding else 0
    return kategori_df


def hitung_peta(df):
    """Persen pesanan terlambat per negara bagian dan rata-rata nasional dari data terfilter."""
    pesanan_df = ke_level_pesanan(df)
    negara_df = pesanan_df.groupby("customer_state", observed=True).agg(
        order_count=("order_id", "nunique"), late_count=("is_late", "sum")).reset_index()
    negara_df["customer_state"] = negara_df["customer_state"].astype(str)
    negara_df["late_pct"] = negara_df["late_count"] / negara_df["order_count"] * 100

    total_pesanan = negara_df["order_count"].sum()
    rata_nasional = negara_df["late_count"].sum() / total_pesanan * 100 if total_pesanan else None
    return negara_df, rata_nasional


def ambil_top5(negara_df):
    """5 negara bagian paling terlambat dengan minimal 100 pesanan (sama dengan Q3)."""
    layak = negara_df[negara_df["order_count"] >= MIN_PESANAN]
    return layak.sort_values(by="late_pct", ascending=False).head(5)


def hitung_skor(df):
    """Rata-rata skor ulasan per kelompok keterlambatan dan selisihnya dengan Tepat waktu."""
    ulasan_df = ke_level_pesanan(df).dropna(subset=["review_score"])
    skor_df = ulasan_df.groupby("delay_status", observed=True)["review_score"].agg(["mean", "count"])
    skor_df.index = skor_df.index.astype(str)
    skor_df = skor_df.reindex(URUTAN_KELOMPOK)
    skor_df.columns = ["skor_rata", "jumlah_ulasan"]
    skor_df["jumlah_ulasan"] = skor_df["jumlah_ulasan"].fillna(0).astype(int)

    skor_tepat_waktu = skor_df.loc["Tepat waktu", "skor_rata"]
    skor_df["turun"] = skor_tepat_waktu - skor_df["skor_rata"]
    skor_df["turun_persen"] = skor_df["turun"] / skor_tepat_waktu * 100
    return skor_df.rename_axis("kelompok").reset_index()


def hitung_rfm(df, df_pembanding, segmen):
    """Jumlah pelanggan dan pendapatan per segmen RFM pada data terfilter.

    Persentase dihitung terhadap df_pembanding (filter periode dan kategori tanpa filter
    segmen), agar segmen yang dipilih tidak selalu 100%.
    """
    daftar = URUTAN_SEGMEN if segmen == "Semua" else [segmen]
    segmen_df = df.groupby("segment", observed=True).agg(
        jumlah_pelanggan=("customer_unique_id", "nunique"), pendapatan=("price", "sum"))
    segmen_df.index = segmen_df.index.astype(str)
    segmen_df = segmen_df.reindex(daftar, fill_value=0)

    total_pelanggan = df_pembanding["customer_unique_id"].nunique()
    total_pendapatan = df_pembanding["price"].sum()
    segmen_df["persen_pelanggan"] = segmen_df["jumlah_pelanggan"] / total_pelanggan * 100 if total_pelanggan else 0
    segmen_df["persen_pendapatan"] = segmen_df["pendapatan"] / total_pendapatan * 100 if total_pendapatan else 0
    return segmen_df.rename_axis("segmen").reset_index()


def hitung_semua(data, dari, sampai, kategori, segmen):
    """Menghitung semua isi dashboard dari satu himpunan data terfilter."""
    df = terapkan_filter(data, dari, sampai, kategori, segmen)
    tanpa_kategori = terapkan_filter(data, dari, sampai, "Semua", segmen)
    tanpa_segmen = terapkan_filter(data, dari, sampai, kategori, "Semua")
    negara_df, rata_nasional = hitung_peta(df)
    return {
        "kpi": hitung_kpi(df),
        "tren": hitung_tren(df, dari, sampai),
        "kategori": hitung_kategori(df, tanpa_kategori["price"].sum()),
        "negara": negara_df,
        "rata_nasional": rata_nasional,
        "top5": ambil_top5(negara_df),
        "skor": hitung_skor(df),
        "rfm": hitung_rfm(df, tanpa_segmen, segmen),
    }


@st.cache_data
def hitung_dashboard(dari, sampai, kategori, segmen):
    """Versi ber-cache dari hitung_semua untuk dipakai aplikasi."""
    return hitung_semua(muat_data(), dari, sampai, kategori, segmen)


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


def buat_grafik_kategori(kategori_df, warna):
    top10 = kategori_df.head(10)
    # tiga kategori teratas disorot biru pekat, sisanya lebih redup
    warna_batang = [warna["biru"] if i < 3 else warna["biru_redup"] for i in range(len(top10))]
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
    # rentang tetap 10 baris, agar tebal batang sama walau hanya satu kategori yang tampil
    fig.update_yaxes(range=[9.5, -0.5], showgrid=False, tickfont=dict(color=warna["teks"]))
    return fig


def buat_grafik_peta(peta, negara_df, nama, warna):
    semua_kode = [f["properties"]["sigla"] for f in peta["features"]]
    data = negara_df[negara_df["customer_state"].isin(semua_kode)]
    tanpa_data = [k for k in semua_kode if k not in set(data["customer_state"])]
    hover = [[nama.get(k, k), format_persen(p), format_angka(t), format_angka(n),
              "" if n >= MIN_PESANAN else f"<br><i>Kurang dari {MIN_PESANAN} pesanan, tidak diperingkat</i>"]
             for k, p, t, n in zip(data["customer_state"], data["late_pct"], data["late_count"], data["order_count"])]

    fig = go.Figure()
    # negara bagian tanpa pesanan pada filter ini diberi warna abu-abu muda
    if tanpa_data:
        fig.add_trace(go.Choropleth(
            geojson=peta, featureidkey="properties.sigla", locations=tanpa_data, z=[0] * len(tanpa_data),
            colorscale=[[0, warna["tanpa_data"]], [1, warna["tanpa_data"]]], showscale=False,
            marker=dict(line=dict(color=warna["tepi_peta"], width=0.6)),
            customdata=[nama.get(k, k) for k in tanpa_data],
            hovertemplate="<b>%{location} · %{customdata}</b><br>Tidak ada pesanan<extra></extra>",
        ))
    fig.add_trace(go.Choropleth(
        geojson=peta, featureidkey="properties.sigla", locations=data["customer_state"], z=data["late_pct"],
        colorscale="Purples", zmin=0, zmax=BATAS_WARNA_PETA,
        marker=dict(line=dict(color=warna["tepi_peta"], width=0.6)), customdata=hover,
        hovertemplate=("<b>%{location} · %{customdata[0]}</b><br>Terlambat: %{customdata[1]}"
                       "<br>%{customdata[2]} dari %{customdata[3]} pesanan%{customdata[4]}<extra></extra>"),
        colorbar=dict(title=dict(text="Terlambat", font=dict(color=warna["redup"], size=12)),
                      ticksuffix="%", tickfont=dict(color=warna["redup"]), thickness=12, len=0.75, outlinewidth=0),
    ))

    tata_letak_dasar(fig, warna, tinggi=440)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), dragmode=False)
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)", projection_type="mercator")
    return fig


def buat_grafik_top5(top5, rata_nasional, nama, warna):
    label_y = [f"{k} · {nama.get(k, k)}" for k in top5["customer_state"]]
    hover = [[format_persen(p), format_angka(t), format_angka(n)]
             for p, t, n in zip(top5["late_pct"], top5["late_count"], top5["order_count"])]

    fig = go.Figure(go.Bar(
        x=top5["late_pct"], y=label_y, orientation="h", marker=dict(color=warna["ungu"]),
        text=[format_persen(p) for p in top5["late_pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=warna["teks"], size=12), customdata=hover,
        hovertemplate="<b>%{y}</b><br>Terlambat: %{customdata[0]}<br>%{customdata[1]} dari %{customdata[2]} pesanan<extra></extra>",
    ))
    fig.add_vline(x=rata_nasional, line=dict(color=warna["redup"], dash="dash", width=1.5))
    fig.add_annotation(x=rata_nasional, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                       text=f"Rata-rata nasional {format_persen(rata_nasional)}",
                       font=dict(color=warna["redup"], size=12))

    batas = max(top5["late_pct"].max(), rata_nasional, 1) * 1.25
    tata_letak_dasar(fig, warna, tinggi=440)
    fig.update_layout(margin=dict(l=8, r=24, t=40, b=8), bargap=0.35)
    fig.update_xaxes(range=[0, batas], ticksuffix="%", title_text="Pesanan terlambat (%)")
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=warna["teks"]))
    return fig


def buat_grafik_skor(skor_df, warna):
    warna_kelompok = [warna["biru"]] + warna["ungu_gradasi"]
    teks = []
    for baris in skor_df.itertuples():
        if pd.isna(baris.skor_rata):
            teks.append("<b>-</b>")  # kelompok tanpa ulasan
            continue
        label = f"<b>{format_angka(baris.skor_rata, 2)}</b>"
        if baris.kelompok != "Tepat waktu" and pd.notna(baris.turun):
            label += f"<br>turun {format_angka(baris.turun, 2)} poin ({format_persen(baris.turun_persen, 1)})"
        teks.append(label)
    label_x = [f"{k}<br>(n = {format_angka(n)})" for k, n in zip(skor_df["kelompok"], skor_df["jumlah_ulasan"])]
    hover = ["-" if pd.isna(s) else format_angka(s, 2) for s in skor_df["skor_rata"]]

    fig = go.Figure(go.Bar(
        x=label_x, y=skor_df["skor_rata"].fillna(0), marker=dict(color=warna_kelompok),
        text=teks, textposition="outside", cliponaxis=False, textfont=dict(color=warna["teks"], size=12),
        customdata=hover, hovertemplate="<b>%{x}</b><br>Rata-rata skor: %{customdata}<extra></extra>",
    ))
    tata_letak_dasar(fig, warna, tinggi=400)
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(showgrid=False, tickfont=dict(color=warna["teks"]))
    fig.update_yaxes(range=[0, 6], tickvals=[0, 1, 2, 3, 4, 5], title_text="Rata-rata skor ulasan (1 sampai 5)")
    return fig


def buat_grafik_segmen(segmen_df, warna):
    # bila hanya satu segmen, lebar batang dibatasi agar tidak memenuhi grafik
    lebar = 0.12 if len(segmen_df) == 1 else None
    fig = go.Figure()
    for kolom, judul, kode_warna in [("persen_pelanggan", "Porsi pelanggan", warna["biru"]),
                                     ("persen_pendapatan", "Porsi pendapatan", warna["ungu"])]:
        fig.add_trace(go.Bar(
            name=judul, x=segmen_df["segmen"], y=segmen_df[kolom], marker=dict(color=kode_warna), width=lebar,
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


def takarir_kosong():
    return kotak_takarir("Tidak ada data.", PESAN_KOSONG)


def buat_takarir_tren(tren):
    if tren.empty or tren["pendapatan"].sum() == 0:
        return takarir_kosong()
    i = int(tren["pendapatan"].idxmax())
    puncak = tren["pendapatan"][i]
    lead = f"Puncak pada {label_bulan(tren['bulan'][i], panjang=True)}: {format_rp(puncak)}."
    if i == 0:
        penjelas = "Puncak berada di bulan pertama rentang, sehingga pembanding bulan sebelumnya tidak tersedia."
    elif tren["pendapatan"][i - 1] == 0:
        penjelas = "Bulan sebelumnya tidak memiliki penjualan, sehingga pertumbuhan tidak dapat dihitung."
    else:
        tumbuh = (puncak / tren["pendapatan"][i - 1] - 1) * 100
        arah = "Naik" if tumbuh >= 0 else "Turun"
        penjelas = f"{arah} {format_persen(abs(tumbuh), 1)} dibanding bulan sebelumnya."
    return kotak_takarir(lead, penjelas, "Aksi: siapkan stok dan kampanye menjelang bulan dengan permintaan tertinggi.")


def buat_takarir_kategori(kategori_df, kategori_terpilih):
    if kategori_df.empty or kategori_df["pendapatan"].sum() == 0:
        return takarir_kosong()
    aksi = "Aksi: prioritaskan stok dan promosi untuk kategori ini."

    if kategori_terpilih not in ("Semua", "Lainnya"):
        baris = kategori_df.iloc[0]
        lead = f"Kategori {html.escape(baris['kategori'])}"
        penjelas = (f"menyumbang {format_persen(baris['persen'], 1)} ({format_rp(baris['pendapatan'])}) dari pendapatan "
                    f"pada periode dan segmen terpilih.")
        return kotak_takarir(lead, penjelas, aksi)

    teratas = kategori_df.head(3)
    nama = html.escape(", ".join(teratas["kategori"]))
    jumlah = ANGKA_KATA.get(len(teratas), str(len(teratas)))
    if kategori_terpilih == "Lainnya":
        lead = f"Kategori di luar 10 teratas menyumbang {format_persen(kategori_df['persen'].sum(), 1)}"
        penjelas = (f"dari pendapatan pada periode dan segmen terpilih. {jumlah} terbesar di kelompok ini: {nama}, "
                    f"dengan {format_persen(teratas['persen'].sum(), 1)}.")
    else:
        lead = f"{jumlah} kategori teratas ({nama})"
        penjelas = f"menyumbang {format_persen(teratas['persen'].sum(), 1)} dari pendapatan pada filter ini."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_peta(negara_df, rata_nasional, nama):
    if negara_df.empty:
        return takarir_kosong()
    layak = negara_df[negara_df["order_count"] >= MIN_PESANAN]
    if layak.empty:
        return kotak_takarir("Data belum cukup.",
                             f"Belum ada negara bagian dengan minimal {MIN_PESANAN} pesanan pada filter ini. "
                             f"Rata-rata seluruh pesanan terfilter {format_persen(rata_nasional)}.")
    teratas = layak.sort_values(by="late_pct", ascending=False).iloc[0]
    kode = teratas["customer_state"]
    lead = f"{kode} ({html.escape(nama.get(kode, kode))}) paling sering terlambat: {format_persen(teratas['late_pct'])}."
    penjelas = f"Rata-rata nasional {format_persen(rata_nasional)}; warna paling gelap menandai keterlambatan tertinggi."
    aksi = "Aksi: evaluasi rute dan mitra pengiriman, atau sesuaikan estimasi tiba, di wilayah berwarna gelap."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_top5(top5, rata_nasional):
    if rata_nasional is None:
        return takarir_kosong()
    if top5.empty:
        return kotak_takarir("Data belum cukup.",
                             f"Belum ada negara bagian dengan minimal {MIN_PESANAN} pesanan pada filter ini.")
    kode = top5["customer_state"].tolist()
    selisih = top5["late_pct"] - rata_nasional

    def bertanda(nilai):
        return ("+" if nilai >= 0 else "-") + format_angka(abs(nilai), 2)

    lead = f"{ANGKA_KATA[len(kode)]} negara bagian teratas: {gabung_daftar(kode)}."
    penjelas = (f"Persentase terlambatnya {format_persen(top5['late_pct'].min())} sampai "
                f"{format_persen(top5['late_pct'].max())}, atau {bertanda(selisih.min())} sampai "
                f"{bertanda(selisih.max())} poin persen dibanding rata-rata nasional ({format_persen(rata_nasional)}).")
    if len(kode) < 5:
        penjelas += f" Hanya {len(kode)} negara bagian yang memiliki minimal {MIN_PESANAN} pesanan pada filter ini."
    aksi = "Aksi: dahulukan evaluasi rute dan mitra pengiriman, atau sesuaikan estimasi tiba, di negara bagian ini."
    return kotak_takarir(lead, penjelas, aksi)


def buat_takarir_skor(skor_df):
    data = skor_df.set_index("kelompok")
    tepat, lambat = data.loc["Tepat waktu"], data.loc["Terlambat > 7 hari"]
    if data["skor_rata"].isna().all():
        return takarir_kosong()
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


def rata_belanja(segmen_df):
    pelanggan = segmen_df["jumlah_pelanggan"].sum()
    return segmen_df["pendapatan"].sum() / pelanggan if pelanggan else None


def buat_takarir_rfm(segmen_df, segmen_terpilih):
    if segmen_df["jumlah_pelanggan"].sum() == 0:
        return takarir_kosong()
    aksi = ("Aksi: pertahankan segmen Aktif dengan program loyalitas dan aktifkan kembali segmen Pasif "
            "lewat kampanye win-back.")

    if segmen_terpilih != "Semua":
        baris = segmen_df.iloc[0]
        lead = (f"Segmen {segmen_terpilih}: {format_persen(baris['persen_pelanggan'], 1)} pelanggan, "
                f"{format_persen(baris['persen_pendapatan'], 1)} pendapatan.")
        penjelas = (f"Sebanyak {format_angka(baris['jumlah_pelanggan'])} pelanggan dengan rata-rata belanja "
                    f"{format_rp(rata_belanja(segmen_df))} per pelanggan pada periode dan kategori terpilih.")
        return kotak_takarir(lead, penjelas, aksi)

    tinggi = segmen_df[segmen_df["segmen"].str.contains("Tinggi")]
    rendah = segmen_df[segmen_df["segmen"].str.contains("Rendah")]
    lead = (f"Segmen Bernilai Tinggi: {format_persen(tinggi['persen_pelanggan'].sum(), 1)} pelanggan, "
            f"{format_persen(tinggi['persen_pendapatan'].sum(), 1)} pendapatan.")
    rata_tinggi, rata_rendah = rata_belanja(tinggi), rata_belanja(rendah)
    if rata_tinggi is not None and rata_rendah is not None:
        penjelas = (f"Rata-rata belanja pelanggan Bernilai Tinggi ({format_rp(rata_tinggi)}) jauh di atas "
                    f"Bernilai Rendah ({format_rp(rata_rendah)}).")
    else:
        penjelas = "Salah satu kelompok segmen tidak memiliki pelanggan pada filter ini."
    return kotak_takarir(lead, penjelas, aksi)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def buat_css(w):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
/* warna latar juga diatur di sini, agar tetap sama walau dijalankan dari folder lain (tanpa config.toml) */
.stApp {{ background: {w["latar"]}; }}
[data-testid="stSidebar"] {{ background: {w["kartu"]}; }}
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
@media (max-width: 1400px) {{ .kpi .nilai {{ font-size: 1.25rem; }} .kpi {{ padding: 14px 13px 12px; }} }}
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


def nilai_default():
    bulan = daftar_bulan(muat_data())
    return {"dari": bulan[0], "sampai": bulan[-1], "kategori": "Semua", "segmen": "Semua"}


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


def pilih_segmen(nama):
    """Klik kartu segmen memilih segmen itu; klik lagi untuk membatalkan."""
    st.session_state.segmen = "Semua" if st.session_state.segmen == nama else nama


# ---------------------------------------------------------------------------
# Tampilan
# ---------------------------------------------------------------------------
def tampilkan_sidebar():
    data = muat_data()
    sb = st.sidebar
    sb.markdown(f'<div class="logo olist"><div class="ikon">{IKON_LOGO}</div><div><div class="nama">Olist Insights</div>'
                f'<div class="sub">Analisis pesanan terkirim</div></div></div>', unsafe_allow_html=True)
    sb.markdown('<div class="label-filter olist">FILTER</div>', unsafe_allow_html=True)

    sb.markdown('<div class="label-periode olist">Periode pembelian</div>', unsafe_allow_html=True)
    kiri, kanan = sb.columns(2)
    kiri.selectbox("Dari", daftar_bulan(data), key="dari", format_func=label_bulan, on_change=cek_urutan_periode)
    kanan.selectbox("Sampai", daftar_bulan(data), key="sampai", format_func=label_bulan, on_change=cek_urutan_periode)
    if st.session_state.pop("periode_ditukar", False):
        sb.warning("Bulan \"Dari\" lebih besar dari \"Sampai\", jadi keduanya ditukar otomatis.")

    sb.selectbox("Kategori produk", ["Semua"] + kategori_teratas(data) + ["Lainnya"], key="kategori")
    sb.selectbox("Segmen pelanggan (RFM)", ["Semua"] + URUTAN_SEGMEN, key="segmen")
    sb.button("Reset semua filter", key="tombol_reset", on_click=reset_filter, width="stretch")


def tampilkan_chip(f):
    bulan = daftar_bulan(muat_data())
    chip = []
    if (f["dari"], f["sampai"]) != (bulan[0], bulan[-1]):
        chip.append(f"Periode: {label_bulan(f['dari'])} sampai {label_bulan(f['sampai'])}")
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


def tampilkan_grafik(fig, kunci):
    st.plotly_chart(fig, width="stretch", theme=None, config=KONFIG_GRAFIK, key=kunci)


def tampilkan_tab_pendapatan(hasil, f, warna):
    kiri, kanan = st.columns([1.1, 1], gap="medium")

    with kiri.container(key="kartu_tren"):
        judul_kartu("Tren Pendapatan Bulanan")
        tren = hasil["tren"]
        if tren["pendapatan"].sum() == 0:
            st.info(PESAN_KOSONG)
        else:
            tampilkan_grafik(buat_grafik_tren(tren, warna), "grafik_tren")
        takarir(buat_takarir_tren(tren))

    with kanan.container(key="kartu_kategori"):
        judul_kartu("Pendapatan per Kategori Produk")
        kategori_df = hasil["kategori"]
        if kategori_df.empty:
            st.info(PESAN_KOSONG)
        else:
            tampilkan_grafik(buat_grafik_kategori(kategori_df, warna), "grafik_kategori")
        takarir(buat_takarir_kategori(kategori_df, f["kategori"]))


def tampilkan_tab_pengiriman(hasil, peta, nama, warna):
    negara_df, rata_nasional, top5 = hasil["negara"], hasil["rata_nasional"], hasil["top5"]
    kiri, kanan = st.columns([1.15, 1], gap="medium")

    with kiri.container(key="kartu_peta"):
        judul_kartu("Peta Keterlambatan per Negara Bagian")
        if peta is None:
            st.warning("File peta tidak ditemukan dan gagal diunduh. Periksa koneksi internet lalu muat ulang halaman.")
        elif negara_df.empty:
            st.info(PESAN_KOSONG)
        else:
            tampilkan_grafik(buat_grafik_peta(peta, negara_df, nama, warna), "grafik_peta")
        takarir(buat_takarir_peta(negara_df, rata_nasional, nama))

    with kanan.container(key="kartu_top5"):
        judul_kartu("5 Negara Bagian Paling Terlambat")
        if top5.empty:
            st.info(PESAN_KOSONG if negara_df.empty else
                    f"Belum ada negara bagian dengan minimal {MIN_PESANAN} pesanan pada filter ini.")
        else:
            tampilkan_grafik(buat_grafik_top5(top5, rata_nasional, nama, warna), "grafik_top5")
        takarir(buat_takarir_top5(top5, rata_nasional))

    with st.container(key="kartu_skor"):
        judul_kartu("Penurunan Skor Ulasan pada Pesanan Terlambat")
        skor_df = hasil["skor"]
        if skor_df["skor_rata"].isna().all():
            st.info(PESAN_KOSONG)
        else:
            tampilkan_grafik(buat_grafik_skor(skor_df, warna), "grafik_skor")
        takarir(buat_takarir_skor(skor_df))


def tampilkan_tab_pelanggan(hasil, f, warna):
    segmen_df = hasil["rfm"]

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
            tampilkan_grafik(buat_grafik_segmen(segmen_df, warna), "grafik_segmen")
        takarir(buat_takarir_rfm(segmen_df, f["segmen"]))


def main():
    st.set_page_config(page_title="Dashboard Olist", page_icon="📊", layout="wide")
    warna = WARNA
    st.markdown(buat_css(warna), unsafe_allow_html=True)

    peta = muat_peta()
    nama = nama_negara_bagian(peta)
    siapkan_session_state()
    tampilkan_sidebar()
    f = {k: st.session_state[k] for k in ["dari", "sampai", "kategori", "segmen"]}

    st.markdown('<div class="olist"><h1 class="judul-halaman">Dashboard Analisis E-Commerce</h1>'
                '<p class="subjudul-halaman">Pendapatan, pengiriman, kepuasan, dan segmen pelanggan dalam satu tampilan.</p></div>',
                unsafe_allow_html=True)
    tampilkan_chip(f)

    hasil = hitung_dashboard(f["dari"], f["sampai"], f["kategori"], f["segmen"])
    tampilkan_kpi(hasil["kpi"], f["kategori"])
    if hasil["kpi"]["jumlah_pesanan"] == 0:
        st.info(PESAN_KOSONG)

    tab_pendapatan, tab_pengiriman, tab_pelanggan = st.tabs(
        ["Pendapatan", "Pengiriman dan Ulasan", "Pelanggan (RFM)"], key="tab_aktif")
    with tab_pendapatan:
        tampilkan_tab_pendapatan(hasil, f, warna)
    with tab_pengiriman:
        tampilkan_tab_pengiriman(hasil, peta, nama, warna)
    with tab_pelanggan:
        tampilkan_tab_pelanggan(hasil, f, warna)


if __name__ == "__main__":
    main()
