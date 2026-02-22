(function () {
  const btn = document.getElementById("btnNilai");
  if (!btn) return;

  const textInput = document.getElementById("textInput");
  const fileInput = document.getElementById("fileInput");
  const statusEl = document.getElementById("status");

  const scoreEl = document.getElementById("score");
  const barEl = document.getElementById("bar");

  const benarEl = document.getElementById("benar");
  const kurangEl = document.getElementById("kurang");
  const perluEl = document.getElementById("perlu");
  const autoFixEl = document.getElementById("autoFix");

  const strukturBox = document.getElementById("strukturBox");
  const breakdownBox = document.getElementById("breakdownBox");

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg || "";
  }

  fileInput?.addEventListener("change", async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const text = await f.text();
    textInput.value = text;
  });

  function renderList(ul, items) {
    ul.innerHTML = "";
    (items || []).forEach((it) => {
      const li = document.createElement("li");
      li.textContent = it;
      ul.appendChild(li);
    });
  }

  function renderChecklist(target, checklist) {
    if (!target) return;
    target.innerHTML = "";

    if (!Array.isArray(checklist) || checklist.length === 0) {
      target.textContent = "Tidak ada checklist.";
      return;
    }

    checklist.forEach((it) => {
      const row = document.createElement("div");
      row.className = "checkRow";

      const mark = document.createElement("span");
      mark.className = "checkMark " + (it.ok ? "ok" : "no");
      mark.textContent = it.ok ? "✓" : "✗";

      const label = document.createElement("span");
      label.className = "checkLabel";
      label.textContent = it.label;

      const note = document.createElement("span");
      note.className = "checkNote";
      note.textContent = it.note || "";

      row.appendChild(mark);
      row.appendChild(label);
      row.appendChild(note);
      target.appendChild(row);
    });
  }

  function renderBreakdown(target, b) {
    if (!target) return;
    target.innerHTML = "";

    if (!b || typeof b !== "object") {
      target.textContent = "Tidak ada rincian.";
      return;
    }

    const rub = b.rubrik || {};
    const sub = b.subscores || {};

    const pre = document.createElement("pre");
    pre.textContent =
      `Struktur: ${sub.struktur ?? "-"} / ${rub.struktur ?? "-"}\n` +
      `Bahasa: ${sub.bahasa ?? "-"} / ${rub.bahasa ?? "-"}\n` +
      `Kejelasan: ${sub.kejelasan ?? "-"} / ${rub.kejelasan ?? "-"}\n` +
      `Kreativitas: ${sub.kreativitas ?? "-"} / ${rub.kreativitas ?? "-"}\n` +
      `Kerapihan: ${sub.kerapihan ?? "-"} / ${rub.kerapihan ?? "-"}\n` +
      (b.kbbi_loaded === false ? `\n⚠️ KBBI CSV belum terbaca. Pastikan python/kbbi_wordlist.csv ada.` : "");

    target.appendChild(pre);
  }

  btn.addEventListener("click", async () => {
    const type = btn.dataset.type;
    const text = (textInput.value || "").trim();

    setStatus("Memproses penilaian...");
    btn.disabled = true;

    try {
      const resp = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, text })
      });

      const data = await resp.json();
      if (!resp.ok || data.ok === false) throw new Error(data.message || "Gagal memproses.");

      const score = Number(data.score ?? 0);
      scoreEl.textContent = Number.isFinite(score) ? score : "-";
      barEl.style.width = Math.max(0, Math.min(100, score)) + "%";

      renderList(benarEl, data.feedback?.benar || []);
      renderList(kurangEl, data.feedback?.kurang_tepat || []);
      renderList(perluEl, data.feedback?.perlu_diperbaiki || []);
      autoFixEl.value = data.auto_fix?.text || "";

      renderChecklist(strukturBox, data.breakdown?.structure?.checklist || []);
      renderBreakdown(breakdownBox, data.breakdown?.meta || {});

      setStatus("Selesai ✅");
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      btn.disabled = false;
    }
  });
})();
