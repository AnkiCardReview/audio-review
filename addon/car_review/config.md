**Use Tools ▸ Car Review ▸ Settings instead of editing this.** The Config button opens the same settings window; this page only describes what it stores.

**decks**: the decks to send to the car, played one after another in this order. Subdecks are included.

**days_ahead**: how many days past today the car list covers (default 1). Each list also carries the next day's exact cards, so 1 is enough when you open Anki most days; more covers days without Anki, with bigger downloads. Cards are only played on the day they're due.

**auto_apply**: car answers are picked up when Anki opens and after each sync. `false` (default) shows what they will do and waits for you to click Apply. `true` applies them straight away (with a backup first) and shows a summary afterwards.

**auto_voice**: `true` (default) makes missing audio automatically when Anki closes while the computer is plugged in. `false` only makes audio when you use Tools ▸ Car Review ▸ Prepare audio. Audio is never made on battery.

**main_bar**: `true` (default) shows the Car Review bar under the deck list on Anki's main screen: when cards were last sent, what the phone has downloaded, and buttons for Send to Car, Make audio and send, Check phone and Settings. `false` hides it (everything is still in Tools ▸ Car Review).


**python**: leave empty. Only set it if Car Review's voice helper runs from a Python other than the `CarReview/venv` folder that voice setup makes.

**setup_done**: set once the setup window has opened by itself, so it only does that once.
