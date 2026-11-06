# Audio Review

**Hear your Anki cards, hands-free.** Your phone reads your due Anki cloze cards out loud, so you can review on a walk, on the treadmill, doing chores or driving. Answer with your headphones' next/previous track buttons, a Bluetooth remote, big buttons on the screen, or your car's steering-wheel buttons. Your answers go back into Anki through Anki's own scheduler, exactly as if you had pressed the buttons yourself.

Free and open source. No account, no app store, no subscription. Works with Anki on Windows, Mac and Linux, and with an iPhone or Android phone.

| On your computer | On your phone |
|---|---|
| ![The Audio Review setup window in Anki](help/images/wizard-decks.png) | ![The Audio Review app on a phone](help/images/phone-intro.jpg) |

## Quick start (about 10 minutes)

1. **Install the add-on.** In Anki, go to **Tools ▸ Add-ons ▸ Get Add-ons…**, paste the add-on code *(coming soon)* and restart Anki. Until the AnkiWeb listing is up, use the `.ankiaddon` file instead: see the [setup guide](help/setup.md#1-install-the-add-on).
2. **Follow the setup window.** It opens by itself after the restart. Tick the decks you want to hear and leave the options as they are.
3. **Set up the voice.** Press **Set up the voice**. It's a one-time download of about 340 MB, and nothing is installed system-wide. You can carry on with the next step while it downloads.
4. **Scan the QR code** with your phone's camera. Then add Audio Review to your Home Screen (iPhone: Share ▸ *Add to Home Screen*; Android: ⋮ ▸ *Add to Home screen*) and open it from there.
5. **Listen.** Close or sync Anki, and your cards go to your phone. Open Audio Review, tap **Start** and put the phone away. Tap **Stop** when you're done; Anki picks up your answers at its next sync and applies them.

**Answering:** ⏭ next track = hear the answer, then ⏭ again = **Good**. ⏮ previous track = **Again** (before the answer, it repeats the question instead). Press ⏮ twice to go back a card (you hear its question again), three times to skip a card that doesn't work as audio. These work from headphones, AirPods, the lock screen and steering-wheel buttons.

**With the screen on:** **walking mode** turns the screen into two big buttons (left half Again, right half answer/Good, swipe right to go back a card). A Bluetooth remote, page turner or game controller in keyboard mode works too, with keys you choose in the app. Hold 🔒 to lock the screen so the phone can go in a pocket without stray taps. If you'd rather not press for the answer, the app can play it by itself after a number of seconds you choose.

**Afterwards:** the phone's home screen shows today's cards, minutes and reviews right, and roughly how long the rest of today will take. In Anki, **Tools ▸ Audio Review ▸ Audio stats** shows your past sessions and compares how you do by audio with how you do in Anki, per deck, for mature and young cards. Anki's main screen also shows what was last sent to your phone.

> **In the car, safety first.** Set everything up and tap Start *before* you drive. While driving, use only the steering-wheel buttons, and never look at or touch the phone. See the [terms of use](TERMS.md).

## Learn more
- [Setup guide](help/setup.md): every step in detail, with what you should see
- [How it works](help/how-it-works.md): privacy, and why your scheduling stays safe, in plain words
- [Troubleshooting and FAQ](help/troubleshooting.md): buttons not working, Spotify taking over, no audio yet, lost phone and more
- [Privacy policy](PRIVACY.md) · [Terms of use](TERMS.md)
- [For developers](CONTRIBUTING.md): how the code fits together, tests and releasing

## What it can and can't do
- **Cloze cards only** for now. Basic cards, cards with an image on the front, cards that point at a picture and AnKing "one by one" cards are skipped, and stay due in Anki as normal.
- **Reviews and learning cards.** New cards aren't played: start them in Anki, and they join your audio reviews from then on.
- **English voice** (Kokoro "Heart"). The audio is made on your own computer while it's plugged in. The first time, a typical laptop takes a few seconds per card (much less with an NVIDIA graphics card); after that, each card is ready for good, so only new cards need audio.
- **Runs a little in the background**, all shown in Settings: audio is made after Anki closes (with a progress window), and each list also carries the next day's cards, worked out by Anki's scheduler on a temporary copy of your collection, so your computer can be off in the morning. [Details](help/how-it-works.md#a-normal-day).
- **Anki desktop** is needed. It is tested with Anki 26.09; versions from 24.11 on should work. AnkiMobile and AnkiDroid keep working as usual alongside it.

## License
[GNU AGPL v3](LICENSE). Free to use, copy and change; changed versions must stay open source.

Audio Review is an independent project. It isn't affiliated with or endorsed by Anki or Ankitects. It was called Car Review before November 2026.
