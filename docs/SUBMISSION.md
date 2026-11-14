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

## Partner Technologies Used / 使用したパートナー技術

AgentField + CodeAF, Tavily, Daytona, Nosana (all four, each at code level).

- AgentField: control plane that runs every agent stage and records the workflow graph. CodeAF: coding harness that writes the theme that styles the video like the product's official site.
- Tavily: map, extract and search across 12 parallel research areas; every fact keeps its source URL and a verbatim excerpt.
- Daytona: sandbox that renders the agent-written video composition and serves the result.
- Nosana: hosted Qwen inference writes the script and plays the local buyer; two Nosana GPU deployments run the voice model that narrates the video and a vLLM server that takes over text generation when the hosted catalog has no chat model.

## What does your agent do? (2-3 sentences) / エージェントの概要(2-3文)

LaunchLocally takes a product URL and a target market (Japan by default) and
launches the product like a local: 12 research agents read the official site
and the local web in parallel with Tavily, a strategist on Nosana writes a
four-scene script in the local language where every sentence carries a source,
a voice model on a Nosana GPU narrates it, CodeAF styles the video like the
official site, and a Daytona sandbox renders it. A local buyer agent (for
Japan, an enterprise IT head reviewing it as a ringi approval) then approves or
rejects the cut, and the system fixes what was rejected. The result is a launch
video plus an interactive brief where clicking any claim opens its source, with
the whole run orchestrated and traced in AgentField.

### Japanese version, if a Japanese answer is preferred

LaunchLocallyは、製品のURLと対象市場（標準は日本）を指定するだけで、現地向けのローンチ動画を作成するエージェントです。12の調査エージェントがTavilyで公式サイトと現地のウェブを並行して調べ、Nosana上のモデルが出典付きの台本と音声を作成し、CodeAFが公式サイトに合わせてデザインを整え、Daytonaのサンドボックスで動画をレンダリングします。最後に現地の購買担当者役のエージェントが内容を審査し、すべての主張から出典を確認できるインタラクティブなレポートとあわせて、AgentFieldで全工程を記録します。
