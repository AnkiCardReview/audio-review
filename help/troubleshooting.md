# Troubleshooting and FAQ

**Quick checks first:** In Anki, **Tools ▸ Audio Review ▸ Status** shows the last send. On the phone, the home screen shows **cards left today**, **Offline** and **Answers sent**, plus a message explaining anything that's waiting.

---

## Buttons and playback

### The headphone or steering-wheel buttons don't do anything
1. **Did you tap Start?** The buttons only reach Audio Review while it's playing. Tap Start first.
2. **In a car: is the phone connected to the car's Bluetooth audio** (not only for calls)? The car's display should show Audio Review as what's playing.
3. **Another app took over the buttons.** Spotify, Apple Music, podcasts and audiobook apps grab the track buttons whenever they've played recently. Close them (swipe them away), open Audio Review, and tap Start again. See the next question.
4. **In a car, try headphones** (or AirPods) while parked. If they work, the car's buttons send something other than next/previous track. Some cars only send these when the phone is in "media" mode.
5. Holding a button is not used; press and release.

### Spotify (or another music app) keeps taking over
iPhone and Android send the track buttons to whichever app played audio last. To keep them with Audio Review:
- Close the music app completely before tapping Start (swipe it away in the app switcher).
- Turn off "autoplay when connected to the car" in your car, CarPlay or the music app, if it has that setting.
- If the music app starts after you connect, tap Start in Audio Review again: it takes the buttons back.

### AirPods
Double-tap (or press the stem twice) = ⏭. Triple-tap (or press three times) = ⏮. If your AirPods are set to something else, change it in Settings ▸ Bluetooth ▸ your AirPods.

### It plays the question and then goes quiet
That's on purpose: after a question it waits as long as you like. Say your answer, then press ⏭ to hear the answer.

### "Next card in 6 minutes"
Only cards waiting on a learning-step timer are left. Audio Review follows Anki's rules (including your "learn ahead limit"), so it waits until they're due, then plays them. You can stop for the day; they'll be finished in Anki.

### The audio stopped when I locked the phone
This is rare. When it's safe, unlock the phone, tap **Stop**, then **Start**: it carries on where you were. Make sure Audio Review was opened from the Home Screen icon rather than a browser tab.

### A card makes no sense as audio
Press ⏮ three times quickly while the question is playing (twice goes back to the card before instead). On the screen, tap **Skip (not for audio)**. The card is skipped with no grade, tagged `audio-review::skip` in Anki (cards tagged `car-review::skip` before the rename stay skipped too), and never comes back as audio. It stays due in Anki as normal.

---

## Cards and audio

### The phone says "Waiting for your first audio list"
Your computer hasn't sent anything yet. On the computer:
1. Make sure the setup is complete: **Tools ▸ Audio Review ▸ Settings**. The **Done** step lists anything missing (decks or voice).
2. Close Anki, or use **Tools ▸ Audio Review ▸ Send to phone**.
3. On the phone, tap **Sync**.

### "N more cards are waiting for audio on your computer" / no audio yet
Audio is made on your computer, and only while it's plugged in. The first time, it takes roughly 10 seconds per card on a typical laptop.
- Plug the computer in and close Anki (with **Make new audio by itself** on, which is the default), or use **Tools ▸ Audio Review ▸ Prepare audio**.
- A small window shows progress. You can keep using the computer. If the window says *Paused: on battery*, plug in.
- Leave the lid open while it works: closing the lid usually puts the computer to sleep.
- Cards reach the phone in batches of 25 as they're ready, so you don't need to wait for the end.

### "No cards to send" / fewer cards than I expected
- Audio Review only plays **cloze** cards. Basic cards stay in Anki.
- It skips cards with an image on the front, cards that point at a picture, AnKing "one by one" cards and very long questions. They stay due in Anki as normal.
- Check the decks: **Tools ▸ Audio Review ▸ Settings ▸ Decks**.
- The phone only plays cards due **today** (Anki's day starts at its "next day starts at" hour, usually 4 am).

### Voice setup failed
- Check your internet connection and press **Try again**. Setup continues where it stopped.
- It needs about 650 MB of free disk space.
- Corporate or school computers sometimes block downloads from GitHub or PyPI; try another network.
- Details are in `CarReview/setup.log` in your home folder. Include that file if you [report a problem](https://github.com/AnkiCardReview/audio-review/issues).

---

## Applying phone answers

### Nothing happened when I opened Anki
- Anki waits for its opening sync first (up to a minute).
- If the phone still shows answers "waiting" to upload, open Audio Review on the phone with signal so it uploads them, then use **Tools ▸ Audio Review ▸ Apply phone answers…** in Anki.
- If there are no answers, you'll see "No phone answers waiting" when you use the menu.

### Some answers were "not applied"
That's the safety checks working. A card's phone answers are skipped if you already reviewed it elsewhere after the audio list was made (for example in AnkiMobile before opening Anki on the computer), or if it was deleted, suspended or moved out of your audio decks. Nothing is lost: the card simply keeps the review you did elsewhere.

### "Some answers are from an earlier day"
The answers are from a session before Anki's day changed (usually 4 am). Applying them now counts their next interval from today, so they land about a day later than they would have. Tick the box to apply them anyway, or leave it unticked to skip them.

### I applied by mistake
**Edit ▸ Undo** right away reverts the whole batch in one step. Anki also made a backup just before applying (**File ▸ Switch Profile ▸ Open Backup…**).

### "Problems (please report these)"
Audio Review checks every card after applying it. If Anki's result differs from what Anki promised, it tells you instead of hiding it. Please [open an issue](https://github.com/AnkiCardReview/audio-review/issues) with the message (it contains card IDs, not card text).

---

## Phone and pairing

### I lost my phone, or got a new one
On the computer: **Tools ▸ Audio Review ▸ Pair phone ▸ Make a new code**. The old phone stops working immediately, and its mailbox is deleted. Scan the new code with the new phone. Grades the old phone hadn't uploaded yet are lost.

### The Home Screen icon says "Not set up yet" (iPhone)
On iPhone, the Home Screen app keeps its own storage, separate from Safari. If you added the icon before scanning the code, delete the icon, scan the QR code again, and add to Home Screen from the page that opens.

### Android
Audio Review works in Chrome on Android: scan the code, then ⋮ ▸ **Add to Home screen**. Android hasn't been tested as widely as iPhone; please report anything odd.

### Will my phone delete Audio Review's cards?
Audio Review asks the browser to keep its data. iPhones can still clear website data that isn't used for a few weeks. If that happens, scan the QR code again; your cards download again and nothing in Anki is affected.

### Can I use two phones?
One phone per computer for now. Pairing a second phone with the same code works, but both would play the same cards.

### Can I use two computers?
Use Audio Review on one computer, the one you open and close each day. Answers are recorded in your collection when applied, so they sync to your other devices as normal Anki reviews.

---

## Privacy and cost

### Does anyone see my cards?
No. Everything is encrypted on your computer or phone before it's sent, and the mailbox only stores scrambled bytes for 3 days. See [Privacy](../PRIVACY.md).

### Does it cost anything?
No. Audio Review is free and open source. The only cost is your computer's electricity while it makes audio.

### Something else?
[Open an issue on GitHub](https://github.com/AnkiCardReview/audio-review/issues). Please never paste your QR code or pairing link.
