# Voice Khata — Audio Recording Script (Phase 1 Bake-Off)

Please record the following ~30 short audio clips.
- **Audio format**: Mono 16 kHz or 44.1/48 kHz WAV or MP3/M4A (PCM16 mono 16 kHz preferred).
- **Environment**:
  - Clips 1–20: Normal/quiet room.
  - Clips 21–30: With background counter/market noise (e.g. ambient fan, road traffic, or store counter audio).
- Save recorded audio files into `eval/audio/clip_01.wav` through `eval/audio/clip_30.wav`.

---

### Set A: Quiet Room (Clips 01 – 20)

| ID | Text to Speak | Language / Script | Expected Intent & Amount |
|----|---------------|-------------------|--------------------------|
| `clip_01` | "Ramesh ka 340 udhaar" | Hinglish | Credit ₹340 to Ramesh |
| `clip_02` | "Ramesh ka teen sau chaalis udhaar" | Hinglish | Credit ₹340 to Ramesh |
| `clip_03` | "Suresh ne 500 diye" | Hinglish | Payment ₹500 from Suresh |
| `clip_04` | "Ramesh ka saadhe teen sau likh do" | Hinglish | Credit ₹350 to Ramesh |
| `clip_05` | "Mahesh ne dedh sau jama kiya" | Hinglish | Payment ₹150 from Mahesh |
| `clip_06` | "Vikram ko do hazaar paanch sau udhaar diya" | Hinglish | Credit ₹2500 to Vikram |
| `clip_07` | "Anita ji ne aath sau diye" | Hinglish | Payment ₹800 from Anita ji |
| `clip_08` | "Pooja ka paune teen sau udhaar" | Hinglish | Credit ₹275 to Pooja |
| `clip_09` | "Ramesh ka sava sau udhaar likho" | Hinglish | Credit ₹125 to Ramesh |
| `clip_10` | "रमेश का 340 उधार" | Hindi (Devanagari) | Credit ₹340 to Ramesh |
| `clip_11` | "सुरेश ने पाँच सौ दिए" | Hindi (Devanagari) | Payment ₹500 from Suresh |
| `clip_12` | "रमेश का साढ़े तीन सौ लिख दो" | Hindi (Devanagari) | Credit ₹350 to Ramesh |
| `clip_13` | "दिनेश का बारह सौ पचास बाकी" | Hindi (Devanagari) | Credit ₹1250 to Dinesh |
| `clip_14` | "Credit 340 to Ramesh" | English | Credit ₹340 to Ramesh |
| `clip_15` | "Received 500 from Suresh" | English | Payment ₹500 from Suresh |
| `clip_16` | "Ramesh ka total kitna hai" | Hinglish (Query) | Balance query for Ramesh |
| `clip_17` | "Aaj kitna udhaar gaya" | Hinglish (Query) | Today's credit query |
| `clip_18` | "Last entry hata do" | Hinglish (Undo) | Undo last entry |
| `clip_19` | "Nahi 430" | Hinglish (Correction) | Amend last entry to ₹430 |
| `clip_20` | "Ramesh ka 340 udhaar, kal 200 diya tha" | Hinglish (Multi-event) | Credit ₹340 today + Payment ₹200 yesterday |

---

### Set B: With Counter / Background Noise (Clips 21 – 30)

| ID | Text to Speak | Language / Script | Notes / Background |
|----|---------------|-------------------|--------------------|
| `clip_21` | "Ramesh ka 340 udhaar" | Hinglish | Ambient noise test |
| `clip_22` | "Suresh ne 500 diye" | Hinglish | Ambient counter noise |
| `clip_23` | "Pooja ka char sau pachaas udhaar" | Hinglish | Traffic/chatter background |
| `clip_24` | "Dinesh ka barah sau pachaas baaki" | Hinglish | Ambient noise test |
| `clip_25` | "रमेश का 340 उधार" | Hindi (Devanagari) | Ambient counter noise |
| `clip_26` | "सुरेश ने पाँच सौ दिए" | Hindi (Devanagari) | Fan/motor noise |
| `clip_27` | "Credit 500 to Suresh" | English | Ambient noise test |
| `clip_28` | "Ramesh ne 200 diya" | Hinglish | Counter noise |
| `clip_29` | "Galti ho gayi, 500 nahi 400 tha" | Hinglish (Correction) | Spoken correction with noise |
| `clip_30` | "Sunita ne aath sau diye, baaki Sunday ko degi" | Hinglish (Partial + Promise) | Multi-clause promise with noise |
