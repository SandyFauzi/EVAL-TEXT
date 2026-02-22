const express = require("express");
const path = require("path");
const { spawn } = require("child_process");

const app = express();
const PORT = process.env.PORT || 3000;

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

app.use(express.json({ limit: "1mb" }));
app.use(express.urlencoded({ extended: true }));

// ✅ CSS/JS
app.use("/public", express.static(path.join(__dirname, "public")));

const TEXT_TYPES = [
  { key: "naratif", name: "Teks Naratif", desc: "Judul, Orientasi, Komplikasi, Resolusi, Koda." },
  { key: "deskriptif", name: "Teks Deskriptif", desc: "Judul, Identifikasi, Deskripsi bagian." },
  { key: "fiksi", name: "Teks Fiksi", desc: "Judul, Orientasi, Rangkaian peristiwa, Klimaks, Resolusi, Amanat." },
  { key: "nonfiksi", name: "Teks Nonfiksi", desc: "Judul, Pendahuluan, Isi, Penutup." },
  { key: "prosedur", name: "Teks Prosedur", desc: "Judul, Tujuan, Alat dan bahan, Langkah-langkah, Penutup." },
  { key: "surat_pribadi", name: "Teks Surat Pribadi", desc: "Tempat/tanggal, Salam pembuka, Isi surat, Salam penutup, Nama pengirim." },
  { key: "eksposisi", name: "Teks Eksposisi", desc: "Judul, Tesis, Argumentasi, Penegasan ulang." },
  { key: "pengumuman", name: "Teks Pengumuman", desc: "Judul, Isi pengumuman, Waktu & tempat, Nama pembuat." },
  { key: "surel", name: "Surel (Email)", desc: "Email tujuan, Subjek, Salam pembuka, Isi email, Salam penutup, Nama pengirim." },
  { key: "informatif", name: "Teks Informatif", desc: "Judul, Pendahuluan, Isi informasi, Penutup." },
  { key: "eksplanasi", name: "Teks Eksplanasi", desc: "Judul, Pernyataan umum, Deretan penjelas, Penutup." },
  { key: "persuasi", name: "Teks Persuasi", desc: "Judul, Pengenalan isu, Rangkaian argumen, Ajakan, Penegasan kembali." },
  { key: "puisi", name: "Puisi", desc: "Judul, Larik & bait, Rima/irama, Amanat." },
  { key: "biografi", name: "Teks Biografi", desc: "Judul, Orientasi, Peristiwa penting, Reorientasi." }
];

function pickPythonCmd() {
  if (process.env.PYTHON && process.env.PYTHON.trim()) return process.env.PYTHON.trim();
  return process.platform === "win32" ? "python" : "python3";
}

function runPython({ type, text }) {
  return new Promise((resolve, reject) => {
    const py = pickPythonCmd();
    const scriptPath = path.join(__dirname, "python", "poem_eval.py"); // ✅ tetap poem_eval.py
    const child = spawn(py, [scriptPath], { stdio: ["pipe", "pipe", "pipe"] });

    let out = "";
    let err = "";

    child.stdout.on("data", (d) => (out += d.toString()));
    child.stderr.on("data", (d) => (err += d.toString()));

    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(err || out || `Python exit ${code}`));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(new Error("Output python bukan JSON. Output: " + (out || err)));
      }
    });

    child.stdin.write(JSON.stringify({ type, text }));
    child.stdin.end();
  });
}

// Pages
app.get("/", (req, res) => res.render("index", { TEXT_TYPES }));

app.get("/evaluate/:type", (req, res) => {
  const type = String(req.params.type || "").trim();
  const item = TEXT_TYPES.find((t) => t.key === type) || TEXT_TYPES[0];
  res.render("evaluate", { item, TEXT_TYPES });
});

// API evaluate (semua tipe lewat Python)
app.post("/api/evaluate", async (req, res) => {
  try {
    const type = String(req.body.type || "").trim();
    const text = String(req.body.text || "");

    if (!type) return res.status(400).json({ ok: false, message: "Tipe teks belum dikirim." });
    if (!text.trim()) return res.status(400).json({ ok: false, message: "Teks masih kosong." });
    if (text.length > 20000) return res.status(400).json({ ok: false, message: "Teks terlalu panjang (maks 20.000 karakter)." });

    const result = await runPython({ type, text });
    return res.json(result);
  } catch (e) {
    return res.status(500).json({ ok: false, message: e.message || "Server error" });
  }
});

app.listen(PORT, () => {
  console.log(`Server: http://localhost:${PORT}`);
  console.log(`Cek CSS: http://localhost:${PORT}/public/css/style.css`);
});
