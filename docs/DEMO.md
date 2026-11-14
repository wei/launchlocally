# Demo run-book

Two to three minutes on stage. A full run takes 90 to 160 seconds, so the run
itself is the demo: start it in the first 15 seconds and talk over the waiting
screen.

## Before you go up (5 minutes)

```sh
cd /Users/wei/Documents/Projects/Personal/launchlocal
scripts/start.sh --tunnel --rehearsal   # practice: reuses saved research, no Tavily credits
scripts/start.sh --tunnel               # judged demo: live Tavily research, about 30 credits per run
```

Each start prints a new public URL. A run for a sponsor that already ran today (daytona.io, tavily.com,
nosana.com, agentfield.ai) uses saved research in rehearsal mode and logs "CACHED RESEARCH".

It prints the local URL, the workflow-graph URL and the public URL. Then:

1. Open `http://127.0.0.1:8787/` in one tab and `http://localhost:8080/ui/` (AgentField, Workflows) in a second tab.
2. Check the voice deployment answers: `curl -s "$(jq -r .endpoint docs/nosana-voice.json)/health"` should print `{"status":"healthy"}`. It stops around 20:20 JST.
3. Start one throwaway run and let it finish, so the Daytona sandbox and the model providers are warm.
4. Turn the laptop volume up. The video has Japanese narration.
5. Keep the cached runs ready in the "past runs" list on the launcher: `daytona-japan`, `tavily-japan`, `nosana-japan`, `agentfield-japan`, and LaunchLocally's own run `launchlocally-intl`.
6. Tavily budget: a live run costs about 30 credits. Do not rehearse without `--rehearsal`.

Stop everything afterwards: `scripts/start.sh --stop`.

## Script

| Time | Do | Say |
|------|----|-----|
| 0:00 | Launcher on screen | "A company entering Japan translates its launch material. Local buyers expect local proof, local tone and a local format. LaunchLocally does that from one URL." |
| 0:10 | Ask a sponsor judge to pick: Daytona, Tavily, Nosana or AgentField. Click that button. Market stays Japan. | "Pick your own product. We will launch it in Japan, in Japanese, right now." |
| 0:20 | Research column fills | "Twelve agents are searching with **Tavily**: five read the official site, seven search the Japanese web for competitors, pricing, trust requirements and how local buyers talk. Every fact keeps its source." |
| 0:40 | Storyboard cards fill; infrastructure column | "A strategist writes the script. **CodeAF** is writing the theme so the video looks like the official site. The voice is generated on a **Nosana** GPU." |
| 0:55 | Buyer gate panel shows the stamp | "This is the part I like. A local buyer agent, the head of IT at a Japanese enterprise, reviews it. It can reject the cut, and the system fixes what it rejected." |
| 1:10 | Switch to the AgentField tab for 5 seconds, then back | "Every stage is its own node in **AgentField**. This is the live workflow graph." |
| 1:20 | Brief opens; press play, stop talking | Video plays with sound, about 25 seconds. Rendered in a **Daytona** sandbox. |
| 1:50 | Click an on-screen claim | "Every sentence is sourced. This claim came from this page, this excerpt." |
| 2:00 | Toggle EN; point at the gaps list | "And it tells the vendor what a Japanese buyer will still ask for: data location, local customers, yen pricing." |
| 2:10 | QR on screen | "It is on your phones. Paste a URL. Launch like a local." |

If the judge's pick takes too long, open the cached run for that sponsor from
the launcher with replay: `/run/<id>?replay=1&speed=3`. The page shows a
"CACHED RUN" badge. Say that it is a recording of the same pipeline.

## What can go wrong

| Problem | What you see | What to do |
|---------|--------------|------------|
| Nosana hosted model missing | A log line: "Nosana hosted inference unavailable ... language calls use ..." | Nothing. The model chain moves to the next provider and labels it. The voice still runs on the Nosana GPU. |
| Voice endpoint down | A log line saying the local CPU fallback was used | Nothing. Narration is still generated, labelled as fallback. |
| CodeAF theme rejected | "baseline look kept: ..." | Nothing. The video renders with the baseline look. |
| Daytona render fails | Renderer error on the infrastructure column | Open the cached run for that sponsor. For the next run: `LAUNCHLOCAL_RENDER=local scripts/start.sh`. |
| Venue network slow | Research lanes stall | Switch to the cached run with replay. |
| QR does not open | Phone shows an error | The tunnel died. Show the brief on the laptop. |

## Dogfood line

"We pointed LaunchLocally at its own website. This is the launch video it made for itself." It is on the
homepage, https://wei.github.io/launchlocally/, and on the slide "We launched ourselves with it". Its buyer
agent rejected both cuts, partly because it would not trust a hackathon project. That is the honest result.

## Reverse direction

Pick the `en-US` market and paste a Japanese product URL to launch it globally
in English. Same pipeline, English voice, a US buyer persona.
