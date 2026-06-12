# Custom Guitar / Keys Splitter — Design Doc (Deferred)

**Status:** parked. We will pick this up later. Not in active development.

**Goal:** train our own model that takes the `other` stem from htdemucs
(vocals/drums/bass already removed) and splits it further into a `guitar`
stem and a `keys` stem (piano + electric piano + organ + synth + pads).

**Why we're not using `htdemucs_6s`:** Meta's official 6-stem model has
no public browser-ready ONNX export, and the piano stem is documented by
Meta themselves as "not working great." We'd rather invest the same
engineering time in a model specialized for the post-Demucs split that
actually performs well on the music we play.

---

## 1. Architecture

**MDX-Net-style spectrogram U-Net.** ~15–30M parameters.

- **Input**: stereo audio at 44.1 kHz. Chunked into ~6-second windows
  (262144 samples). STFT with window 4096, hop 1024.
- **Trunk**: 4–7 level encoder-decoder U-Net with skip connections.
  Convolutions over the complex STFT (real + imaginary as separate
  channels or magnitude + phase).
- **Output**: two complex soft masks (one per target stem). Multiply
  each mask against the input STFT, inverse-STFT, get guitar + keys
  audio.

**Why this and not something fancier:**
- Demucs-style hybrid (time + freq dual branches) is marginally better
  in raw SDR but ~5x harder to ONNX-export and deploy in a browser.
- BS-RoFormer is current SOTA but ~250–400 MB, rotary attention is
  messy to export, and overkill for a 2-way specialized split.
- A 2-way post-Demucs split is a much smaller learning problem than
  full music demixing; MDX-Net is well-matched to its scope.

**Loss:** L1 on the reconstructed waveform + multi-resolution STFT loss
(the standard combo). Consider Si-SDR loss as a finishing pass later.

---

## 2. Data plan

Source separation quality is overwhelmingly driven by data, not by
architecture. Plan for 3 real sources + heavy synthetic augmentation.

### Real datasets (in priority order)

1. **MedleyDB v2** — ~196 songs, real productions, per-instrument stems
   with detailed labels ("Electric Guitar (Clean)", "Distorted Electric
   Guitar", "Piano", "Synth Pad", "Hammond Organ", etc.). Free for
   research. Highest-quality real-music source.
   - Ingestion: for each song, sum vocals/drums/bass-equivalent stems
     and subtract from the mix → synthesized `other` stem (the input).
     Sum guitar-labeled stems → guitar target. Sum keys-labeled stems
     → keys target. Maintain a label dictionary mapping MedleyDB
     instrument names to `{guitar, keys, neither}`.

2. **Cambridge-MT (Mike Senior multitracks)** — ~600 real
   commercial-grade multitrack sessions, mostly free. Per-instrument
   files with descriptive filenames (`GTR-MAIN.wav`, `PNO-VERSE.wav`).
   - Ingestion: filename-parsing pipeline → label classifier. ~2-3
     days of engineering to build cleanly.

3. **Slakh2100** — 2100 synthetic MIDI-rendered tracks with perfect
   per-instrument labels. Free. Use ONLY for pre-training (models
   trained only on synthetic data overfit to sample-library timbres
   and generalize poorly to real recordings).

### Synthetic augmentation (the secret weapon)

Generate unlimited training pairs by mixing isolated guitar + isolated
keys recordings. Solo recordings exist in abundance:

- **GuitarSet** — ~360 short solo guitar performances
- **MAESTRO** — ~1300 hours of high-quality solo piano
- Any commercial guitar/piano one-shot libraries we have access to
- YouTube guitar/piano lesson rips (license-questionable; for personal
  research only)

Mix one solo guitar + one solo keys → that's an `other` stem with
perfect ground truth for both targets. Augment with random pitch-shift,
time-stretch, EQ randomization, reverb, and a small amount of ambient
noise. We can generate 10x more synthetic training pairs than real and
it actually improves generalization.

### Splits

- Train: ~85% of MedleyDB + Cambridge-MT, plus all Slakh + augmentation
- Val: ~5% MedleyDB
- Test: ~10% MedleyDB — never seen during training. Used only for the
  final SDR/SAR/SIR numbers and model selection.

---

## 3. Training plan

Three phases on the same model architecture:

1. **Pre-train on Slakh2100** — ~2 days on a single A100. Cheap, fast,
   gets the optimizer to a good starting point on the basic separation
   concept.

2. **Main train on MedleyDB + Cambridge-MT + synthetic** — ~4–6 days
   on a single A100. This is where real quality is built.
   - Batch size ~64
   - AdamW, lr 1e-3 → cosine schedule
   - ~500K total steps
   - Mixed precision (fp16/bf16)
   - Checkpoint every ~10K steps

3. **Optional fine-tune** on a curated 30–100-song corpus of music
   similar to what we play. Low learning rate (1e-5), ~1 day. Adapts
   to our taste.

**Compute cost (rented):**
- RunPod / Lambda Labs A100 ~$1.20–1.50/hour
- Full arc: ~$150–300 across all three phases
- Add ~$50 for hyperparameter exploration

**Compute cost (local):** A 4090 (24 GB VRAM) will train this at ~3x the
wall-clock of an A100. ~3 weeks for the main phase. $0 GPU but
electricity + your machine being tied up.

---

## 4. Evaluation

**Primary metric:** SDR (signal-to-distortion ratio) computed by the
`museval` library — the standard from the MUSDB / MDX challenges.
Compute SDR for guitar and keys separately on the held-out test set.

**Secondary metrics:** SAR (signal-to-artifacts), SIR
(signal-to-interference), Si-SDR.

**Target:** beat `htdemucs_6s` by ≥1 dB SDR on guitar, ≥0.5 dB on keys.

**Qualitative listening:** also do A/B listening tests on 20–30 songs
across genres. SDR alone doesn't capture perceptual quality — a model
with slightly lower SDR can still sound noticeably cleaner.

---

## 5. Deployment

**ONNX export.**
- PyTorch → ONNX is straightforward for U-Net (no dynamic shapes if we
  fix the chunk size).
- Run through `onnx-simplifier` for the cleanest graph.
- Validate ONNX numerical output matches PyTorch within ~1e-4 tolerance.
- Expected size: 40–80 MB.

**Hosting:** HuggingFace static model hosting (already used for the
htdemucs model — same CDN pattern).

**Browser integration:** runs as a SECOND PASS after the existing
Demucs run.
- Take the `other` stem (already an AudioBuffer at this point).
- Chunk into 6-second windows with 50% overlap.
- Run each chunk through the model via `onnxruntime-web`.
- Overlap-add the outputs.
- Replace the `other` entry in `splitterState.stems` with two new
  entries: `guitar` and `keys`.
- Existing pipeline (Tone Match, MIDI export, chord detection, sheet
  view) flows downstream automatically — they all just read from
  `splitterState.stems`.

**UI:**
- New entries in `SPLITTER_STEMS` for guitar + keys.
- Quality toggle: "Standard (4 stems)" / "Detailed (5 stems with
  guitar/keys split)" — same UX as the existing Fast/Accurate toggle.
- Detailed mode is slower (extra inference pass) and adds ~50 MB to
  the model download.

---

## 6. Tooling stack

- **PyTorch 2.x** for the model + training
- **PyTorch Lightning** for the trainer (handles checkpointing,
  mixed precision, multi-GPU, callbacks cleanly)
- **torchaudio** for STFT/iSTFT + audio loading
- **Weights & Biases** (free tier) for experiment tracking
- **Hydra** for config management — we'll run dozens of experiments
  and config sprawl is a real killer without it
- **`asteroid`** (the audio source separation toolkit on GitHub) — has
  well-tested implementations of MDX-Net, U-Net Sep, ConvTasNet. Start
  by forking from there rather than rebuilding from scratch.
- **`museval`** for the evaluation script
- **ONNX Runtime + onnx-simplifier** for the export step
- **RunPod or Lambda Labs** for GPU rental (or Modal for pay-per-second
  scheduled training)

---

## 7. Realistic timeline

If one person works on this full-time:

- **Week 1:** Set up training infrastructure (cloud GPU account, W&B
  project, Hydra config skeleton). Ingest MedleyDB. Get a baseline U-Net
  training end-to-end on a tiny subset. **Milestone:** training loop
  works and loss decreases.
- **Week 2:** Full data pipeline — Cambridge-MT ingestion + synthetic
  augmentation generator. Slakh download + preprocessing.
  **Milestone:** unified DataLoader yielding well-balanced batches.
- **Weeks 3–4:** Pre-training on Slakh, then main training on real
  data. Hyperparameter exploration in parallel. **Milestone:** model
  beats the baseline (Demucs `other` stem, naive split).
- **Week 5:** Iteration — multi-resolution STFT loss, longer training,
  curriculum learning, augmentation tuning. **Milestone:** model beats
  `htdemucs_6s` on the test set.
- **Week 6:** ONNX export, browser integration, A/B testing in Lime Labs,
  ship behind a feature flag. **Milestone:** shipped.

Part-time evenings/weekends: 3–4 months realistic.

---

## 8. Risks

**Piano/keys quality may plateau** at or near `htdemucs_6s` levels
because the underlying training data problem (limited isolated piano
in non-classical-solo contexts) is shared with everyone training in
this space. Aggressive synthetic augmentation is our main lever against
this. If it doesn't fully solve it, we still beat them on guitar where
data is more plentiful.

**Same-register guitar + keys mixes are fundamentally hard.** Solo
fingerpicked clean guitar over solo piano in the same octave range
will smear in any model, ours or Meta's. Document this honestly in the
UI rather than overpromising.

**ONNX export sometimes surfaces numerical issues** that don't show up
in PyTorch (subtle differences in op implementations, complex-number
handling, edge cases at chunk boundaries). Budget real debug time.

**Browser inference performance** — even a 30M-param model running a
6-second chunk at a time across a 4-minute song means ~40 inferences.
At 1–2 sec per chunk on WASM (slower on mobile), total processing
adds maybe 1–2 minutes on top of the existing Demucs run. May want
WebGPU as the preferred backend (already supported in `ort-web`).

---

## 9. Non-obvious leverage points

- **Synthetic augmentation done well** (random pitch-shift / time-stretch
  / EQ / room reverb on solo recordings before mixing) can 3x your
  effective dataset for almost no cost.
- **Multi-resolution STFT loss** adds ~0.5–1 dB SDR over plain L1.
  Small models love it.
- **Slakh pre-training** saves about 30% of training time on the real
  data even though it's synthetic.
- **Curriculum learning** (start with easy examples — sparse
  arrangements, big SNR separation; then move to dense mixes) helps
  convergence on small datasets.
- **Mid/side training augmentation** — randomly process M and S
  channels independently sometimes. Forces the model to learn
  channel-aware separation.

---

## 10. When we pick this up — first concrete steps

1. Set up a GitHub repo separate from Lime Labs: `lime-labs-splitter-training`.
2. Apply for MedleyDB access (free, takes a few days).
3. Spin up a RunPod A100 instance, install PyTorch + Lightning + asteroid.
4. Write the MedleyDB ingestion script + label dictionary. This alone
   will take ~2 days and is the foundation of everything else.
5. Get a dumb baseline (constant-output U-Net, no augmentation, MedleyDB
   only) training end-to-end. Confirm the loss decreases. This is the
   "infrastructure works" milestone.
6. From there, the plan in Section 7 takes over.

---

## Open questions for when we resume

- Do we want a 3rd stem? "guitar" / "keys" / "other-other" (sound
  effects, ambient pads that don't fit cleanly into guitar OR keys)?
  Might improve quality at the cost of more output channels.
- Is licensing of the training data going to be a problem if we ever
  open-source the model? MedleyDB is research-only. Cambridge-MT has
  per-track licenses. MoisesDB is paid. Worth thinking about up front.
- Mono fallback? Some old recordings are mono. Train with random
  channel duplication, or just accept lower quality on mono inputs?
- Inference chunk size — 6 seconds is a guess; might want longer for
  pad-heavy material, shorter for staccato guitar parts. Worth ablating.
