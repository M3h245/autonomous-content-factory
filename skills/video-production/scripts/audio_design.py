"""audio_design — self-generated (royalty-free) sound design for doodle videos.

* SFX synthesised from scratch and placed on the animation events the doodle engine reports:
  pop, scribble (marker on paper), whoosh, page flip, boing, thump (camera punch), ding.
* `playful_bed`: a light marimba/pizzicato/shaker bed in a major key; tempo, key, progression and pattern are seeded
  per video so a batch never shares one identical track.
* `mix`: voice + music (side-chain ducked under speech) + SFX (lightly ducked) → stereo 48 kHz float.
Nothing here is sampled from recordings, so every sound is self-generated and licence-free.
"""
from __future__ import annotations

import math

import numpy as np

SR = 48000


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(x.size, 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, x.size)


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x * (peak / m)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)[:n]
    if r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


# ----------------------------------------------------------------------------- SFX
def sfx_pop(rng) -> np.ndarray:
    t = _t(0.13)
    f0 = rng.uniform(520, 880)
    f = f0 * (0.45 + 0.55 * np.exp(-t / 0.03))
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.032)
    click = _band(rng.normal(0, 1, t.size), 2000, 9000) * np.exp(-t / 0.0025) * 0.35
    return _norm((body + click) * _env(t.size, 0.0015, 0.02), 1.0)


def sfx_scribble(rng, dur: float) -> np.ndarray:
    dur = float(np.clip(dur, 0.12, 1.4))
    t = _t(dur)
    noise = _band(rng.normal(0, 1, t.size), 1400, 6500)
    am = np.zeros(t.size)
    pos = 0.0
    while pos < dur:  # individual strokes
        L = rng.uniform(0.07, 0.19)
        a, b = int(pos * SR), int(min(dur, pos + L) * SR)
        if b > a:
            seg = np.sin(np.linspace(0, np.pi, b - a)) ** 0.7 * rng.uniform(0.55, 1.0)
            am[a:b] = np.maximum(am[a:b], seg)
        pos += L + rng.uniform(0.0, 0.05)
    squeak = 0.12 * np.sin(2 * np.pi * rng.uniform(2300, 3100) * t + 3 * np.sin(2 * np.pi * 7 * t))
    return _norm((noise + squeak) * am * _env(t.size, 0.01, 0.04), 1.0)


def sfx_whoosh(rng, dur: float = 0.32) -> np.ndarray:
    dur = float(np.clip(dur + 0.12, 0.2, 0.7))
    n = int(dur * SR)
    noise = rng.normal(0, 1, n)
    out = np.zeros(n)
    seg = 2048
    hop = seg // 2
    win = np.hanning(seg)
    for k, start in enumerate(range(0, n - seg, hop)):
        u = start / n
        fc = 350 + 3200 * math.sin(math.pi * u) ** 1.5
        chunk = _band(noise[start:start + seg] * win, fc * 0.6, fc * 1.6)
        out[start:start + seg] += chunk
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return _norm(out * env, 1.0)


def sfx_page(rng) -> np.ndarray:
    t = _t(0.34)
    noise = _band(rng.normal(0, 1, t.size), 500, 5000)
    flutter = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 26 * t))
    env = np.minimum(1, t / 0.04) * np.exp(-np.maximum(0, t - 0.06) / 0.08)
    return _norm(noise * flutter * env, 1.0)


def sfx_boing(rng, dur: float = 0.5) -> np.ndarray:
    t = _t(float(np.clip(dur, 0.35, 0.7)))
    f = rng.uniform(170, 240) * (1 + 0.42 * np.sin(2 * np.pi * 13 * t) * np.exp(-t / 0.22))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * np.exp(-t / 0.22)
    return _norm(x * _env(t.size, 0.003, 0.05), 1.0)


def sfx_thump(rng) -> np.ndarray:
    t = _t(0.22)
    f = 95 * (0.5 + 0.5 * np.exp(-t / 0.04))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / 0.07) + 0.5 * np.sin(2 * ph) * np.exp(-t / 0.04)
    x += _band(rng.normal(0, 1, t.size), 1500, 6000) * np.exp(-t / 0.004) * 0.3
    return _norm(x * _env(t.size, 0.001, 0.03), 1.0)


def sfx_ding(rng) -> np.ndarray:
    t = _t(0.9)
    f0 = rng.choice([1046.5, 1174.7, 1318.5])
    parts = [(1, 1.0, 0.55), (2.76, 0.45, 0.28), (5.4, 0.22, 0.15), (8.93, 0.1, 0.08)]
    x = sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-t / d) for r, a, d in parts)
    return _norm(x * _env(t.size, 0.002, 0.08), 1.0)


SFX_GAIN = {"pop": 0.30, "scribble": 0.10, "whoosh": 0.20, "page": 0.22, "boing": 0.22, "thump": 0.34, "ding": 0.20}


def schedule_sfx(events: list[dict], duration: float, seed: int = 7, density: float = 1.0) -> tuple[np.ndarray, list[dict]]:
    """Place SFX for engine events with sensible spacing rules. Returns (stereo track, events actually used)."""
    rng = np.random.default_rng(seed)
    n = int(duration * SR) + 1
    track = np.zeros((n, 2))
    used, last = [], {}
    scrib_until = -1.0
    recent: list[float] = []
    min_gap = {"pop": 0.10, "thump": 0.6, "whoosh": 0.25, "page": 0.3, "boing": 0.4, "ding": 0.5, "scribble": 0.0}
    for ev in sorted(events, key=lambda e: e["t"]):
        kind, t0 = ev["kind"], max(0.0, float(ev["t"]))
        if kind not in SFX_GAIN or t0 >= duration - 0.05:
            continue
        if kind == "scribble":
            if t0 < scrib_until - 0.05:   # merge overlapping draws into one continuous scribble
                continue
        elif t0 - last.get(kind, -9) < min_gap[kind]:
            continue
        recent = [x for x in recent if t0 - x < 1.0]
        if kind != "scribble" and len(recent) >= int(4 * density):
            continue
        if kind == "pop":
            x = sfx_pop(rng)
        elif kind == "scribble":
            dur = float(ev.get("dur", 0.4))
            # extend over overlapping draws that start within this one
            for other in events:
                if other["kind"] == "scribble" and t0 < other["t"] < t0 + dur:
                    dur = max(dur, other["t"] - t0 + other.get("dur", 0.3))
            dur = min(dur, 1.4)
            x = sfx_scribble(rng, dur)
            scrib_until = t0 + dur
        elif kind == "whoosh":
            x = sfx_whoosh(rng, float(ev.get("dur", 0.3)))
        elif kind == "page":
            x = sfx_page(rng)
        elif kind == "boing":
            x = sfx_boing(rng, float(ev.get("dur", 0.5)))
        elif kind == "thump":
            x = sfx_thump(rng)
        else:
            x = sfx_ding(rng)
        x = x * SFX_GAIN[kind] * density ** 0.5
        a = int(t0 * SR)
        b = min(n, a + x.size)
        pan = float(np.clip(rng.normal(0, 0.25), -0.6, 0.6))
        track[a:b, 0] += x[: b - a] * math.sqrt(0.5 * (1 - pan))
        track[a:b, 1] += x[: b - a] * math.sqrt(0.5 * (1 + pan))
        last[kind] = t0
        recent.append(t0)
        used.append({"t": round(t0, 3), "kind": kind})
    return track, used


# ----------------------------------------------------------------------------- music
PROGRESSIONS = [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4], [0, 3, 5, 4], [3, 0, 4, 5], [0, 2, 3, 4]]
SCALE = [0, 2, 4, 5, 7, 9, 11]
ARP_PATTERNS = [[0, 1, 2, 1, 3, 2, 1, 2], [0, 2, 1, 2, 0, 2, 3, 2], [0, 1, 2, 3, 2, 1, 2, None],
                [2, 1, 0, 1, 2, None, 3, 2], [0, None, 2, 1, 3, None, 2, 1]]


def _midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _marimba(f: float, dur: float = 0.5) -> np.ndarray:
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.28) + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t / 0.05)
    x += 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t / 0.018)
    return x * _env(t.size, 0.002, 0.03)


def _pluck_bass(f: float, dur: float = 0.55) -> np.ndarray:
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(4 * np.pi * f * t) * np.exp(-t / 0.08) + 0.15 * np.sin(6 * np.pi * f * t) * np.exp(-t / 0.04)
    return x * np.exp(-t / 0.32) * _env(t.size, 0.004, 0.05)


def _glock(f: float) -> np.ndarray:
    t = _t(0.8)
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.1)) * np.exp(-t / 0.4) * _env(t.size, 0.001, 0.05)


def playful_bed(duration: float, seed: int = 7) -> tuple[np.ndarray, dict]:
    rng = np.random.default_rng(seed)
    bpm = float(rng.choice([94, 98, 102, 106, 110]))
    root = int(rng.choice([60, 62, 65, 67, 57]))           # C, D, F, G, A (major keys)
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    pattern = ARP_PATTERNS[int(rng.integers(len(ARP_PATTERNS)))]
    beat = 60.0 / bpm
    n = int((duration + 1.0) * SR)
    mel, bass, perc = np.zeros(n), np.zeros(n), np.zeros(n)

    def add(buf, x, t0, g=1.0):
        a = int(t0 * SR)
        if a >= n:
            return
        b = min(n, a + x.size)
        buf[a:b] += x[: b - a] * g

    shaker = _band(rng.normal(0, 1, int(0.05 * SR)), 5000, 14000) * np.exp(-_t(0.05) / 0.012)
    knock = _band(rng.normal(0, 1, int(0.08 * SR)), 900, 3200) * np.exp(-_t(0.08) / 0.018)
    kick_t = _t(0.16)
    kick = np.sin(2 * np.pi * np.cumsum(60 * (0.6 + 0.4 * np.exp(-kick_t / 0.03))) / SR) * np.exp(-kick_t / 0.07)
    bars = int(math.ceil(duration / (4 * beat))) + 1
    for bar in range(bars):
        deg = prog[bar % len(prog)]
        chord = [root + SCALE[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
        tones = chord + [chord[0] + 12]
        t_bar = bar * 4 * beat
        for k, idx in enumerate(pattern):
            if idx is None or (bar == 0 and k < 2):
                continue
            jitter = rng.normal(0, 0.004)
            vel = (0.9 if k % 2 == 0 else 0.65) * rng.uniform(0.85, 1.0)
            add(mel, _marimba(_midi(tones[idx] + 12)), t_bar + k * beat / 2 + jitter, vel)
        for b, off in ((0, 0), (2, 7)):
            add(bass, _pluck_bass(_midi(chord[0] - 24 + off)), t_bar + b * beat, 0.9)
        if bar >= 1:
            for k in range(8):
                add(perc, shaker, t_bar + k * beat / 2 + beat / 4, 0.28 if k % 2 else 0.18)
            add(perc, knock, t_bar + beat, 0.30)
            add(perc, knock, t_bar + 3 * beat, 0.30)
            add(perc, kick, t_bar, 0.55)
        if bar % 4 == 3:
            add(mel, _glock(_midi(tones[2] + 24)), t_bar + 3.5 * beat, 0.25)
    mix = 0.55 * _norm(mel) + 0.45 * _norm(bass) + 0.22 * _norm(perc)
    mix = mix[: int(duration * SR)]
    fade = int(1.2 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    # gentle stereo: marimba slightly right, bass centre (Haas-free; mono-compatible)
    st = np.stack([mix * 0.96, mix], axis=1)
    keys = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return _norm(st, 0.9), {"bpm": bpm, "key": keys[root % 12] + " major", "progression": prog, "seed": seed}


# ----------------------------------------------------------------------------- mixer
def speech_envelope(voice: np.ndarray, attack: float = 0.01, release: float = 0.35) -> np.ndarray:
    """0..1 speech-activity envelope (smoothed absolute amplitude with fast attack / slow release)."""
    x = np.abs(voice)
    hop = 240
    frames = x[: x.size // hop * hop].reshape(-1, hop).max(axis=1)
    thr = max(0.02, 0.12 * np.percentile(frames, 95))
    act = (frames > thr).astype(float)
    a, r = math.exp(-hop / (attack * SR)), math.exp(-hop / (release * SR))
    env = np.zeros_like(act)
    v = 0.0
    for i, s in enumerate(act):
        v = (a * v + (1 - a) * s) if s > v else (r * v + (1 - r) * s)
        env[i] = v
    env = np.repeat(env, hop)
    return np.pad(env, (0, max(0, voice.size - env.size)))[: voice.size]


def music_component(music: np.ndarray, n: int, env: np.ndarray, music_db: float, duck_db: float = -9.0,
                    carve_db: float = 0.0) -> np.ndarray:
    """Music as it sits in the mix: gain + side-chain duck under speech, and (Phase 3) a dynamic cut of the speech band
    (300-4000 Hz) while someone is talking — the voice gets its own frequency room without lowering the bed overall."""
    m = np.zeros((n, 2))
    m[: min(n, music.shape[0])] = music[:n] if music.ndim == 2 else np.repeat(music[:n, None], 2, axis=1)
    g = (10 ** (music_db / 20) * 10 ** (duck_db * env / 20))[:, None]
    if carve_db:
        mid = np.stack([_band(m[:, c], 300, 4000) for c in range(2)], axis=1)
        m = (m - mid) + mid * (10 ** (-carve_db * env / 20))[:, None]
    return m * g


def mix(voice: np.ndarray, music: np.ndarray | None, sfx: np.ndarray | None, music_db: float = -19.0,
        duck_db: float = -9.0, sfx_duck_db: float = -3.0, carve_db: float = 0.0) -> np.ndarray:
    """voice: mono float @48k. Returns stereo float mix (unnormalised loudness; peak-safe)."""
    v = _norm(voice, 0.7)
    out = np.stack([v, v], axis=1)
    env = speech_envelope(v)[:, None]
    n = out.shape[0]
    if music is not None:
        out += music_component(music, n, env[:, 0], music_db, duck_db, carve_db)
    if sfx is not None:
        s = np.zeros((n, 2))
        s[: min(n, sfx.shape[0])] = sfx[:n]
        out += s * 10 ** (sfx_duck_db * env / 20)
    peak = np.max(np.abs(out))
    if peak > 0.98:
        out *= 0.98 / peak
    return out


def mix_report(voice: np.ndarray, music: np.ndarray | None, sfx: np.ndarray | None, music_db: float = -19.0,
               duck_db: float = -9.0, sfx_duck_db: float = -3.0, used: list | None = None, carve_db: float = 0.0) -> dict:
    """Measured balance of the mix as built by `mix` (same gains): music level under speech, SFX density/loudness."""
    v = _norm(voice, 0.7)
    env = speech_envelope(v)
    n = v.size
    sp = env > 0.5
    db = lambda x: float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))  # noqa: E731
    out = {"voice_rms_db": round(db(v[sp]), 1) if sp.any() else None, "music_under_voice_db": None,
           "sfx_per_s": round(len(used or []) / max(n / SR, 1e-6), 2), "sfx_near_voice_share": None}
    if music is not None:
        m = music_component(music, n, env, music_db, duck_db, carve_db).mean(axis=1)
        if sp.any():
            out["music_under_voice_db"] = round(db(v[sp]) - db(m[sp]), 1)
    if sfx is not None:
        s_ = np.zeros(n); s_[: min(n, sfx.shape[0])] = sfx[:n].mean(axis=1) if sfx.ndim == 2 else sfx[:n]
        s_ = s_ * 10 ** (sfx_duck_db * env / 20)
        w = 2400
        k = n // w
        if k:
            sv = np.sqrt((s_[: k * w].reshape(k, w) ** 2).mean(axis=1))
            vv = np.sqrt((v[: k * w].reshape(k, w) ** 2).mean(axis=1))
            out["sfx_near_voice_share"] = round(float(np.mean(sv > vv * 0.5)), 3)
    return out


# ============================================================================= Phase 3: density cap, speech protection, metrics
SFX_PRIORITY = {"page": 0, "whoosh_transition": 0, "thump": 1, "boing": 2, "ding": 2, "pop": 3, "whoosh": 4, "scribble": 5}


def cap_events(events: list[dict], duration: float, max_rate: float = 0.8, min_spacing: float = 0.35,
               tail_guard: float = 0.15) -> tuple[list[dict], dict]:
    """Deterministic SFX budget: at most `max_rate`·duration events, ≥ min_spacing apart, nothing whose tail would run
    into the last `tail_guard` s. Priority: transitions → camera punches → accents → pops → slides → scribbles."""
    budget = int(max_rate * duration)
    def pri(e):
        k = "whoosh_transition" if e["kind"] == "whoosh" and str(e.get("id", "")).startswith("transition:") else e["kind"]
        return SFX_PRIORITY.get(k, 6)
    kept, dropped = [], {"budget": 0, "spacing": 0, "tail": 0}
    for e in sorted(events, key=lambda e: (pri(e), e["t"], str(e.get("id")))):
        tail = e["t"] + min(max(float(e.get("dur", 0.2)), 0.12), 1.4)
        if tail > duration - tail_guard:
            dropped["tail"] += 1
        elif any(abs(e["t"] - k["t"]) < min_spacing for k in kept):
            dropped["spacing"] += 1
        elif len(kept) >= budget:
            dropped["budget"] += 1
        else:
            kept.append(e)
    return sorted(kept, key=lambda e: e["t"]), {"in": len(events), "kept": len(kept), "budget": budget, "dropped": dropped,
                                                "max_rate": max_rate}


def _frame_rms(x: np.ndarray, hop: int) -> np.ndarray:
    k = x.size // hop
    return np.sqrt((x[: k * hop].reshape(k, hop) ** 2).mean(axis=1) + 1e-12)


def protect_speech(voice: np.ndarray, sfx: np.ndarray, sfx_duck_db: float = -3.0, headroom_db: float = 12.0,
                   music_bed: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Where SFX in the speech band (300-4000 Hz) would sit within `headroom_db` of the voice during speech, attenuate
    the SFX there (50 ms frames, 10 ms ramps). Accounts for the ducking `mix` applies afterwards."""
    v = _norm(voice, 0.7)
    n = min(v.size, sfx.shape[0])                 # the SFX track may be one sample longer than the voice
    v = v[:n]
    env = speech_envelope(v)
    s_mono = sfx[:n].mean(axis=1) * 10 ** (sfx_duck_db * env / 20)
    hop = 2400
    vb, sb = _frame_rms(_band(v, 300, 4000), hop), _frame_rms(_band(s_mono, 300, 4000), hop)
    act = _frame_rms(env, hop) > 0.5
    # the SFX may only use the room the music leaves: (music + sfx) in the speech band stays headroom_db under the voice
    mb = _frame_rms(_band(music_bed[:n].mean(axis=1) if music_bed is not None and music_bed.ndim == 2 else
                          (music_bed[:n] if music_bed is not None else np.zeros(n)), 300, 4000), hop)
    allowed = np.maximum(vb ** 2 * 10 ** (-headroom_db / 10) - mb ** 2, (vb * 10 ** (-(headroom_db + 18) / 20)) ** 2)
    gain_db = np.where(act & (sb ** 2 > allowed), 10 * np.log10(allowed / sb ** 2), 0.0)
    g = np.repeat(10 ** (gain_db / 20), hop)
    g = np.pad(g, (0, max(0, sfx.shape[0] - g.size)), constant_values=1.0)[: sfx.shape[0]]
    ramp = int(0.01 * SR)
    g = np.convolve(g, np.ones(ramp) / ramp, mode="same")    # smooth the gain changes (no clicks)
    return sfx * g[:, None], {"frames_attenuated": int((gain_db < 0).sum()), "max_cut_db": round(float(-gain_db.min()), 1) if gain_db.size else 0.0}


def speech_masking(voice: np.ndarray, mixed: np.ndarray) -> dict:
    """Speech-to-interference ratio in the speech band during speech, measured on the actual mix
    (interference = mix − voice component)."""
    v = _norm(voice, 0.7)
    n = min(v.size, mixed.shape[0])
    inter = mixed[:n, 0] - v[:n]
    env = speech_envelope(v[:n])
    hop = 2400
    vb, ib = _frame_rms(_band(v[:n], 300, 4000), hop), _frame_rms(_band(inter, 300, 4000), hop)
    in_env = _frame_rms(env, hop) > 0.5
    lvl = 20 * np.log10(vb)
    # active speech (ITU-T P.56 style): frames whose speech-band level is within 16 dB of the voice's 95th percentile —
    # the pauses between words inside the envelope carry no speech to mask
    act = in_env & (lvl >= (np.percentile(lvl[in_env], 95) - 16 if in_env.any() else 0))
    sir = 20 * np.log10(vb[act] / ib[act]) if act.any() else np.array([99.0])
    return {"speech_frames": int(act.sum()), "envelope_frames": int(in_env.sum()), "sir_p5_db": round(float(np.percentile(sir, 5)), 1),
            "sir_median_db": round(float(np.median(sir)), 1), "frames_below_10db": round(float((sir < 10).mean()), 4)}


def ending_report(final: np.ndarray, music: np.ndarray | None) -> dict:
    """Clean ending: silence in the last 30 ms and a music fade (last 0.3 s ≥ 6 dB quieter than 1.5-1.2 s before end)."""
    tail = final[-int(0.03 * SR):]
    tail_db = 20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-9)
    fade = None
    if music is not None and music.shape[0] > int(1.6 * SR):
        m = music.mean(axis=1) if music.ndim == 2 else music
        a = np.sqrt(np.mean(m[-int(1.5 * SR):-int(1.2 * SR)] ** 2)) + 1e-9
        b = np.sqrt(np.mean(m[-int(0.3 * SR):] ** 2)) + 1e-9
        fade = round(float(20 * np.log10(a / b)), 1)
    return {"tail_30ms_dbfs": round(float(tail_db), 1), "music_fade_db": fade}
