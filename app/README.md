# AURA-AI Bedrock App

A Python app that connects the three DynamoDB tables to Amazon Bedrock.

**Flow:**
1. Read a request from **`AuraRequests`** (by `requestId`)
2. Send its `prompt` to Bedrock using **`anthropic.claude-sonnet-4-6`** (Converse API)
3. Write the response to **`AuraResources`**
4. On failure, log an entry to **`AuraAlerts`**

## Files

| File | Purpose |
| ---- | ------- |
| `handler.py` | Lambda entry point (`handler.handler`) running the full flow |
| `bedrock_client.py` | Reusable Bedrock Converse wrapper |
| `local_test.py` | Run the flow locally without deploying |
| `iam-policy.json` | Permissions the function needs (Bedrock + DynamoDB) |
| `requirements.txt` | Dependencies (`boto3`) |

## Prerequisites

1. The three DynamoDB tables exist (see `../infrastructure/`).
2. **Bedrock model access is enabled** for `anthropic.claude-sonnet-4-6`
   (Console → Bedrock → *Model access*). Without this you get `AccessDeniedException`.
3. You are running from an AWS-authenticated terminal or **AWS CloudShell**.
4. Region is `us-east-1`.

## Configuration (environment variables)

| Variable | Default |
| -------- | ------- |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-6` |
| `AWS_REGION` | `us-east-1` |
| `REQUESTS_TABLE` | `AuraRequests` |
| `RESOURCES_TABLE` | `AuraResources` |
| `ALERTS_TABLE` | `AuraAlerts` |
| `SYSTEM_PROMPT` | `You are AURA-AI, a concise and helpful assistant.` |

## Run locally (quickest way to test)

```bash
cd app
pip install -r requirements.txt

# Seed a new request and run the whole flow:
python local_test.py --seed --prompt "Summarize what AURA-AI does"

# Or process an existing request already in AuraRequests:
python local_test.py --request-id req-123
```

Expected output is a JSON blob with `statusCode: 200`, the generated
`response`, and the new `resourceId` written to `AuraResources`.

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
  --payload '{"requestId":"req-123"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  out.json && cat out.json
```

## Verify results

```bash
aws dynamodb scan --table-name AuraResources --region us-east-1
```
