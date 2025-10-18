# 🏀 All-Ahraga — Kelompok 4 PBP E

## Nama-nama Anggota Kelompok
- **Amadio Juno Trisanto**  
- **Felicia Evangeline Mubarun**  
- **Ahsan Parvez**  
- **Muhammad Razka Faltasyah**
- **Mafaza Ananda Rahman**

---

## Deskripsi Aplikasi

All-ahraga adalah aplikasi web berbasis Django yang menyediakan layanan serba ada untuk kebutuhan olahraga. Mulai dari booking lapangan, sewa alat olahraga, hingga pesan sesi coaching/pelatihan olahraga.

Aplikasi ini dibuat untuk mempermudah masyarakat dalam mengakses layanan olahraga tanpa perlu berpindah-pindah platform. Pengguna dapat mencari lapangan olahraga di sekitar mereka, menyewa peralatan yang dibutuhkan, atau memesan pelatih profesional hanya dalam satu website.

Dengan All-ahraga, semua kebutuhan olahraga dapat terpenuhi secara praktis, efisien, dan terintegrasi dalam satu tempat.

---

### Cerita Singkat Penggunaan

Seorang pengguna ingin bermain futsal dengan teman-temannya namun kesulitan mencari lapangan kosong pada waktu tertentu.  
Ia membuka **All-Ahraga**, memilih jenis olahraga *Futsal*, melihat daftar lapangan yang tersedia di sekitar lokasi, lalu melakukan pemesanan.  
Jika ingin berlatih tenis, pengguna juga bisa memesan pelatih (*coach*) yang tersedia di area tersebut.


---

### Kebermanfaatan
- Mempermudah pengguna menemukan dan menyewa lapangan olahraga.  
- Meningkatkan pendapatan bagi pengelola lapangan.  
- Memberikan peluang bagi pelatih untuk memasarkan jasanya.  
- Mendorong gaya hidup sehat dan aktif melalui kemudahan akses fasilitas olahraga.
- Memberikan pengalaman olahraga yang efisien, mudah diakses, dan terpercaya.

---

## Daftar Modul yang Akan Diimplementasikan

1. **Modul Autentikasi Pengguna**  
   - Register, login, dan logout (untuk user dan admin).

2. **Modul Coaching**  
   - Daftar pelatih berdasarkan olahraga dan rating.  
   - Pemesanan sesi latihan dengan jadwal fleksibel.

3. **Modul Manajemen Lapangan (Admin/Pengelola)**  
   - CRUD data lapangan, harga, dan jadwal ketersediaan.

4. **Modul Manajemen Pelatih (Coach)**  
   - CRUD profil pelatih, jadwal, dan tarif.

5. **Modul Review & Rating**  
   - Pengguna dapat memberikan ulasan terhadap lapangan dan pelatih.

6. **Modul Pembayaran (Simulasi 50:50)**  
   - Simulasi pembayaran seperti *Bayar di Tempat* atau *Transfer Manual*.

---

## Sumber Initial Dataset Kategori Utama Produk

Dataset awal untuk kategori utama produk (lapangan tenis, padel, futsal, dll.) dikumpulkan dari berbagai sumber dengan validasi manual.

**Sumber utama meliputi:**
- [Ayo Indonesia](https://ayo.co.id/venues): Daftar lapangan futsal, tenis, padel, dan badminton di kota besar.  
- [Gelora.id](https://gelora.id/venue): Listing venue olahraga (fokus sepak bola, basket, dan tenis).  
- [G-Sports.id](https://g-sports.id): Data padel court
- **Google Maps**: Referensi lokasi dan data tambahan lapangan olahraga.

https://docs.google.com/spreadsheets/d/1t_XP8-ce49bFA8lb_G9DQBf5znkMyC4y4aohg_ZZn74/edit?usp=sharing

---

## Role atau Peran Pengguna

| Role | Deskripsi |
|------|------------|
| **Visitor** | Dapat melihat daftar lapangan, alat, dan pelatih, tetapi belum bisa melakukan booking. |
| **Customer** | Pengguna yang mencari, memesan, dan membayar lapangan atau coaching. Dapat mengakses dashboard pribadi untuk riwayat dan ulasan. |
| **Coach** | Pelatih terverifikasi yang menawarkan sesi privat/grup. Dapat mengelola profil, jadwal, dan rating. |
| **Venue Owner** | Pemilik lapangan yang mengelola listing, ketersediaan jadwal, dan laporan pendapatan. |
| **Admin** | Tim internal yang mengelola platform, melakukan verifikasi user/venue, moderasi konten, dan memantau laporan global. |

---

## Tautan Deployment PWS dan Link Design
- **Link PWS:**  
  https://pbp.cs.ui.ac.id/muhammad.razka41/allahraga

- **Link Design (Figma):**  
  https://www.figma.com/design/5QlFEjv6Icwo8CMqN7bh0C/Design-All-ahraga?node-id=0-1&t=kbMu2oTsx7oVALKj-1