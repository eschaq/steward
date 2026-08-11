# RDD — Estate Belongings Disposition Agent

Hackathon: All Things Agentic Hackathon (Devpost, Gemini/Google Cloud)
Deadline: Aug 31, 2026 @ 7:00pm CDT
Track: **The Collaborative Partner**
Last updated: 2026-08-10

**Revision note:** Initial scope (photo → classify → claim/contest/resolve → marketplace routing) was a solid multi-user system but didn't clear the Collaborative Partner track's actual technical bar — the brief specifically requires stateful, adaptive behavior ("learns from your corrections"), which the original design didn't have. Three mechanics were added to close the gap: agent-initiated clarifying questions on low-confidence items, agent-mediated contested-item resolution, and an override-memory loop that adapts future suggestions per estate. All three are now Tier 1, not stretch. Marketplace channel/pricing (Tier 2) is unchanged but no longer part of the core demo arc — the demo now foregrounds the adaptive-agent behavior the track is actually judging.

---

## Problem Statement

When someone dies or downsizes, executors and beneficiaries face a second, unaddressed burden after the legal/financial estate process: deciding what happens to the physical belongings. Existing estate-settlement software (EstateExec, Estateably, SwiftProbate) handles wills, court forms, and tax deadlines but stops entirely at the household's contents. Existing reseller/marketplace tools (Voolist, Crosslist, Meta's Seller app) handle photo-to-listing well, but are built for repeat power-sellers running an ongoing hustle, not a family doing this once, under grief, with multiple people who may disagree about who gets what. Nobody serves the multi-stakeholder decision problem that sits between these two mature categories.

## Solution Overview

A multi-user agent that:
1. Classifies household items from photos (category, condition, suggested disposition)
2. Lets invited beneficiaries claim items they want
3. Surfaces and holds contested claims (2+ people want the same item) for the executor to resolve
4. Routes resolved, unclaimed items toward disposition — starting with marketplace sale research/pricing/listing drafts

## MVP Feature List

**In (Tier 1 — Core, must work end-to-end):**
- Multi-user estate creation, executor + beneficiary roles, invite flow
- Photo-based item classification with confidence scoring
- Claim / contest / resolve workflow
- Central Message Center — unified feed for item-specific and general estate discussion, including two agent-authored behaviors:
  - **Clarifying questions** when classification confidence is low
  - **Contested-item mediation** — agent proactively suggests resolution paths the moment an item flips to Contested
- **Adaptive suggestion memory** — agent tracks executor overrides of its disposition suggestions per estate and weights future suggestions accordingly (the retrieval-and-adapt loop required by the track)
- Dashboard: inventory grid + contested-item resolution view

**In (Tier 2 — Stretch, build after Tier 1 is solid):**
- Marketplace channel recommendation (Vinted vs. FB Marketplace vs. eBay vs. Poshmark) per item category
- AI-suggested pricing + draft listing text for resolved, sell-routed items

**Explicitly out (Tier 3 — designed for, cut first under time pressure):**
- Bulk auction/estate-sale batch pricing (schema scaffolded, not built live — see data model doc)
- Actual API posting to marketplaces (draft only, not live listing, for demo + cost-control reasons)
- Donation receipt/tax-value documentation
- Payment/commission handling of any kind

## Target User (Audience Sharpening Test)

❌ "Executors" — one modifier, still a category
❌ "Estate executors settling a family member's estate" — two modifiers
✅ **"The executor of a mid-size family estate — typically an adult child — managing 2-5 beneficiary siblings who each have emotional claims on overlapping household items, with no professional estate-sale company involved."**

Three modifiers: role (executor, typically adult child), constraint (multiple beneficiaries with competing/overlapping claims), and context (no professional intermediary — this is a DIY family situation, not one already outsourced to an estate-sale company).

## Named Anchor Users

Not literal companies (no B2B anchor exists yet for this consumer-facing tool), but sharp personas standing in for the SOP's anchor-user requirement:
1. The eldest of three adult siblings named co-executor after a parent's death, physically present to sort the house, needing to keep peace between out-of-state siblings who can't see the items in person
2. A person downsizing an aging parent into assisted living, where the parent is still alive and has opinions, adding a fourth "claimant" who isn't a beneficiary but has a vote
3. A small independent estate-sale coordinator (1-2 person operation, not a franchise) who currently uses a spreadsheet to track family claims before the sale, who could be a Tier 2+ paid-tier user later

## Demo Arc (5 steps, under 2 minutes)

1. Executor uploads photos of 5-6 household items — agent classifies each; one item has low confidence and the agent posts a **clarifying question** in the Message Center instead of guessing silently
2. Two "beneficiary" logins (pre-seeded demo accounts) both claim the same item — dashboard immediately shows it flip to **Contested**, and the agent proactively posts a **mediating suggestion** in the item's thread (not just raw conflict data)
3. Executor resolves the contested item using the agent's suggestion or their own call
4. Executor overrides the agent's disposition suggestion on 2-3 items (e.g., agent suggests sell, executor picks donate each time) — dashboard/agent then visibly **adapts its next suggestion** to match the pattern, demonstrating the persistent-memory loop live, not just described
5. Dashboard view zooms out: full inventory grid showing the mix of resolved/contested/routed states — the "aha" is seeing consensus tracked **and** the agent visibly learning from this specific estate's decisions, not just classifying photos

## System Framing (System vs. Feature Test)

One sentence: **"A complete household-disposition workflow for estates with multiple beneficiaries — from photo to consensus, guided by an agent that asks, mediates, and adapts as it learns each family's decisions."**
Multi-step workflow (classify → ask when uncertain → claim → mediate conflict → resolve → learn from the resolution) — passes the test, and now explicitly demonstrates the stateful, adaptive behavior the Collaborative Partner track requires rather than gesturing at it.

## Five Whys

1. **Why now?** Vision-model classification is finally cheap and accurate enough to run against an entire household's contents without manual triage — that wasn't practical 2 years ago. Estate-tech has fully professionalized the paperwork side in the same window, leaving physical disposition untouched by comparison.
2. **Why this team/you?** Already built and running a real Vision API/ML Kit item-triage pipeline for a personal household purge — working prototype with real data, not a cold start.
3. **Why this approach?** Multi-stakeholder consensus-holding is the differentiator, now paired with real adaptive memory: the agent asks clarifying questions when uncertain, mediates contested items instead of just displaying conflict, and tracks executor overrides per estate to weight future suggestions — a genuine retrieval-and-adapt loop, not a one-shot classifier. Existing tools classify once for a single user; none hold multi-party state or learn from a specific family's decisions over time.
4. **Why won't this be solved by someone else?** The gap persists because it sits at the seam between two mature, well-funded categories (estate-legal software, reseller tools) that have no structural reason to expand into each other's territory.
5. **Why does the business model work?** Free/low-cost for individual family use (drives word-of-mouth at the exact moment of need); paid tier for executors/small estate-sale coordinators managing multiple estates concurrently; potential referral/commission with donation orgs or consignment partners on routed items. Weakest of the five — needs real-world volume testing post-hackathon.

## Tech Stack (per Phase 1.3 analysis)

**Mandatory requirements (all tracks, not optional):**
- Gemini 3.5 or newer (Gemini API or Vertex AI)
- At least one Google Agent Framework: ADK, GenAI SDK, Antigravity SDK, or GenKit
- At least one Google Cloud infra service (Cloud Run, Cloud SQL, Firestore, GKE, Pub/Sub)

**Stack decision:** Google ADK for the agent orchestration layer (claim/contest/resolve reasoning, marketplace channel recommendation), Gemini 3.5 for image classification + listing draft generation, **two separate Cloud Run services — frontend and backend split** (established security practice: frontend never touches Firestore/Storage directly, only through the backend API; trust boundary stays clean even though Steward's data isn't regulated/financial). Frontend serves the static build; backend handles API + ADK agent logic + Firestore/Storage access. Kept deliberately simple — two services, no API gateway or further service splitting, to manage deploy complexity under the ~20-day window. Firestore for the multi-user dashboard's real-time-ish state (claims/contests updating live across users), Firebase Authentication for executor/beneficiary role-based login, Cloud Storage for item photos.

**Rationale:** No meaningful stack-choice tension here the way Prism had with Claude vs. Gemini — this hackathon mandates the Google stack across every track, so there's no opportunity cost calculation to make. The interesting decision is Firestore over Cloud SQL: Firestore's listener model fits the "beneficiary claims something, executor's dashboard updates" use case better than polling a relational DB would, and it's still one Google Cloud infra service for eligibility purposes.

## Build Tooling (separate from runtime tech stack above)

- **Coding:** Claude Code — primary driver for implementation. Judging criteria (Innovation, Architectural Discipline, Demo/Production Readiness) evaluate the shipped artifact, not which tool wrote the code, so this is a velocity/reliability choice, not a "Google-first" tradeoff. The mandatory-Google requirement is satisfied by the runtime stack (Gemini/ADK/Cloud infra), not the coding assistant.
- **UI design:** Google Stitch (stitch.withgoogle.com) — generate multi-screen mockups from prompts, export `DESIGN.md` for Claude Code to build directly against. Must prompt Stitch explicitly with the branding doc (palette, "warm/unhurried/plainspoken, not clinical, not cutesy") rather than a generic app description — default Stitch output drifts toward a clean, Material-flavored aesthetic that would fight the locked Steward persona.
- **Prompt prototyping:** Google AI Studio — test classification/listing-draft prompts against Gemini before wiring into the app
- **Async background tasks:** Jules — scoped, well-defined chunks handed off during swivel-chair windows

**Explicitly avoided:** Firebase Studio — sunsetting March 2027, new workspace creation already disabled as of June 2026.

## Hackathon Resources Applied

Per official resources page (allthingsagentichackathon.devpost.com/resources):

- **Google Cloud credit form** — request the $150 credit immediately (Day 1), not mid-build. Approval reportedly takes 1-5 business days.
- **Relevant webinars** (pre-recorded reference if live attendance doesn't fit the swivel-chair schedule):
  - Aug 13 — *Build a Long-Running Agent: Persistent Workflows with Google ADK* (crash recovery, idempotency — relevant if the clarifying-question flow needs to survive a session interruption)
  - Aug 27 — *Architecting Agent Memory: Session State, Vector Search, and Managed Cloud Memory* — directly describes the OverrideLog adaptive-suggestion mechanic; useful as a design reference even without live attendance
- **Firestore confirmed** as Google's own recommended datastore for "agent state/memory" — validates the stack decision above, not just a convenient choice
- **Memory Bank (GEAP) deliberately not used** — Google explicitly scopes Memory Bank/Agent Registry/Agent Runtime to the Fortified Enterprise Fleet track's recommended platform, not Collaborative Partner. Steward's hand-rolled OverrideLog in Firestore is the leaner, track-appropriate choice, not a missed opportunity to use "the real" Google memory tooling.
- **No vector search needed** — OverrideLog does simple category-based override counting, not semantic retrieval, matching the resources page's cost-saving guidance to avoid dedicated vector search infrastructure where a simpler query suffices.
- **Cost discipline confirmed:** Gemini Flash as default (Pro reserved only for complex final reasoning, if ever needed), Cloud Run scale-to-zero, budget alerts on, and explicitly turn off/delete resources after the demo video is recorded.

## Prize Tracks Targeted

| Track | Eligible? | Notes |
|---|---|---|
| Grand Prize ($50K) | Yes | Open to all categories |
| The Collaborative Partner ($20K) | **Yes — primary target** | This is the track the concept was built for |
| The Taskmaster ($20K) | No | Different framing (workflow automation, not guided consensus) |
| The Fortified Enterprise Fleet ($20K) | No | Requires enterprise agent registry infrastructure out of scope |
| Startup Excellence ($20K) | No | Requires incorporated org + corporate email |
| Individual/Hobbyist Best Team/Solo Build ($10K, 2 winners) | Yes | Solo build qualifies |
| Best Architectural Design ($5K, 2 winners) | Yes | Disposition-table seam design is a genuine architecture story to tell |
| Best Multimodal UX ($5K, 2 winners) | Yes | Photo classification + dashboard is inherently multimodal |
| Honorable Mentions ($2K, 5 winners) | Yes | Fallback catch-all |

**Total realistic prize value pursued:** Collaborative Partner ($20K) as primary, with Individual/Hobbyist, Architectural Design, and Multimodal UX as plausible stacked secondary tracks — all compatible with the same single build, no stack tradeoffs required to stay eligible for all four simultaneously.

## Failure Handling (per Architectural Discipline judging criterion)

Judging explicitly weighs "how you handle failures — robust, production-minded agents, not brittle scripts." Minimum viable handling for Tier 1, decided now so it's not improvised mid-build:

- **Classification call fails/times out:** Item status falls back to `needs_clarification` with a generic "couldn't classify — take a look?" message from the agent, rather than blocking the upload or silently dropping the item.
- **Race condition on simultaneous claims:** Two claims arriving near-simultaneously both get recorded (Claim table has no uniqueness constraint by design) — status logic already treats 2+ claims as `contested`, so a race just produces the correct contested state rather than a bug to prevent.
- **OverrideLog retrieval fails/is empty:** Agent falls back to raw classification confidence with no history-based adjustment, and says so explicitly ("no pattern yet for this estate — here's my best guess") rather than failing silently or blocking the suggestion.

Design principle: every failure mode degrades to a visible, honest agent statement ("I'm not sure," "no pattern yet") rather than a silent guess or a blocked flow — consistent with the Collaborative Partner track's emphasis on transparent, adaptive behavior.

## Hosting Plan

Cloud Run — **two services**, frontend and backend split per established security practice. Both scale to zero when idle, avoiding both the cold-start problem that hit HuggingFace during Prism and unnecessary credit burn between build sessions. $150 in Google Cloud credits provided by the hackathon should cover build + demo costs across both services; neither needs to stay publicly live after judging per the hackathon's own cost-control note. CORS configured on the backend to accept only the frontend's Cloud Run URL — the one piece of extra plumbing the split requires, worth setting up early rather than debugging under deadline pressure.

## Submission Requirements (per hackathon rules)

- Category selection (Collaborative Partner)
- URL to hosted project (hosted demo encouraged)
- Text description: features/functionality, technologies used, other data sources, findings/learnings
- Public code repo (GitHub) with README spin-up instructions
- Architecture diagram
- ~4-min demo video: problem overview, value prop, live app demo, proof of Google Cloud backend (Console/Cloud Run dashboard/Vertex AI logs)
- Bonus points available: public build-log content (ties directly to DWS capture opportunity, Phase 10), social post with #AllThingsAgenticHackathon hashtag, successful Gemma/Veo/Lyria integration (not currently planned — evaluate if time allows)
