# RESEARCH-PACKAGING.md — evidence for the 3.3 packaging patch

Scope: the packaging and strategy decisions the factory currently makes on **assumption**, not evidence —
strategy, hook, CTA, thumbnail, captions, title, hashtags, on-screen "stickers", and the long-form choice.

Every claim below carries a source. Claims are graded:

| grade | meaning |
|---|---|
| **certain** | YouTube states it in its own documentation; it is a platform rule, not a theory |
| **strong** | a large published analysis or an official YouTube product behaviour with measurable effects |
| **indicative** | a credible expert/industry source; directionally useful, not proven |
| **unverified** | no source found. Treated as an **experiment to run**, never as a rule |
| **refuted** | a widespread belief that the evidence does not support |

Reported by an agent, 2026-10-20. Sources fetched directly on that date; `websearch` was unavailable, so
only exact-URL fetches were used. Anything not fetched is marked as such.

---

## 0. The headline findings (what changes our code)

These are the findings that directly contradict or support what the factory does today.

1. **Our long-form plan is not "long-form" at all.** YouTube classifies **any square-or-vertical upload of
   ≤3 minutes as a Short** (since 2024-10-15). Our long-form format is portrait 1080×1920, and our target was
   ~3 minutes. At 184 s we are *under* three minutes → the video would be published **as a Short**, monetised
   through the Shorts Creator Pool, and would not build the watch-hour threshold. *(certain)*
2. **There is a hard CTA surface we are not using: end screens.** YouTube supports end screens on the last
   5–20 s of a video, including a **Subscribe** element, with documented best practice to *leave time* for
   them. Our videos end on a spoken CTA and stop. *(certain)*
3. **Thumbnails on Shorts are real, supported, and need 9:16.** Custom Shorts thumbnails are desktop-only,
   need a verified account, recommended **2160×3840**, minimum height 640 px. And: **a vertical video with a
   16:9 thumbnail gets its thumbnail replaced by an auto-generated 4:5 one** on Home/Explore/Subs. *(certain)*
4. **Hashtags do not go in the title.** YouTube itself takes up to **three "most engaging" description
   hashtags** and shows them next to the title. So the manual workaround ("stuff hashtags into the title") is
   worse than the platform behaviour it duplicates. *(certain)*
5. **A/B testing of titles and thumbnails exists and is the correct way to settle "is the red sticker
   better".** Up to 3 variants, decided by **watch time share**, not CTR, finished within 2 weeks. Shorts are
   **not** eligible. *(certain)*
6. **"Inauthentic content" is now an explicit monetisation rule against templated, mass-produced video.**
   Our whole factory is a template pipeline. This is a real, named risk to monetisation, not a vague worry. *(certain)*

---

## 1. Strategy — why shorts gain views but not subscribers

### 1.1 YouTube's own monetisation thresholds *(certain)*

> "Get 1,000 subscribers with 4,000 qualified watch hours in the last 12 months, **or** Get 1,000 subscribers
> with 10 million qualified Shorts views in the last 90 days."

Source: https://support.google.com/youtube/answer/72851

**And the door closes further on 2027-02-01** *(certain)*:

> "Starting Feb. 1, 2027, YPP entry thresholds for new creators are changing to **8,000 qualified watch hours
> in the last 365 days**, or **20M qualified Shorts views in the last 90 days**, in addition to still needing
> 1k subscribers."

Source: https://support.google.com/youtube/answer/12843009

So the long-form target is **8,000 watch hours** for a channel that applies after 2027-02-01. Existing YPP
members are unaffected — which is an argument for **getting in before the gate rises**.

Also from the same page, the "active channel" rule: a channel stays active if it meets 1,000 watch hours/365 d,
**or** 1 M shorts views/90 d, **or** uploads **2 long-form videos or 5 Shorts per 90 days**. The owner's plan
of "2–3 long videos per week" clears the upload-count path with enormous margin.

And the decisive sentence for our strategy:

> "Keep in mind that any qualified watch hours from Shorts views in the Shorts Feed **won't count towards the
> 4,000 qualified public watch hours threshold**."

Source: https://support.google.com/youtube/answer/72851

**Consequence for Brain Academy.** The channel has 16 published shorts, median 1,260 views, 6 subscribers.
To reach 4,000 watch hours from shorts is *impossible* — shorts watch time does not count. The only two doors
are:
- 10 M qualified shorts views / 90 days (≈111 k views/day — about **88× the channel's current best week**, not
  a near-term path), or
- 4,000 watch hours from **long-form watch-page views** (~240,000 minutes; at the channel's 55.6 % AVP that is
  ~7,200 hours of 3-minute-long-form sessions… i.e. thousands of long-form views).

**This removes the "is long-form worth it" question.** For this channel, long-form watch time is the only
threshold that is even in reach. *(strong — arithmetic on certain inputs)*

### 1.2 Shorts are capped at 3 minutes and vertical ⇒ they are Shorts *(certain)*

> "Any videos uploaded on or after this date with a **square or vertical aspect ratio up to three minutes** in
> length will be categorized as **Shorts** on YouTube. These videos can be monetized in the **Shorts revenue
> sharing model** from the Shorts Feed."

Source: https://support.google.com/youtube/answer/15424877

And the only way to stay long-form:

> "If you don't want your content to be classified as Shorts, use a **wider aspect ratio such as 16:9** for
> long-form videos."

Source: https://support.google.com/youtube/answer/15424877

**This is the single most consequential finding.** Our decided long-form format (portrait 9:16, 1080×1920,
target ~3 min) is, by YouTube's own definition, a **Short**. It would:
- be served in the Shorts Feed, not the Watch Page;
- earn from the Shorts Creator Pool (needs 10 M views / 90 days to be eligible from 2027-02-01);
- contribute **zero** to the 4,000 watch-hour threshold.

See §9 for the decision this forces.

### 1.3 What the ranking system actually uses *(certain)*

> "Our systems use both **avg. view duration** and **avg. % viewed** as signals to inform ranking. Lastly, we
> look at whether or not viewers enjoyed the video using **likes and post-watch survey results**."

Source: https://support.google.com/youtube/answer/11914225

Also from the same page: "Our system has **no opinion about what type of video you make, and doesn't favor any
particular format**."

**Consequence.** Retention/AVP and likes are the levers. That supports the existing factory emphasis on
hook/retention gates, and means the *format* argument (shorts vs long) is **not** about algorithmic
preference — it is purely about which monetisation threshold each door opens (§1.1).

### 1.4 "Inauthentic content" — a named risk for a template factory *(certain)*

YouTube renamed "repetitious content" to "inauthentic content" on 2025-07-15 and lists as **not allowed to
monetise**:

> "AI-generated content made with **generic or unoriginal templates** giving the impression of mass production
> without adding the creator's original, authentic insights or perspective"
> "Image slideshows, **templated storylines**, or scrolling text with minimal or no narrative …"
> "channels where content feels interchangeable from video to video are not allowed to monetize"

Source: https://support.google.com/youtube/answer/1311392

Also from the same policy: reviewers look at "**Video metadata (including titles, thumbnails, and
descriptions)**" and the channel's "Main theme / Most viewed videos / Newest videos".

**Consequence for the factory.** Every video the factory makes is template-driven. The defence the policy
itself describes is *material variation + original insight per video*, which is exactly what our
RESEARCH→SCRIPT stages are supposed to produce. But **it must be visible in the packaging** (titles,
thumbnails, descriptions must not read as one template), and the channel must not look interchangeable. This
should become an explicit gate, not a hope.

### 1.5 Returning vs new viewers is a first-class, measurable segment *(certain)*

> "New viewers are viewers who watched something on your channel for the first time… Returning viewers could
> be viewers who have watched your channel previously and returned."

Source: https://support.google.com/youtube/answer/9314415

This is the metric that answers "are we becoming a channel people come back to" — better than raw views. It is
available per video, and by subscriber/non-subscriber. Our pre-registered D7 measurement should use it.

---

## 2. Hook — the first 30 seconds (and the first 3)

### 2.1 YouTube's own definition of "Intro" *(certain)*

> "Intro tells you what percentage of your audience still watched your video after the **first 30 seconds**."
> "A high intro percentage could mean: The content in the first 30 seconds **matched the viewer's expectation
> of the video's thumbnail and title**."

Source: https://support.google.com/youtube/answer/9314415

And the recommended fixes if the intro is weak:

> "Consider changing your video **thumbnail and title** to better reflect your video content."
> "Modify the **first 30 seconds** of your video and experiment with different styles."

Source: https://support.google.com/youtube/answer/9314415

**Consequence.** The hook and the thumbnail/title are **one system**, not two stages. A perfect 3-second hook
under a thumbnail that promises something else fails at the 30-second mark. Our pipeline treats HOOK and
PACKAGE as unrelated stages; they need a shared contract (see §4.4).

### 2.2 YouTube's own long-form hook recommendation: 5–10 seconds *(strong)*

> "**Hook viewers in the first 5–10 seconds** to keep them watching."
> "Map out a beginning → middle → end structure."

Source: https://www.youtube.com/creators/create/longform/

This is YouTube's creator guidance page, not a policy — so graded **strong**, not certain. But it is the closest
thing to an official "how long should the hook be" statement, and it is *longer* than the "3 seconds" folklore.
For long-form, plan a **5–10 second** hook; for Shorts the factory's existing tighter hook stays.

The widely-repeated "you have 3 seconds" figure was **not** found in any YouTube source. The 3-second rule is
**indicative/unverified** as a platform rule; it remains a reasonable craft heuristic for Shorts.

---

## 3. CTA — what exists, what we are missing

### 3.1 End screens: the surface we are not using *(certain)*

> "End screens can be added to the **last 5–20 seconds** of a video. You can use them to promote other videos,
> **encourage viewers to subscribe**, and more."
> "Your video has to be at least **25 seconds long** to have an end screen."
> "Make sure you leave **enough space and time at the end of the video** for an end screen."

Source: https://support.google.com/youtube/answer/6388789

Elements available: video, playlist, **Subscribe**, channel, external link (YPP). A **Subscribe** end-screen
element is a first-party CTA; end-screen click rate is reported in Analytics.

**Consequence.** The current "spoken CTA capped at 2.8 s" is not the only CTA we can have. An end screen (and
the visual CTA the owner asked for) can occupy the final 5–20 s. **The video must leave room for it** — that
means our last 5–20 s should be a visually stable "end-screen-safe" area, not busy full-frame motion.

Also relevant: **info cards** exist for mid-video, non-intrusive CTA (source: the "Add info cards to videos"
sibling page in the same help section). Not yet fetched in detail — see GAPS.

### 3.2 A related video under a Short *(certain)*

> "You can add a **related video** after you upload your Short to help direct viewers to your other YouTube
> content… Viewers will see a **clickable link below your channel handle**."

Source: https://support.google.com/youtube/answer/14075157
(Requires advanced feature access; the linked video must be public/unlisted.)

**Consequence.** This is the *official* shorts→long-form funnel. If we ever publish shorts again, each one
should carry a related-video link to the long-form video. It costs nothing and it is first-party.

### 3.3 Mid-video CTA and retention

*Gap:* no source found that measures whether a mid-video CTA **hurts retention**. YouTube's own advice is only
"leave time for the end screen" (§3.1) and "encourage viewers to click using calls to action for different end
screen elements".

**Decision:** mid-video visual CTA is **unverified** — an experiment, not a default. Personal belief ("the red
sticker did better") is likewise **unverified** at n=15.

### 3.4 A CTA *is* officially endorsed — just placed at content-defined moments *(certain)*

> "Encourage your viewers to engage with your content by subscribing, leaving a comment, or liking and sharing
> the video."
> "As you plan your video content, think of **appropriate moments** that you can encourage viewers to
> subscribe."

Source: https://support.google.com/youtube/answer/11913421

And for Shorts specifically:

> "Don't forget to engage. Something as simple as asking your viewers, 'If you liked the Short, give it a like
> and comment,' can do wonders!"

Source: https://support.google.com/youtube/answer/13363900

**Consequence.** The owner's instinct ("هیچ کال تو اکشنی نداریم … فکر نکنم خوب باشه") is **endorsed by
YouTube's own docs** — not just plausible. The only nuance: YouTube says *appropriate moments*, not a fixed
timestamp, and the end screen is the sanctioned surface for the subscribe ask.

### 3.5 The 8-minute threshold *(certain)*

> "You can also turn on mid-roll ads for videos **longer than 8 minutes**."
> "two back-to-back video ads can occur when you turn on ads for your long-form video (**at least 5 minutes** in
> length)."
> Watch While ads serve on "videos **between 2–8 minutes**".

Source: https://support.google.com/youtube/answer/2467968

**Consequence.** Length is a **revenue** decision, not just a retention one: <2 min earns with no mid-rolls at
all; 2–8 min gets Watch-While; >8 min unlocks mid-rolls; ≥5 min unlocks ad pods. Our earlier "target ~5 min"
sat at an arbitrary point with no source behind it. Now there is a reason to pick either "just over 8" (mid-rolls)
or to accept Watch-While. This should be an explicit, sourced choice.

---

## 4. Thumbnail

### 4.1 Shorts thumbnails are supported, 9:16, desktop-only *(certain)*

> "Custom video and **Shorts** thumbnails… Custom thumbnails for Shorts are currently only available to add in
> YouTube Studio on a computer. Your account must be **verified**."
> "For Shorts, try to upload a thumbnail with an aspect ratio of **9:16**."
> Recommended: "**2160 x 3840** for Shorts, with a minimum **height of 640 pixels** for Shorts."
> Desktop limit: **50 MB** for video, Shorts, and podcast thumbnails.

Source: https://support.google.com/youtube/answer/72431

### 4.2 The 4:5 trap *(certain)*

> "**Vertical videos with 16:9 custom thumbnails will be replaced by an auto-generated 4:5 thumbnail** on the
> home, explore, and subscription pages. Your custom thumbnail will still appear on the watch feed, watch
> history, and non-mobile platforms."

Source: https://support.google.com/youtube/answer/72431

**Consequence.** A 16:9 cover on a 9:16 video is silently thrown away where it matters most. Our cover must be
9:16. (Our pipeline already builds a vertical cover — this confirms the requirement and gives the exact spec.)

### 4.3 Thumbnail winner is decided by **watch time**, not CTR *(certain)*

> "At the end of the test, the title or combination of title and thumbnail with the **highest watch time** will
> be shown to all viewers."
> "We optimize tests for overall **watch time** over other metrics, like click-through-rate."

Source: https://support.google.com/youtube/answer/16391400

**Consequence.** This is the strongest argument in the whole document for the owner's instinct. A "sticker that
gets more clicks" can still be the *worse* thumbnail if it attracts the wrong viewers who then leave. So the
test must be judged on watch time / returning viewers, not views.

### 4.4 Thumbnail and title must promise what the video delivers *(certain)*

Per §2.1, YouTube's own diagnosis of a poor Intro is "the content in the first 30 seconds matched the viewer's
expectation of the video's thumbnail and title" — so the fix is to change the **thumbnail and title**.

**Consequence.** The factory's thumbnail gates are geometric; §4.4's requirement is semantic. This is exactly
the owner's complaint ("از روی متنش و عکسش نمیشه فهمید چیه"). It is now backed by YouTube's own retention
diagnosis, and it needs an **agent judge** (the P6.2 item in ROADMAP.md).

### 4.5 A/B testing eligibility *(certain)*

> "**You are not able to A/B test Shorts**, Scheduled Lives, and Premiere videos at this time."
> "Desktop only… enable advanced features… cannot be used on videos made for kids, mature audiences, or private."
> "Your test should be completed within **two weeks**."
> "If the resolution of any thumbnail is lower than 720p (1280x720), all experiment thumbnails will be
> downscaled to 480p."

Source: https://support.google.com/youtube/answer/16391400

**Consequence.** For **long-form** (16:9) we can A/B test titles and thumbnails natively — the clean way to
settle packaging questions. For **Shorts** we cannot; testing shorts packaging requires sequential tests and
is therefore much weaker evidence.

---

## 5. Title

- Titles are part of what reviewers assess for monetisation ("Video metadata (including titles, thumbnails,
  and descriptions)") — https://support.google.com/youtube/answer/1311392 *(certain)*
- Title character limit: **not fetched in this pass** — see GAPS. (Commonly stated as 100 characters; not
  verified against a YouTube page in this session, so **do not encode it as certain**.)
- The only mechanism by which hashtags appear near the title is **YouTube promoting description hashtags**
  (§7), not the creator writing `#` in the title.
- Title A/B testing: up to 3 titles, decided by watch time, long-form only (§4.3/§4.5) *(certain)*

**Consequence.** Our `title_options` should be written as *testable variants* (different promises, not
punctuation tweaks) — YouTube's own tip: "Testing titles and thumbnails that are too similar to each other can
cause tests to run for longer." Source: https://support.google.com/youtube/answer/16391400 *(certain)*

---

## 6. Captions / subtitles

*Gap:* No YouTube page found in this session stating that captions improve retention or discovery. The
frequently-cited "captions increase watch time by ~12 %" figure has **no primary source** found here.

What is certain and relevant:
- Burned-in captions are an **accessibility and mobile-silent-autoplay** aid; YouTube does not require them but
  provides its own auto-captions and manual caption upload.
- Our burned word-synced captions remove dependence on YouTube's auto-captions, which for a heavily-accented or
  technical narration can be wrong.

**Decision:** keep burned captions. Justify them as **craft and accessibility**, not as a proven ranking
lever. *Gap stands.*

---

## 7. Hashtags — the owner's question ("هشتگ در تایتل مهم است؟")

### 7.1 YouTube promotes up to three description hashtags by the title *(certain)*

> "**Out of all the hashtags you add to the video's description, up to three hashtags that are considered most
> engaging will appear by your video title.** Your hashtags will still appear in the video description, and
> your videos can still appear in search results."

Source: https://support.google.com/youtube/answer/6390658

**Answer to the owner's question:** you do **not** need to put hashtags in the title. Put them in the
**description**; YouTube itself selects up to three and shows them beside the title. Putting `#` in the title
is manual, competing with the platform, and eats title characters.

### 7.2 Over-tagging is actively punished *(certain)*

> "If a video or playlist has **more than 60 hashtags, we'll ignore each hashtag** on that content.
> **Over-tagging may result in the removal of your video from your uploads or from search.**"

Also prohibited: "adding ordinary descriptive tags or repetitive sentences in the description", misleading or
unrelated hashtags → "may result in the removal of your video or playlist".

Source: https://support.google.com/youtube/answer/6390658

**Consequence.**
- **Hard cap: ≤ 60**, and in practice far fewer (3–8 relevant ones).
- **Every hashtag must be directly related** to the video, or it risks removal from search.
- The `#Shorts` question: this page does **not** mention `#Shorts` as a requirement. YouTube classifies short
  videos by **aspect ratio + duration**, not by hashtag (§1.2). So `#Shorts` is **not needed** for
  classification. *(certain — by absence in the official hashtag/Shorts docs plus the explicit
  aspect-ratio rule)*

---

## 8. On-screen "stickers" / coloured callouts (the owner's red-sticker observation)

### 8.1 What is certain

- YouTube does **not** publish guidance claiming on-screen shapes/stickers improve retention. *(absence of
  source — treated as unverified)*
- YouTube **does** explicitly warn against **deceptive or misleading imagery** in thumbnails/titles, and lists
  "Titles or thumbnails with sexualized themes (including misleading signals)" and "Circling out or otherwise
  calling attention to something in a thumbnail which suggests implied sexual acts" under policy violations.
  Source: https://support.google.com/youtube/answer/6162278 *(certain)*
  → So red callouts on **thumbnails** must not imply something the video does not contain.

### 8.2 The owner's observation, graded honestly

"توی یه ویدیو استیکر قرمز گذاشتم حس میکنم ویوش بالا تر رفت" — **unverified**.
n = 1 video. At median 1,260 views and a range of 168–1,945, a single video landing high is well inside normal
variance.

**The correct instrument already exists:** A/B testing (§4.5) — but **not on Shorts**. For long-form (16:9)
titles/thumbnails can be A/B tested properly. Inside the video, a red callout can be tested as a **title/thumb
variant** or by comparing matched pairs of videos.

**Decision:** capture the hypothesis as a pre-registered experiment; do not encode "red sticker → more views"
as a rule.

---

## 9. Long-form strategy — and the format problem

### 9.1 The three-minute vertical trap (restated because it decides the plan)

| if we upload | YouTube calls it | served in | counts toward 4,000 h |
|---|---|---|---|
| 9:16, ≤ 3:00 | **Short** | Shorts Feed | **no** |
| 16:9, any length | long-form | Watch Page | **yes** |
| 9:16, > 3:00 | long-form (not a Short) | Watch Page | **yes** |

Source: https://support.google.com/youtube/answer/15424877 and https://support.google.com/youtube/answer/72851

Our 184-second portrait video is a **Short**. Our target of "~3 minutes, portrait" accidentally aims at the
least useful cell in the table.

Options:
- **(A) 16:9 long-form.** The only format that looks like long-form to YouTube *and* is A/B testable *and*
  earns Watch-Page watch hours. Costs: art must be re-laid-out landscape (all 29 SVGs, camera moves, caption
  band). Deferred in v3.2.0 as "16:9 in v3.3".
- **(B) 9:16 but > 3:00.** Keeps the existing portrait renderer, but must exceed 3:00 (we have 184 s ≈ 3:04 —
  *just* over, and dangerously fragile: a re-render that trims 5 s silently converts it back into a Short).
- **(C) Keep making Shorts and pursue 10 M views / 90 days.** Given 6 subscribers and 1,260 median views, this
  is not a near-term path.

**Recommendation:** (A) for real long-form, with (B) explicitly rejected as fragile. If (A) is too expensive
for this iteration, publish the current video as a *Short* and be honest that it is a Short — do not call it
long-form or measure it as long-form.

### 9.2 Vertical long-form is not forbidden, just padded *(certain)*

> "For some video and device aspects ratios like **9:16 vertical videos on computer browsers**, YouTube may add
> more padding for optimal viewing."
> "For best results, **avoid adding padding or black bars directly to your video**."

Source: https://support.google.com/youtube/answer/6375112

So portrait >3:00 long-form is allowed, but is *padded* on desktop — a worse viewing experience on the device
where long-form is actually watched.

### 9.3 Encoding targets *(certain)*

> 1080p (HD): **1920x1080**; 720p (HD): 1280x720; standard aspect 16:9.
> Note: "In 2022, we started removing support for playback at resolutions between 4K and 8K."

Source: https://support.google.com/youtube/answer/6375112

Our 1080×1920 is the portrait twin of 1080p and remains valid for Shorts; for 16:9 long-form the target is
1920×1080.

---

## 10. Gaps — what we could NOT verify (do not encode these as rules)

1. **Title character limit** for 2026 — not fetched. Verify at
   https://support.google.com/youtube/answer/57407 before hard-coding.
2. **Mid-roll ad minimum length** — the URL previously assumed (6162278) is now *Advertiser-friendly content
   guidelines*, not the mid-roll page. The mid-roll minimum was **not** verified in this session.
3. **Captions → retention/watch time** — no primary source found. Do not cite the "~12 %" figure.
4. **"You have 3 seconds"** — no YouTube source. Craft heuristic only.
5. **Mid-video CTA effect on retention** — no source found in either direction.
6. **"Red sticker increases views"** — unverified, n=1 (owner's observation).
7. **Info cards** — the page exists ("Add info cards to videos") but was not fetched in this pass; their
   current behaviour and any effect on retention is unverified.
8. **Hashtag count → reach** — YouTube says over-tagging is punished; it does **not** say more hashtags help.
   The "sweet spot" number is unknown; choose by relevance, not by a magic count.

---

## 11. Code reality — finding vs. what the factory already does

Read against the current tree so the 3.3 patch is a delta, not a rewrite. Each row is either **aligned**
(nothing to do), **gap** (a real missing capability) or **wrong** (contradicts a source).

| finding | current code | verdict |
|---|---|---|
| Shorts thumbnail vertical, min 640 px height, ≤50 MB | `package_run.py:184` reads size; cover is 1080×1920 | **aligned** on aspect; check the min-height and 50 MB caps are *asserted*, not assumed |
| 4:5 replacement trap for 16:9 thumbs on vertical video | cover is portrait | **aligned** |
| Hashtags in description, ≤3 promoted by YouTube, >60 ignored, over-tagging punished | `script_lint.py:72` gate is `1 ≤ len(tags) ≤ 8` | **aligned** (far below 60) — but the *why* is not recorded; add the source to the gate message |
| Do **not** put `#` in the title | titles come from `title_options`; hashtags only go into description/caption (`package_run.py:152-154`) | **aligned** |
| Title ≤100 chars | `script_lint.py:69` `SCRIPT.TITLE_LENGTH` ≤100; `package_run.py:26` `YT_TITLE=100` | **aligned** — but the 100 figure is not source-verified (§10 gap 1) |
| **≤3 min vertical ⇒ it is a Short** | `factory.py:686` `video_kind = "long" if a.max_s > 180 else "short"` | **wrong by YouTube's definition** — `>180` is exactly the 3-minute boundary, but the *aspect ratio* is portrait, so a "long" run at 184 s is a Short. `video_kind` must also consider aspect ratio (owner decision D1: go 16:9) |
| **Mid-roll needs >8 min; ad pods ≥5 min** | no length decision is sourced | **gap** — length should be an explicit revenue choice, cited, not "target ~5 min" |
| **Shorts get paid via a separate pool needing 10 M views/90 d** | `platform-policies.md` mentions short/long windows | **gap** — the *money* consequence of the classification is not documented |
| **YouTube's 5–10 s hook for long-form** | hook gates are tuned for shorts | **gap** — long-form hook window should be 5–10 s, not the shorts window |
| **Inauthentic-content: templated AI = not monetisable** | nothing gates on packaging *variation* | **gap** — highest-risk item for a template factory; needs a variation check |
| **End screens need 5–20 free seconds at the end** | nothing leaves room; the hook/CTA stage caps the spoken CTA at `min(2.8 s, 12 %)` | **gap** — no end-screen-safe tail, no Subscribe end-screen instruction in `metadata.human_must_set` |
| **Related video under a Short** | already emitted for `cta.type == "part_2"` (`package_run.py:168`) | **aligned but under-used** — should be emitted for *every* Short that has a long-form sibling, not only part_2 |
| Thumbnail/title must promise what the video delivers | thumbnail gates are geometric (`package_engine.thumb_checks`, 18 gates) | **gap** — semantic check needs the agent judge (ROADMAP P6.2) |
| A/B test titles/thumbs, decided by watch time, not for Shorts | not modelled | **gap** — PACKAGE should hand the owner 3 *diverse* title variants marked "A/B testable (long-form only)" |
| Ranking uses avg view duration / avg % viewed / likes | AVP is already in `experiment.METRICS` | **aligned** |
| Intro = first 30 s; thumb+title are the fix | the 30 s mark is not a named gate | **gap** — add an `intro_30s` observation to the long-form measurement |
| CTA/relevance needs shared words with `title_options[0]` | `cta.py` `check()` does this | **aligned** |

---

## 12. Decisions taken from this research (owner, 2026-10-20)

| # | decision | rationale |
|---|---|---|
| D1 | **Build real 16:9 long-form.** The portrait long-form plan is dropped as fragile (a 9:16 ≤3:00 upload is a Short by definition). | §9.1 — only 16:9 both *is* long-form to YouTube and is A/B testable, and only long-form watch hours open the YPP door. |
| D2 | **Add end-screen support.** Leave a calm, end-screen-safe tail (5–20 s) and emit the "add a Subscribe end screen" instruction to the human. **Not applied to Shorts** (owner: "روی شورت نداره فکر کنم"). | §3.1 — official Subscribe element; needs free time at the end. |
| D3 | **Record every no-source belief as a pre-registered experiment judged by watch time.** Red sticker, mid-video CTA, title phrasing. | §4.3/§8.2 — YouTube itself decides title/thumb winners by watch time, not CTR; Shorts can't be A/B tested natively, long-form can. |

Pre-registration record (to be added to the experiments layer before any A/B runs):

| id | hypothesis | status | judged by |
|---|---|---|---|
| X-STICKER | a coloured callout on the cover changes performance | **unverified**, n=1 | watch time share (long-form A/B only) |
| X-MIDCTA | a mid-video visual CTA costs more retention than it gains | **unverified** | retention curve + avp/avd |
| X-TITLECASE | sentence-case vs title-case titles change reach | **unverified** | watch time share |

---

## 13. Sources fetched (all 2026-10-20)

| # | URL | what it established |
|---|---|---|
| 1 | https://support.google.com/youtube/answer/72851 | YPP thresholds; shorts watch time excluded from 4,000 h |
| 2 | https://support.google.com/youtube/answer/15424877 | ≤3 min vertical = Short; 16:9 to stay long-form; claimed >1 min Shorts blocked |
| 3 | https://support.google.com/youtube/answer/11914225 | ranking uses avg view duration, avg % viewed, likes, surveys; no format preference |
| 4 | https://support.google.com/youtube/answer/1311392 | inauthentic content: templated / mass-produced AI = not monetisable |
| 5 | https://support.google.com/youtube/answer/9314415 | Intro = first 30 s; new vs returning viewers; retention segments |
| 6 | https://support.google.com/youtube/answer/6388789 | end screens: last 5–20 s, Subscribe element, ≥25 s video, leave time |
| 7 | https://support.google.com/youtube/answer/14075157 | related video under a Short = clickable link below channel handle |
| 8 | https://support.google.com/youtube/answer/72431 | Shorts custom thumbnails: 9:16, 2160×3840, min h 640, desktop-only, 4:5 replacement rule |
| 9 | https://support.google.com/youtube/answer/16391400 | A/B test ≤3 titles/thumbs, decided by watch time, 2 weeks, **not for Shorts** |
| 10 | https://support.google.com/youtube/answer/6390658 | up to 3 description hashtags shown by the title; >60 ignored; over-tagging can remove from search |
| 11 | https://support.google.com/youtube/answer/6162278 | advertiser-friendly guidelines; misleading thumbnail/callout imagery prohibited |
| 12 | https://support.google.com/youtube/answer/6375112 | 16:9 standard; 1920×1080; 9:16 desktop padding warning |
| 13 | https://support.google.com/youtube/answer/12504220 | Shorts Creator Pool; 10 M views/90 d requirement from 2027-02-01; engaged views |
| 14 | https://support.google.com/youtube/answer/12843009 | 2027 thresholds 8,000 h/365 d; monthly Shorts pool 10 M; active-channel rules; Premium pools |
| 15 | https://support.google.com/youtube/answer/2467968 | mid-rolls need >8 min; ad pods ≥5 min; Watch-While serves 2–8 min |
| 16 | https://support.google.com/youtube/answer/11913421 | official CTA guidance: "appropriate moments"; signature sign-off; ask for comment/like |
| 17 | https://support.google.com/youtube/answer/13363900 | Shorts guidance explicitly endorses an in-Shorts engagement CTA |
| 18 | https://support.google.com/youtube/answer/10059070 | 3-minute Shorts; Shorts YPP path; Shorts views metric change 2025-03-31 |
| 19 | https://support.google.com/youtube/answer/16089387 | recommendation signals list (watch history, surveys, etc.); "satisfaction, not just watch time" |
| 20 | https://www.youtube.com/creators/create/longform/ | long-form guidance: hook in the first 5–10 s; 15-min default upload; 256 GB / 12 h max |
| 21 | https://support.google.com/youtube/answer/10343433 | title 100-character limit; titles may be truncated (verify before encoding) |

Companion reports (same date, by background research agents, kept alongside this file):
`research/youtube-shorts-packaging-2026.md`, `research/youtube-longform-strategy-2026.md`.
