# Singing Practice — Comprehensive Spec

A new main view in Fymuse next to Playground / Listener / Splitter. The most exhaustive vocal-training analysis tool available outside of pro studio software, tuned specifically for **Bollywood pop singers preparing for live performance**. Not a generic karaoke scorer.

This document is the canonical reference for the build. v1, v2, and v3 are phased — but the analysis engine, data model, and scoring framework are designed once, end-to-end, so v2/v3 features bolt on as feature flags rather than rewrites.

---

## 1. Vision and scope

The tool exists because consumer voice-training apps (Vanido, Singscope, Voice Tutor, etc.) fail Bollywood singers preparing for stage in three specific ways. First, they score Western pop rubrics — they penalize meend, harkat, taan, and microtonal raga inflection, which are *features* of good Bollywood singing, not flaws. Second, they don't model live performance demands — stamina decay across a setlist, projection (singer's formant), pitch stability under physical stress. Third, they measure but don't *prescribe* — you get a score but no plan for what to drill next session. This tool fixes all three.

Three design commitments shape every decision below:

It is **Bollywood-aware at the engine level**, not the cosmetic level. Raga-aware pitch scoring, ornament detection that credits rather than penalizes, vowel-space targets calibrated to Hindi/Urdu vowel formants, vibrato bands calibrated to Bollywood vocal style, timing tolerances that respect rhythmic flexibility.

It is **live-performance focused**. Stamina mode is a first-class phase, not an afterthought. Projection (singer's formant) is one of the eight scored dimensions. Setlist progression follows real stage pacing.

It **prescribes, not just measures**. Every session ends with a concrete drill list — three weakness-targeted exercises with reps, tempo, and acceptance criteria — that seeds the next session's Drill tab. The bridge between sessions is what makes compounding improvement possible.

The tool runs entirely in the browser. No server roundtrips for analysis. Mic audio never leaves the device. The Splitter handoff brings instrumental + reference vocal stems already cached locally.

---

## 2. Practice methodology — the five-phase session

A vocal practice session that actually builds the voice follows a fixed structure. The tool's UI is built around this structure to enforce it.

**Phase 1: Warm-up (5–8 minutes).** Wake the voice safely before asking it to do hard things. Lip trills bottom-to-top, sirens, octave scales on [ɑː], descending fifths for relaxation. The objective is not to practice the song. It is to verify the instrument is ready and capture *today's baseline* — your comfortable range, strain zone boundaries, current pitch accuracy on neutral material, current vibrato rate on a held vowel. Every later score in this session compares against this baseline.

**Phase 2: Range and control work (5–10 minutes, optional).** Targeted exercises for what the song demands. Passaggio jumps, sustained taans, head-voice access drills. Skipped on light days. Drawn from the prescription engine's queue.

**Phase 3: Spot practice — drill the hard phrases (10–20 minutes).** The highest-leverage phase and the one amateur singers skip. Pick the 2–4 hardest phrases in the song. Loop just those. Slow tempo first (70 percent), then on a vowel only (strip consonants), then with words, then at full tempo. Five to ten loops per phrase. If a phrase isn't clean in isolation, doing it once inside a full take won't fix it. The Drill tab automates the loop boundaries, tempo control, and per-loop scoring.

**Phase 4: Full take (10–15 minutes).** Sing the whole song against the backing track. *Don't stop mid-phrase even if something goes wrong.* This rehearses recovery — what live performance actually demands. The take is recorded and scored holistically.

**Phase 5: Review and notes (5 minutes).** Listen back. Read the evaluation. Note what worked, what didn't. The prescription engine produces a drill list for next session automatically; the textarea is for personal qualitative notes.

A serious live-prep regimen runs three or four such sessions per week with at least one Stamina session per week (Phase 4 extended to a full setlist).

---

## 3. Section architecture — fitting into Fymuse

Follows the established Listener / Splitter pattern exactly. Six additions:

A new header button `header-singer-btn` between Splitter and Songwriter. A new entry in `GENRES`: `singer: { name: 'Singing', isSinger: true, … }`. A `showSingerView()` function added next to `showSplitterView()`, with `'singer-view'` added to the `SUBVIEW_CHILDREN` set. A `view-singer` body-class toggle in `renderAll()`. A `renderSinger()` dispatcher in `renderAll()`. A `buildSingerViewSkeleton(root)` builder that mirrors the Listener / Splitter skeleton builders.

Cleanup on leave: when `renderAll()` detects the user is leaving Singer view, it tears down the mic stream, stops any active backing-track playback, stops any active recording, cancels any RAF loops — the same pattern Listener and Splitter use for their own resources.

Layout: Singer takes the full `graph-panel` area, like Listener and Splitter. The right-hand sidebar (key picker, sound picker, etc.) remains visible because key/mode is meaningful for in-key scoring. The Songwriter shutter, Path Finder, and Melody Mode side panels are auto-closed when entering Singer view.

Entry points:

- **Direct.** Click the Singing header button. User uploads a backing track (raw audio) directly.
- **From Splitter handoff.** The Splitter view gains a small "Practice singing this →" button that appears once stems are ready. Clicking it loads the instrumental stems (drums + bass + other, mixed inline) and vocals stem into Singer's `singerState.instrumentalBuffer` and `singerState.vocalBuffer`, then switches to Singer view. This is the recommended entry — reference-based scoring requires it.

---

## 4. UI structure — five phase tabs

The Singer view is dominated by five horizontal phase tabs: **Warm-up · Drill · Full Take · Stamina · Review**. Switching tabs is free (doesn't reset takes). The Review tab aggregates everything from the current session regardless of which tab generated it.

### 4.1 Warm-up

A vertical list of warm-up exercises with three preset routines: *Quick (5 min)*, *Standard (10 min)*, *Full (15 min)*. Each exercise is driven by Tone.js — piano cues play the target pattern, the user sings along, the mic captures the response.

Per-exercise UI shows the target pattern as a piano-roll strip (notes the user should sing), the user's live pitch as a moving dot overlaid on the target, a transport bar with start / stop / next, and a per-exercise summary at the end (accuracy, lowest-cleanly-sung note, highest-cleanly-sung note, average cents offset).

At the end of the routine the tab produces today's **baseline card**: comfortable range (lowest to highest *clean* note — defined as a note held ≥600 ms within ±50¢ of target), strain zone boundaries (the top and bottom 20% of the range where pitch accuracy drops >20%), baseline pitch accuracy on sargam, baseline vibrato rate on a held [ɑː], baseline RMS dynamic range. This card is pinned to the session and fed forward — every subsequent take's range and dynamics scores reference these numbers.

Warm-up exercises selected for the v1 routine: lip trills C3→C5 in semitone steps; descending fifths on [ɑː]; ascending and descending sargam on chosen raga; sustained [ɑː] crescendo-decrescendo (messa di voce) on each scale degree; one octave aakar sweep (lowest to highest) on a comfortable held [ɑː] for range capture.

### 4.2 Drill

Pre-requisite: a song loaded with both instrumental and vocal stems (the Splitter handoff path).

When the song loads, a phrase-extraction pass runs on the vocal stem: silence gaps ≥400 ms split the vocal into discrete phrases. Each phrase gets a difficulty score (range stretch × max F0 leap × note density × ornament density). Phrases are listed in a vertical queue, ordered by difficulty descending — the hardest stuff sits at the top, which is what should be drilled first.

Click a phrase. The transport now loops just that phrase. Three controls sit above the loop:

A tempo slider with snaps at 70 / 85 / 100 percent. Slowdown uses **SoundTouch.js** for time-stretching without pitch shift (Web Audio's native `playbackRate` shifts pitch, which destroys the practice value — you'd be drilling against the wrong pitch).

A "vocal guide" toggle: on plays the original vocal stem alongside the instrumental so you can sing along; off mutes the vocal stem entirely so the user is exposed.

A "record this loop" toggle: when on, every loop pass is captured to MediaRecorder and scored immediately on loop-end. The user sees their accuracy climb across loops — first loop 64%, second 71%, third 78%, etc. The phrase's "best score this session" is displayed.

Each phrase has a "mark clean" checkbox. Marking a phrase clean removes it from the drill queue. The next session, the engine re-queues phrases that haven't been touched in 5+ days (skill decays).

A "drill prescribed exercises" sub-tab inside Drill displays the prescription engine's output from last session — specific technical exercises (not song phrases) tied to weaknesses. These run with the same loop / tempo / record machinery, but the target is a Tone.js-generated pattern instead of an extracted phrase.

### 4.3 Full Take

Single full-song pass. Backing plays start to finish, instrumental-only by default with a vocal-guide toggle for the rare case the user wants the reference in their ear. A 4-beat count-in (rendered as a metronome click + visible "1 2 3 4" overlay) precedes the song start. Record button locks during the take — no pausing.

Visual during the take: a horizontal time strip shows the user where they are in the song. A live pitch indicator shows their current note + cents offset, but no reference contour overlay (the v1 user explicitly chose "Record-only, evaluate after"). The reference contour overlay is reserved for the Review tab playback.

On stop: the take is decoded, the full analysis pipeline runs (this takes 2–8 seconds depending on song length), and the Evaluation panel renders inline. The take is added to the session's take list and is now accessible from the Review tab.

### 4.4 Stamina

Two modes, user-selectable:

**Single-song stamina.** Three takes of the same song back-to-back, 60-second forced rest between takes. The engine plots per-take decay across the eight composite sub-scores. The clearest decay-readout — same demands, same notes, the only variable is the singer fatiguing.

**Setlist stamina.** A configurable queue of 3–5 songs. Default order follows real-show pacing: medium-difficulty opener → emotional ballad (head voice) → upbeat (chest-heavy) → climax piece (high range, sustained) → closer (sing-along, vocal rest). The user can reorder the queue, swap songs, or build their own setlist. Per-song full-take scoring runs as in 4.3, and a cumulative-decay overlay charts how the eight sub-scores trend across the set.

The decay deltas feed the prescription engine. *Pitch accuracy collapsed 20% by take 3* prescribes low-intensity sustained-vowel stamina-building drills. *Vibrato rate sped up by 1 Hz by song 4* prescribes diaphragmatic-breath retraining. *Singer's formant ratio dropped 30% in the last song* prescribes resonance drills with rest intervals.

### 4.5 Review

A chronological list of every recording from this session — warm-up readings, drill loops, full takes, stamina takes — tagged by phase. Click any take to open it. The take opens with synchronized playback (recording + reference vocal + instrumental, each independently mutable) and a full evaluation panel.

The Review tab also surfaces the **session summary**: today's strengths (top 2 sub-scores), today's weaknesses (bottom 3 sub-scores), the prescribed drill list for next session (auto-generated by the prescription engine), and a free-text notes field for personal qualitative observations. The summary persists in-memory until page reload; v3 adds persistence.

A "compare takes" toggle lets the user select two takes from the same song and view side-by-side pitch contours, score deltas, and a diff strip showing where the differences are concentrated.

---

## 5. The analysis engine

The engine is structured as five aggregation layers. Lower layers are dense and cheap; higher layers are sparse and semantically meaningful. The engine runs once per take, fully offline (no realtime constraint in v1 since Full Take is record-only).

### 5.1 Frame-level features (20 ms hop, 2048 sample window at 48 kHz)

For each frame the extractor produces:

**F0 (fundamental frequency)** via HPS + parabolic interpolation (reuses `splitterDetectMonophonicNotes` machinery). Cents-from-target where target is the active scoring reference (raga-aware target, see §6.1).

**RMS** (linear) and **dB-RMS** (with EMA noise floor for voicing decisions).

**Voicing flag** — boolean: is this frame a sung note, breath, consonant, or silence? Decision: F0 is found, peak HPS strength above 15% of session median, dB-RMS above noise floor + 12 dB.

**Spectral centroid** (Hz) — energy-weighted mean frequency. Brightness indicator.

**Spectral tilt** (dB/octave) — slope of log-magnitude spectrum 200 Hz to 4 kHz. Voice quality / chest-vs-head indicator.

**Spectral rolloff** (Hz at 85% cumulative energy) — bandwidth indicator.

**Spectral flux** (frame-to-frame magnitude change L2 norm) — for onset detection.

**HNR (harmonics-to-noise ratio)** in dB — strength of harmonic structure vs noise floor in the spectrum. Breathiness indicator. v1: from harmonic-peak sum vs total energy. v2: full autocorrelation-based HNR.

**H1–H2** (dB) — amplitude of first harmonic minus second harmonic. Fold-closure indicator (positive = lax/breathy, negative = pressed/forced).

**Singer's formant ratio** — energy in 2.4–3.4 kHz band as fraction of total 0–8 kHz energy. Projection indicator. Above 0.10 is excellent for stage.

**Formant estimates F1, F2** (Hz) via LPC (12th order at 48 kHz). v2 feature; not extracted in v1.

**Cepstral peak prominence (CPP)** in dB — peak in cepstrum relative to regression line through cepstrum. Robust voice-quality indicator. v2.

Frame outputs are stored as parallel typed arrays in `singerState.frames` — F0[], rms[], voiced[], centroid[], etc. — keeping memory contiguous and aggregation fast.

### 5.2 Note-level aggregation

A note event starts when voicing turns on and ends when voicing turns off or F0 jumps by more than a configurable threshold (default: 70¢ within a single frame triggers a new note; smooth glides under that threshold stay within the same note event and become a *meend* — see §6.2).

Per-note attributes computed: start time, end time, duration, F0 trajectory (the slice of frame F0 array), centered F0 (median F0 minus target), F0 stability (intra-note F0 stdev), entry attack shape (scoop / swoop / straight / glide — classified from the first 100 ms of F0 trajectory relative to median), release shape (last 100 ms), vibrato presence and parameters (see §6.3), peak RMS, attack envelope (time from voicing-on to peak RMS), sustain envelope, breath/consonant fraction (frames inside the note that were unvoiced), centroid mean, spectral tilt mean, singer's formant mean.

Notes are also tagged with their position in the reference vocal — which reference note they align to under a DTW (dynamic time warping) alignment of the take's voiced segments against the reference's voiced segments. DTW alignment runs once per take and produces a per-frame mapping `takeFrame → refFrame`.

### 5.3 Phrase-level aggregation

Phrases are inherited from the reference vocal's phrase segmentation (silence gap ≥400 ms). The user's take's notes are bucketed into reference phrases by DTW alignment.

Per-phrase attributes: phrase index, start time (take), end time (take), reference duration, take duration, note count (take vs reference), per-note pitch accuracy mean, ornament events detected (see §6.2), vibrato usage (which notes got vibrato), dynamic arc shape (slope-fit of phrase RMS envelope), onset offset distribution (per-note start-time deltas vs reference), perceived difficulty (the difficulty score that ordered the phrase in the Drill queue).

### 5.4 Take-level aggregation

The 60+ features that constitute the full Bollywood-aware vocal analysis fall out of phrase- and note-level aggregation:

**Pitch dimension.** Mean pitch accuracy (cents-within-tolerance fraction), centering bias (median cents offset across all voiced frames), pitch stability (mean intra-note F0 stdev), pitch leap accuracy (per-note start-pitch accuracy on jumps >6 semitones), microtonal drift (linear regression of median-cents-offset against take time — negative slope means going flat as you tire).

**Ornament dimension.** Meend count, mean meend duration, mean meend pitch span; harkat count and rate per minute; murki count; taan event count, mean taan tempo, mean taan accuracy; khatka count. Combined into an "ornamentation richness" score weighted by the song's reference ornament density (so an empty Western pop song with no ornaments doesn't punish a clean Western-pop-style take).

**Vibrato dimension.** Fraction of sustained-note frames with detected vibrato, mean rate (Hz), mean extent (cents), regularity (sine-fit residual mean), mean onset delay (ms from note start to vibrato onset), classification distribution (straight / vibrato / wobble / tremolo).

**Dynamics dimension.** Dynamic range (loudest minus quietest voiced RMS, dB), shimmer (mean intra-note RMS variance), attack envelope distribution (soft/medium/hard onset counts), per-phrase crescendo slope mean, sustain energy stability.

**Texture / timbre dimension.** Mean spectral centroid (Hz), mean tilt (dB/oct), mean HNR (dB), mean H1–H2 (dB), CPP (v2), register classification distribution (v2).

**Projection dimension.** Mean singer's formant ratio, mean onset rise time (ms), peak singer's formant ratio.

**Range dimension.** Lowest voiced note (MIDI), highest voiced note (MIDI), range span (semitones), time-in-strain-zone fraction (frames whose F0 was above the warm-up's strain-zone boundary), tessitura center (median sung F0 weighted by note duration).

**Timing dimension.** Mean onset offset (ms, signed), median onset offset (ms, signed), onset offset IQR (ms — consistency), rubato-detected sections count (sections with high IQR but low mean offset indicate intentional rubato, not sloppy timing).

**Breath dimension.** Detected breath events count, mean breath duration, longest sustained phrase, phrase-end energy drop frequency (phrases where the last 300 ms dropped >6 dB — running-out-of-breath flag).

**Style markers.** Belt fraction, head-voice fraction, falsetto fraction, mix-voice fraction (all v2 — require register classification from §5.1 formants), aalap-section detection (free-time intros).

### 5.5 Session-level aggregation

Across all takes in the session: trend slopes for each take-level dimension (improving / steady / degrading across takes), single-best take per song, fatigue index (stamina-mode-specific — decay across takes), prescription input vector (the set of dimensions where the user's session-best is meaningfully below the song's reference).

---

## 6. Bollywood-specific scoring rubric

This section overrides Western-pop defaults. Everywhere a Western-pop scorer would dock points, the Bollywood scorer either credits the same behavior or ignores it.

### 6.1 Raga-aware pitch

The user tags each loaded song with a tonal framework: **Major**, **Minor**, or one of five v1 ragas — **Bhairavi**, **Yaman**, **Kafi**, **Khamaj**, **Bhairav**. The picker sits next to the existing Key picker in the header; together (Key + Raga) they define the active scoring reference.

Scale-degree structure (semitones from Sa = tonic):

| Raga      | Sa | Re      | Ga      | Ma       | Pa | Dha     | Ni      |
|-----------|----|---------|---------|----------|----|---------|---------|
| Bhairavi  | 0  | komal 1 | komal 3 | shuddha 5| 7  | komal 8 | komal 10|
| Yaman     | 0  | 2       | 4       | teevra 6 | 7  | 9       | 11      |
| Kafi      | 0  | 2       | komal 3 | 5        | 7  | 9       | komal 10|
| Khamaj    | 0  | 2       | 4       | 5        | 7  | 9       | komal 10|
| Bhairav   | 0  | komal 1 | 4       | 5        | 7  | komal 8 | 11      |
| Major     | 0  | 2       | 4       | 5        | 7  | 9       | 11      |
| Minor     | 0  | 2       | 3       | 5        | 7  | 8       | 10      |

Microtonal tuning offsets (cents from 12-TET) per raga, sourced from Hindustani performance-practice measurements (Daniélou, Bhatkhande, and contemporary measured-singer corpora). These shift the *target* the scorer compares F0 against. The implementation stores these as a JSON table at `singer/raga-shrutis.json`:

For Bhairavi, common practice offsets: komal Re ≈ -90¢, komal Ga ≈ -16¢ from the 3-semitone position, komal Dha ≈ -16¢, komal Ni ≈ -16¢. For Yaman: teevra Ma ≈ +6¢ to +20¢ depending on phrase context. For Bhairav: komal Re ≈ -90¢ to -100¢ (often quite flat in performance), komal Dha similar. For Kafi and Khamaj: more equal-tempered, with the komal Ni often falling neutral 12-TET position.

Pitch accuracy scoring then computes cents-from-target where target is the raga-shifted scale degree closest to the F0. The default acceptance band is ±50¢ (within band = perfect score), ramping linearly to 0 score by ±150¢. Pitch outside ±150¢ counts as off-key. The scorer applies this per voiced frame, weights by frame RMS (so loud-and-pitched frames count more than soft-and-pitched), and outputs the fraction "in band" as the pitch accuracy sub-score.

For songs without raga inflection (some modern Bollywood pop is fully Western harmonic), the user picks Major or Minor and scoring is equal-tempered. Songs heavy with raga character (ballads, classical-leaning material) use the raga tuning. v2 may add automatic raga detection from the reference vocal's F0 distribution.

### 6.2 Ornament detection and credit

Five ornament types, each with a dedicated detector running over the take's voiced-frame F0 array. Each detected ornament emits an event with start time, end time, type, and quality score (0–100). Ornaments are *credited*: each contributes positively to the Ornamentation Richness sub-score, and pitch frames *inside* an ornament are excluded from the strict pitch-accuracy denominator (so a glide passing through 50¢ off-target on the way to a clean landing doesn't count as off-pitch).

**Meend (glide).** A continuous F0 trajectory ≥200 ms in duration where the F0 changes monotonically by more than 70¢ between two stable target pitches and where the per-frame F0 derivative stays bounded (no sudden jumps). Quality factors: smoothness (low derivative variance is high quality), span (wider spans within reason are higher quality), endpoint accuracy (landing on the target pitch within ±30¢ is required).

**Harkat (grace note / fast ornament).** A brief F0 excursion of 100–400¢ that lasts 40–120 ms before returning to within 30¢ of the originating pitch. Quality factors: clean return (post-harkat F0 settles back to within tolerance), pitch span (>200¢ excursions are scored higher), distinct from vibrato (must not be periodic).

**Murki (turn).** A sequence of 3–5 adjacent F0 excursions around a central pitch within 250 ms total. The classic pattern is "main → upper neighbor → main → lower neighbor → main." Detected as a clustered sequence of micro-harkats with alternating sign.

**Taan (fast scale run).** A sequence of ≥4 distinct pitched notes within 500 ms, each note ≥40 ms, with F0 jumps approximating scale-degree intervals. Quality factors: tempo (notes per second), accuracy (each note's centered F0 within tolerance), evenness (note-duration variance).

**Khatka (mordent).** A single-cycle excursion: main pitch → adjacent pitch (≤200¢ away) → main pitch, all within 80–200 ms. Distinguished from harkat by the single-cycle, adjacent-pitch constraint.

Detector implementation notes: each runs as a one-pass scan over the voiced-frame F0 array with a state machine. Detection thresholds are calibrated against a reference corpus of measured Bollywood takes (TBD: assemble during build — likely 20–30 short clips from known singers spanning ornament types). The detectors are deliberately conservative — false-negative is preferred over false-positive, since false-positive credits inflate the score.

Ornamentation Richness sub-score: `(detected_count_weighted / reference_count_weighted)` capped at 1.2 (slight bonus possible for over-ornamenting where the reference is sparse, since a singer adding tasteful extra ornaments is rarely a flaw). Reference is the reference vocal's ornament count from the same detectors run on the reference stem.

### 6.3 Vibrato — Bollywood band

Vibrato detection runs per sustained note (duration ≥300 ms). Bandpass the note's F0 trajectory at 3.5–9 Hz. Peak-pick the periodicity. Extract:

**Rate** (Hz): cycle rate of the periodic F0 modulation. Healthy Bollywood range: 4.5–7.5 Hz. Below 4 Hz: too slow (sounds wobbly). Above 8 Hz: tremolo (sounds nervous).

**Extent** (cents): peak-to-peak F0 modulation amplitude. Healthy Bollywood range: 80–200¢. Below 50¢: barely-vibrato / straight tone. Above 250¢: wobble.

**Regularity** (0–1): how well a sine wave at the detected rate fits the F0 modulation. 1.0 = perfect sinusoid, <0.5 = chaotic / wobble.

**Onset delay** (ms): time from note voicing-on to the first vibrato cycle reaching half-extent. Trained Bollywood singers often start straight and *introduce* vibrato 200–400 ms in. Onset delay >150 ms is rewarded (delayed-vibrato is a stylistic positive); onset delay <50 ms is acceptable but not bonus.

**Depth modulation** (0–1): does the extent grow over the note's duration (crescendo into vibrato) or stay flat? Crescendo into vibrato is rewarded.

**Classification**: straight (rate <3 Hz or extent <50¢), vibrato (rate 4.5–7.5 Hz, extent 80–200¢, regularity >0.6), wobble (extent >250¢ or regularity <0.5), tremolo (rate >8 Hz).

Vibrato sub-score: weighted blend — 40% (in-band rate and extent), 25% (regularity), 20% (onset-delay bonus when delayed), 15% (vibrato-use rate, i.e., did you put vibrato on appropriate notes — long sustained notes should get vibrato; short notes shouldn't).

### 6.4 Timing — style-aware

Bollywood timing tolerance: ±60 ms acceptance band on onset offset, ramping to 0 by ±200 ms. Western pop would use ±30 ms / ±150 ms. The slacker band reflects rhythmic flexibility that's stylistically correct.

**Aalap-section detection.** Some Bollywood songs (and most Hindustani-leaning material) open with a free-time aalap — single vowel, no clear pulse, no fixed tempo. The engine detects aalap sections from the reference vocal: rolling window where the reference vocal's onset count is low (<2 onsets per 4 seconds) and the instrumental's energy in 80–500 Hz (bass+kick band) is low. Aalap sections have *zero* timing weight in the composite — pure free-time singing should not be timing-scored.

**Rubato vs sloppy.** A section with high onset-offset variance but low mean offset (around zero) is rubato — intentional flexibility. A section with high variance and a directional bias (consistently late or consistently early) is sloppy. The timing sub-score distinguishes these and penalizes only the latter.

### 6.5 Vowel space — Hindi/Urdu (v2 feature, deferred)

Canonical Hindi vowel formant targets (F1, F2 in Hz, from published Hindi acoustic phonetics literature):

| Vowel | F1     | F2     | Notes |
|-------|--------|--------|-------|
| आ (ɑː) | 700-800 | 1100-1300 | Open back, the dominant Bollywood sustained vowel |
| ई (iː) | 280-360 | 2200-2500 | Close front |
| ऊ (uː) | 280-360 | 700-900   | Close back |
| ए (eː) | 400-500 | 1900-2200 | Close-mid front |
| ओ (oː) | 450-550 | 800-1000  | Close-mid back |

Vowel-purity scoring (v2): on sustained notes ≥400 ms, extract F1/F2 via LPC (12th order). Compare against canonical Hindi targets weighted by the lyric's vowel at that timecode (requires lyric alignment — also v2). Distance in Bark-scale formant space yields vowel-purity score. Western mouth-shape on Hindi vowels shows up as F1/F2 offsets toward English equivalents — the score catches it.

v1 does not implement vowel-purity scoring. The infrastructure exists (LPC formant extraction can run from the same frame-level features), but lyric alignment is a substantial v2 addition.

---

## 7. Composite score

A single 0–100 number per take, computed as a weighted blend of eight sub-scores. The weighting reflects what matters for Bollywood live performance.

| Sub-score                | Weight | Source                                           |
|--------------------------|--------|--------------------------------------------------|
| Pitch accuracy           | 25%    | §5.4 pitch dim, raga-aware (§6.1)                |
| Ornamentation richness   | 15%    | §5.4 ornament dim (§6.2)                         |
| Vibrato quality          | 15%    | §5.4 vibrato dim (§6.3)                          |
| Timing                   | 10%    | §5.4 timing dim, style-aware (§6.4)              |
| Dynamics & expression    | 10%    | §5.4 dynamics dim                                |
| Projection (singer's F)  | 10%    | §5.4 projection dim                              |
| Range & control          | 10%    | §5.4 range dim + warm-up baseline                |
| Stamina decay (when applicable) | 5%    | §5.5 cross-take decay (stamina mode only)       |

In non-stamina takes the stamina-decay slice is redistributed proportionally across the other seven. The composite is displayed prominently next to each take. Each sub-score is independently visible and expandable into its per-feature breakdown.

Style sub-rubrics (v2): the same eight dimensions are re-weighted for Bollywood-ballad (down-weight timing, up-weight vibrato), Bollywood-EDM (up-weight timing and projection, down-weight ornament), ghazal (up-weight ornament heavily, down-weight projection), qawwali (up-weight projection and stamina, up-weight ornament). v1 ships only the base Bollywood-pop weighting.

---

## 8. Exercise bank

The exercise bank is the substrate for warm-up routines, range/control work, drill prescriptions, and stamina rest exercises. Each exercise is a structured object: `{ id, name, family, description, tags, target_pattern, duration_sec, difficulty, voice_register, language }`. The `tags` field is what the prescription engine matches against — tags like `vibrato-rate-trainer`, `singers-formant`, `pitch-centering`, `passaggio`, `taan-builder`, `stamina-low-intensity`.

v1 ships ~25 exercises distributed across five families.

### 8.1 Foundations (Western/universal) — 5 exercises

**Lip trills full-range.** Sustained lip trill ascending C3 to C5 (or comfortable equivalent) in chromatic steps, then descending. Forces relaxed phonation, builds breath stamina. 90 seconds. Tags: `breath`, `warm-up-essential`, `relaxation`.

**Descending fifths on [ɑː].** Pattern: do-mi-sol-mi-do, descending one semitone per repetition. Loosens vocal folds, encourages relaxed head-voice access. 60 seconds. Tags: `warm-up-essential`, `head-voice-access`, `relaxation`.

**Octave arpeggio on [oː].** Pattern: do-mi-sol-do'-sol-mi-do, ascending one semitone per repetition. Builds octave-leap accuracy and register-blend. 90 seconds. Tags: `pitch-leap-accuracy`, `register-blend`.

**Messa di voce on each scale degree.** Hold [ɑː] on each scale degree for 6 seconds, crescendo first 3 seconds, decrescendo last 3 seconds. Builds dynamic control and breath efficiency. 2 minutes. Tags: `dynamics-control`, `breath`, `sustain`.

**Five-tone scale on [iː].** Ascend/descend do-re-mi-fa-sol on [iː], one semitone per rep. Builds forward placement, encourages singer's formant. 90 seconds. Tags: `singers-formant`, `forward-placement`, `vowel-target-iː`.

### 8.2 Sargam and paltas — 6 exercises

**Plain ascending/descending sargam (chosen raga).** Sa-Re-Ga-Ma-Pa-Dha-Ni-Sa' and back. One octave. The structural backbone. 60 seconds. Tags: `raga-internalization`, `scale-fluency`, `pitch-centering`.

**Palta-1: 3-note ascending groups.** Sa-Re-Ga / Re-Ga-Ma / Ga-Ma-Pa / Ma-Pa-Dha / Pa-Dha-Ni / Dha-Ni-Sa'. Then descending. Builds intra-scale fluency. 90 seconds. Tags: `scale-fluency`, `agility`.

**Palta-2: 4-note groups.** Sa-Re-Ga-Ma / Re-Ga-Ma-Pa / Ga-Ma-Pa-Dha / etc. 90 seconds. Tags: `agility`, `taan-prep`.

**Palta-3: zigzag.** Sa-Ga-Re-Ma / Re-Ma-Ga-Pa / Ga-Pa-Ma-Dha / etc. Non-linear pitch leaps within the scale. Builds interval accuracy. 120 seconds. Tags: `pitch-leap-accuracy`, `interval-training`.

**Palta-4: cross-octave.** Sa-Re-Ga-Ma | Sa-Re-Ga-Pa | Sa-Re-Ga-Dha | Sa-Re-Ga-Ni | Sa-Re-Ga-Sa'. Builds upper-range access. 90 seconds. Tags: `range-extension-upper`, `head-voice-access`.

**Palta-5: descending fast.** Full descending sargam at 160 BPM eighths, looped. Builds top-down agility. 60 seconds. Tags: `agility`, `taan-builder-descending`.

### 8.3 Aakar — 5 exercises

**Long-tone aakar across range.** Sustain [ɑː] for 8 seconds on each semitone from lowest comfortable to highest comfortable. The canonical tone-building drill. 3 minutes. Tags: `tone-building`, `range-extension`, `sustain`, `breath`.

**Messa di voce aakar.** Same as long-tone aakar but with crescendo-decrescendo shape on each note. 3 minutes. Tags: `dynamics-control`, `breath`, `sustain`.

**Aakar with delayed vibrato.** Sustain [ɑː] for 6 seconds: first 2 seconds straight, then introduce vibrato gradually over next 4 seconds. Trains delayed-onset vibrato. 90 seconds. Tags: `vibrato-onset-delay`, `vibrato-control`.

**Two-octave aakar sweep.** Single sustained [ɑː] slides from lowest comfortable through highest comfortable and back, over 8 seconds. Builds connected-voice range. 60 seconds. Tags: `meend-control`, `range-connection`, `register-blend`.

**Aakar over chord changes.** Sustain [ɑː] while Tone.js plays a 4-chord progression underneath (e.g., I-vi-IV-V in chosen key). Trains pitch stability across changing harmonic context. 2 minutes. Tags: `pitch-stability`, `harmonic-context`.

### 8.4 Ornament drills — 5 exercises

**Meend on every scale degree.** Slow glide from Sa up to each scale degree (Re, Ga, Ma, Pa, Dha, Ni, Sa') and back, 2 seconds up + 2 seconds down. Trains controlled meend with clean endpoints. 2 minutes. Tags: `meend-control`, `pitch-leap-accuracy`.

**Harkat pattern: 3-note clusters.** Pattern: Sa-Re-Sa-Ga-Sa, fast, on a fixed tonic. Repeat with Sa-Ga-Sa-Pa-Sa, Sa-Pa-Sa-Sa'-Sa. Builds harkat agility. 90 seconds. Tags: `harkat`, `agility`.

**Murki turns.** Around each scale degree: Sa-Re-Sa-Ni(prev)-Sa, Re-Ga-Re-Sa-Re, Ga-Ma-Ga-Re-Ga, etc. Builds turn agility. 2 minutes. Tags: `murki`, `ornament`.

**Taan-builder (variable tempo).** Ascending Sa-Re-Ga-Ma-Pa-Dha-Ni-Sa' starting at 60 BPM eighths, increment 5 BPM per pass until the user marks "break point." The break point becomes the prescription target for next session — beat the previous break point. 3 minutes. Tags: `taan-builder`, `agility`, `progress-tracked`.

**Khatka mordent practice.** On a held Sa: Sa-Re-Sa as a fast single ornament. Then on each scale degree. Trains single-cycle mordent. 90 seconds. Tags: `khatka`, `ornament`.

### 8.5 Live-prep / projection — 4 exercises

**"Ng" → [ɑː] resonance.** Sustain "ng" (back-of-tongue closure) for 2 seconds, then open to [ɑː] for 4 seconds, holding the resonance position. Forces engagement of the singer's formant. 90 seconds. Tags: `singers-formant`, `resonance`, `projection-builder`.

**Sustained [iː] forward placement.** 6-second [iː] sustains on each scale degree, focusing on forward-mask resonance. 2 minutes. Tags: `forward-placement`, `singers-formant`, `vowel-target-iː`.

**Nasal-to-open transitions.** [m] for 1 second → [mɑː] for 4 seconds, keeping the resonance from the nasal carrier in the open vowel. 90 seconds. Tags: `resonance`, `forward-placement`.

**Volume-without-strain test.** Sustain [ɑː] at increasing intensity (mp → mf → f → ff) on each comfortable note, monitor singer's formant ratio — the score should *increase* with intensity, not decrease (decrease = pushing chest, which fails live). 2 minutes. Tags: `projection`, `singers-formant`, `dynamics-control`, `progress-tracked`.

v2 expands to ~50 exercises adding ghazal-specific ornament drills, qawwali stamina drills, sargam in additional ragas (Marwa, Todi, Bilaval, Asavari, Bageshri), passaggio-specific exercises, and recovery exercises (for use between stamina-mode takes).

---

## 9. Prescription engine

After every take, the engine compares the take's eight sub-scores against three reference levels: the warm-up baseline (today, this user), the reference vocal (this song), and a published competence threshold (per dimension). A weakness is registered when the take's sub-score falls below the smallest of the three by more than 10%.

A weakness vector for the session is the union of all takes' weaknesses, ranked by severity (sub-score deficit × frequency across takes).

The prescription engine matches weaknesses against exercise tags and produces a **next-session drill list** — the top 3 weaknesses with 1–2 exercises each. Mapping rules live in a JSON table at `singer/prescriptions.json`. Examples of mapping rules:

*Weakness: pitch centering (median offset > 15¢).* → Prescribe: messa di voce on each scale degree (tag `pitch-centering`) + tone-fork drone exercise.

*Weakness: vibrato rate > 7.5 Hz.* → Prescribe: messa di voce aakar at 60 BPM with deliberate slow vibrato + delayed-vibrato aakar.

*Weakness: vibrato regularity < 0.5.* → Prescribe: long-tone aakar with metronome-clicked vibrato cycles.

*Weakness: singer's formant ratio < 0.08.* → Prescribe: "ng" → [ɑː] resonance + sustained [iː] forward placement.

*Weakness: taan accuracy < 60% at song's reference tempo.* → Prescribe: taan-builder starting at the user's current break-point tempo, plus palta-2 at 90% of break-point.

*Weakness: time-in-strain-zone > 30%.* → Prescribe: descending fifths + two-octave aakar sweep for range relaxation, plus a recommendation to transpose the song down by 2 semitones.

*Weakness: pitch accuracy dropped >15% by take 3 in stamina mode.* → Prescribe: low-intensity stamina-building (sustained [ɑː] at mp for 5 minutes continuous) before next session's Drill phase.

*Weakness: ornament richness < 0.6× reference.* → Prescribe: harkat 3-note clusters + murki turns at slow tempo.

*Weakness: meend endpoint accuracy < 80%.* → Prescribe: meend on every scale degree, slow first then up to tempo.

*Weakness: phrase-end energy drop >6 dB on >25% of phrases.* → Prescribe: long-tone aakar with breath-target durations (6s → 8s → 10s holds).

*Weakness: belt fraction > head fraction but song reference reverses this (v2).* → Prescribe: descending fifths + octave arpeggio on [oː] for head-voice access; flag song as "register-mismatched, consider transposition."

The list of mapping rules grows with the exercise bank — v2 adds ~30 more rules, v3 adds rules tied to cross-session trends ("you've stalled on taan-builder break-point for 3 sessions; switch to palta-5 for variety").

The prescribed exercises seed next session's Drill tab. The user can override, but the default is "the engine picked these because of how you sang yesterday."

---

## 10. Stamina mode — detail

Already described in §4.4. Implementation specifics:

Between-take rest enforcement: a 60-second timer with a soft chime at 0:50. The Record button is locked during rest. The user can extend rest manually but cannot skip it — fatigue analysis requires consistent recovery intervals across takes.

Stamina-decay metric: per sub-score, compute the slope of (take_score) vs (take_index) within the stamina session. Steep negative slopes indicate poor stamina on that dimension. The Stamina sub-score in the composite (5%) is `100 - (mean absolute slope across all dimensions × 30)`, clamped 0–100. A flat-decay (steady performance across takes) scores ~100; aggressive decay scores near 0.

Setlist mode song selection: at v1, the user manually selects songs from the Splitter History. The default ordering applied: load all selected songs' reference vocal ranges; sort by ascending median pitch (low songs first, high songs at climax); within similar pitch, sort by ascending difficulty score. v2 may add a "warm-up song" / "climax song" / "closer" tagging system and a smarter sort.

Inter-song instrumental transitions: optional 30-second silence between songs (default) or user-uploaded transition audio (e.g., applause loop, MC patter — for full live simulation).

---

## 11. Technical plumbing

### 11.1 Data model

```
singerState = {
  active: bool,               // mic is open
  phase: 'warmup' | 'drill' | 'fulltake' | 'stamina' | 'review',
  audioCtx: AudioContext,
  micStream: MediaStream,
  micSource: MediaStreamAudioSourceNode,
  fftAnalyser: AnalyserNode,  // for live readouts only — not for offline analysis
  recorder: MediaRecorder,
  recording: bool,
  recordChunks: Blob[],

  // Loaded song
  songId: string | null,      // from Splitter History
  instrumentalBuffer: AudioBuffer | null,
  vocalBuffer: AudioBuffer | null,
  raga: 'major' | 'minor' | 'bhairavi' | 'yaman' | 'kafi' | 'khamaj' | 'bhairav',
  referencePhrases: Phrase[], // extracted from vocalBuffer
  referenceNotes: Note[],     // extracted via splitterDetectMonophonicNotes
  referenceFeatures: TakeFeatures | null,  // full analysis of reference

  // Backing track playback
  trackPlaying: bool,
  trackStartCtxTime: number,
  trackOffset: number,
  trackSource: AudioBufferSourceNode | null,
  vocalGuide: bool,           // play vocal stem alongside backing
  tempoRatio: 1.0 | 0.85 | 0.7,
  soundTouchNode: AudioWorkletNode | null,  // for time-stretching

  // Session state
  warmupBaseline: BaselineCard | null,
  takes: Take[],              // every recording from this session
  currentDrillPhraseId: string | null,
  drillProgress: { [phraseId]: { loops: number, bestScore: number, marked_clean: bool } },
  prescription: PrescribedExercise[] | null,
  sessionNotes: string,

  // Stamina state
  staminaMode: 'single-song' | 'setlist' | null,
  staminaQueue: string[],     // song IDs
  staminaCurrentIdx: number,
  staminaRestTimer: number,
};
```

Take, Phrase, Note, BaselineCard, TakeFeatures, PrescribedExercise are all typed records with documented shapes. The full schemas live in `singer/types.md` (to be written during build).

### 11.2 New code modules

All inline in `index.html` for consistency with the rest of Fymuse, but logically separated by clear section comments:

`singerFeatures` — the frame-level extractor (§5.1). Pure functions, no DOM, no state. Operates on Float32Array audio buffers.

`singerAggregate` — note/phrase/take/session aggregation (§5.2–5.5). Pure functions.

`singerOrnaments` — five ornament detectors (§6.2). Pure functions.

`singerScoring` — composite scoring, raga-aware pitch (§6.1), vibrato rubric (§6.3), timing rubric (§6.4), all sub-score computation, composite weighting (§7).

`singerExercises` — the exercise bank (§8). Static data + a function to render an exercise into a Tone.js playable pattern.

`singerPrescribe` — the prescription engine (§9). Static rules table + the weakness → exercise matching algorithm.

`singerView` — DOM construction. `buildSingerViewSkeleton(root)`, `renderSinger()`, per-tab renderers (`renderWarmupTab`, `renderDrillTab`, `renderFulltakeTab`, `renderStaminaTab`, `renderReviewTab`), evaluation panel renderer.

`singerAudio` — audio plumbing. Mic open/close, MediaRecorder lifecycle, backing track playback, SoundTouch.js integration for time-stretch, vocal-guide stem mixing.

`singerHandoff` — Splitter → Singer handoff logic. New button in Splitter view, song loading into singerState.

### 11.3 Reuse from existing Fymuse code

`splitterDetectMonophonicNotes` — reused as-is for both reference and take F0 extraction. The HPS + parabolic-interpolation pipeline is excellent for vocal.

`splitterFFT`, `splitterHannWindow`, `splitterMixToMono` — reused for the frame-level extractor.

`splitterDetectedTempo` and onset detection logic — reused for timing scoring against the beat grid in no-reference fallback mode.

Header Key picker — reused for the tonal-framework picker (Key + Raga together define the scoring target).

Tone.js — reused for warm-up exercise playback (already loaded in Fymuse).

WebAudio playback graph patterns from Splitter — reused for backing track + vocal-guide playback.

### 11.4 New dependencies

**SoundTouch.js** (≈50 KB) for time-stretching without pitch shift in Drill mode. Native Web Audio `playbackRate` shifts pitch with tempo, which destroys slow-practice utility. Loaded from CDN.

No other new dependencies. ONNX Runtime Web is already loaded for Splitter ML mode but not used by Singer.

### 11.5 Persistence (v1)

In-memory only. `singerState` lives in JS heap. Reload = fresh session. The Review tab's session summary and prescribed drill list are lost on reload — the user can copy/paste the drill list into a notes app if they want it for next session. v3 adds IndexedDB persistence.

### 11.6 Performance budget

The take-analysis pipeline targets <8 seconds for a 4-minute song on a mid-range MacBook. Profile budget: frame-extraction ≈3s (this is the heavy lift — FFT every 20ms × 12000 frames at 4-min × 60s × 50 fps = ~12000 FFTs of 2048 samples). Aggregation + scoring ≈1s. Ornament detection ≈1s. DTW alignment ≈1.5s. Rendering ≈0.5s.

Web Worker offloading: the frame-extraction stage runs in a Web Worker (new — not used elsewhere in Fymuse yet) so the UI stays responsive. The worker is reused across takes in a session (one-time spin-up cost amortized).

---

## 12. Phasing

### 12.1 v1 — Foundation (this build)

All five phase tabs functional. Splitter handoff working. Frame extractor producing F0, RMS, voicing, centroid, tilt, rolloff, flux, HNR-v1, H1-H2, singer's-formant-ratio. Note/phrase/take aggregation complete. Raga-aware pitch scoring with the five v1 ragas + major/minor. All five ornament detectors. Vibrato analysis with Bollywood rubric. Range, dynamics, timing with Bollywood tolerances. Composite score with the §7 weighting. Stamina mode (both single-song and setlist). Exercise bank with the ~25 v1 exercises. Prescription engine with ~15 mapping rules. SoundTouch.js integration for Drill tempo control. Web Worker offloading for analysis. In-memory persistence only.

What's deliberately *not* in v1: vowel-purity scoring, formant extraction, register classification, CPP, cross-session persistence, style sub-rubrics, automatic raga detection, lyric alignment, live-pitch reference contour overlay during Full Take, voice-doctor flags.

### 12.2 v2 — Texture / fatigue / style sub-rubrics

Frame extractor adds: LPC formant extraction (F1, F2), CPP, full autocorrelation-based HNR. Aggregation adds: register classification (chest/mix/head/falsetto/belt/whistle/fry), vowel-purity scoring against Hindi vowel targets, microtonal fatigue drift detection, belt/head/mix/falsetto fraction reporting.

Style sub-rubrics: Bollywood-ballad, Bollywood-EDM, ghazal, qawwali, each re-weighting the composite per §7.

Stamina decay: full per-dimension decay reporting with annotated decline curves and prescriptive output specific to which dimension fatigued first.

Exercise bank expands to ~50: ghazal-specific ornament drills, qawwali stamina drills, sargam in 5 more ragas (Marwa, Todi, Bilaval, Asavari, Bageshri), passaggio-specific exercises, recovery exercises for stamina mode.

Prescription engine expands to ~30 mapping rules including register-mismatch flags and song-transposition suggestions.

### 12.3 v3 — Long game

IndexedDB persistence: sessions persist across reloads. Cross-session trend charts (pitch accuracy over weeks, taan break-point progression, range expansion over months, vibrato regularity convergence).

Live-performance simulator: mic-distance perturbation (the engine simulates the spectral effect of varying mic distance and the user has to compensate); "sing while moving" mode (uses device accelerometer if available, or asks the user to do jumping jacks between takes and compares pitch stability); simulated stage volume (loud playback through speakers, mic captures the room sound and the analyzer compensates).

Setlist mode: real performance order, configurable transitions, applause/MC-patter loops, full-set dry-run with all eight sub-scores tracked across the entire setlist.

Voice-doctor module: long-term jitter/shimmer/HNR baselines per user. Drift detection (sudden departure from baseline = potential vocal strain or illness). Recommendations: rest, hydrate, see an ENT.

Automatic raga detection from reference vocal F0 distribution. Lyric alignment via a small in-browser speech-recognition model (e.g., a quantized Whisper-tiny, ~40 MB) — enables phoneme-aware scoring and lyric-synced display in Drill mode.

Reference-singer benchmarking: pre-analyzed feature vectors from known Bollywood singers (Arijit Singh, Sonu Nigam, KK, Shreya Ghoshal, Sunidhi Chauhan, Rahat Fateh Ali Khan, etc.) per song they've recorded. The user can compare their take to the reference singer dimension-by-dimension — "your vibrato rate is closer to Arijit, but your singer's formant ratio is closer to Sonu."

---

## 13. Out of scope at every phase

Real-time pitch-correction playback. The user must hear their dry voice, not an autotuned version — autotune playback defeats the practice purpose.

Lyrics intelligibility / pronunciation accuracy. Requires real ASR. The vowel-purity score in v2 catches gross vowel-shape errors; full diction scoring needs a speech-recognition model and a language model for context, which is multi-hundred-megabyte territory and not worth it for this tool.

Multi-track band-context analysis. The reference vocal is what the user is scored against; the rest of the band is essentially the click track.

Cloud sync of takes or features. Everything stays on-device. The mic audio never leaves the browser.

Live (real-time) pitch correction or harmonization. Performance / monitoring tooling, not training tooling.

Generative songwriting assist for vocal lines. Out of scope; that's Songwriter territory.

---

## 14. Open questions / design risks

**Raga tuning offset table accuracy.** The cents-from-12-TET offsets per raga vary across schools (Bhatkhande vs Daniélou vs Carnatic-cross-influenced). v1 uses a single performance-practice-derived table; v2 may add per-school presets. Risk: a user trained in a different school may find some scoring decisions feel "off." Mitigation: the in-key tolerance band (±50¢) is wide enough to absorb most school-difference variance.

**Ornament detector false-positive rate.** A taan detector that fires on every fast scale run will inflate ornamentation richness; one that misses real taans will deflate it. v1 calibration uses a hand-labeled corpus of ~30 Bollywood vocal clips spanning the five ornament types. Risk: the corpus is too small to generalize across all song styles. Mitigation: detectors are conservative (false-negative-biased); v2 expands the calibration corpus.

**Reference vocal quality.** Splitter's vocal stem isn't perfect — bleed from instruments, occasional artifacts. The reference's F0 contour and ornament events inherit this noise. Mitigation: pre-filter reference F0 with strict voicing thresholds; smooth aggressively before comparison.

**Phrase-boundary detection from silence gaps.** Works for sparse-sung ballads. Fails on densely-sung material (qawwali, sustained-singing songs where there are no 400 ms silences). Fallback: musical phrase boundaries detected from instrumental cues (chord changes, drum fills) in v2.

**SoundTouch.js artifacts at 70% tempo.** Time-stretching at 0.7× produces audible artifacts on dense material. Mitigation: 0.85× is the recommended "real practice" tempo; 0.7× is for break-down work only.

**MediaRecorder format inconsistency.** Different browsers default to different containers (Chrome → WebM/Opus, Safari → MP4/AAC). The take-analysis pipeline decodes via `AudioContext.decodeAudioData`, which handles both, but the user-download experience differs. Mitigation: detect browser and offer the user-appropriate download with the right extension.

**Web Worker availability in Cloudflare Pages deployment.** Should work — Web Workers are standard browser API — but the COOP/COEP headers Fymuse already sets for ONNX Runtime are sufficient. Verify during build.

---

## Build order (suggested)

1. View skeleton + Splitter handoff + mic open/close — get into the section.
2. Frame extractor + note aggregation — produce the substrate.
3. Pitch / dynamics / range sub-scores + composite — first sub-scores running end-to-end.
4. Raga support (header picker, tuning table, raga-aware pitch scorer).
5. Vibrato analysis + sub-score.
6. Ornament detectors (meend → harkat → murki → taan → khatka, in that order — meend is the bedrock detector).
7. Singer's formant + projection sub-score.
8. Timing sub-score (style-aware, aalap detection).
9. Warm-up tab + baseline card.
10. Drill tab with SoundTouch tempo control.
11. Full Take tab + evaluation panel.
12. Stamina tab (single-song mode first, then setlist).
13. Review tab + session summary.
14. Exercise bank + Tone.js exercise playback.
15. Prescription engine + drill-list output.
16. Web Worker offloading for analysis pipeline.
17. Testing + tuning against a corpus of known Bollywood takes.
18. Documentation pass — update README and MEMORY.md.

Estimated v1 build effort: roughly 4000–6000 lines of new code in `index.html` plus the JSON data tables (`raga-shrutis.json`, `prescriptions.json`, `exercises.json` — these may stay inline as JS objects rather than external JSON for build simplicity).
