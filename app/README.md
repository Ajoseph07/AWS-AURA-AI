# AURA-AI Bedrock App

A small, stateless Python app that sends a prompt to Amazon Bedrock and returns
the response. No database involved — the prompt comes in on the event and the
answer goes out in the response.

**Flow:**
1. Receive an event with a `prompt`
2. Send it to Bedrock using **`anthropic.claude-sonnet-4-6`** (Converse API)
3. Return the generated response

## Files

| File | Purpose |
| ---- | ------- |
| `handler.py` | Lambda entry point (`handler.handler`) |
| `bedrock_client.py` | Reusable Bedrock Converse wrapper |
| `local_test.py` | Run it locally without deploying |
| `iam-policy.json` | Permissions the function needs (Bedrock only) |
| `requirements.txt` | Dependencies (`boto3`) |

## Prerequisites

1. **Bedrock model access is enabled** for `anthropic.claude-sonnet-4-6`
   (Console → Bedrock → *Model access*). Without this you get `AccessDeniedException`.
2. You are running from an AWS-authenticated terminal or **AWS CloudShell**.
3. Region is `us-east-1`.

## Configuration (environment variables)

| Variable | Default |
| -------- | ------- |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-6` |
| `AWS_REGION` | `us-east-1` |
| `SYSTEM_PROMPT` | `You are AURA-AI, a concise and helpful assistant.` |

## Run locally (quickest way to test)

```bash
cd app
pip install -r requirements.txt

python local_test.py --prompt "Summarize what AURA-AI does"
```

Expected output is a JSON blob with `statusCode: 200` and the generated `response`.

## Deploy as a Lambda function

```bash
cd app

# 1. Package the code
pip install -r requirements.txt -t package
cp handler.py bedrock_client.py package/
cd package && zip -r ../function.zip . && cd ..

# 2. Create an execution role (one time) with the permissions in iam-policy.json
#    plus the AWS managed AWSLambdaBasicExecutionRole for CloudWatch Logs.

# 3. Create the function (replace ROLE_ARN)
aws lambda create-function \
  --function-name aura-ai-processor \
  --runtime python3.12 \
  --handler handler.handler \
  --zip-file fileb://function.zip \
  --role ROLE_ARN \
  --timeout 60 \
  --region us-east-1

# 4. Invoke it
aws lambda invoke \
  --function-name aura-ai-processor \
  --payload '{"prompt":"Say hello from AURA-AI"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  out.json && cat out.json
```
