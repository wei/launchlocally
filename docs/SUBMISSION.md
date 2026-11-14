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

AgentField, CodeAF, Tavily, Daytona, Nosana.

- AgentField runs the pipeline. Each stage is its own node, so we can open any run and see its workflow graph.
- CodeAF writes the video's theme. It works from the brand profile of the product's official site, and we check its stylesheet before using it.
- Tavily does the research. Twelve agents run in parallel, 5 on the official site and 7 on the Japanese web, and each fact keeps its source link and an excerpt.
- Daytona renders the video. The composition goes into a sandbox and comes back as an MP4.
- Nosana runs the models. Its hosted Qwen writes the script and plays the local buyer. Two GPU deployments we created run the narration voice and a backup text model.

## What does your agent do? (2-3 sentences) / エージェントの概要(2-3文)

Companies entering Japan usually translate their launch material, but Japanese buyers expect local evidence presented their way, so LaunchLocally takes a product URL, researches the product and the Japanese market, and makes a narrated launch video in Japanese. Every claim on screen links to its source, and an agent playing a Japanese enterprise IT head reviews the script as a ringi approval and can send it back for a second cut. We ran it on the four sponsors' own sites and on our own; all 7 runs are public and each took 90 to 160 seconds.

### Japanese version, if a Japanese answer is preferred

日本に参入する企業の多くは発売資料を翻訳するだけですが、日本の買い手は現地の根拠と、現地の流儀に沿った伝え方を求めます。LaunchLocallyは製品のURLを受け取り、製品と日本市場を調査して、日本語のナレーション付きローンチ動画を作成します。画面上の主張にはすべて出典へのリンクが付き、大企業の情報システム部門長を演じるエージェントが稟議として台本を審査し、差し戻すと修正版が作られます。スポンサー4社のサイトと自社サイトで実行し、7件の実行記録を公開しています（1件あたり90〜160秒）。
