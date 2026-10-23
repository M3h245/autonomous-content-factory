# YouTube Shorts Packaging in 2026 — Research Report

Scope: what is verifiable, as of October 2026, about YouTube Shorts **packaging** — thumbnails, titles, hashtags, on-screen text/stickers, captions, and the link between Shorts reach and subscriber conversion.

Method and constraints:
- `websearch` was disabled. Every source below was retrieved by fetching its exact full URL. Nothing here was inferred from a search-result snippet.
- Every claim is marked with a confidence level. Where a widely repeated number could not be traced to a primary source, it is marked **NOT VERIFIED** rather than repeated.
- Primary sources (YouTube Help Center, YouTube Official Blog, youtube.com/creators) are preferred. Secondary sources (vidIQ) are used only where explicitly labelled and are never treated as authoritative.
- Claims are labelled **[EVIDENCE]** (a documented statement or documented product behaviour) or **[OPINION]** (a recommendation or interpretation, whether from YouTube or a third party).
- All facts were observed on these pages in October 2026.

---

## 1. Thumbnails for Shorts

**CLAIM:** YouTube officially supports custom thumbnails for Shorts, and this is a first-class, documented feature, not a workaround.
**SOURCE:** https://support.google.com/youtube/answer/72431 (Add custom thumbnails on YouTube) — "Custom video and Shorts thumbnails let your audience view a quick snapshot of your content." The page has a dedicated procedure titled "Add a custom Short thumbnail," reached via YouTube Studio → Content → **Shorts** at the top.
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is the single most important packaging fact for the project: uploaded Shorts can carry a designed thumbnail rather than only an auto-selected frame.

**CLAIM:** Custom Shorts thumbnails can currently only be added in YouTube Studio on a computer, and the uploading account must be verified.
**SOURCE:** https://support.google.com/youtube/answer/72431 — "**Note:** Custom thumbnails for Shorts are currently only available to add in YouTube Studio on a computer. Your account must be verified to use this feature."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** For an automated factory, this constrains where thumbnail attachment can happen: it is a Studio-on-desktop operation, not a mobile-app operation. The separate mobile frame-picker is a different feature (see below).

**CLAIM:** For Shorts, YouTube recommends a 9:16 aspect ratio, a resolution of 2160 x 3840 pixels, and a minimum height of 640 pixels.
**SOURCE:** https://support.google.com/youtube/answer/72431 — "Have a resolution of 3840 x 2160 pixels for videos and 2160 x 3840 for Shorts, with a minimum width of 640 pixels for videos and a minimum height of 640 pixels for Shorts" and "For Shorts, try to upload a thumbnail with an aspect ratio of 9:16."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** The minimum for Shorts is expressed as **height** ≥ 640 px (the inverse of the long-form width rule), consistent with a portrait asset.

**CLAIM:** On desktop, Shorts thumbnails may be up to 50 MB; the larger file limit applies to video, Shorts and podcast thumbnails.
**SOURCE:** https://support.google.com/youtube/answer/72431 — "**Desktop:** 50MB for video, Shorts, and podcast thumbnails." (Mobile list is "2 MB for video thumbnails or 10 MB for podcasts" and does not name Shorts.)
**CONFIDENCE:** High for the desktop figure. **[EVIDENCE]**
**NOTE:** The mobile row does not mention Shorts, which is consistent with custom Shorts thumbnails being desktop-only.

**CLAIM:** A vertical video given a 16:9 custom thumbnail will have that thumbnail replaced by an auto-generated 4:5 thumbnail on the Home, Explore and Subscriptions pages, while the custom thumbnail is retained on the watch feed, watch history and non-mobile platforms.
**SOURCE:** https://support.google.com/youtube/answer/72431 — "**Note:** Vertical videos with 16:9 custom thumbnails will be replaced by an auto-generated 4:5 thumbnail on the home, explore, and subscription pages. Your custom thumbnail will still appear on the watch feed, watch history, and non-mobile platforms."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is a concrete reason to author Shorts thumbnails at 9:16 rather than reusing a 16:9 long-form asset: mismatched assets are silently swapped out on the highest-traffic surfaces.

**CLAIM:** Separately from custom thumbnails, YouTube's own Shorts creation flow lets a creator pick a frame from the Short as the thumbnail, and this frame-picking can be done in the YouTube mobile app (before or after upload) — explicitly "not from Studio."
**SOURCE:** https://support.google.com/youtube/answer/10343433 (Create YouTube Shorts), section "Select a thumbnail" — "You can choose a frame from your Short to be used as the thumbnail before and after you upload your Shorts. Keep in mind that you can only edit your thumbnail from the YouTube app and not from Studio." The procedure includes a tip: "You can add text and apply filters to your thumbnail."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** There are therefore two distinct Shorts-thumbnail paths with opposite location constraints: frame selection in the app; custom image upload in Studio on desktop. The app frame-picker also supports adding text and filters to the frame.

**CLAIM:** Because A/B testing of thumbnails is not available for Shorts, a channel cannot natively test two Shorts thumbnails against each other.
**SOURCE:** https://support.google.com/youtube/answer/16391400 (A/B test titles & thumbnails) — "**Video format:** You are not able to A/B test Shorts, Scheduled Lives, and Premiere videos at this time." and the FAQ "Can I A/B test videos that transitioned into Shorts?" — "A/B testing is not available for Shorts."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Any thumbnail decision for Shorts must be made on reasoning or external testing, not on YouTube's built-in experiment tool.

**CLAIM:** YouTube states as a "fun fact" that 90% of the best-performing videos have custom thumbnails.
**SOURCE:** https://support.google.com/youtube/answer/12340300 (Thumbnail & title tips) — "**Fun fact**: 90% of the best-performing videos have [custom thumbnails]."
**CONFIDENCE:** Medium-high for "YouTube published this sentence." **[EVIDENCE of the statement]**
**NOTE:** The claim is correlational and about videos generally, not Shorts specifically, and YouTube gives no methodology. Do not treat 90% as a measured Shorts figure. Note also the phrasing is about *videos*; whether it extends to Shorts is unstated.

**CLAIM:** YouTube advises overlaying thumbnail images with branding and descriptive text, using a readable font, and keeping the design simple rather than complex.
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "Then, overlay your images with your branding and descriptive text. If you add text, make sure to use a font that's easy to read." and "Try not to make the design too complex."
**CONFIDENCE:** High that YouTube says this. **[OPINION]**
**NOTE:** This is YouTube's guidance, not a measured effect size. It supports including a short text overlay, not a specific word count.

**CLAIM:** YouTube also advises that thumbnails display differently across devices, and that creators should experiment with updating older thumbnails.
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "Thumbnails show up differently across devices, so make sure your thumbnail image is as large as possible." and "We also recommend experimenting with updating older thumbnails to increase your video's appeal to new viewers."
**CONFIDENCE:** High that YouTube says this. **[OPINION]**

**CLAIM:** YouTube states that changing a title or thumbnail does not itself re-rank a video; any effect comes from how viewers respond to the change.
**SOURCE:** https://support.google.com/youtube/answer/141805 (YouTube performance FAQ & Troubleshooting) — "Does changing a video's title or thumbnail re-rank the video in the algorithm? Maybe, but it's because our systems are responding to how viewers are interacting with your video differently rather than the act of changing the video title or thumbnail."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Directly relevant to a factory that may rewrite metadata post-publish: the mechanism is viewer response, not a metadata-change trigger.

**CLAIM:** The date on which custom Shorts thumbnails launched was **not verified** from a primary source during this research.
**SOURCE:** No YouTube Official Blog post or Help Center changelog confirming the launch date was located. The Help Center page (72431) documents the feature as live but carries no launch date. A secondary source (vidIQ) has described the capability as having "rolled out across 2025 into 2026," but no primary announcement was found.
**CONFIDENCE:** High that the date is unverified. **NOT VERIFIED**
**NOTE:** Do not state a launch date. If a date is needed, it must be found on an official YouTube channel (blog.youtube or Creator Insider) first.

**CLAIM:** A commonly repeated claim that Shorts thumbnails never appear in the swipe feed but do appear in the channel grid, search and shelves comes from a secondary source and was not confirmed by YouTube documentation.
**SOURCE:** vidIQ (secondary) Shorts custom-thumbnail post. Contrast with the primary sources above, which state only that a vertical video's 16:9 thumbnail "will be replaced by an auto-generated 4:5 thumbnail on the home, explore, and subscription pages" while the custom thumbnail "will still appear on the watch feed, watch history, and non-mobile platforms."
**CONFIDENCE:** Low for the specific surface-by-surface list as stated by vidIQ. **[OPINION]**
**NOTE:** The primary page implies the custom thumbnail *does* appear on the watch feed, which conflicts with the blanket "never in the feed" framing. Prefer the primary wording: custom thumbnails appear on watch feed, watch history and non-mobile platforms, and are replaced by an auto 4:5 thumbnail on home/explore/subscriptions when the asset is 16:9.

---

## 2. Titles

**CLAIM:** A Short's title has a maximum length of 100 characters.
**SOURCE:** https://support.google.com/youtube/answer/10343433 — "add a title (max 100 characters)"; corroborated on https://support.google.com/youtube/answer/10059070 — "add a title (max 100 characters)".
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is a hard limit enforced in the creation flow. Place the highest-value words first (see next claim).

**CLAIM:** YouTube explicitly warns that viewers may only see part of a title, and advises keeping it short, putting the most important words near the beginning, and saving episode numbers and branding for the end.
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "**Be succinct.** Viewers may only see part of your title. So aim to keep it short and put the most important words near the beginning. Save episode numbers and branding for the end."
**CONFIDENCE:** High that YouTube says this. **[EVIDENCE]**
**NOTE:** This is the primary reason not to front-load channel or series branding in Shorts titles.

**CLAIM:** YouTube advises limiting ALL CAPS and emoji, using them only to emphasise emotion or a special element.
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "**Limit ALL CAPS and emoji.** Use them carefully, to emphasize emotion or special elements in the video."
**CONFIDENCE:** High that YouTube says this. **[OPINION]**
**NOTE:** The performance FAQ goes further and lists "Loud: Uses ALL CAPS or !!!!! to overemphasize titles" among styles that "can turn potential new viewers away from your content." SOURCE: https://support.google.com/youtube/answer/141805.

**CLAIM:** YouTube distinguishes two useful title styles: "searchable titles" that clearly state what to expect, and "intriguing titles" that spark curiosity for viewers not looking for the topic.
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "**Searchable titles** that clearly outline what to expect so you can easily reach viewers searching for similar content" and "**Intriguing titles** that spark curiosity and appeal to viewers who may not be looking for topic-specific content."
**CONFIDENCE:** High that YouTube says this. **[OPINION]**
**NOTE:** Useful as a two-archetype switch for generated titles rather than one blended style.

**CLAIM:** YouTube requires titles to be accurate, warning that a misleading title can cause viewers to stop watching, "which can impact discoverability."
**SOURCE:** https://support.google.com/youtube/answer/12340300 — "**Be accurate.** Make sure your title accurately represents the video. If not, viewers may stop watching, which can impact discoverability."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is YouTube linking title honesty to the retention signal that contributes to ranking, which matters for a factory that generates many titles at scale.

**CLAIM:** Shorts ranking uses view-duration and choice signals, and for search, "how well the metadata matches the viewer's search" plus click-and-watch behaviour.
**SOURCE:** https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts — Search: "Content is ranked based on various factors. These factors include how well the metadata matches the viewers' search and whether or not the viewers click and watch the content." Performance: "Our systems use the signals for % of viewers who chose to view, avg. view duration and avg. % viewed to inform ranking."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Titles matter most for Shorts in search surfaces; in the swipe feed the dominant signals named are choice and duration.

**CLAIM:** YouTube states that titles and thumbnails serve a purpose beyond getting clicks — helping a viewer understand the video so they don't waste time on the wrong video — and that its A/B test optimises for watch time rather than click-through rate.
**SOURCE:** https://support.google.com/youtube/answer/16391400 — "Great titles and thumbnails serve an important purpose beyond getting viewers to click." and "To help your video get high quality engagement, we optimize tests for overall watch time over other metrics, like click-through-rate."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** YouTube also warns that third-party tools that optimise for CTR may pick a different winner than watch time.

**CLAIM:** The precise way a Short's title is truncated or displayed within the swipe feed was **not verified** from a primary source.
**SOURCE:** Not found in the pages retrieved. YouTube says only that "Viewers may only see part of your title" (12340300) without stating a cutoff length for Shorts specifically.
**CONFIDENCE:** High that the cutoff is unverified. **NOT VERIFIED**
**NOTE:** The 100-character limit is confirmed; the visible-character count in the feed is not. Do not assert a specific truncation value.

---

## 3. Hashtags

**CLAIM:** Hashtags are supported on Shorts, and can be added when recording a Short as well as in a video title or description.
**SOURCE:** https://support.google.com/youtube/answer/6390658 (Find playlists & videos using hashtags) — "You can add hashtags to a title and description when you upload a video or record a Short on YouTube..."
**CONFIDENCE:** High. **[EVIDENCE]**

**CLAIM:** Of all hashtags in a video's description, up to three that YouTube considers "most engaging" are shown next to the title; the rest remain in the description and the video can still appear in search.
**SOURCE:** https://support.google.com/youtube/answer/6390658 — "Out of all the hashtags you add to the video's description, up to three hashtags that are considered most engaging will appear by your video title. Your hashtags will still appear in the video description, and your videos can still appear in search results."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** The selection of the three is made by YouTube, not the creator — so the "top 3" cannot be chosen deliberately.

**CLAIM:** If a video or playlist has more than 60 hashtags, YouTube ignores every hashtag on that content, and over-tagging may result in removal from uploads or search.
**SOURCE:** https://support.google.com/youtube/answer/6390658 — "If a video or playlist has more than 60 hashtags, we'll ignore each hashtag on that content. Over-tagging may result in the removal of your video from your uploads or from search."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** A hard, testable ceiling. Also note the explicit warning that "The more tags you add, the less relevant they become."

**CLAIM:** Hashtags in a title or description link to a results page featuring other videos sharing the hashtag.
**SOURCE:** https://support.google.com/youtube/answer/6390658 — "Hashtags in the title and description will link to a results page featuring other videos sharing the hashtag."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This confirms hashtags create a navigation/discovery surface, but the page does not state that they increase distribution.

**CLAIM:** A YouTube page on Shorts discovery lists "Sounds & hashtags" as one of the ways audiences find Shorts, mentioning that creators leaning into trends with popular sounds can increase their chances of appearing on sounds pages by using Audio Library sounds.
**SOURCE:** https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts — section "How does the audience find your Shorts?" includes the bullet "Sounds & hashtags: Creators leaning into trends that feature popular sounds can increase their chances of appearing on sounds pages by using sounds from the Audio Library."
**CONFIDENCE:** High that YouTube lists this surface. **[EVIDENCE]**
**NOTE:** Read carefully: the sentence names hashtags in the heading but the mechanism described is about **sounds**, not hashtags. The page does not state that hashtag use improves Shorts distribution.

**CLAIM:** YouTube's own FAQ states that Tags (a different feature from hashtags) are "not important" and are primarily used to correct for common misspellings.
**SOURCE:** https://support.google.com/youtube/answer/141805 — "How important are Tags? Not important. Tags are primarily used to help correct for common spelling mistakes (for example YouTube vs. U Tube vs. You-tube)."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Do not conflate tags with hashtags; they are documented separately, and only the tags verdict is explicit.

**CLAIM:** A secondary source advises that hashtags are optional context, that creators do not need to add `#Shorts`, and that metadata should not be keyword-stuffed.
**SOURCE:** https://vidiq.com/blog/post/youtube-shorts-algorithm/ (secondary) — "Hashtags can provide additional context when they are useful, but you don't need to add `#Shorts` or stuff your metadata with keywords."
**CONFIDENCE:** Low-medium. **[OPINION]**
**NOTE:** This is vidIQ's recommendation, not a YouTube statement. No primary source was found for or against the necessity of `#Shorts`.

**CLAIM:** A directly measured, primary-source effect of hashtags on Shorts distribution was **not verified**.
**SOURCE:** No YouTube page retrieved states that adding hashtags changes recommendation or feed distribution. The Help Center page (6390658) covers display, linking and policy but makes no distribution claim.
**CONFIDENCE:** High that the effect is unverified. **NOT VERIFIED**
**NOTE:** Treat hashtags as a discovery/navigation and categorisation aid, not as a proven distribution lever. Any statement that hashtags "boost reach" is unsupported by the sources located.

---

## 4. On-screen text and stickers

**CLAIM:** YouTube provides "visual guides" in the Shorts editor that show where interface elements such as the like button, comments and video description will appear, specifically to help creators place text and stickers where they remain fully visible.
**SOURCE:** https://support.google.com/youtube/answer/16215842 (Enhance your Shorts), section "Use visual guides" — "Visual guides help you position and align video elements correctly within the Shorts feed. These guidelines and visual cues aid you to easily find the best placement to make sure your text or other visual elements are fully visible to viewers." and "These guides show you where elements like the like button, comments, and video description might appear for viewers."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is the strongest primary evidence that on-screen text placement is governed by a UI safe area, and that YouTube actively warns about overlaps.

**CLAIM:** Dragging an overlay too close to the screen edge produces animated white lines signalling a "non-safe" area where content may be partially hidden on some devices, and icons display if an overlay is placed where viewer elements like the like button appear.
**SOURCE:** https://support.google.com/youtube/answer/16215842 — "**Note:** If you drag an overlay too close to the edge of the screen, animated white lines will appear, signaling a 'non-safe' area where your content might be partially hidden on some devices. Icons will also display if you place an overlay where viewer elements like the like button might appear."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Confirms the safe area is device-dependent — a perfect fit on one device does not guarantee visibility on another.

**CLAIM:** The Shorts editor supports adding text with controllable colour, style and alignment, multiple messages per video, and precise timing via the timeline editor.
**SOURCE:** https://support.google.com/youtube/answer/16215842 — "Tap **Text** to put text on your video after you record. Place multiple messages over your video and change the color, style, and alignment on the screen. You can also use Timeline for even more control." Timeline section: "Adjust the start and stop points of a clip, such as text or video, to control how long they appear in your video."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Text timing is a first-class, controllable property, not an afterthought.

**CLAIM:** YouTube supports several interactive sticker types on Shorts — Q&A, "Add yours," Poll, Quiz, AI sticker, Image sticker, and Shopping product sticker.
**SOURCE:** https://support.google.com/youtube/answer/16215842 — sections "Q&A sticker," '"Add yours" sticker,' "Poll sticker," "Quiz sticker," "AI sticker," "Image sticker," "Shopping product sticker."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Functional details that affect planning: polls stay open as long as the Short is published and viewers can change their vote; quizzes on Made-for-Kids, unlisted or private Shorts are not interactive; the poll sticker cannot be applied to unlisted or private Shorts; Q&A responses become public comments.

**CLAIM:** YouTube recommends interactive stickers and text as ways to "transform your Short into a dynamic and interactive video," and states that Sync-to-beat can create "even more engaging Shorts."
**SOURCE:** https://support.google.com/youtube/answer/16215842 — "enhance your video with Shorts creation tools to add music, filters, and backgrounds that transform your Short into a dynamic and interactive video" and "Use this feature to sync your media clips to match the beat of the music and create even more engaging Shorts."
**CONFIDENCE:** High that YouTube says this. **[OPINION]**
**NOTE:** YouTube asserts engagement benefits for stickers and beat-sync without publishing measurements. Treat as direction, not effect size.

**CLAIM:** A primary-source measurement of the effect of on-screen text, colour, arrows, or callouts on Shorts retention or CTR was **not verified**.
**SOURCE:** No YouTube Help Center page, YouTube Official Blog post or cited eye-tracking study was located that quantifies the effect of specific on-screen-text styles on Shorts performance. YouTube's only on-screen-text material found is about placement safety (16215842) and the general thumbnail advice to add readable text (12340300).
**CONFIDENCE:** High that no such measurement was found. **NOT VERIFIED**
**NOTE:** Any specific figure such as "captions increase retention by X%" must not be attributed to YouTube. See the captions section for the related, separately unverified statistic.

**CLAIM:** YouTube exposes a "Get feedback" capability on Shorts that analyses the video's hook and pacing before publishing.
**SOURCE:** https://support.google.com/youtube/answer/10343433 — "**Get feedback:** Tap the **Get feedback** button to get an analysis of your video's hook, pacing, and more."
**CONFIDENCE:** High that the feature is described. **[EVIDENCE]**
**NOTE:** Of interest to the factory as a possible native pre-publish check, though its criteria are not published.

---

## 5. Captions

**CLAIM:** YouTube automatically generates captions for Shorts as well as long-form videos, and encourages creators to add professional captions first because automatic captions may misrepresent speech.
**SOURCE:** https://support.google.com/youtube/answer/6373554 (Use automatic captioning) — "**Automatic captions on long-form videos and Shorts**"; "We encourage creators to add professional captions first"; "automatic captions might misrepresent the spoken content due to mispronunciations, accents, dialects, or background noise."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Automatic captions, if available, are published on the video automatically. For a factory producing narration, a reviewed caption track is strictly better than relying on ASR.

**CLAIM:** YouTube's own FAQ answer to "Does adding subtitles (captions) help my channel grow?" is that captions let you share videos with a larger audience, including deaf or hard-of-hearing viewers and viewers who speak another language — and it makes no retention or watch-time claim.
**SOURCE:** https://www.youtube.com/creators/grow/optimize-your-content/ — "Yes, subtitles and captions allow you to share your videos with a larger audience, including deaf or hard-of-hearing viewers and viewers who speak another language."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is the crucial negative finding. YouTube's own growth FAQ does **not** claim captions raise retention or watch time; it claims accessibility and audience breadth only.

**CLAIM:** Automatic captions in English support "expressive captions" that display the intensity of speech in all caps and render non-speech sounds such as sighs, gasps and environmental noise.
**SOURCE:** https://support.google.com/youtube/answer/6373554 — "Automatic captions in English support expressive captions which create a more immersive content experience by displaying the intensity of speech in all caps, expressions of sounds like sighs and gasps, as well as noises from the environment."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Relevant to caption style choices: YouTube itself treats expressive, non-speech-aware captioning as more immersive.

**CLAIM:** YouTube automatically publishes auto-translated subtitles and provides automatic dubbing, and reported that in December, YouTube averaged more than 6 million daily viewers who watched at least 10 minutes of autodubbed content.
**SOURCE:** https://blog.youtube/inside-youtube/the-future-of-youtube-2026/ — "We're also using AI to make more videos accessible. In December, YouTube averaged more than 6 million daily viewers who watched at least 10 minutes of autodubbed content." (Auto-translated subtitles referenced on 6373554: "This setting is available for automatic captions and auto-translated subtitles.")
**CONFIDENCE:** High for the quoted figure. **[EVIDENCE]**
**NOTE:** This is a platform-level metric about autodubbed content generally, not about captions on Shorts, and it is not a per-video uplift. Do not repurpose it as a captions-ROI number.

**CLAIM:** The widely repeated statistic that captions or subtitles raise watch time by a specific percentage was **not verified** against a primary source.
**SOURCE:** No YouTube Help Center page, YouTube Official Blog post or primary research report containing such a figure was located. Across the YouTube pages retrieved, the only growth claim attached to captions is the accessibility/audience-breadth statement on https://www.youtube.com/creators/grow/optimize-your-content/.
**CONFIDENCE:** High that the statistic is unverified from a primary source. **NOT VERIFIED**
**NOTE:** This claim circulates widely through SEO and creator blogs. Per the research rules, it must not be cited via a blog that itself cites another blog. If the project needs a captions-ROI number, it can only come from an owned experiment, not from this report.

---

## 6. Shorts reach vs. subscriber conversion

**CLAIM:** YouTube analytics for Shorts includes a dedicated "Subscribers" metric, defined as the change in subscribers compared to typical performance, and YouTube states it can help a creator understand what types of Shorts lead viewers to subscribe or unsubscribe.
**SOURCE:** https://support.google.com/youtube/answer/12942217?co=YOUTUBE._YTVideoType%3Dshorts (Content tab analytics tips — Shorts) — "**Subscribers** … **Definition:** Change in subscribers compared to your typical performance. **Insight:** Over time, this metric can help you to understand what types of shorts lead viewers to subscribe to or unsubscribe from your channel."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This is the correct native measurement surface for the Shorts→subscriber question. It confirms the conversion is measurable per-Short, but YouTube publishes no benchmark.

**CLAIM:** YouTube provides a native way to send Shorts viewers onward to other content: a related video, shown as a clickable link below the channel handle in the Shorts player, which YouTube describes as "designed to complement your Short and encourage viewers to watch more of your content."
**SOURCE:** https://support.google.com/youtube/answer/14075157 (Add a related video to your YouTube Shorts) — "A related video allows you to showcase your Videos, Shorts, and Live in the Shorts player" and "Viewers will see a clickable link below your channel handle. A related video is designed to complement your Short and encourage viewers to watch more of your content."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Requires advanced feature access; the selected video must be public or unlisted and follow Community Guidelines. This is the strongest primary mechanism found for converting Shorts reach into deeper channel engagement.

**CLAIM:** YouTube states that Shorts performance does not negatively impact long-form Video recommendations, and that Shorts "can help with audience discovery but can't hurt your Video performance."
**SOURCE:** https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts — "Shorts performance doesn't negatively impact long form Video recommendations. Shorts can help with audience discovery but can't hurt your Video performance."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** YouTube frames Shorts as a discovery asset. Note the careful wording: it asserts Shorts cannot *hurt* long-form performance; it does not promise subscriber conversion.

**CLAIM:** Subscribers gained from watching Shorts count toward Creator Awards Program milestones wherever viewers find the Short, including search, the homepage, the channel homepage, Subscriptions and notifications.
**SOURCE:** https://support.google.com/youtube/answer/10059070 (Get started creating YouTube Shorts) — "Wherever they find them, subscribers gained from watching your Shorts count toward Creator Awards Program milestones."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Confirms Shorts-attributed subscribers are real, counted subscribers, not a separate category.

**CLAIM:** To become eligible for the YouTube Partner Program via Shorts, a creator needs 1,000 subscribers plus 10 million qualified Shorts views in the last 90 days.
**SOURCE:** https://support.google.com/youtube/answer/10059070 — "To become eligible for the YouTube Partner Program (YPP) with Shorts, you must gain 1,000 subscribers with 10 million qualified Shorts views in the last 90 days."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** This makes the subscriber count, not just views, a hard requirement — the practical reason the Shorts→subscriber gap matters.

**CLAIM:** Since 31 March 2025, a Short view counts each time it starts or replays with no minimum watch time, and the previous metric still exists as "Engaged views"; YPP eligibility and Shorts ad revenue sharing are based on engaged views.
**SOURCE:** https://support.google.com/youtube/answer/10059070 — "Starting 3/31/2025, we're updating how Shorts views are counted. Views will count the number of times a Short starts to play or replay, with no minimum watch time requirement." and "This change will not directly impact the YouTube Partner Program (YPP) eligibility and Shorts ad revenue sharing. They will both be based on 'Engaged Shorts views.'"
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Raw Shorts view counts now overstate genuine attention; engaged views and the subscriber delta are the more meaningful packaging outcomes.

**CLAIM:** YouTube states that a subscriber count does not represent the number of viewers who watch your videos, and that viewers are on average subscribed to dozens of channels and may not return for every upload.
**SOURCE:** https://support.google.com/youtube/answer/141805 — "Your subscriber count reflects how many viewers have subscribed to follow your YouTube channel. The count doesn't represent the number of viewers who watch your videos."
**CONFIDENCE:** High. **[EVIDENCE]**
**NOTE:** Context for interpreting conversion improvements: subscriber growth and per-video viewership are not the same quantity.

**CLAIM:** A secondary source advises that a Short can reach a large audience without that reach converting automatically, and that the strongest strategy is to give viewers somewhere to go next, including via the related-video feature.
**SOURCE:** https://vidiq.com/blog/post/youtube-shorts-algorithm/ (secondary), section "Turn Shorts Reach Into Channel Growth" — "A Short can reach a large audience, but views alone don't automatically translate into long-term channel growth."
**CONFIDENCE:** Low-medium. **[OPINION]**
**NOTE:** The opinion is plausible and is consistent with YouTube's related-video feature, but it is vidIQ's interpretation, not a measured finding. Note the source's own date metadata ("Updated Oct 09, 2026") indicates it is current.

**CLAIM:** The widely reported claim that subscribers are unnecessary for reach on Shorts was **not verified** against a primary source.
**SOURCE:** Attributed in earlier research to Hootsuite (secondary). No YouTube page retrieved makes an equivalent statement. YouTube's own pages instead tie the subscriber count to YPP eligibility (10059070) and warn that subscriber count is not a measure of viewers (141805).
**CONFIDENCE:** High that it is unverified. **NOT VERIFIED**
**NOTE:** The 1,000-subscriber YPP floor is a concrete counterexample: subscribers are demonstrably required for monetisation even if they are not required for feed distribution.

**CLAIM:** A primary-source, quantified conversion rate from Shorts views to subscribers was **not verified**.
**SOURCE:** Not found. YouTube exposes the Subscribers metric for Shorts (12942217) and provides the related-video mechanism (14075157) but publishes no conversion benchmark. The vidIQ analysis of 35 billion Shorts views is a secondary analysis and reports length and volume findings (13s and 60s performing best; channels with 200+ Shorts seeing steady view growth), not a subscriber-conversion rate.
**CONFIDENCE:** High that no primary benchmark was found. **NOT VERIFIED**
**NOTE:** Do not quote any Shorts→subscriber conversion percentage. This must be measured on the project's own channel via the Shorts Subscribers metric.

---

## GAPS

Items that could not be verified from a primary source and must not be asserted:

1. **Custom Shorts thumbnail launch date.** The feature is documented as live (support 72431) but no official announcement date or changelog entry was found. Secondary sources give inconsistent framing ("rolled out across 2025 into 2026").
2. **Short title truncation length in the swipe feed.** The 100-character maximum is confirmed (10343400 / 10059070); the number of characters actually visible in the feed is not stated anywhere found.
3. **Hashtag effect on distribution.** Hashtags are documented for display (up to 3 by the title), linking, and a > 60 ceiling, but no YouTube source states that hashtags improve Shorts distribution. The "Sounds & hashtags" bullet on the Shorts discovery page describes a **sounds** mechanism, not a hashtag mechanism.
4. **Necessity or value of `#Shorts`.** No primary source either recommends or discourages it.
5. **On-screen text / sticker performance effect.** No YouTube measurement or cited eye-tracking study was found for text, colour, arrows or callouts affecting retention or CTR. Only placement-safety guidance exists (16215842).
6. **Captions watch-time uplift.** YouTube's own growth FAQ (creators/grow/optimize-your-content) claims accessibility and audience breadth only. The widely repeated captions/watch-time percentage has **no primary source** located and must not be cited.
7. **Exact Shorts thumbnail surfaces.** The primary source states only that a vertical video's 16:9 thumbnail is replaced by an auto 4:5 thumbnail on home/explore/subscriptions while the custom thumbnail appears on the watch feed, watch history and non-mobile platforms. The more detailed surface list circulating in secondary sources was not confirmed and partly conflicts with the primary wording.
8. **Shorts→subscriber conversion benchmarks.** No primary benchmark exists. Any figure must come from the project's own Shorts Subscribers metric.
9. **Reach without subscribers.** The secondary claim that subscribers are unnecessary for reach was not confirmed by any YouTube source and is contradicted in spirit by the 1,000-subscriber YPP requirement.
10. **Ask Studio / Get feedback criteria.** Both are documented as existing features (16291691, 10343433) but their evaluation criteria and any measured effectiveness are not published.

---

## Source index

Primary (YouTube):
- https://support.google.com/youtube/answer/72431 — Add custom thumbnails on YouTube (Shorts thumbnails, sizes, limits, 4:5 replacement note)
- https://support.google.com/youtube/answer/10343433 — Create YouTube Shorts (100-char title, frame thumbnail, Get feedback)
- https://support.google.com/youtube/answer/10059070 — Get started creating YouTube Shorts (view count change 3/31/2025, discovery surfaces, YPP via Shorts)
- https://support.google.com/youtube/answer/12340300 — Thumbnail & title tips (90% fun fact, succinct titles, ALL CAPS, searchable vs intriguing)
- https://support.google.com/youtube/answer/16391400 — A/B test titles & thumbnails (no Shorts A/B; watch time over CTR)
- https://support.google.com/youtube/answer/141805 — YouTube performance FAQ & Troubleshooting (metadata change ≠ re-rank; tags not important; subscriber count meaning)
- https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts — Search & discovery tips (Shorts) (ranking signals, discovery surfaces, Shorts vs long-form)
- https://support.google.com/youtube/answer/6390658 — Find playlists & videos using hashtags (3 shown, >60 ignored, linking)
- https://support.google.com/youtube/answer/6373554 — Use automatic captioning (captions on Shorts, expressive captions)
- https://support.google.com/youtube/answer/16215842 — Enhance your Shorts (visual guides, safe area, text, stickers, sync to beat)
- https://support.google.com/youtube/answer/14075157 — Add a related video to your YouTube Shorts
- https://support.google.com/youtube/answer/12942217?co=YOUTUBE._YTVideoType%3Dshorts — Content tab analytics tips (Shorts) (Subscribers metric, viewed vs swiped away)
- https://support.google.com/youtube/answer/16291691 — Learn about Ask Studio in YouTube Studio
- https://support.google.com/youtube/answer/12950272 — Channel banner & profile picture tips
- https://www.youtube.com/creators/create/shorts/ — YouTube for Creators: Shorts (200 billion daily views, average April 2025)
- https://www.youtube.com/creators/grow/optimize-your-content/ — Optimize your content (captions growth FAQ answer)
- https://blog.youtube/news-and-events/tall-updates-coming-to-shorts/ — Tall updates coming to Shorts (Oct 3, 2024; three-minute Shorts from Oct 15, 2024)
- https://blog.youtube/news-and-events/made-on-youtube-2025/ — Made on YouTube 2025 (Sep 16, 2025)
- https://blog.youtube/inside-youtube/the-future-of-youtube-2026/ — From the CEO: What's coming to YouTube in 2026 (Jan 21, 2026; 200 billion daily Shorts views; autodub viewers)

Secondary (used only where labelled as opinion, or to flag unverified claims):
- https://vidiq.com/blog/post/youtube-shorts-algorithm/ — vidIQ, YouTube Shorts algorithm (updated Oct 9, 2026). Contains: explore/exploit framing attributed to a Creator Insider interview with Todd Sherman; Nate Black analysis of 35 billion Shorts views (13s and 60s lengths; channels with 200+ Shorts); hashtags-as-optional-context advice; "views alone don't automatically translate into long-term channel growth."

Explicitly excluded:
- Social Blade blog — dormant, no relevant posts since approximately 2020; not usable for 2026 claims.
- Several YouTube blog URLs attempted during research returned 404 and therefore contributed nothing: buffer.com/resources/youtube-shorts/, blog.youtube news items on Shorts thumbnails, Shorts in 100+ countries, and Shorts monetization.
