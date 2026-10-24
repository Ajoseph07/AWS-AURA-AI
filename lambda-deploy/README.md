# Deploy AURA AI to AWS Lambda (public HTTPS URL)

Your AWS project blocks **App Runner** (via an organization Service Control
Policy), so the `web-app/` App Runner path won't work on this account. This
folder deploys AURA AI as an **AWS Lambda function with a public Function URL**
instead — which your project **does** allow — giving you a real, shareable
`https://` link with no servers to manage.

## What gets deployed

`lambda_function.py` adapts the same routes as the local `aura-ai/web/server.py`
(the map, dashboard, classic UI, and the `/api/*` endpoints) to the Lambda
Function URL event format. All pipeline modules and the HTML/JSON assets are
bundled into one zip.

## Prerequisites

- You're logged in: `aws login --profile AJ --region us-east-2`
- Run from the repo root on your Mac.

## Deploy (one command)

```bash
cd ~/Desktop/AWS-AURA-AI
bash lambda-deploy/deploy.sh
```

The script is **idempotent** — re-run it anytime to redeploy after code changes.
It will:

1. Package the app into `lambda-deploy/aura-ai-lambda.zip`
2. Create an IAM role (`aura-ai-lambda-role`) with CloudWatch Logs + Bedrock access (first run only)
3. Create or update the Lambda function `aura-ai-web` (Python 3.12, us-east-2)
4. Create a public Function URL (first run only)
5. Print your public URL

When it finishes it prints something like:

```
Public URL: https://abc123....lambda-url.us-east-2.on.aws/
  https://abc123....lambda-url.us-east-2.on.aws/            (map — home)
  https://abc123....lambda-url.us-east-2.on.aws/dashboard   (dashboard + search)
```

## Notes

- **Live AI** is on by default (`USE_BEDROCK=1`). The function's IAM role grants
  `bedrock:InvokeModel` / `bedrock:Converse`. To deploy in offline (rules) mode:
  `USE_BEDROCK=0 bash lambda-deploy/deploy.sh`
- **Model access:** make sure Bedrock model access is enabled for
  `anthropic.claude-haiku-4-5-20251001-v1:0` in us-east-2 (you already verified
  this works from the CLI).
- **Cost:** Lambda + Function URL is pay-per-request and effectively free at
  demo traffic. Bedrock charges a tiny per-call fee only when the app extracts.
- **Remove it later:**
  ```bash
  aws lambda delete-function --function-name aura-ai-web --region us-east-2 --profile AJ
  ```
