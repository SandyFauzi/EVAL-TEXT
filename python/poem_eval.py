import sys, json, re, os, csv
from collections import Counter

# =========================================================
# PATHS
# =========================================================
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KBBI_CSV = os.path.join(THIS_DIR, "kbbi_wordlist.csv")
EYD_DB_TXT = os.path.join(THIS_DIR, "eyd_db.txt")

# =========================================================
# LOAD KBBI CSV (1 kolom: kata)
# =========================================================
KBBI_WORDS = set()
KBBI_LOADED = False

def _clean_cell(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.lstrip("\ufeff")  # BOM
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return s

def load_kbbi():
    global KBBI_WORDS, KBBI_LOADED
    if not os.path.exists(KBBI_CSV):
        KBBI_LOADED = False
        return
    try:
        with open(KBBI_CSV, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                w = _clean_cell(row[0])
                if not w or w == "kata":
                    continue
                if w.startswith("'") and w[1:].isalpha():
                    KBBI_WORDS.add(w[1:])
                KBBI_WORDS.add(w)
        KBBI_LOADED = len(KBBI_WORDS) > 1000
    except:
        KBBI_LOADED = False

load_kbbi()

# =========================================================
# LOAD EYD DB (JSON Lines)
# =========================================================
EYD_RULES = []
EYD_LOADED = False

def load_eyd_db():
    global EYD_RULES, EYD_LOADED
    rules = []
    if not os.path.exists(EYD_DB_TXT):
        EYD_RULES = []
        EYD_LOADED = False
        return
    try:
        with open(EYD_DB_TXT, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                ln = (line or "").strip()
                if not ln or ln.startswith("#"):
                    continue
                try:
                    obj = json.loads(ln)
                    if isinstance(obj, dict) and obj.get("id"):
                        rules.append(obj)
                except:
                    continue
        EYD_RULES = rules
        EYD_LOADED = len(EYD_RULES) > 0
    except:
        EYD_RULES = []
        EYD_LOADED = False

load_eyd_db()

# =========================================================
# UTIL
# =========================================================
VOWELS = set("aiueo")
WEIRD_SYMBOLS_RE = re.compile(r"[@#$%^&*_=\|~<>`]+")

# --- kata lokasi/arah untuk bedain "di rumah" vs "dikenal"
LOCATION_WORDS = {
    "rumah","sekolah","kelas","kantor","pasar","taman","halaman","lapangan","aula","perpustakaan","kantin",
    "jalan","gang","kota","desa","kampung","pantai","laut","sungai","gunung","hutan",
    "depan","belakang","samping","atas","bawah","dalam","luar",
    "sini","situ","sana",
}

def clamp(n, lo, hi):
    return lo if n < lo else hi if n > hi else n

def norm_space(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def get_lines(text: str):
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [ln.rstrip("\n") for ln in t.split("\n")]

def get_paragraphs(text: str):
    t = norm_space(text)
    if not t:
        return []
    parts = re.split(r"\n\s*\n+", t)
    return [p.strip() for p in parts if p.strip()]

def tokenize_words(text: str):
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)?|\d+", text)

def alpha_words(text: str):
    return [w for w in tokenize_words(text) if w.isalpha()]

def tokenize_alpha_with_spans(text: str):
    # token alpha + span untuk cek konteks (awal kalimat / nama)
    out = []
    for m in re.finditer(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)?", text):
        out.append((m.group(0), m.start(), m.end()))
    return out

def sentences(text: str):
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", t)
    return [p.strip() for p in parts if p.strip()]

def count_numbers(text: str):
    return len(re.findall(r"\b\d+([.,]\d+)?\b", text))

def count_bullets(text: str):
    return len(re.findall(r"(^|\n)\s*([-•]|(\d+[\.\)]))\s+", text))

def lexical_diversity(text: str):
    w = [x.lower() for x in alpha_words(text)]
    if not w:
        return 0.0
    return len(set(w)) / len(w)

def avg_sentence_len(text: str):
    ss = sentences(text)
    if not ss:
        return 0.0
    lens = [len([w for w in tokenize_words(s) if w.isalpha()]) for s in ss]
    return sum(lens) / len(lens) if lens else 0.0

def strip_pronoun_suffix(word: str) -> str:
    for suf in ("ku","mu","nya"):
        if word.endswith(suf) and len(word) > len(suf) + 2:
            return word[:-len(suf)]
    return word

def is_sentence_start(text: str, start_idx: int) -> bool:
    # cari karakter signifikan sebelum token
    i = start_idx - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    if i < 0:
        return True
    # awal setelah pemisah kalimat / baris
    return text[i] in ".!?…\n"

def is_probable_proper_noun(token: str, sent_start: bool, next_is_cap: bool) -> bool:
    # Akronim (semua kapital) dianggap valid, bukan proper noun, tapi juga jangan dicek KBBI
    if token.isupper() and 2 <= len(token) <= 6:
        return True

    if not token or len(token) < 2:
        return False
    if token[0].isupper() and not token.isupper():
        # kalau bukan awal kalimat -> sangat mungkin nama diri
        if not sent_start:
            return True
        # kalau awal kalimat: anggap nama diri jika diikuti token kapital (mis. "Bacharuddin Jusuf")
        if next_is_cap:
            return True
    return False

# =========================================================
# KBBI + MORFOLOGI SEDERHANA
# =========================================================
PREFIXES = [
    "memper","meng","meny","mem","men","ber","ter","per","pe","pen","pem","peng",
    "ke","se","di"
]
SUFFIXES = ["kan","i","an","nya","lah","kah","pun","ku","mu"]

def possible_roots(w: str):
    low = w.lower()
    yield low

    if "-" in low:
        parts = [p for p in low.split("-") if p]
        for p in parts:
            yield p

    for pre in PREFIXES:
        if low.startswith(pre) and len(low) > len(pre) + 2:
            yield low[len(pre):]

    for suf in SUFFIXES:
        if low.endswith(suf) and len(low) > len(suf) + 2:
            yield low[:-len(suf)]

    for pre in PREFIXES:
        if low.startswith(pre) and len(low) > len(pre) + 2:
            mid = low[len(pre):]
            for suf in SUFFIXES:
                if mid.endswith(suf) and len(mid) > len(suf) + 2:
                    yield mid[:-len(suf)]

def is_kbbi_word(w: str) -> bool:
    if not KBBI_LOADED:
        return True

    # inisial nama (mis. "J", "A") -> jangan dihitung non-KBBI
    if len(w) == 1 and w.isalpha() and w.isupper():
        return True

    low = w.lower()
    if low.isdigit():
        return True
    if w.upper() == w and 2 <= len(w) <= 6:
        return True
    for cand in possible_roots(low):
        if cand in KBBI_WORDS:
            return True
    return False

# =========================================================
# SLANG + "ASAL KETIK" + TANDA BACA ANEH
# =========================================================
SLANG_MAP = {
    "ga": "tidak", "gak": "tidak", "nggak": "tidak", "ngga": "tidak",
    "yg": "yang", "tdk": "tidak", "dgn": "dengan", "dr": "dari",
    "krn": "karena", "sm": "sama", "trus": "terus", "udh": "sudah",
    "udah": "sudah", "pengen": "ingin", "bgt": "sangat", "gmn": "bagaimana",
    "km": "kamu", "sy": "saya", "lo": "kamu", "gue": "saya", "dl": "dulu"
}
SLANG_SET = set(SLANG_MAP.keys())

def find_slang(text: str):
    found = []
    for t in tokenize_words(text):
        low = t.lower()
        if low in SLANG_SET:
            found.append(t)
        if re.search(r"(.)\1\1+", low):
            found.append(t)
    out, seen = [], set()
    for x in found:
        if x.lower() not in seen:
            out.append(x); seen.add(x.lower())
    return out[:10]

def vowel_ratio(w: str) -> float:
    w = w.lower()
    if not w:
        return 0.0
    v = sum(1 for ch in w if ch in VOWELS)
    return v / len(w)

def has_long_consonant_run(w: str) -> bool:
    return bool(re.search(r"[^aiueoAIUEO]{5,}", w))

def is_keyboard_smash(w: str):
    low = w.lower()
    if len(low) >= 8 and vowel_ratio(low) < 0.20:
        return True, "vokal sangat minim"
    if len(low) >= 7 and has_long_consonant_run(low):
        return True, "konsonan berturut-turut panjang"
    if re.search(r"(.)\1\1+", low):
        return True, "huruf berulang berlebihan"
    rare = sum(1 for ch in low if ch in "qxz")
    if len(low) >= 6 and rare >= 2:
        return True, "terlalu banyak q/x/z"
    return False, ""

def find_weird_punct(text: str):
    issues = []
    if WEIRD_SYMBOLS_RE.search(text):
        issues.append("Ada simbol aneh (@/#/$/%/dll).")
    if re.search(r"([.,!?;:])\1{1,}", text):
        issues.append("Ada tanda baca berulang (.. ,,, ?? !!).")
    if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}[.,!?;:][A-Za-zÀ-ÖØ-öø-ÿ]{2,}", text):
        issues.append("Ada tanda baca nyelip di tengah kata.")
    if re.search(r"\s+[,.!?;:…]", text):
        issues.append("Ada spasi sebelum tanda baca (mis. 'kata ,').")
    if re.search(r"[,.!?;:][A-Za-zÀ-ÖØ-öø-ÿ]", text):
        issues.append("Ada tanda baca tanpa spasi setelahnya (mis. 'kata,ini').")
    return issues[:8]

def detect_gibberish_and_non_kbbi(text: str):
    toks = tokenize_alpha_with_spans(text)
    smash = []
    nonkbbi = []

    for i, (t, s, e) in enumerate(toks):
        sm, reason = is_keyboard_smash(t)
        if sm:
            smash.append((t, reason))
            continue

        low = t.lower()
        if low in SLANG_SET:
            continue

        sent_start = is_sentence_start(text, s)
        next_is_cap = False
        if i + 1 < len(toks):
            nxt = toks[i+1][0]
            # next token kapital dan masih satu kalimat (heuristik)
            next_is_cap = nxt[:1].isupper() and not nxt.isupper()

        # ✅ Nama diri: jangan dianggap non-KBBI
        if is_probable_proper_noun(t, sent_start=sent_start, next_is_cap=next_is_cap):
            continue

        if not is_kbbi_word(t):
            nonkbbi.append(t)

    def uniq_list(items):
        out, seen = [], set()
        for x in items:
            key = x.lower() if isinstance(x, str) else x[0].lower()
            if key not in seen:
                out.append(x); seen.add(key)
        return out

    smash = uniq_list(smash)[:12]
    nonkbbi = uniq_list(nonkbbi)[:12]
    return smash, nonkbbi, len(toks)

# =========================================================
# EYD RULE ENGINE (from eyd_db.txt)
# =========================================================
def _re_flags(flag_str: str):
    s = (flag_str or "").upper().strip()
    flags = 0
    if "IGNORECASE" in s:
        flags |= re.IGNORECASE
    return flags

def _excerpt(text: str, start: int, end: int, pad: int = 28):
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    frag = text[a:b].replace("\n", " ")
    return ("..." if a > 0 else "") + frag + ("..." if b < len(text) else "")

def check_initial_capital(text: str, data=None):
    viol = []
    for s in sentences(text):
        m = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", s)
        if not m:
            continue
        ch = s[m.start()]
        if ch != ch.upper():
            viol.append({"example": s[:120]})
    return viol

def check_pun_spacing(text: str, data=None):
    exc = set((data or {}).get("exceptions_serangkai", []))
    viol = []
    for m in re.finditer(r"\b([A-Za-zÀ-ÖØ-öø-ÿ]+)pun\b", text, flags=re.IGNORECASE):
        tok = m.group(0).lower()
        if tok in exc:
            continue
        viol.append({"example": _excerpt(text, m.start(), m.end())})
    return viol

def check_sentence_final_punct(text: str, data=None):
    viol = []
    for s in sentences(text):
        if not re.search(r"[.!?…]$", s.strip()):
            viol.append({"example": s[:120]})
    return viol

def check_question_mark(text: str, data=None):
    qwords = (data or {}).get("question_words", [])
    qwords = [qw.lower() for qw in qwords]
    viol = []
    for s in sentences(text):
        low = s.lower()
        hit = any(qw in low for qw in qwords)
        if hit and not s.strip().endswith("?"):
            viol.append({"example": s[:120]})
    return viol

def check_exclamation_mark(text: str, data=None):
    triggers = (data or {}).get("triggers", [])
    triggers = [t.lower() for t in triggers]
    viol = []
    for s in sentences(text):
        low = s.lower()
        hit = any(t in low for t in triggers)
        if hit and not s.strip().endswith("!"):
            viol.append({"example": s[:120]})
    return viol

def check_comma_before_conjunction(text: str, data=None):
    conj = (data or {}).get("conj", [])
    conj = [c.lower() for c in conj]
    viol = []
    for s in sentences(text):
        low = s.lower()
        for c in conj:
            idx = low.find(" " + c + " ")
            if idx == -1:
                continue
            j = idx - 1
            while j >= 0 and s[j].isspace():
                j -= 1
            if j >= 0 and s[j] != ",":
                viol.append({"example": s[:140], "conj": c})
    return viol

def check_intro_subclause_comma(text: str, data=None):
    starters = (data or {}).get("starters", [])
    starters = [st.lower() for st in starters]
    viol = []
    for s in sentences(text):
        low = s.lower().strip()
        for st in starters:
            if low.startswith(st + " ") or low.startswith(st + ",") or low.startswith(st + "—"):
                pos = s.find(",")
                if pos == -1 or pos > 70:
                    viol.append({"example": s[:160], "starter": st})
                break
    return viol

def check_no_comma_before_subclause(text: str, data=None):
    markers = (data or {}).get("markers", [])
    markers = [m.lower() for m in markers]
    viol = []
    for s in sentences(text):
        low = s.lower()
        for mk in markers:
            if re.search(r",\s+" + re.escape(mk) + r"\b", low):
                viol.append({"example": s[:160], "marker": mk})
                break
    return viol

EYD_FUNCTIONS = {
    "check_initial_capital": check_initial_capital,
    "check_pun_spacing": check_pun_spacing,
    "check_sentence_final_punct": check_sentence_final_punct,
    "check_question_mark": check_question_mark,
    "check_exclamation_mark": check_exclamation_mark,
    "check_comma_before_conjunction": check_comma_before_conjunction,
    "check_intro_subclause_comma": check_intro_subclause_comma,
    "check_no_comma_before_subclause": check_no_comma_before_subclause,
}

def apply_eyd_rules(text: str, type_key: str):
    report = {
        "loaded": bool(EYD_LOADED),
        "violations": [],
        "counts": {"error": 0, "warning": 0, "info": 0},
        "by_id": {},
        "by_category": {}
    }
    if not EYD_LOADED:
        return report

    counts_by_id = Counter()
    counts_by_cat = Counter()
    counts_by_sev = Counter()
    violations = []

    def add_violation(rule, example):
        rid = rule.get("id", "UNKNOWN")
        sev = (rule.get("severity") or "warning").lower()
        cat = (rule.get("category") or "lainnya").lower()

        counts_by_id[rid] += 1
        counts_by_cat[cat] += 1
        counts_by_sev[sev] += 1

        violations.append({
            "id": rid,
            "severity": sev,
            "category": cat,
            "title": rule.get("title", ""),
            "message": rule.get("message", ""),
            "example": example
        })

    for rule in EYD_RULES:
        rid = rule.get("id", "")

        # relax untuk puisi: jangan “maksa” tiap kalimat harus bertitik
        if type_key == "puisi" and rid in {"TITIK_01", "KOMA_02"}:
            continue

        ctype = rule.get("check_type", "")
        if ctype == "regex":
            pat = rule.get("pattern", "")
            flags = _re_flags(rule.get("flags", ""))
            if not pat:
                continue
            try:
                # ✅ Filter khusus KDEP_01: hanya flag kasus kata depan di/ke/dari yang nempel ke lokasi,
                #    bukan imbuhan "di-" pada kata kerja (dikenal, ditulis, dibuat, dll).
                if rid == "KDEP_01":
                    for m in re.finditer(r"\b(di|ke|dari)[A-Za-zÀ-ÖØ-öø-ÿ]+", text, flags=flags):
                        word = m.group(0)
                        pref_m = re.match(r"^(di|ke|dari)", word, flags=re.IGNORECASE)
                        if not pref_m:
                            continue
                        prefix = pref_m.group(0).lower()
                        rest = word[len(prefix):]
                        if not rest:
                            continue

                        rest_low = strip_pronoun_suffix(rest.lower())

                        keep = False
                        # diBandung / keJakarta / dariSurabaya -> jelas kata depan + nama tempat
                        if rest[0].isupper():
                            keep = True
                        # dirumah / kesekolah / dipasar -> kata depan + lokasi umum
                        elif rest_low in LOCATION_WORDS:
                            keep = True

                        if keep:
                            add_violation(rule, _excerpt(text, m.start(), m.end()))
                            if counts_by_id[rid] >= 10:
                                break
                    continue

                for m in re.finditer(pat, text, flags=flags):
                    add_violation(rule, _excerpt(text, m.start(), m.end()))
                    if counts_by_id[rid] >= 10:
                        break
            except:
                continue

        elif ctype == "function":
            fn = rule.get("function", "")
            f = EYD_FUNCTIONS.get(fn)
            if not f:
                continue
            try:
                data = rule.get("data") or {}
                res = f(text, data=data) or []
                for it in res[:10]:
                    add_violation(rule, it.get("example") if isinstance(it, dict) else str(it))
            except:
                continue

    report["violations"] = violations[:40]
    report["counts"] = {
        "error": int(counts_by_sev.get("error", 0)),
        "warning": int(counts_by_sev.get("warning", 0)),
        "info": int(counts_by_sev.get("info", 0)),
    }
    report["by_id"] = dict(counts_by_id)
    report["by_category"] = dict(counts_by_cat)
    return report

# =========================================================
# DENOTATIF vs KONOTATIF (heuristik)
# =========================================================
FIGURATIVE = {
    "bagai","bagaikan","laksana","seperti","ibarat",
    "senja","fajar","rindu","hampa","sunyi","gelap","cahaya",
    "bayang","angin","hujan","bintang","bulan","langit","samudra",
    "luka","peluk","hati","jiwa","mimpi","mendung","riuh","bisik"
}
FACT_MARKERS = {"data","fakta","menurut","berdasarkan","penelitian","laporan","survei","statistik","persen","%","tahun"}
CONNECTORS = {"dan","tetapi","namun","karena","sehingga","oleh karena itu","selain itu","kemudian","lalu","setelah itu","di samping itu","akibatnya","meskipun"}

def count_hits(text: str, vocab: set):
    w = [x.lower() for x in alpha_words(text)]
    return sum(1 for x in w if x in vocab)

DENOTATIVE_TYPES = {"prosedur","pengumuman","surel","informatif","eksplanasi","nonfiksi","biografi"}
CONNOTATIVE_TYPES = {"puisi","fiksi","naratif","deskriptif","persuasi"}

# =========================================================
# AUTO FIX SEDERHANA
# =========================================================
def auto_fix_basic(text: str, is_poem: bool):
    t = norm_space(text)
    t = re.sub(r"\s+([,.!?…;:])", r"\1", t)
    t = re.sub(r"([,.!?;:])(?!\s|$)", r"\1 ", t)

    def repl(m):
        w = m.group(0)
        low = w.lower()
        if low in SLANG_MAP:
            rep = SLANG_MAP[low]
            if w[0].isupper():
                rep = rep[0].upper() + rep[1:]
            return rep
        return w

    t = re.sub(r"\b[A-Za-zÀ-ÖØ-öø-ÿ']+\b", repl, t)

    if is_poem:
        lines = t.split("\n")
        fixed = []
        for ln in lines:
            ln2 = ln.strip()
            if not ln2:
                fixed.append("")
                continue
            m = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", ln2)
            if m:
                i = m.start()
                ln2 = ln2[:i] + ln2[i].upper() + ln2[i+1:]
            fixed.append(ln2)
        return "\n".join(fixed).strip()

    def cap_after(m):
        return m.group(1) + " " + m.group(2).upper()

    t = re.sub(r"([.!?…])\s+([a-zà-öø-ÿ])", cap_after, t)
    m = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", t)
    if m:
        i = m.start()
        t = t[:i] + t[i].upper() + t[i+1:]
    return t

# =========================================================
# RUBRIK
# =========================================================
RUBRIK = {"struktur": 30, "bahasa": 35, "kejelasan": 15, "kreativitas": 15, "kerapihan": 5}

# =========================================================
# STRUKTUR (30) per tipe (heuristik)
# =========================================================
TIME_MARKERS = {"kemarin","hari","pagi","siang","sore","malam","suatu","ketika","saat","akhirnya","tiba-tiba","kemudian","lalu"}
PLACE_MARKERS = {"di","ke","dari","pada","dalam","atas","bawah","sebelah","dekat","jauh","kampung","sekolah","rumah","pasar","kota","desa"}
CONFLICT_MARKERS = {"tetapi","namun","sayang","masalah","kesulitan","bingung","marah","takut","celaka","tiba-tiba"}
RESOLUTION_MARKERS = {"akhirnya","pada akhirnya","sejak itu","selesai","berhasil","membaik","damai","lega"}

def detect_title(text: str):
    lines = [ln.strip() for ln in get_lines(text) if ln.strip()]
    if not lines:
        return ("", False)
    first = lines[0]
    if len(alpha_words(first)) <= 12:
        return (first, True)
    return (first, False)

def has_date_place_line(text: str):
    return bool(re.search(
        r"\b[A-Z][a-z]+\b\s*,\s*\d{1,2}\s+[A-Za-z]+\s+\d{4}\b|\b[A-Z][a-z]+\b\s*,\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        text
    ))

def has_email_address(text: str):
    return bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))

def mk_check(label, ok, note=""):
    return {"label": label, "ok": bool(ok), "note": note}

def score_structure(type_key: str, text: str):
    benar, kurang, perlu = [], [], []
    checklist = []

    paras = get_paragraphs(text)
    low = text.lower()
    w = [x.lower() for x in alpha_words(text)]

    title, title_ok = detect_title(text)

    def add(label, ok, note_ok="", note_no=""):
        checklist.append(mk_check(label, ok, note_ok if ok else note_no))
        if ok:
            benar.append(f"{label} terdeteksi.")
        else:
            kurang.append(f"{label} belum lengkap.")
            if note_no:
                perlu.append(note_no)

    if type_key == "naratif":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul singkat di baris pertama.")
        orient = any(x in TIME_MARKERS for x in w) and any(x in PLACE_MARKERS for x in w)
        add("Orientasi", orient, note_ok="Ada waktu & tempat.", note_no="Tambahkan orientasi (waktu dan tempat) di awal.")
        comp = any(x in CONFLICT_MARKERS for x in w)
        add("Komplikasi", comp, note_ok="Ada konflik/masalah.", note_no="Tambahkan konflik/masalah (komplikasi).")
        resol = ("akhirnya" in low) or any(x in RESOLUTION_MARKERS for x in w)
        add("Resolusi", resol, note_ok="Ada penyelesaian.", note_no="Tambahkan resolusi (penyelesaian).")
        koda = any(k in low for k in ["pesan", "amanat", "pelajaran", "sejak itu", "jadi"])
        add("Koda", koda, note_ok="Ada penutup/pesan.", note_no="Tambahkan koda (pesan/penutup).")

    elif type_key == "deskriptif":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        ident = any(k in low for k in ["adalah", "merupakan", "yaitu"]) or (len(paras) >= 1 and len(alpha_words(paras[0])) >= 8)
        add("Identifikasi", ident, note_ok="Objek dikenalkan di awal.", note_no="Tambahkan identifikasi objek di paragraf awal.")
        adj = count_hits(text, {"indah","besar","kecil","tinggi","rendah","panjang","pendek","lebar","sempit","gelap","terang","harum","wangi","sejuk","hangat","dingin","panas"})
        bagian = (len(paras) >= 2) or (adj >= 5)
        add("Deskripsi bagian", bagian, note_ok="Ada detail bagian/ciri.", note_no="Tambahkan deskripsi bagian (ciri, warna, ukuran, suasana).")

    elif type_key == "fiksi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        orient = any(x in TIME_MARKERS for x in w) or any(x in PLACE_MARKERS for x in w)
        add("Orientasi", orient, note_ok="Ada latar awal.", note_no="Tambahkan orientasi (waktu/tempat/tokoh) di awal.")
        rangkaian = any(k in low for k in ["lalu","kemudian","setelah itu","selanjutnya"]) or (len(paras) >= 2)
        add("Rangkaian peristiwa", rangkaian, note_ok="Ada urutan peristiwa.", note_no="Tambahkan rangkaian peristiwa yang runtut.")
        klimaks = any(k in low for k in ["tiba-tiba","puncaknya","mendadak","ketika itu","seketika"])
        add("Klimaks", klimaks, note_ok="Ada puncak konflik.", note_no="Tambahkan klimaks (puncak kejadian).")
        resol = ("akhirnya" in low) or any(x in RESOLUTION_MARKERS for x in w)
        add("Resolusi", resol, note_ok="Ada penyelesaian.", note_no="Tambahkan resolusi (akhir cerita).")
        amanat = any(k in low for k in ["amanat","pesan","pelajaran"])
        add("Amanat", amanat, note_ok="Amanat ada.", note_no="Tambahkan amanat/pesan (boleh eksplisit).")

    elif type_key == "nonfiksi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        pend = len(paras) >= 1 and (any(k in paras[0].lower() for k in ["adalah","merupakan","yaitu"]) or len(alpha_words(paras[0])) >= 10)
        add("Pendahuluan", pend, note_ok="Topik dikenalkan.", note_no="Tambahkan pendahuluan (pengenalan topik).")
        isi = len(paras) >= 2
        add("Isi", isi, note_ok="Ada isi pembahasan.", note_no="Tambahkan isi (penjelasan/fakta/contoh).")
        penutup = any(k in low for k in ["kesimpulan","oleh karena itu","dengan demikian","penutup"])
        add("Penutup", penutup, note_ok="Ada penutup.", note_no="Tambahkan penutup/kesimpulan.")

    elif type_key == "prosedur":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul prosedur.")
        add("Tujuan", "tujuan" in low, note_ok="Ada bagian tujuan.", note_no="Tambahkan bagian 'Tujuan'.")
        add("Alat dan bahan", ("alat" in low) or ("bahan" in low), note_ok="Ada alat/bahan.", note_no="Tambahkan 'Alat dan Bahan'.")
        langkah = ("langkah" in low) or (count_bullets(text) >= 3) or ("pertama" in low)
        add("Langkah-langkah", langkah, note_ok="Langkah jelas.", note_no="Tuliskan langkah-langkah bernomor minimal 3.")
        add("Penutup", any(k in low for k in ["selesai","penutup","demikian"]), note_ok="Ada penutup singkat.", note_no="Tambahkan penutup singkat (mis. selesai/demikian).")

    elif type_key == "surat_pribadi":
        add("Tempat dan tanggal", has_date_place_line(text), note_ok="Pola tempat,tanggal terdeteksi.", note_no="Tambahkan tempat dan tanggal (mis. Jakarta, 12 Desember 2025).")
        add("Salam pembuka", any(k in low for k in ["halo","hai","assalamualaikum","selamat"]), note_ok="Salam pembuka ada.", note_no="Tambahkan salam pembuka.")
        add("Isi surat", len(alpha_words(text)) >= 40, note_ok="Isi surat cukup.", note_no="Tambahkan isi surat yang jelas (minimal 40 kata).")
        add("Salam penutup", any(k in low for k in ["salam","salam hangat","hormat","terima kasih"]), note_ok="Salam penutup ada.", note_no="Tambahkan salam penutup.")
        lines = [ln.strip() for ln in get_lines(text) if ln.strip()]
        add("Nama pengirim", bool(lines and 1 <= len(alpha_words(lines[-1])) <= 4), note_ok="Ada nama pengirim.", note_no="Tambahkan nama pengirim di baris terakhir.")

    elif type_key == "eksposisi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        add("Tesis", any(k in low for k in ["menurut", "pendapat", "seharusnya", "perlu", "penting"]), note_ok="Ada pernyataan tesis.", note_no="Nyatakan tesis/pendapat di awal.")
        arg = sum(1 for p in ["karena","sebab","sehingga","selain itu","namun","tetapi"] if p in low) >= 3
        add("Argumentasi", arg, note_ok="Ada argumentasi/penguat.", note_no="Tambahkan argumentasi (karena, sehingga, selain itu).")
        add("Penegasan ulang", any(k in low for k in ["kesimpulan","oleh karena itu","dengan demikian","penegasan"]), note_ok="Ada penegasan ulang.", note_no="Tambahkan penegasan ulang/kesimpulan.")

    elif type_key == "pengumuman":
        add("Judul", ("pengumuman" in low) or title_ok, note_ok="Judul pengumuman ada.", note_no="Tambahkan judul 'PENGUMUMAN'.")
        add("Isi pengumuman", len(alpha_words(text)) >= 25, note_ok="Isi cukup.", note_no="Tambahkan isi pengumuman yang jelas.")
        waktu = bool(re.search(r"\b(jam|pukul)\b|\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", low))
        tempat = any(k in low for k in ["tempat","lokasi","ruang","aula","lapangan","kelas","di "])
        add("Waktu dan tempat", waktu and tempat, note_ok="Waktu & tempat terdeteksi.", note_no="Tambahkan waktu dan tempat pelaksanaan.")
        add("Nama pembuat", any(k in low for k in ["panitia","kepala sekolah","sekretaris","ketua"]) or (len(get_lines(text)) >= 3),
            note_ok="Ada penanggung jawab/pembuat.", note_no="Tambahkan nama pembuat/panitia.")

    elif type_key == "surel":
        add("Alamat email tujuan", has_email_address(text), note_ok="Email terdeteksi.", note_no="Tambahkan alamat email tujuan.")
        subjek = any(ln.lower().strip().startswith(("subjek:", "subject:")) for ln in get_lines(text))
        add("Subjek", subjek, note_ok="Subjek ada.", note_no="Tambahkan baris 'Subjek: ...'.")
        add("Salam pembuka", any(k in low for k in ["yth","dengan hormat","halo","hai"]), note_ok="Salam pembuka ada.", note_no="Tambahkan salam pembuka.")
        add("Isi email", len(alpha_words(text)) >= 35, note_ok="Isi email cukup.", note_no="Perjelas isi email (minimal 35 kata).")
        add("Salam penutup", any(k in low for k in ["terima kasih","hormat saya","salam","regards"]), note_ok="Salam penutup ada.", note_no="Tambahkan salam penutup.")
        lines = [ln.strip() for ln in get_lines(text) if ln.strip()]
        add("Nama pengirim", bool(lines and 1 <= len(alpha_words(lines[-1])) <= 4), note_ok="Ada nama pengirim.", note_no="Tambahkan nama pengirim di baris terakhir.")

    elif type_key == "informatif":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        pend = len(paras) >= 1 and any(k in paras[0].lower() for k in ["adalah","merupakan","yaitu"])
        add("Pendahuluan", pend, note_ok="Pendahuluan/definisi ada.", note_no="Tambahkan pendahuluan (definisi/pengenalan).")
        add("Isi informasi", len(paras) >= 2, note_ok="Isi informasi ada.", note_no="Tambahkan isi informasi (penjelasan).")
        add("Penutup", any(k in low for k in ["kesimpulan","penutup","oleh karena itu","dengan demikian"]),
            note_ok="Penutup ada.", note_no="Tambahkan penutup singkat.")

    elif type_key == "eksplanasi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        umum = len(paras) >= 1 and any(k in paras[0].lower() for k in ["adalah","merupakan","yaitu"])
        add("Pernyataan umum", umum, note_ok="Pernyataan umum ada.", note_no="Tambahkan pernyataan umum (definisi fenomena).")
        deret = any(k in low for k in ["sebab","karena","proses","akibat","sehingga","maka","oleh karena itu"])
        add("Deretan penjelas", deret, note_ok="Ada sebab-akibat/proses.", note_no="Tambahkan deretan penjelas (sebab-akibat/proses).")
        add("Penutup", any(k in low for k in ["penutup","kesimpulan","dengan demikian"]),
            note_ok="Penutup ada.", note_no="Tambahkan penutup/kesimpulan.")

    elif type_key == "persuasi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        add("Pengenalan isu", len(paras) >= 1 and len(alpha_words(paras[0])) >= 10, note_ok="Isu dikenalkan.", note_no="Tambahkan pengenalan isu di paragraf awal.")
        arg = sum(1 for p in ["karena","sebab","buktinya","contohnya","selain itu","oleh karena itu"] if p in low) >= 2
        add("Rangkaian argumen", arg, note_ok="Ada argumen.", note_no="Tambahkan argumen pendukung.")
        add("Ajakan", any(k in low for k in ["ayo","mari","sebaiknya","hendaknya","jangan","harus"]), note_ok="Ada ajakan.", note_no="Tambahkan ajakan (ayo/mari/sebaiknya).")
        add("Penegasan kembali", any(k in low for k in ["penegasan","kesimpulan","jadi","maka"]), note_ok="Ada penegasan.", note_no="Tambahkan penegasan kembali (kalimat penutup).")

    elif type_key == "puisi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul puisi di baris pertama.")
        lines = [ln.strip() for ln in get_lines(text)]
        non_empty = [ln for ln in lines[1:] if ln.strip()]
        add("Larik dan bait", len(non_empty) >= 6, note_ok=f"{len(non_empty)} larik terdeteksi.", note_no="Minimal 6 larik setelah judul.")
        ends = []
        for ln in non_empty:
            ws = [w.lower() for w in alpha_words(ln)]
            if ws:
                ends.append(ws[-1][-3:])
        rhyme_ok = False
        if len(ends) >= 6:
            common = Counter(ends).most_common(1)[0][1]
            rhyme_ok = common >= 2
        add("Rima/irama", rhyme_ok, note_ok="Ada pola bunyi (heuristik).", note_no="Coba buat rima/irama (pengulangan bunyi akhir).")
        add("Amanat", any(k in low for k in ["pesan","amanat","ingatlah","jangan","harus","semoga"]), note_ok="Amanat/pesan terdeteksi.", note_no="Tambahkan amanat/pesan.")

    elif type_key == "biografi":
        add("Judul", title_ok, note_ok=title, note_no="Tambahkan judul di baris pertama.")
        orient = any(k in low for k in ["lahir","dilahirkan","adalah","merupakan"]) and (count_numbers(text) >= 1 or "tahun" in low)
        add("Orientasi", orient, note_ok="Ada identitas awal (lahir/tahun).", note_no="Tambahkan orientasi: tokoh + lahir/tahun/asal.")
        peristiwa = any(k in low for k in ["kemudian","setelah itu","pada tahun","selanjutnya","karier","prestasi"]) or (count_numbers(text) >= 2)
        add("Peristiwa penting", peristiwa, note_ok="Ada peristiwa penting.", note_no="Tambahkan peristiwa penting kronologis.")
        reorient = any(k in low for k in ["sejak itu","hingga kini","akhirnya","menginspirasi","teladan","penutup"])
        add("Reorientasi", reorient, note_ok="Ada penutup/reorientasi.", note_no="Tambahkan reorientasi (kesan/penutup).")

    total_items = max(1, len(checklist))
    ok_count = sum(1 for c in checklist if c["ok"])
    score = round((ok_count / total_items) * 30)
    return clamp(score, 0, 30), {"checklist": checklist, "ok_count": ok_count, "total": total_items}, benar, kurang, perlu

# =========================================================
# BAHASA (35) — include EYD DB violations
# =========================================================
def score_language(text: str, type_key: str, eyd_report: dict):
    benar, kurang, perlu = [], [], []
    sub = {}

    weird = find_weird_punct(text)
    slang = find_slang(text)
    smash, nonkbbi, _ = detect_gibberish_and_non_kbbi(text)

    by_id = (eyd_report or {}).get("by_id", {}) if isinstance(eyd_report, dict) else {}
    eyd_viol = (eyd_report or {}).get("violations", []) if isinstance(eyd_report, dict) else []
    eyd_loaded = bool((eyd_report or {}).get("loaded", False))

    # Kapital (0..5)
    hkal = int(by_id.get("HKAL_01", 0))
    s_cap = 5
    if hkal >= 1: s_cap -= 2
    if hkal >= 3: s_cap -= 2
    s_cap = clamp(s_cap, 0, 5)
    sub["kapital"] = s_cap
    if s_cap >= 4: benar.append("Huruf kapital awal kalimat cukup konsisten.")
    else:
        kurang.append("Huruf kapital awal kalimat belum konsisten.")
        perlu.append("Perbaiki huruf kapital pada awal kalimat.")

    # Tanda baca (0..8)
    tit = int(by_id.get("TITIK_01", 0))
    tny = int(by_id.get("TANYA_01", 0))
    km1 = int(by_id.get("KOMA_01", 0))
    km2 = int(by_id.get("KOMA_02", 0))

    s_punct = 8
    s_punct -= min(4, tit)
    s_punct -= min(2, tny)
    s_punct -= min(2, km1)
    s_punct -= min(2, km2)
    if weird:
        s_punct -= min(4, len(weird))
    s_punct = clamp(s_punct, 0, 8)
    sub["tanda_baca"] = s_punct

    if s_punct >= 6:
        benar.append("Tanda baca relatif rapi.")
    else:
        kurang.append("Tanda baca masih bermasalah.")
        perlu.append("Rapikan titik/koma/tanya/seru dan hindari tanda baca nyelip/berulang.")

    # Bahasa baku + penulisan kata (0..10)
    s_baku = 10
    s_baku -= min(8, len(slang) * 2)
    s_baku -= min(10, len(smash) * 3)
    if KBBI_LOADED:
        s_baku -= min(8, max(0, len(nonkbbi) - 1) * 2)

    penulisan_ids = ["KDEP_01","PART_01","PART_02","PART_03","KGNT_01","KGNT_02","SAND_01","ULANG_01","ANGKA_01","ANGKA_02"]
    penulisan_hits = sum(int(by_id.get(i, 0)) for i in penulisan_ids)
    s_baku -= min(8, penulisan_hits)
    s_baku = clamp(s_baku, 0, 10)
    sub["baku_kbbi_eyd"] = s_baku

    if slang:
        kurang.append("Ada kata tidak baku: " + ", ".join(slang))
        perlu.append("Ganti kata tidak baku menjadi kata baku (KBBI).")
    if smash:
        contoh = ", ".join([f"{w}({r})" for (w, r) in smash[:5]])
        kurang.append("Ada kata seperti asal ketik/typo: " + contoh)
        perlu.append("Perbaiki/hapus kata yang tidak bermakna.")
    if KBBI_LOADED and nonkbbi:
        kurang.append("Ada kata tidak terverifikasi KBBI: " + ", ".join(nonkbbi[:12]))
        perlu.append("Periksa ejaan kata sesuai KBBI (catatan: nama diri tidak dihitung).")
    if penulisan_hits > 0:
        kurang.append(f"Ada {penulisan_hits} indikasi salah penulisan kata (aturan EYD).")
        perlu.append("Periksa 'di/ke/dari', partikel, kata ganti (-ku/-mu/-nya), bentuk ulang, penulisan angka.")

    # Denotatif/konotatif (0..7)
    figur = count_hits(text, FIGURATIVE)
    facts = count_hits(text, FACT_MARKERS) + count_numbers(text)
    wc = len(alpha_words(text)) or 1
    fig_per_100 = (figur / wc) * 100.0

    s_dk = 7
    if type_key in DENOTATIVE_TYPES:
        if fig_per_100 > 3.5:
            s_dk -= 3
            kurang.append("Bahasa terlalu konotatif/puitis untuk tipe ini.")
            perlu.append("Gunakan bahasa denotatif (lugas), kurangi majas/metafora.")
        if facts == 0 and type_key in {"nonfiksi","informatif","eksplanasi","biografi"}:
            s_dk -= 2
            kurang.append("Fakta/penanda informasi masih minim.")
            perlu.append("Tambahkan data/tahun/rujukan sederhana.")
    if type_key in CONNOTATIVE_TYPES:
        if type_key in {"puisi","fiksi"} and fig_per_100 < 1.0:
            s_dk -= 2
            kurang.append("Diksi konotatif/majas masih minim.")
            perlu.append("Tambah imaji/metafora/perumpamaan secukupnya.")
    s_dk = clamp(s_dk, 0, 7)
    sub["denotatif_konotatif"] = s_dk

    # Variasi kosakata (0..5)
    div = lexical_diversity(text)
    top = Counter([w.lower() for w in alpha_words(text)]).most_common(1)
    top_ratio = (top[0][1] / max(1, len(alpha_words(text)))) if top else 0.0
    s_vocab = 5
    if div < 0.52: s_vocab -= 2
    if top_ratio > 0.10: s_vocab -= 1
    s_vocab = clamp(s_vocab, 0, 5)
    sub["variasi_kosakata"] = s_vocab
    if s_vocab >= 4: benar.append("Variasi kosakata cukup baik.")
    else:
        kurang.append("Variasi kosakata kurang.")
        perlu.append("Kurangi pengulangan kata yang sama, gunakan sinonim.")

    total = clamp(s_cap + s_punct + s_baku + s_dk + s_vocab, 0, 35)

    # contoh pelanggaran EYD (maks 3)
    if eyd_loaded and eyd_viol:
        for v in eyd_viol[:3]:
            msg = f"EYD {v.get('id','')}: {v.get('title','')}. Contoh: {v.get('example','')}"
            kurang.append(msg)

    meta = {
        "kbbi_loaded": bool(KBBI_LOADED),
        "eyd_loaded": bool(eyd_loaded),
        "weird_punct": weird,
        "slang": slang,
        "eyd_counts": (eyd_report or {}).get("counts", {}),
    }
    return total, sub, meta, benar, kurang, perlu

# =========================================================
# KEJELASAN (15)
# =========================================================
def score_clarity(text: str):
    benar, kurang, perlu = [], [], []
    ss = sentences(text)
    if not ss:
        return 0, {"kalimat": 0, "rata2_kata": 0}, benar, ["Tidak ada kalimat."], ["Tambahkan kalimat yang jelas."]

    avglen = avg_sentence_len(text)
    w = [w.lower() for w in alpha_words(text)]
    conn = sum(1 for c in CONNECTORS if c in " ".join(w))

    too_short = sum(1 for s in ss if len(alpha_words(s)) <= 3)
    too_long = sum(1 for s in ss if len(alpha_words(s)) >= 30)

    s = 15
    if avglen < 7 or avglen > 24: s -= 3
    if too_short >= max(2, len(ss)//3): s -= 3
    if too_long >= 2: s -= 2
    if conn == 0 and len(ss) >= 4: s -= 3

    s = clamp(s, 0, 15)
    if s >= 12:
        benar.append("Kalimat cukup nyambung dan mudah dipahami.")
    else:
        kurang.append("Kejelasan/koherensi masih kurang.")
        perlu.append("Gunakan penghubung (karena, sehingga, kemudian, namun) dan rapikan kalimat.")
    return s, {"kalimat": len(ss), "rata2_kata": round(avglen,2), "penghubung": conn}, benar, kurang, perlu

# =========================================================
# KREATIVITAS (15)
# =========================================================
def score_creativity(text: str, type_key: str):
    benar, kurang, perlu = [], [], []
    wcount = len(alpha_words(text)) or 1
    figur = count_hits(text, FIGURATIVE)
    div = lexical_diversity(text)

    s = 15
    if type_key in CONNOTATIVE_TYPES:
        if figur == 0: s -= 5
        if div < 0.5: s -= 3
        if wcount < 60 and type_key in {"puisi","fiksi","naratif"}: s -= 2
    else:
        if div < 0.45: s -= 2
        if wcount < 50: s -= 2

    s = clamp(s, 0, 15)
    if s >= 12:
        benar.append("Kreativitas cukup terasa (diksi/penyajian).")
    else:
        kurang.append("Kreativitas masih bisa ditingkatkan.")
        perlu.append("Gunakan variasi diksi, contoh/ilustrasi, atau gaya bahasa sesuai tipe teks.")
    return s, {"figuratif_hits": figur, "diversity": round(div,2), "jumlah_kata": wcount}, benar, kurang, perlu

# =========================================================
# KERAPIHAN (5)
# =========================================================
def score_neatness(text: str):
    benar, kurang, perlu = [], [], []
    raw = (text or "")

    s = 5
    if re.search(r"[ \t]{2,}", raw):
        s -= 1
        kurang.append("Ada spasi ganda/berlebih.")
        perlu.append("Hapus spasi ganda.")
    if re.search(r"\n{3,}", raw):
        s -= 1
        kurang.append("Terlalu banyak baris kosong.")
        perlu.append("Rapikan paragraf (maks 1 baris kosong).")
    if WEIRD_SYMBOLS_RE.search(raw):
        s -= 2
        kurang.append("Ada simbol aneh yang mengganggu kerapihan.")
        perlu.append("Hapus simbol asing (@/#/$/%/dll).")

    caps = sum(1 for ch in raw if ch.isupper())
    letters = sum(1 for ch in raw if ch.isalpha())
    if letters > 0 and (caps / letters) > 0.25:
        s -= 1
        kurang.append("Huruf kapital terlalu banyak (tidak rapi).")
        perlu.append("Gunakan kapital seperlunya (awal kalimat, nama diri).")

    s = clamp(s, 0, 5)
    if s >= 4:
        benar.append("Teks cukup rapi.")
    return s, {"baris": len(get_lines(text))}, benar, kurang, perlu

# =========================================================
# MAIN
# =========================================================
VALID_TYPES = {
    "naratif","deskriptif","fiksi","nonfiksi","prosedur","surat_pribadi","eksposisi",
    "pengumuman","surel","informatif","eksplanasi","persuasi","puisi","biografi"
}

def evaluate(type_key: str, text: str):
    type_key = (type_key or "").strip()
    cleaned = norm_space(text or "")

    if not cleaned:
        return {
            "ok": False,
            "type": type_key,
            "score": 0,
            "message": "Teks kosong.",
            "feedback": {
                "benar": [],
                "kurang_tepat": ["Teks masih kosong."],
                "perlu_diperbaiki": ["Tempel/unggah teks terlebih dahulu."]
            },
            "auto_fix": {"text": ""},
            "breakdown": {}
        }

    if type_key not in VALID_TYPES:
        type_key = "informatif"

    eyd_report = apply_eyd_rules(cleaned, type_key)

    s_str, b_str, okS, kS, pS = score_structure(type_key, cleaned)
    s_lang, sub_lang, meta_lang, okL, kL, pL = score_language(cleaned, type_key, eyd_report)
    s_clr, b_clr, okC, kC, pC = score_clarity(cleaned)
    s_crv, b_crv, okR, kR, pR = score_creativity(cleaned, type_key)
    s_neat, b_neat, okN, kN, pN = score_neatness(cleaned)

    total = clamp(s_str + s_lang + s_clr + s_crv + s_neat, 0, 100)

    smash, _, _ = detect_gibberish_and_non_kbbi(cleaned)
    weird = find_weird_punct(cleaned)
    if total > 98 and (len(smash) > 0 or len(weird) > 0):
        total = 98

    fixed = auto_fix_basic(cleaned, is_poem=(type_key == "puisi"))

    benar = (okS + okL + okC + okR + okN)[:18]
    kurang = (kS + kL + kC + kR + kN)[:18]
    perlu = (pS + pL + pC + pR + pN)[:18]

    return {
        "ok": True,
        "type": type_key,
        "score": int(total),
        "feedback": {
            "benar": benar,
            "kurang_tepat": kurang,
            "perlu_diperbaiki": perlu
        },
        "auto_fix": {"text": fixed},
        "breakdown": {
            "structure": b_str,
            "eyd": {
                "loaded": bool(eyd_report.get("loaded", False)),
                "counts": eyd_report.get("counts", {}),
                "top_violations": eyd_report.get("violations", [])[:8]
            },
            "meta": {
                "rubrik": RUBRIK,
                "kbbi_loaded": bool(KBBI_LOADED),
                "eyd_loaded": bool(EYD_LOADED),
                "subscores": {
                    "struktur": int(s_str),
                    "bahasa": int(s_lang),
                    "kejelasan": int(s_clr),
                    "kreativitas": int(s_crv),
                    "kerapihan": int(s_neat)
                },
                "bahasa_detail": sub_lang,
                "bahasa_meta": meta_lang,
                "kejelasan_detail": b_clr,
                "kreativitas_detail": b_crv,
                "kerapihan_detail": b_neat
            }
        }
    }

def main():
    payload = json.loads(sys.stdin.read() or "{}")
    type_key = payload.get("type", "informatif")
    text = payload.get("text", "")
    sys.stdout.write(json.dumps(evaluate(type_key, text), ensure_ascii=False))

if __name__ == "__main__":
    main()
