# Long-Form YouTube Strategy and Calls-to-Action (2026)

Research report for changing production code. All claims are tied to a URL. Where a claim could
not be verified from a primary (YouTube-owned) source, it is marked **unverified** and repeated in
GAPS.

Conventions used here:

- `CLAIM:` the statement being made
- `SOURCE:` the exact URL fetched
- `CONFIDENCE:` certain | strong | indicative | unverified
- `NOTE:` what the source actually says, in the source's own terms

---

## 1. Long-form content: what YouTube officially says it is for, and the format rules

**CLAIM:** YouTube frames long-form as the format for depth, community and durable income.
**SOURCE:** https://blog.youtube/news-and-events/made-on-youtube-2025/
**CONFIDENCE:** indicative
**NOTE:** The Made on YouTube 2025 keynote (Sep 16, 2025, Johanna Voolich, Chief Product Officer)
does not set numeric long-form rules. It states YouTube "paid out over $100 billion to creators,
artists, and media companies globally over the last four years" and describes new creation tools.
It is a strategy/announcement post, not a spec — referenced here only for directional context.

**CLAIM:** YouTube's own "Longform" creator page positions long-form content as the way to "go
beyond trends and fads," build community and create sustainable income, and gives a first-5–10-second
hook recommendation.
**SOURCE:** https://www.youtube.com/creators/create/longform/
**CONFIDENCE:** strong
**NOTE:** The page's headline framing: "Longform content creates meaningful connections that spark
cultural moments and fuel sustainable growth as billions watch on desktop, mobile, and TV." Under
"Outline your video" it says: "Hook viewers in the first 5–10 seconds to keep them watching" and
"Map out a beginning → middle → end structure." It also says default upload length is 15 minutes,
verified accounts can upload longer, and the maximum upload is 256 GB or 12 hours, whichever is less.
This is a marketing/guidance page (youtube.com/creators), so treat the 5–10 second hook as
YouTube's recommendation, not a ranking guarantee.

**CLAIM:** Upload length and size limits are as follows: default 15 minutes; verified accounts may
upload longer; maximum file size 256 GB or 12 hours, whichever is less.
**SOURCE:** https://www.youtube.com/creators/create/longform/
**CONFIDENCE:** strong
**NOTE:** Stated verbatim in the FAQ section of the page ("By default, you can upload videos that are
up to 15 minutes long. Verified accounts can upload videos longer than 15 minutes." and "The maximum
file size you can upload is 256 GB or 12 hours, whichever is less.").

**CLAIM:** YouTube explicitly says its recommendation system "doesn't favor any particular format."
**SOURCE:** https://support.google.com/youtube/answer/11914225
**CONFIDENCE:** certain
**NOTE:** On "Search & discovery tips," under "What kind of videos does the YouTube system favor?":
"Our system has no opinion about what type of video you make, and doesn't favor any particular
format. Videos are ranked based on performance and viewer personalization, including their watch and
search history." This directly contradicts any code assumption that long-form is algorithmically
privileged.

**CLAIM:** YouTube states there is no vertical/9:16-specific long-form recommendation boost documented
in official help; the only aspect-ratio consequence documented officially concerns the *number of
end-screen elements*, not reach.
**SOURCE:** https://support.google.com/youtube/answer/6388789
**CONFIDENCE:** certain
**NOTE:** "You can add up to four elements to your end screen for videos with standard 16:9 aspect
ratio. Other aspect ratios may have a lower limit." This is the only official statement found tying
aspect ratio to a feature limit. No official statement was found saying vertical/9:16 long-form videos
are demoted, boosted, or excluded from anything. (See GAPS.)

**CLAIM:** Three-minute Shorts exist (Shorts can be up to 3 minutes), and views/monetization rules
differ between Shorts and long-form on the Watch Page.
**SOURCE:** https://support.google.com/youtube/answer/10059070
**CONFIDENCE:** certain
**NOTE:** "YouTube's Shorts creation tools makes it easy to create short-form videos that are up to 3
minutes long." And: "To become eligible for the YouTube Partner Program (YPP) with Shorts, you must
gain 1,000 subscribers with 10 million qualified Shorts views in the last 90 days." Also states that
as of 3/31/2025 the Shorts *views* metric counts each play/replay with no minimum watch time, while
the old metric is now "Engaged views" (see Section 5).

> ⚠️ Code implication: A 9:16 "long-form" upload is still a long-form Watch Page video, not a Short,
> once it exceeds the Shorts length limit. Do not assume aspect ratio changes the surface.

---

## 2. Watch time, retention and the ranking signals YouTube documents

**CLAIM:** YouTube's official doc lists watch history, search history, subscriptions, likes,
dislikes, "not interested," "don't recommend channel," and satisfaction surveys as the *primary
signals*, and explicitly says it does not rank by watch time alone.
**SOURCE:** https://support.google.com/youtube/answer/16089387
**CONFIDENCE:** certain
**NOTE:** "Our recommendation system is constantly evolving, learning every day from over 80 billion
pieces of information we call signals." Primary signals listed: Watch history, Search history, Channel
subscriptions, Likes, Dislikes, "Not interested" feedback selections, "Don't recommend channel"
feedback selections, Satisfaction surveys — with the note that surveys "help the system understand
satisfaction, not just watch time." Also: "our system uses the video you're currently watching as the
main signal when suggesting a video to play next."

**CLAIM:** YouTube uses average view duration AND average percentage viewed as ranking signals, plus
likes and post-watch survey results.
**SOURCE:** https://support.google.com/youtube/answer/11914225
**CONFIDENCE:** certain
**NOTE:** "Our systems use both avg. view duration and avg. % viewed as signals to inform ranking.
Lastly, we look at whether or not viewers enjoyed the video using likes and post-watch survey results."
It also lists three external factors: Topic interest, Competition, Seasonality.

**CLAIM:** YouTube's historical account of the recommendation system describes adding watchtime in
2012 and a resulting 20% drop in views, and describes "valued watchtime" measured through surveys.
**SOURCE:** https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/
**CONFIDENCE:** strong
**NOTE:** Sep 15, 2021 post by Cristos Goodrow, VP of Engineering. Verbatim: "When we first
incorporated watchtime into recommendations, we saw an immediate 20% drop in views." And: "we measure
what we call 'valued watchtime'—the time spent watching a video that you consider valuable... Only
videos that you rate highly with four or five stars are counted as valued watchtime." Also:
"Recommendations drive a significant amount of the overall viewership on YouTube, even more than
channel subscriptions or search." This is a 2021 blog post — still YouTube-owned and on-point for
signal history, but date it in any code comment.

**CLAIM:** YouTube's audience-retention report defines what a good/bad intro looks like and that
"audience sizes typically decrease over the length of the video."
**SOURCE:** https://support.google.com/youtube/answer/9314415
**CONFIDENCE:** certain
**NOTE:** Definitions from the doc: flat line = full watch; gradual declines = losing interest;
spikes = rewatching/sharing; dips = abandoning/skipping. "Intro tells you what percentage of your
audience still watched your video after the first 30 seconds." And: "If the top moments are occurring
in a later portion in the video, consider introducing the compelling content earlier in the video—
audience sizes typically decrease over the length of the video." Also: report needs the video to be at
least 60 seconds long and have at least 100 views; audience retention data "typically takes 1–2 days
to process."

**CLAIM:** YouTube's creator guidance repeats the "hook early" principle and frames packaging
(title/thumbnail) as the thing that must match the first 30 seconds.
**SOURCE:** https://support.google.com/youtube/answer/9314415
**CONFIDENCE:** certain
**NOTE:** A high intro percentage "could mean: The content in the first 30 seconds matched the
viewer's expectation of the video's thumbnail and title." Recommended fix: "Consider changing your
video thumbnail and title to better reflect your video content" and "Modify the first 30 seconds."

> ⚠️ Code implication: Optimize for both avg. view duration and avg. % viewed; do not treat a long
> runtime as automatically better. The retention curve is the tool YouTube tells creators to use.

---

## 3. Calls-to-action: what YouTube officially recommends, and where

**CLAIM:** YouTube tells creators to place CTAs at "appropriate moments" and to ask for subscribe,
comment, like and share.
**SOURCE:** https://support.google.com/youtube/answer/11913421
**CONFIDENCE:** certain
**NOTE:** Under "Ask your audience for feedback": "Encourage your viewers to engage with your content
by subscribing, leaving a comment, or liking and sharing the video." Under "Reminders for your
viewers → Subscribe to your channel": "As you plan your video content, think of appropriate moments
that you can encourage viewers to subscribe." This is the explicit CTA guidance and the source of the
quote referenced in the earlier draft of this research. (The quote in the prior draft attributed to
"creator-tips pages" lives on this page.)

**CLAIM:** End screens occupy the last 5–20 seconds, can hold up to four elements (16:9), require a
25-second minimum video, and include a dedicated "Subscribe" element.
**SOURCE:** https://support.google.com/youtube/answer/6388789
**CONFIDENCE:** certain
**NOTE:** "End screens can be added to the last 5–20 seconds of a video. You can use them to promote
other videos, encourage viewers to subscribe, and more." Elements include: Video, Playlist,
Subscribe, Channel, Link (Link only for YPP members). "Your video has to be at least 25 seconds long
to have an end screen." "Other interactive elements, like card teasers and video watermarks, are
suppressed during the end screen." "Viewers have the ability to hide end screens while watching."
Best-practice bullet: "Encourage viewers to click using calls to action for different end screen
elements."

**CLAIM:** YouTube's own Shorts guidance explicitly endorses an engagement CTA in Shorts ("If you
liked the Short, give it a like and comment").
**SOURCE:** https://support.google.com/youtube/answer/13363900
**CONFIDENCE:** certain
**NOTE:** Under "We recommend": "Don't forget to engage. Something as simple as asking your viewers,
'If you liked the Short, give it a like and comment,' can do wonders!"

**CLAIM:** YouTube's official guidance also recommends building a signature welcome/sign-off and
crowd-sourced questions, and using the Community/Posts and Live features for two-way engagement.
**SOURCE:** https://support.google.com/youtube/answer/11913421
**CONFIDENCE:** certain
**NOTE:** "Having a signature welcome or sign off in your videos is a fun and easy way to build your
channel branding." Also recommends asking viewers for direct insight and using memes/catch phrases to
build "traditions."

**CLAIM:** On YouTube's official "Engage your community" page, engagement is framed as two-way and
collaboration is described as a discoverability lever ("introduced to new, already-engaged
communities who are more likely to watch and subscribe").
**SOURCE:** https://www.youtube.com/creators/grow/engage-your-community/
**CONFIDENCE:** strong
**NOTE:** "The more you engage with your audience, the more they'll engage with you." Collabs listed
as "a proven way to reach new viewers"; benefit bullet: "Boost discoverability: Get introduced to new,
already-engaged communities who are more likely to watch and subscribe." Also details the Collaborations
feature (invite up to five creators on long-form or Shorts; not on active live streams). This is a
guidance/marketing page, not a policy.

> ⚠️ Code implication: A CTA is best placed at a *content-defined* moment, not a fixed arbitrary
> timestamp. YouTube explicitly says "appropriate moments." End-screen CTAs must live in the last
> 5–20 seconds and the video must be ≥25 s.

---

## 4. Shorts → long-form funnel and the related-video feature

**CLAIM:** YouTube provides a built-in "related video" feature on Shorts that links viewers to the
creator's other content, described as designed to "encourage viewers to watch more of your content."
**SOURCE:** https://support.google.com/youtube/answer/14075157
**CONFIDENCE:** certain
**NOTE:** "You can add a related video after you upload your Short to help direct viewers to your
other YouTube content. A related video allows you to showcase your Videos, Shorts, and Live in the
Shorts player." And: "A related video is designed to complement your Short and encourage viewers to
watch more of your content." Constraints: only with advanced feature access; the selected video "has
to be public or unlisted and must follow our Community Guidelines." Viewers see a clickable link
below your channel handle. This is the concrete Shorts→other-content funnel mechanism.

**CLAIM:** YouTube says subscribers gained from Shorts count toward Creator Awards milestones, and
that Shorts can be monetized as a supplement.
**SOURCE:** https://support.google.com/youtube/answer/10059070
**CONFIDENCE:** certain
**NOTE:** "Wherever they find them, subscribers gained from watching your Shorts count toward Creator
Awards Program milestones."

**CLAIM:** YouTube says Shorts reach can be found across surfaces (search on TVs/consoles, homepage,
channel homepage, subscriptions, notifications), i.e. Shorts are framed as an audience-acquisition
surface.
**SOURCE:** https://support.google.com/youtube/answer/10059070
**CONFIDENCE:** certain
**NOTE:** Verbatim list: "In search results across YouTube, including on most smart TVs, game
consoles, and other streaming devices. On the YouTube homepage. Featured on your channel homepage.
By checking their Subscriptions. In their notifications."

**CLAIM:** YouTube's "Why choose Shorts" page frames Shorts as an audience-growth and revenue
*supplement*, and cites creator quotes about subscriber gains.
**SOURCE:** https://support.google.com/youtube/answer/13363900
**CONFIDENCE:** indicative
**NOTE:** "You can use YouTube Shorts as a new revenue source to supplement your existing YPP ad
revenue income!" It includes a creator testimonial ("I've already gained 199000 new subscribers with
a 14-second video") — attributed to a named creator ("Jooj Natu ENG"), not YouTube's own statistical
claim. Do not treat creator testimonials as data.

**CLAIM:** Shorts ad revenue is pooled and shared separately from the Watch Page; Shorts views
receive ad revenue "exclusively... from the Shorts Feed, which is separate from long-form video
monetization on the Watch Page."
**SOURCE:** https://support.google.com/youtube/answer/12504220
**CONFIDENCE:** certain
**NOTE:** "Revenue is shared on ads that are viewed between videos in the Shorts Feed. Shorts views
exclusively receive ad revenue sharing from the Shorts Feed, which is separate from long-form video
monetization on the Watch Page." Creators keep 45% of allocated Creator Pool revenue; eligibility
requires 10M qualified Shorts views in the last 90 days (monthly). Creator Pool split rules and a
worked example are given.

> ⚠️ Code implication: There is no official claim that Shorts *cause* long-form watch time at any
> particular rate. The only official funnel mechanic is "related video" plus the general claim that
> Shorts can grow audience/subscribers. See GAPS for the missing conversion data.

---

## 5. Monetization thresholds and the 2026/2027 changes that affect production choices

**CLAIM:** The current YPP entry thresholds are 1,000 subscribers + either 4,000 qualified watch
hours (last 12 months) or 10 million qualified Shorts views (last 90 days).
**SOURCE:** https://support.google.com/youtube/answer/72851
**CONFIDENCE:** certain
**NOTE:** "Once you understand what you need to join, your channel can become eligible for YPP with
either Shorts or long-form video... 1. Get 1,000 subscribers with 4,000 qualified watch hours in the
last 12 months, or 2. Get 1,000 subscribers with 10 million qualified Shorts views in the last 90
days." Also: "any qualified watch hours from Shorts views in the Shorts Feed won't count towards the
4,000 qualified public watch hours threshold." Qualified watch hours count only from public long-form
videos; watch hours from private/unlisted/deleted videos, ad campaigns, Shorts, and unlisted/deleted
livestreams do not count.

**CLAIM:** Starting February 1, 2027, YPP entry thresholds increase to 8,000 qualified watch hours
(last 365 days) or 20M qualified Shorts views (last 90 days), still requiring 1,000 subscribers.
Existing YPP members are not affected.
**SOURCE:** https://support.google.com/youtube/answer/12843009
**CONFIDENCE:** certain
**NOTE:** "Starting Feb. 1, 2027, YPP entry thresholds for new creators are changing to 8,000
qualified watch hours in the last 365 days, or 20M qualified Shorts views in the last 90 days, in
addition to still needing 1k subscribers. If you are already in YPP, your status is not impacted by
this update." The same page also states fan funding / Creator Partnerships / Shopping remain at 500
subscribers + 3,000 qualified watch hours (last year) or 3M qualified Shorts views (last 90 days).

**CLAIM:** Starting February 1, 2027, monthly Shorts revenue eligibility requires 10M qualified
Shorts views over the last 90 days; missing it does not remove you from YPP or affect long-form
earnings.
**SOURCE:** https://support.google.com/youtube/answer/12843009
**CONFIDENCE:** certain
**NOTE:** "To earn each month from the Shorts Creator Pool, creators will now need to maintain 10M
qualified Shorts views over the last 90 days. If you miss this threshold, you will not be removed from
YPP and this will not impact other YPP earnings, including long-form video."

**CLAIM:** YPP "active channel" rules change Feb 1, 2027: active if you meet 1,000 qualified watch
hours in the past 365 days, OR 1 million qualified Shorts views in the last 90 days, OR upload 2
long-form videos or 5 Shorts every 90 days.
**SOURCE:** https://support.google.com/youtube/answer/12843009
**CONFIDENCE:** certain
**NOTE:** Verbatim from "Updated channel activity requirements." Restore-active path offers a 90-day
window to reach 1,000 qualified watch hours (365 days) or 1 million qualified Shorts views (90 days).
Also: channels that haven't uploaded a video or posted to the Posts tab for 6 months or more may have
monetization turned off (stated on answer/72851).

**CLAIM:** Premium Lite expansion: creators share in a pool representing 60% of net subscription
revenue for Premium Lite and 30% for Premium; YouTube states that "on average, creators earn more per
user from Premium than from ads (based on 2026 performance)."
**SOURCE:** https://support.google.com/youtube/answer/12843009
**CONFIDENCE:** certain
**NOTE:** "On average, creators earn more per user from Premium than from ads (based on 2026
performance)." and "For Premium Lite, creators will share in a pool representing 60% of net
subscription revenue. For Premium views, creators will share in a pool representing 30% of net
subscription revenue." Note the 30%/60% figures refer to the *pool size*, not a per-creator rate.

**CLAIM:** Mid-roll ads require a video longer than 8 minutes; ad pods can occur on videos at least 5
minutes long; Watch While ads serve on videos 2–8 minutes.
**SOURCE:** https://support.google.com/youtube/answer/2467968
**CONFIDENCE:** certain
**NOTE:** "You can also turn on mid-roll ads for videos longer than 8 minutes and decide whether to
manually or automatically insert the ad breaks." And: "two back-to-back video ads can occur when you
turn on ads for your long-form video (at least 5 minutes in length)." And Watch While ads "automatically
serve on monetizing videos that are ineligible for mid-roll ads (videos between 2–8 minutes, or videos
over 8 minutes with mid-rolls turned off)."

> ⚠️ Code implication for production length: crossing 8 minutes unlocks mid-rolls; crossing 5 minutes
> enables ad pods. Both are official, numeric and directly relevant to revenue-per-video decisions.

---

## 6. Inauthentic content, mass-production risk and AI-specific rules (critical for a video automation project)

**CLAIM:** On July 15, 2025 YouTube renamed its "repetitious content" policy to "inauthentic content"
and clarified that it includes repetitive or mass-produced content; this was described as a *minor*
update with no change to the reused-content policy.
**SOURCE:** https://support.google.com/youtube/answer/1311392
**CONFIDENCE:** certain
**NOTE:** Verbatim changelog note: "July 15, 2025: We're making a minor update to our 'repetitious
content' policy to better clarify this includes content that is repetitive or mass-produced. We are
also renaming this policy from 'repetitious content' to 'inauthentic content.' This type of content
has always been ineligible for monetization under our existing policies... There is no change to our
reused content policy which reviews content like commentary, clips, compilations, and reaction videos."

**CLAIM:** YouTube's monetization policy requires monetized content to be original and "authentic":
not mass-produced, generic, or repetitive, and not "made with a template."
**SOURCE:** https://support.google.com/youtube/answer/1311392
**CONFIDENCE:** certain
**NOTE:** "If you're making money on YouTube, your content should be original and 'authentic.' This
means that we expect your content to: Be your original creation... Not be mass-produced, generic,
repetitive, or manipulative. It should be made for the enjoyment or education of viewers, rather than
for the sole purpose of getting views." Under "Generic or Repetitive Content": "content that looks
like it's made with a template, or that may feel repetitive to viewers after watching several videos
in a row from the same channel." Under "What is allowed to monetize": "the substance of each video
should be materially varied and deliver creative, educational, or other value."

**CLAIM:** Explicit examples of content that is NOT allowed to monetize include "AI-generated content
made with generic or unoriginal templates giving the impression of mass production without adding the
creator's original, authentic insights or perspective."
**SOURCE:** https://support.google.com/youtube/answer/1311392
**CONFIDENCE:** certain
**NOTE:** Direct bullet under "Examples of what's not allowed to monetize (this list is not
exhaustive)." Also listed: image slideshows, templated storylines, scrolling text with minimal or no
narrative; characters in the same situation over and over with the same outcome.

**CLAIM:** "Unsatisfying or Off-putting Content" policy forbids content that relies on "emotionally
manipulative formulas," mimics existing formats until videos "feel interchangeable," or uses
templates; but explicitly permits AI to *assist* if the final product demonstrates the creator's
creative vision.
**SOURCE:** https://support.google.com/youtube/answer/1311392
**CONFIDENCE:** certain
**NOTE:** Allowed examples include: "Content that expresses your unique creative voice, like using AI
to visualize a unique character and narrative you invented" and "using AI to edit your video scripts
or generate a unique background visual." Not allowed: "Channels that heavily rely on generic
templates or emotionally manipulative themes." Key sentence: "If you use automated tools or templates
to help create your content, the final product must still demonstrate your creative vision and provide
educational or entertainment value."

**CLAIM:** A policy forbids AI personas delivering information on sensitive topics (health, legal,
finances, politics) from monetizing.
**SOURCE:** https://support.google.com/youtube/answer/1311392
**CONFIDENCE:** certain
**NOTE:** "AI Personas Related to Sensitive Topics... channels uploading this content will not be
allowed to monetize." Examples: an AI "doctor" giving diagnoses; AI-generated podcast hosts giving
financial guidance; AI personas giving legal advice. This is an affirmative monetization ban for that
category — highly relevant to any code that auto-generates such content.

**CLAIM:** Creators must disclose realistic altered/synthetic content, and labels are shown on the
video or in its description.
**SOURCE:** https://www.youtube.com/howyoutubeworks/recommendations/ (served in Italian locale)
**CONFIDENCE:** strong
**NOTE:** The page (Italian) states creators are required to disclose realistic synthetic or altered
media, including generative-AI content, and that labels appear on the video or description. Because
this fetch returned the Italian locale, quote it only as to *existence and meaning of the
requirement*, not as an English verbatim quote. (See GAPS for the English URL.)

**CLAIM:** Content that fails advertiser-friendly guidelines receives limited or no ad earnings;
"AI Personas" aside, the general advertiser-friendly rules also apply to thumbnails, titles,
descriptions and tags.
**SOURCE:** https://support.google.com/youtube/answer/6162278
**CONFIDENCE:** certain
**NOTE:** "This article aims to help you understand which individual videos or Shorts on your channel
are suitable for advertisers." And: "Our policies apply to all portions of your content (video, Short,
or live stream, thumbnail, title, description, and tags)." The page enumerates categories
(inappropriate language, violence, adult content, shocking content, harmful acts, hateful content,
misinformation, etc.) with three monetization outcomes: "can earn ad revenue," "will receive limited
ad earnings," "will receive no ad earnings."

> ⚠️ Code implication for an autonomous factory: The single biggest policy risk to a templated video
> pipeline is the "mass-produced / template / interchangeable" language in answer/1311392. The safe
> design is *materially varied substance per video* plus an authentic point of view, not cosmetic
> variation of a fixed template.

---

## GAPS

The following could not be answered from a primary (YouTube-owned) source that was actually
retrievable. Do not fill these with guesses.

1. **Official July 2025 blog post for the inauthentic-content change — URL not found.**
   The help-center changelog entry at https://support.google.com/youtube/answer/1311392 is dated
   July 15, 2025 and is the authoritative source used above. Candidate blog.youtube slugs tried
   returned 404 (e.g. `/news-and-events/youtube-announces-youtube-front-row-and-new-monetization-options-for-creators/`,
   `/news-and-events/new-monetization-options-for-creators/`, `/creator-and-artist-stories/how-creators-are-using-shorts-to-grow/`).
   A web search surfaced only third-party blogs (subsub.io, dreamtuber, ppc.land, etc.), which are
   deliberately NOT cited. **Status: NOT VERIFIED (primary blog URL).**

2. **Vertical / 9:16 long-form distribution, ranking, and monetization.**
   No official YouTube page was found stating whether vertical long-form videos are treated
   differently by recommendations or monetization. The only documented aspect-ratio consequence found
   is the end-screen element limit (answer/6388789). **Status: NOT VERIFIED.**

3. **Shorts→long-form conversion rate / "Shorts drive long-form" quantified claim.**
   No official YouTube statistic was found quantifying how often Shorts viewers convert to long-form
   viewers or subscribers. Only the "related video" feature (answer/14075157) and the general
   claim that subscribers from Shorts count toward Creator Awards (answer/10059070) exist.
   **Status: NOT VERIFIED (numbers).**

4. **Subscribe-conversion large-sample analysis.**
   No official YouTube-published analysis of subscribe conversion rates by CTA type/placement was
   found. Only prescriptive guidance ("think of appropriate moments..." — answer/11913421) exists.
   **Status: NOT VERIFIED.**

5. **YouTube's own "subscribers vs. viewers" framing / subscriber value claims.**
   The only official-adjacent statement found is from the 2021 recommendation blog ("Recommendations
   drive a significant amount of the overall viewership on YouTube, even more than channel
   subscriptions or search" — blog.youtube/inside-youtube/on-youtubes-recommendation-system/), which
   is about viewership share, not subscriber economics. **Status: PARTIAL / NOT VERIFIED for
   subscriber-value numbers.**

6. **English-locale "How YouTube works → Recommendations" page.**
   `https://www.youtube.com/howyoutubeworks/recommendations/` was fetched twice and served Italian
   content; `?intl=ALL_en` did not change locale. The English version was not obtained.
   **Status: PARTIAL.**

7. **Official YouTube statement that "watch time is the main ranking signal."**
   No such unconditional statement was found. Official docs list multiple signals and explicitly say
   the system "doesn't favor any particular format" and that surveys measure "satisfaction, not just
   watch time" (answer/16089387, answer/11914225). Any code comment asserting watch time is *the*
   main signal would be unsupported. **Status: NOT VERIFIED.**

8. **Mid-video CTA placement efficacy evidence (retention impact of CTAs).**
   No official YouTube study on the retention cost/benefit of CTA placement was found.
   **Status: NOT VERIFIED.**

---

## Primary sources used (all fetched successfully)

| URL | What it supports |
|---|---|
| https://support.google.com/youtube/answer/72851 | YPP entry thresholds; qualified watch hours/Shorts views |
| https://support.google.com/youtube/answer/12843009 | 2027 YPP changes; Premium Lite; active-channel rules |
| https://support.google.com/youtube/answer/12504220 | Shorts monetization; Creator Pool; 45% share |
| https://support.google.com/youtube/answer/1311392 | Inauthentic content; reused content; AI personas; template risk |
| https://support.google.com/youtube/answer/6162278 | Advertiser-friendly guidelines |
| https://support.google.com/youtube/answer/11913421 | Official CTA guidance; fanbase tips |
| https://support.google.com/youtube/answer/10059070 | Shorts creation; views metric change; Shorts YPP path |
| https://support.google.com/youtube/answer/13363900 | Why choose Shorts; engagement CTA example |
| https://support.google.com/youtube/answer/13362274 | Why choose video; format framing |
| https://support.google.com/youtube/answer/16089387 | Recommendation signals (official) |
| https://support.google.com/youtube/answer/11914225 | Search & discovery tips; ranking signals; format neutrality |
| https://support.google.com/youtube/answer/9314415 | Audience retention; intro; hook guidance |
| https://support.google.com/youtube/answer/6388789 | End screens; 5–20 s window; 16:9 element limit; CTA |
| https://support.google.com/youtube/answer/2467968 | Mid-roll 8-min rule; ad pods 5-min rule |
| https://support.google.com/youtube/answer/14075157 | Related video on Shorts |
| https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/ | Recommendation history; watchtime/valued watchtime |
| https://blog.youtube/news-and-events/made-on-youtube-2025/ | 2025 keynote context |
| https://www.youtube.com/creators/create/longform/ | Long-form guidance; hook 5–10 s; upload limits |
| https://www.youtube.com/creators/grow/engage-your-community/ | Engagement; collaborations |
| https://www.youtube.com/creators/grow/understand-your-audience/ | "How the algorithm works" (creator-facing) |
| https://www.youtube.com/creators/grow/optimize-your-content/ | Optimize/experiment guidance |
| https://developers.google.com/youtube/analytics/metrics | (from earlier pass) engagedViews metric definition |
| https://www.youtube.com/howyoutubeworks/recommendations/ | AI disclosure/labels (Italian locale) |

**Third-party blog sources surfaced by search were intentionally excluded.** No statistic, study
name, or quote in this report originates from a non-YouTube source.
