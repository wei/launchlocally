# Submission form answers

Form: <https://tinyurl.com/20261114submission>. Submitted on 2026-11-14 before the 17:30 JST deadline.
The two long answers below are recorded exactly as submitted.

## Project Name / プロジェクト名

LaunchLocally

## Team Name & Member Names / チーム名とメンバー氏名

Filled in on the form. Not recorded in this public file.

## Member Emails / メールアドレス

Filled in on the form. Not recorded in this public file.

## GitHub Repo URL (public) / GitHubリポジトリのURL

https://github.com/wei/launchlocally

## Live Demo / Deployment URL / デモ・デプロイURL

https://wei.github.io/launchlocally/

## Slide Deck URL / スライドURL

https://wei.github.io/launchlocally/slides/

PDF with a text layer, if the form or a judge needs a file: https://wei.github.io/launchlocally/slides/launchlocally-slides.pdf

## Partner Technologies Used / 使用したパートナー技術

As submitted:

We used AgentField CodeAF, Tavily, Daytona, Nosana.

- AgentField runs the pipeline and acts as the main harness and orchastrator. Each stage is its own node, so we can open any run and see its workflow graph.
- CodeAF writes the video's theme. It works from the brand profile of the product's official site, and we check its stylesheet before using it.
- Tavily does the research. Twelve agents run in parallel, 5 on the official site and 7 on the Japanese web, and each fact keeps its source link and an excerpt.
- Daytona renders the video. The composition goes into a sandbox and comes back as an MP4.
- Nosana runs the models. Its hosted Qwen writes the script and plays the local buyer. Two GPU deployments we created run the narration voice and a backup text model.

## What does your agent do? (2-3 sentences) / エージェントの概要(2-3文)

As submitted:

Companies entering Japan usually translate their launch material, but Japanese buyers expect local content presented their way, so LaunchLocally takes a product URL, researches the product and the Japanese market, and makes a narrated launch video in Japanese. Every claim on screen links to its source, and an agent playing a Japanese enterprise IT head reviews the script as a eval and approval gate and can send it back for revisions. We ran it on the four sponsors AgentField/CodeAF, Tavily, Daytona, Nosana's sites and on our own. All 7 runs and each took 90 to 160 seconds and is viewable on our website.
