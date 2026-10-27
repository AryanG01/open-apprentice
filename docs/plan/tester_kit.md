# Tester kit: outside users and practitioners

Goal: at least 10 outside people each run **their own** banner (at least 5 should be real banners from a shop, club, event, side
project or job), and 2-3 practitioners answer five questions. Everything below can be copied and sent as is.
Honest limits to keep in mind when reading the results: friends are not customers, n is small, testers are self-selected. I will report
the numbers with those caveats and will not call this a study.

## A. The message you send (copy, paste, change the first line)
> Hi [name]. I'm finishing a hackathon project (Open Apprentice) and need 10 minutes of honest feedback before Friday.
> It turns a landscape ad banner into a vertical story/reel card **without changing the approved words, price or link**, and asks you
> when something doesn't fit instead of guessing. I need you to try it on **your own banner** (a poster, a shop promo, a club or event
> banner, anything 16:9 with a logo, a picture, a headline and ideally a price and a button). Please be critical: failures help me
> more than praise. Link: **[URL]**. Instructions and 8 short questions: **[form link]**. Please don't use a confidential banner:
> the image is sent to an AI service (Nebius Token Factory) to be read, and kept in the app's memory for about 30 minutes, then dropped.
> I don't keep your image; I do keep your answers. Thank you!

## B. What the tester does (10 minutes, laptop; phone works but is harder)
1. Open the link. Note the time.
2. Choose **your banner** (PNG or JPG, landscape 16:9, for example 1600 x 900). No banner? Ask me for one; or use "Try a sample" and say so in the form.
3. Check what the app found. Drag any box that is wrong; type any word it misread. **Write down how many things you had to fix.**
4. Press "Looks right: make the story card". If it asks a question, answer it and say whether the two options made sense.
5. Look at the card at phone size. Ask yourself: are all my words there, is the picture whole, would I post this?
6. Download the card. Optional: send me a screenshot **only if you are happy to have it shown** (otherwise describe what you saw).
7. Fill in the form (below).

## C. The form (build it in Google Forms; every question below, in this order)
Required: 1 to 12. Mark the form "collect no email".
1. Your role (shop or business owner / marketer or designer / student / other: ____).
2. Did you use your own banner or a sample? (own / sample)
3. If your own: what was it for? (one line, no names needed)
4. How long from opening the link to a finished card? (minutes)
5. Did you get a story card? (yes / no, it stopped / no, it broke)
6. If it stopped or broke: what did the screen say, and did you understand why? (free text)
7. How many things did you have to fix before the card was right? (0 / 1-2 / 3-5 / more than 5)
8. Are all your words, your price and your picture correct in the card? (everything / something wrong: say what)
9. Would you post this card as it is? (1 = never ... 5 = yes today). If not 5, what stops you?
10. How long would this have taken you in your usual tool (Canva, Photoshop, ...)? (minutes, a guess is fine)
11. Rate each 1 (strongly disagree) to 5 (strongly agree): "I understood what to do without help." "The app told me clearly what it was doing." "I trusted the result." "I'd use this again for real work." "It felt finished, not like a prototype."
12. What is the one thing you would fix first?
13. Optional: may I quote your answer to question 9 or 12 in the submission, with your first name and role? (yes / no)
14. Optional: may I show your story card screenshot publicly? (yes / no)

## D. Practitioner interviews (marketer, agency or ad-ops person, SME owner; 15 minutes, call or voice note)
1. How do you turn a landscape ad into vertical formats today, and how long does it take for one campaign?
2. What has gone wrong when an ad was resized (a changed price, a cut-off legal line, a wrong picture)? What did it cost?
3. If a tool gave you a record proving the approved words, price, link and picture survived, would you use or pay for it? Who in your team would care?
4. What would make you trust an AI that resizes your ads? What would make you stop?
5. Which format or channel do you most need that this does not do?
Ask permission for one quote (name or "a marketer at an agency in Singapore" is fine).

## E. What you send me back
- The form's responses sheet as CSV (File > Download), after the last response.
- For each tester who agreed: the screenshot, the quote and the permission line.
- Your own log: who you asked, who replied, who did not (non-response counts), and the time each tester started if you know it.
- The interview notes, even if rough.
- Tell me about every bug or confusion that came up in conversation, even if they did not put it in the form.

## F. What I do with it (so you can tell them)
- I report: number of testers, number with their own banner, number with a card, number who rated it 4 or 5 on "would post", median time, the problems found. Failures are published next to successes.
- I fix only crashes and wrong-answer bugs found by testers before the final deploy; I do not tune the product to a single tester's banner and then claim it worked on it.
- Nothing is identified without permission.

## G. Practical notes for you
- Production today (00056-roj, the older build) is at https://open-apprentice-md76de375q-uc.a.run.app. The new build is not deployed yet; testers are better served by the candidate after your Wednesday-night deploy. Start asking people now, send the link after the deploy.
- Each address can read about 10 banners an hour; fine for one person, tell colleagues in one office not to all test at the same minute.
- Aim for variety: at least 3 testers who run ads or posters for a real purpose, at least 2 who are not technical.
