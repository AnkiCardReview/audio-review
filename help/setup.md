# Setup guide

This takes about 10 minutes, plus a download that runs in the background. You need:

- **Anki on a computer** (Windows, Mac or Linux), with the cards you want to review. Audio Review plays **cloze** cards.
- **An iPhone or Android phone.**
- **A way to answer:** Bluetooth headphones with next/previous track controls (such as AirPods), a Bluetooth remote, the phone's screen, or a car with Bluetooth audio and steering-wheel track buttons (⏭ / ⏮).

Nothing here needs an account, a terminal or any settings files.

---

## 1. Install the add-on

**From AnkiWeb (once the listing is up):**
1. In Anki, open **Tools ▸ Add-ons ▸ Get Add-ons…**
2. Paste the code *(coming soon)* and press OK.
3. Restart Anki.

**From a file (until then):**
1. Download `audio_review.ankiaddon` from the project's [Releases page](https://github.com/AnkiCardReview/audio-review/releases) *(not published yet)*.
2. Double-click the file, or in Anki use **Tools ▸ Add-ons ▸ Install from file…**
3. Restart Anki.

## 2. The setup window

A few seconds after Anki restarts, the **Audio Review setup** window opens by itself. It has six steps on the left; **Next** walks through them. You can open it again any time from **Tools ▸ Audio Review ▸ Settings**.

![The welcome step](images/wizard-welcome.png)

### Decks
Tick the decks to hear as audio. Ticking a deck includes its subdecks. Each ticked deck appears in **Play order** on the right, and the phone plays them one at a time, top to bottom. Use **↑ Up** / **↓ Down** (or drag) to change the order.

The first time, every top-level deck with cards due is ticked for you. That's a fine start.

![The decks step](images/wizard-decks.png)

### Options
The defaults suit most people:
- **Also send cards due in the next 1 day** (the default). Each list also carries the next day's exact cards, so 1 is enough when you open Anki most days; more covers days without Anki, with bigger downloads. Cards are only ever played on the day they're due.
- **Make audio for whole decks** (Tools ▸ Audio Review): voices every card in your audio decks ahead of time, the ones you'll need soonest first, after showing how many clips that is and how long it should take on this computer (measured as it makes audio). It runs only when you start it, on the charger, and you can pause or stop it.
- **Make new audio by itself when I close Anki while plugged in** (on). Leave this on.
- **Apply my phone answers without asking first** (off). Phone answers are picked up when Anki opens and each time it syncs (the Sync button or automatic sync). While it's off, Anki shows you what your phone answers will do and waits for you to click **Apply**.

### Voice
Press **Set up the voice**. Audio Review downloads its own voice, about **340 MB**, into a folder called `CarReview` in your home folder:
- uv, a small open-source installer
- a private copy of Python 3.12
- the voice engine (ONNX Runtime, kokoro-onnx and misaki)
- the Kokoro "Heart" voice

Nothing is installed system-wide, and you won't be asked for an administrator password. Every file is checked against a fixed fingerprint before it's used. It takes about 3–10 minutes; you can press **Next** and carry on while it runs. When it's done you'll see **✓ The voice is ready.**

![The voice step](images/wizard-voice.png)

### Phone
1. Open your phone's **Camera** and point it at the QR code. Tap the link that appears.
2. **Add Audio Review to your Home Screen:**
   - **iPhone (Safari):** tap Share **□↑** ▸ **Add to Home Screen** ▸ **Add**.
   - **Android (Chrome):** tap **⋮** ▸ **Add to Home screen** (or **Install app**) ▸ **Add**.
3. **Open Audio Review from the Home Screen icon.** On iPhone this matters: the Home Screen app keeps its own storage, separate from Safari.

The phone shows **Paired ✓** and a short walk-through of the buttons and a safety note. Tap **I understand**.

![The phone step](images/wizard-phone.png)

### Done
The last step lists anything still missing and what happens from now on. If the voice is ready, press **Make audio and send to my phone now**, ideally with the computer plugged in. A small window shows progress. The first time, this takes roughly 10 seconds per card on a typical laptop (faster on newer computers). You can keep using the computer while it works, and it pauses on battery. Cards appear on the phone in batches as they're ready, so you don't have to wait for the end.

Press **Finish**.

## 3. Your first session

**Before you go:**
1. Close (or sync) Anki on the computer. It sends your due cards to the phone. (If you just did "Make audio and send", that's already happened.)
2. Open Audio Review on the phone, ideally on Wi-Fi. It downloads the cards and their audio. **Cards left today** and **Offline** show how many are ready.
3. Connect your headphones, or the phone to your car's Bluetooth. **Close Spotify or any other music app**, or it may take over the buttons.
4. Tap **Start**, lock the phone and put it away. It plays the first question.

**Answering with headphones, the lock screen or the steering wheel:**

| You hear | ⏭ next track | ⏮ previous track |
|---|---|---|
| A question (or silence after it) | Hear the answer | Repeat the question |
| A question, pressed twice | | Go back a card: undo its answer and hear its question again (⏭ then plays its answer) |
| A question, pressed three times | | Skip: "doesn't work as audio" |
| "All done" or waiting for a learning card | | Go back a card |
| The answer | **Good** (the next question starts) | **Again** (the next question starts) |

In a car, press at a steady pace, about once a second: many cars pass on at most one button press per second, so faster presses can be lost. Each ⏮ counts toward a double or triple for about 2 seconds after the one before. Nothing plays on its own: after a question, it waits silently as long as you like. Cards you answer **Again** come back after your learning step, just as in Anki.

**On a walk, the treadmill or anywhere you can glance at the screen:** in the app, turn on **Walking mode**. During a session the whole screen is two buttons: the left half is Again (on a question, it repeats it) and the right half shows the answer, then Good. Swipe right anywhere to go back a card. The screen stays on.

**A Bluetooth remote:** a remote, page turner, keyboard or game controller in keyboard mode (like the 8BitDo Zero 2) works while the app is on screen. The standard keys: G, Space, → or Page Down = show answer, then Good; J, 1, ← or Page Up = Again; K, Z or Backspace = back a card; H or R = hear it again; L = lock the screen. Change them under **Remote keys** in the app: tap **+ Add**, then press the button.

**Pocket lock:** a remote only works with the screen on, so hold 🔒 at the top of a session: the screen goes black and ignores touches, and the phone can go in a pocket. Hold the lock again to unlock.

> **Safety in the car:** set up and tap Start before you move. While driving, use only the steering-wheel buttons and never look at or touch the phone. If a card needs thought, let it wait.

**When you're done:**
Tap **Stop** on the phone (it sends your answers). Then open or sync Anki on the computer **first**, before reviewing on another device. After its usual sync, Audio Review shows your phone answers ("120 answers for 95 cards…") with an **Apply** button. Anki makes a backup first, and **Edit ▸ Undo** reverts everything in one step. Then Anki syncs as usual, so AnkiMobile or AnkiDroid see those cards as done.

## 4. Every day after that

Your routine doesn't change: **close or sync Anki when you're done on the computer, open it again later.** Audio Review sends fresh cards each time Anki syncs or closes, makes audio for new cards while the computer is plugged in, and offers to apply your phone answers when Anki opens.

## Changing things later
- **Decks, options, voice, phone:** Tools ▸ Audio Review ▸ Settings
- **New or lost phone:** Tools ▸ Audio Review ▸ Pair phone ▸ *Make a new code*
- **Something's not right:** see [Troubleshooting](troubleshooting.md)

## Removing Audio Review
1. In Anki, **Tools ▸ Add-ons**, select Audio Review and press **Delete**.
2. Delete the `CarReview` folder in your home folder (the voice, audio and pairing).
3. On the phone, delete the Audio Review icon. On iPhone, also go to Settings ▸ Apps ▸ Safari ▸ Advanced ▸ Website Data and remove `ankicardreview.github.io`.

Your Anki collection and review history aren't affected: phone answers become normal Anki reviews once they're applied.
