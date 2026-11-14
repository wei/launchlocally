# Submission form draft

Form: <https://tinyurl.com/20261114submission> (deadline 17:30 JST, one
submission per team). Copy each answer into the matching field. Items marked
TODO are for the team to fill in or for the lead to confirm before submitting.

## Project Name / プロジェクト名

LaunchLocally

## Team Name & Member Names / チーム名とメンバー氏名

TODO (team name, then each member's name)

## Member Emails / メールアドレス

TODO

## GitHub Repo URL (public) / GitHubリポジトリのURL

https://github.com/wei/launchlocally

## Live Demo / Deployment URL / デモ・デプロイURL

https://wei.github.io/launchlocally/

## Slide Deck URL / スライドURL

https://wei.github.io/launchlocally/slides/

PDF with a text layer, if the form or a judge needs a file: https://wei.github.io/launchlocally/slides/launchlocally-slides.pdf

## Partner Technologies Used / 使用したパートナー技術

AgentField + CodeAF, Tavily, Daytona, Nosana. All four partners, each called from code.
- AgentField: control plane. Each pipeline stage is a reasoner run as its own node through `app.call`, so every run has a traced workflow graph (launchlocal/agents.py).
- CodeAF: headless `codeaf exec` writes the theme stylesheet that styles the video after the product's official site; the result is checked and linted before use (launchlocal/coder.py).
- Tavily: `AsyncTavilyClient` map, extract and search feed 12 parallel research agents, 5 on the official site and 7 on the local web. Every fact keeps its source URL and an excerpt checked against the page text (launchlocal/research.py).
- Daytona: the Python SDK (`Daytona.create`, `execute_session_command`, `get_preview_link`) renders the HTML video composition to MP4 in a sandbox and hosts it (launchlocal/render.py).
- Nosana: hosted Qwen 3.8 27B, called through the OpenAI-compatible API, writes the script and plays the local buyer. Two GPU deployments created through Nosana's REST API run the Kokoro voice model (`POST /v1/audio/speech`) and a vLLM Qwen2.5-14B backup text model (launchlocal/llm.py, launchlocal/voice.py).

## What does your agent do? (2-3 sentences) / エージェントの概要(2-3文)

Translated launch material fails abroad because local buyers expect local proof, tone and format, so LaunchLocally turns one product URL into a narrated launch video in the local language, made for foreign companies entering Japan. Every scene and on-screen claim must cite one of about 40 facts found by 12 Tavily research agents, and a local buyer agent (for Japan, an enterprise head of IT doing a ringi-style review) can reject the script and trigger a revised cut. It runs in 90 to 160 seconds across AgentField, CodeAF, Daytona and two Nosana GPU deployments, and 7 recorded runs are public, including the four sponsors' own sites and the launch video LaunchLocally made for itself.

### Japanese version, if a Japanese answer is preferred

発売資料を翻訳するだけでは、現地の買い手が求める根拠、語調、形式に応えられません。LaunchLocallyは製品URLを1つ受け取り、日本市場に参入する海外企業向けに、現地の言語でナレーション付きのローンチ動画を作成します。動画の各シーンと画面上の主張は、Tavilyを使う12のリサーチエージェントが集めた約40件の事実を出典として示し、現地の買い手役エージェント(日本では大企業の情報システム部門長による稟議形式の審査)が台本を差し戻すと修正版が作られます。AgentField、CodeAF、Daytona、Nosanaの2つのGPUデプロイメントを使って90〜160秒で完成し、スポンサー4社のサイトとLaunchLocally自身のローンチ動画を含む7件の実行記録を公開しています。
