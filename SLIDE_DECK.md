# Servelens — Slide Deck Structure & Design Guide

---

## Design System

### Color Palette

| Role | Color | Hex |
|---|---|---|
| Background (primary) | Deep Navy | `#0D1B2A` |
| Background (card / panel) | Dark Slate | `#152535` |
| Accent / CTA | Electric Blue | `#1B8EF2` |
| Heading text | Pure White | `#FFFFFF` |
| Body text | Soft Gray | `#A8B8CC` |
| Alert highlight | Amber | `#F59E0B` |
| Danger / Fire | Red-Orange | `#EF4444` |
| Success / Recognized | Teal Green | `#22C55E` |
| Dividers / borders | Dim Blue | `#1E3048` |

### Typography

| Element | Font | Weight | Size |
|---|---|---|---|
| Slide title | Inter / DM Sans | Bold (700) | 40–48px |
| Section label (eyebrow) | Inter | Semibold (600), all caps, letter-spaced | 12px |
| Body copy | Inter | Regular (400) | 18–20px |
| Feature callout | Inter | Semibold (600) | 22px |
| Caption / label | Inter | Regular (400) | 14px |

### Layout Rules

- **Margins:** 64px on all sides (safe zone for projectors)
- **Grid:** 12-column grid; content never exceeds 10 columns
- **Two-column split default:** 50/50 or 55/45 (text left, visual right)
- **Max 4 bullet points per slide** — one idea per line, no sub-bullets
- **One image placeholder per slide minimum** — visuals carry equal weight to text
- **Accent line:** 3px horizontal rule in Electric Blue under each slide title
- **Icons:** Minimal line icons (Phosphor or Lucide set), 28px, Electric Blue tint

### Image Placeholder Style

All placeholders are labeled `[IMG: description]` in this document.
In the actual deck, render as:
- A dark card with a dashed Electric Blue border (`1px dashed #1B8EF2`)
- Rounded corners (12px radius)
- Centered label in Soft Gray text
- 16:9 or 4:3 aspect ratio as noted

---

## Slide-by-Slide Structure

---

### SLIDE 01 — Cover

**Layout:** Full-bleed background, centered content

**Background:** Deep Navy with a subtle dark-toned CCTV camera grid pattern or abstract node mesh (low opacity, 10–15%)

**Content:**
```
[Eyebrow — Electric Blue, top left]
INTELLIGENT SURVEILLANCE PLATFORM

[Logo — centered, top third]
[IMG: Servelens logo — white version, 200px wide]

[Main heading — centered, large]
See Everything.
Know What Matters.

[Subheading — Soft Gray, centered]
Real-time detection · Face recognition · Instant alerts

[Bottom center]
[IMG: Small row of 3–4 camera feed thumbnails as strip]
```

**Notes:** No bullet points. Pure brand statement. Strip of live feed thumbnails at the bottom creates immediate visual context of what the product does.

---

### SLIDE 02 — The Problem

**Layout:** Two-column — left: text; right: illustration

**Eyebrow:** THE CHALLENGE

**Heading:** Security cameras record everything. But who's watching?

**Body (left column — 3 points, icon + one line each):**
- Hours of footage with no way to find what matters
- Alerts that are too slow, too vague, or too many
- No easy answer to "who was there and when?"

**Right column:**
```
[IMG: Placeholder — illustration or blurred CCTV footage wall,
      4:3, with a question mark overlay or "MISSED ALERT" watermark]
```

**Notes:** Keep the tone matter-of-fact, not fear-based. The goal is to frame the gap that Servelens fills.

---

### SLIDE 03 — Introducing Servelens

**Layout:** Full-width with centered content block + dashboard screenshot below heading

**Eyebrow:** MEET SERVELENS

**Heading:** One platform. Every camera. Total awareness.

**Subheading (Soft Gray):**
Servelens turns your camera network into an intelligent system that recognizes people, reads plates, detects hazards, and keeps you informed — automatically.

**Below heading:**
```
[IMG: Full dashboard screenshot — multi-camera grid view with alert panel visible,
      16:9, full width of content area, rounded corners 12px]
```

**Notes:** This is the "wow" slide. The screenshot should do the heavy lifting. Keep text minimal. If the dashboard screenshot is strong, this slide sells itself.

---

### SLIDE 04 — Live Monitoring Dashboard

**Layout:** Large visual left (60%), stacked text blocks right (40%)

**Eyebrow:** LIVE VIEW

**Heading:** Every camera. One screen.

**Right column — 3 stacked feature cards (dark card `#152535`, 12px radius, Electric Blue left border):**

```
Card 1:
  Icon: [grid icon]
  "All cameras in one place"
  Sub: Any device, any time — no separate apps

Card 2:
  Icon: [wifi/signal icon]
  "Near-zero delay streaming"
  Sub: What you see is what's happening right now

Card 3:
  Icon: [activity icon]
  "Live status per camera"
  Sub: Instantly see which feeds are live, connecting, or offline
```

**Left column:**
```
[IMG: Dashboard screenshot — camera grid focused on status indicators
      and FPS display, 16:9, rounded corners]
```

---

### SLIDE 05 — Face Recognition & Identity

**Layout:** Two-column, 50/50

**Eyebrow:** IDENTITY

**Heading:** Know exactly who was there — and when.

**Left column — body text + bullets:**
The system recognizes your staff, regular visitors, and anyone you've added — and logs every appearance automatically.

- Recognizes known faces in real time
- Instantly alerts when an unknown person appears
- Keeps a timestamped record of every sighting

**Right column — stacked visuals:**
```
[IMG: Top — Face recognition camera view with bounding box and name label,
      4:3, rounded corners]

[IMG: Bottom — Recent faces gallery UI showing photo grid of captured faces,
      4:3, rounded corners]
```

**Notes:** The two images tell the full story — detection in the field + management in the UI.

---

### SLIDE 06 — Adding People Is Simple

**Layout:** Step flow — horizontal 3-step diagram, center of slide

**Eyebrow:** FACE MANAGEMENT

**Heading:** Add someone new in under a minute.

**Step flow (3 cards in a row, connected by arrow →):**

```
Step 1                    Step 2                    Step 3
[Icon: camera]            [Icon: user-check]        [Icon: bell-check]
"Camera detects           "Select their photo       "System recognizes
 a new face"               from recent captures"     them from now on"
```

**Below the flow:**
```
[IMG: Faces registration page — showing photo upload / recent captures selection,
      16:9, full content width, rounded corners]
```

**Notes:** This slide addresses the "how hard is it to set up?" question before it's asked.

---

### SLIDE 07 — License Plate Recognition

**Layout:** Two-column, 55/45 — visual left, text right

**Eyebrow:** VEHICLE ACCESS

**Heading:** Every vehicle logged. Automatically.

**Right column:**
Every vehicle entering or leaving is captured and its plate number read — no manual effort, no missed entries.

- Reads plates as vehicles pass
- Logs plate text and timestamp with each alert
- Works day or night on standard cameras

```
[IMG: Right column bottom — Alert panel entry showing plate text
      and vehicle detection snapshot, 4:3, rounded corners]
```

**Left column:**
```
[IMG: Camera view with ANPR bounding box and plate text overlaid
      on a vehicle, 4:3, rounded corners]
```

---

### SLIDE 08 — Fire & Smoke Detection

**Layout:** High-contrast, dark background — single strong visual with text overlay

**Background:** Deep Navy, slight red-orange vignette at edges (very subtle, 5% opacity)

**Eyebrow (Red-Orange `#EF4444`):** SAFETY

**Heading:** Get alerted the moment fire or smoke appears.

**Body:**
Servelens monitors every camera for signs of fire and smoke in real time — and sends an immediate alert before the situation escalates.

- Detects both fire and smoke independently
- Works on any camera already pointed at a risk area
- Faster than a manual check, every time

**Right side:**
```
[IMG: Camera view with fire/smoke bounding boxes overlaid,
      orange-red accent color on detection boxes, 4:3, rounded corners]
```

**Notes:** Use the amber/red from the palette intentionally here — this slide should feel slightly more urgent than the others, but not alarming.

---

### SLIDE 09 — Instant Alerts That Actually Help

**Layout:** Two-column, 50/50

**Eyebrow:** ALERTS

**Heading:** The right information, the moment it happens.

**Left column:**
When something is detected, you get an email — with a photo of exactly what triggered it, the camera name, the time, and what was seen. No app to check. No dashboard to monitor.

- Delivered to any email address
- Snapshot attached so you see what happened immediately
- Includes plate numbers and recognized names where relevant

**Right column:**
```
[IMG: Top — Alert sidebar in dashboard showing recent alerts with thumbnails,
      4:3, rounded corners]

[IMG: Bottom — Example email alert layout (mockup or screenshot) showing
      subject line, camera name, time, and attached snapshot thumbnail,
      4:3, rounded corners]
```

---

### SLIDE 10 — People Count & Focused Zones

**Layout:** Two-column, 55/45 — text left, visual right

**Eyebrow:** OCCUPANCY & ZONES

**Heading:** Watch exactly the right area. Count who's in it.

**Left column:**

Know how many people are in any camera's view at any moment — and tell the system to only raise alerts for specific areas, so you're never flooded with noise.

- Live headcount visible per camera
- Focus detection on doors, gates, or restricted areas only
- Reduce false alerts from irrelevant movement

**Right column:**
```
[IMG: Camera tile showing people count overlay badge ("3 PEOPLE"),
      4:3, rounded corners]
```

---

### SLIDE 11 — Recording & Evidence

**Layout:** Two-column, 50/50

**Eyebrow:** RECORDINGS

**Heading:** Footage that tells the full story.

**Left column:**
Every recording includes the detection boxes and labels overlaid on the video — so reviewing footage later is fast, clear, and unambiguous. Clips are saved automatically when events are detected.

- Detection annotations baked into saved recordings
- Event clips saved automatically on alert
- Continuous recording available per camera, toggled from the dashboard

**Right column:**
```
[IMG: Top — Recording toggle button on camera tile (active state),
      showing "■ STOP" button, 4:3, rounded corners]

[IMG: Bottom — File browser or folder showing saved clip files
      with timestamps in filename, 4:3, rounded corners]
```

---

### SLIDE 12 — Event History & Audit Log

**Layout:** Large screenshot top, 3 icon + text blocks below

**Eyebrow:** HISTORY & COMPLIANCE

**Heading:** A complete record of every event, always.

**Top:**
```
[IMG: Alert history panel — full list view with thumbnails, timestamps,
      camera names, detection classes, 16:9, full content width, rounded corners]
```

**Bottom — 3 columns:**
```
[Icon: clock]          [Icon: file-text]      [Icon: search]
"Every alert           "Exportable log        "Click any entry
 timestamped           file — ready for        to see the full
 and stored"           reporting"              snapshot"
```

---

### SLIDE 13 — Activity Timeline & Trends

**Layout:** Two-column, 50/50

**Eyebrow:** ANALYTICS

**Heading:** Understand patterns, not just incidents.

**Left column:**
See when your busiest periods are, how detection events trend over time, and whether alert frequency is increasing or decreasing — at a glance, without digging through logs.

- Hourly and daily activity breakdown per camera
- Detection frequency charts by category
- Spot unusual spikes before they become problems

**Right column:**
```
[IMG: Timeline / statistics UI — chart or graph showing event frequency
      over time, per camera or per detection class, 4:3, rounded corners]
```

**Notes:** This slide is forward-looking — if the analytics UI is not fully built yet, use a wireframe or mockup placeholder clearly labeled "Coming soon" in a subtle badge.

---

### SLIDE 14 — Why Servelens

**Layout:** Comparison table or side-by-side grid — centered

**Eyebrow:** THE DIFFERENCE

**Heading:** Built for real security needs. Not just recording.

**Comparison grid (3 columns: Feature · Generic NVR · Servelens):**

| | Generic NVR | Servelens |
|---|---|---|
| Face recognition | Expensive add-on | Included |
| License plate reading | Plugin required | Built-in |
| Fire & smoke detection | Not available | Built-in |
| Email alerts with photo | Needs third-party setup | Included |
| Detection per zone | Basic or none | Configurable |
| Annotated recordings | No | Yes |
| People count | No | Yes |
| Audit log | No | Yes |

**Servelens column cells** — use Electric Blue background with white text to make them pop visually.

**Below table (centered, Soft Gray italic):**
*Everything runs on your hardware. Your footage stays with you.*

---

### SLIDE 15 — Get Started

**Layout:** Centered, minimal — strong CTA focus

**Background:** Deep Navy, Electric Blue radial glow from center (subtle, 20% opacity)

**Top:**
```
[IMG: Servelens logo — white, centered, 180px]
```

**Heading (large, centered):**
Ready to make your cameras smarter?

**Subheading (Soft Gray, centered):**
Servelens runs on your existing camera infrastructure — no rip and replace, no cloud dependency.

**3 next-step blocks (horizontal, centered):**
```
[Icon: monitor]           [Icon: message-circle]    [Icon: play-circle]
"Request a Demo"          "Talk to the Team"         "See It Live"
[Button — Electric Blue]  [Button — outline]         [Button — outline]
```

**Bottom (Soft Gray, small):**
`servelens.io  ·  renata@renataiot.com`

---

## Slide Count Summary

| # | Slide Title | Section |
|---|---|---|
| 01 | Cover | Brand |
| 02 | The Problem | Context |
| 03 | Introducing Servelens | Overview |
| 04 | Live Monitoring Dashboard | Features |
| 05 | Face Recognition & Identity | Features |
| 06 | Adding People Is Simple | Features |
| 07 | License Plate Recognition | Features |
| 08 | Fire & Smoke Detection | Features |
| 09 | Instant Alerts That Actually Help | Features |
| 10 | People Count & Focused Zones | Features |
| 11 | Recording & Evidence | Features |
| 12 | Event History & Audit Log | Features |
| 13 | Activity Timeline & Trends | Features |
| 14 | Why Servelens | Differentiation |
| 15 | Get Started | CTA |

**Total: 15 slides**

---

## Image Capture Checklist

Screenshots to take from the running Servelens app:

- [ ] Full dashboard — camera grid with all 4 cameras live
- [ ] Single camera tile — showing FPS, status dot, REC button
- [ ] Camera tile — people count badge active ("3 PEOPLE")
- [ ] Camera view — face detection with bounding box and name label
- [ ] Camera view — ANPR with plate text overlaid on vehicle
- [ ] Camera view — fire/smoke detection with colored bounding boxes
- [ ] Alert sidebar — list of recent alerts with thumbnails
- [ ] Alert lightbox — full snapshot open in viewer
- [ ] Faces page — recent faces gallery grid
- [ ] Faces page — register face / upload photo form
- [ ] Email alert — screenshot of received alert email with snapshot
- [ ] Recordings folder — file listing showing event clip filenames
