# How Audio Review works

## The three pieces

| Piece | Where it runs | What it does |
|---|---|---|
| **The add-on** | Anki on your computer | Picks the cards that are due, makes their audio, sends them to your phone, and applies your phone answers |
| **The app** | Your phone, as a Home Screen icon (a web page; no app store) | Reads the cards out loud, takes your button presses, works offline |
| **The mailbox** | A small free relay on Cloudflare | Holds your encrypted cards, audio and answers so the phone and computer never need to be online at the same time |

```
 Computer (Anki + add-on)            Mailbox (relay)              Phone (Audio Review app)
 ─────────────────────────           ───────────────              ──────────────────────
 close Anki ──► cards + audio ──►  [ scrambled bytes ]  ──►  download, play aloud
 open Anki  ◄── apply answers  ◄── [ scrambled bytes ]  ◄──  upload your answers
```

## A normal day
| When | You do | What happens by itself |
|---|---|---|
| Evening | Close (or sync) Anki after your last review | Audio Review sends the cards due today, the next day's exact list (worked out by Anki's own scheduler on a temporary copy of your collection), and audio for tomorrow's cards |
| Early morning | Nothing | When Anki's day starts, the phone switches to the next day's list by itself. Your computer can be off |
| Before a session | Open Audio Review on the phone | On a new Anki day it syncs by itself: the new list, and audio only for cards it doesn't have yet. The **Sync** button turns green (✓ Synced) when there's nothing left to do |
| Listening | Tap Start, then answer with headphones, a remote, the screen or the steering wheel | Each answer is saved on the phone right away. Nothing is uploaded during a session |
| Done | Tap Stop | The answers upload (or as soon as there's signal, or when you next open the app) |
| Back at the computer | Open or sync Anki | It syncs, downloads your phone answers, checks them, and (after you click Apply) records them through Anki's own scheduler |

**Syncing works like Anki's.** Nothing checks in on a timer. The computer sends when Anki syncs, opens or closes, and on **Send to phone**, but only if the list actually changed: an unchanged send makes no requests at all. The phone shows when your computer last sent (**From laptop**), with ⚠ old when that list doesn't cover today; then sync or close Anki on your computer. The phone syncs when you tap **Sync**, by itself when it opens on a new Anki day or with answers still to send, and after Stop. The Sync button's color says whether there's anything to do: green ✓ Synced (nothing; tapping again only says "Already up to date"), blue Sync now (with the reason underneath), amber (no signal; answers are kept and sent later).

**On the computer, Anki's main screen** has an Audio Review box under your decks: when cards were last sent and how many are ready, whether the phone has downloaded everything (or how many audio files are still waiting for it) and whether phone answers are waiting. Its buttons are **Send to phone**, **Make audio and send**, **Check phone** (looks at the mailbox once and picks up phone answers) and **Settings**. The box never contacts the relay by itself; it shows what the last send or check saw. Turn it off in Settings ▸ Options.

**Why it uses so little data.** Each card's audio is made once on your computer and kept there for good, and it crosses to the phone once: the phone keeps it after playing (up to the limit under **Storage**, 1 GB by default, about 16,000 cards), tells the computer which clips it has, and the computer sends only the missing ones, many clips to a file. The phone deletes those files from the mailbox as soon as it has them, and the mailbox holds at most about 80 MB for you at a time: on a first setup, the rest follows once the phone has fetched what's waiting. Downloads over 50 MB ask first, so you can wait for Wi-Fi. The list itself is compressed and only downloaded when it changed.

**What runs on your computer when Anki is closed.** Audio Review never runs in secret; each of these shows in Settings and can be turned off:
- **Making audio and sending**: after you close Anki, with a small progress window you can pause or stop.
- **Nothing else.** Earlier versions added a 4:30 am task ("Car Review morning list") and kept a plugged-in laptop awake for it; this version removes that task the first time it sends.

**Your stats.** The phone's home screen shows today: cards, minutes and the share of reviews you got right (per deck), each session (headphones, remote, screen or car), and the past week's days. These stay on the phone. In Anki, **Tools ▸ Audio Review ▸ Audio stats** shows up to 10 recent sessions, audio vs Anki retention per deck over the last 7 and 30 days (mature and young separately), and where the drive's time went: listening, your thinking and the phone's own delay. The phone measures those times for each clip (times only, no card text) and sends them along with your answers.

**The two rules:** sync or close Anki on the computer after your last review of the day, so the next day's list includes it. And after a session, open Anki on the computer before reviewing on AnkiMobile or AnkiDroid. If you forget, nothing breaks: any card you've already reviewed elsewhere is skipped when the phone answers are applied, so nothing is ever counted twice.

Data use: about 62 KB per card the phone hasn't had before, and nothing for cards it already has. A first setup is about 60–125 MB (today's and tomorrow's cards); the first weeks, while cards come up for the first time, about 5–30 MB a day; after that usually a few MB a day.

## Your privacy, simply

- **Your cards stay yours.** Everything that leaves your computer is locked (encrypted with AES-256) *before* it leaves, and only unlocked on your phone, and the other way round for your answers. The mailbox, Cloudflare and the people who run Audio Review only ever see scrambled bytes.
- **The key is the QR code.** Scanning it gives your phone the key. The key sits in the part of the link after `#`, which browsers never send to any server. (It stays in the page address so that *Add to Home Screen* can hand it to the Home Screen app; that's also why the QR code and that browser tab should stay private.) If a phone is lost, make a new code and the old one stops working.
- **The voice runs on your computer.** Your cards are never sent to a speech service.
- **No accounts, no tracking.** The app has no analytics, no ads and no third-party scripts. It only talks to your own mailbox.
- **Nothing lingers.** The mailbox deletes everything after 3 days.

More detail: [Privacy policy](../PRIVACY.md).

## Why your scheduling stays safe

Audio Review never edits your cards or invents intervals. When you click **Apply**, each answer goes through **Anki's own answer function**, the same one used when you press Again or Good in Anki, with the time you pressed the button on the phone. So FSRS (or SM-2), learning steps, the load balancer, leech handling and sibling burying all behave exactly as they would in Anki.

Before anything is applied:
1. **Backup.** Anki makes a backup, and **Edit ▸ Undo** reverts the whole batch in one step.
2. **Sync first.** Audio Review waits for Anki's opening sync, so it knows about reviews you did on other devices.
3. **Per-card checks.** A card is skipped if it was reviewed anywhere after the audio list was made, if it was deleted, suspended, buried or moved out of your audio decks, or if it isn't in the state the audio list recorded.
4. **In order, never twice.** Each card's answers are applied oldest first. Applied answers are recorded inside your collection (which syncs), so no computer can apply them twice.
5. **Late answers are flagged.** Answers from an earlier Anki day are only applied if you tick the box, because Anki would measure the next interval from today.
6. **Self-check.** For each card, Audio Review notes the interval Anki promised for that button, applies the answer, and checks the new due date matches. Anything unexpected is reported instead of hidden.
7. **Only what's possible.** It accepts only cards that were in your own audio list, only Again or Good, and only sensible times.

The phone works like Anki too: a card you miss comes back after your learning step, cards are played in the order Anki would show them, one deck at a time, and only cards due today are played.

## Which cards are played
- Cloze cards in the decks you chose: reviews due today and learning cards (no new cards).
- One card per note per day, as Anki's sibling burying does.
- **Skipped automatically** (they stay due in Anki): non-cloze cards, cards with an image, table or audio on the front, cards that point at a picture ("shown", "labeled", "arrow"), questions over 60 words, AnKing "one by one" cards, and cards you triple-pressed ⏮ on (tagged `audio-review::skip`). New cards aren't played either: which ones Anki shows depends on burying and how many you want that day, so they're best done in Anki.
- **Read naturally:** formatting is removed, symbols become words (↑ "increased", → "leads to"), ranges and units are spoken ("24–28 mg/dL" → "24 to 28 milligrams per deciliter"), and common shorthand is expanded. A blank is said as "blank", or as its hint ("…is *which drug?*").

## The audio
The add-on makes each card's audio with **Kokoro "Heart"**, an open-source voice that runs on your computer. It runs only while the computer is plugged in, at low priority, with a small progress window you can pause or stop. Each clip is saved, so a card is only ever voiced once (unless you edit it). On a typical laptop the first batch takes roughly 10 seconds per card; after that it's only new cards, usually a few minutes a day. Voice speed is set on the phone.
