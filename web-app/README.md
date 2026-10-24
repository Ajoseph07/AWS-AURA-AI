# AURA AI Web App — Deployable to AWS

A production-ready version of the AURA AI mutual-aid exchange UI, built with
**Flask + gunicorn** and containerized for **AWS App Runner**. Uses **live
Amazon Bedrock** for message extraction (with an automatic offline fallback so
the service stays up even before Bedrock permissions are wired in).

## Contents

| File | Purpose |
| ---- | ------- |
| `app.py` | Flask application (routes + JSON API) |
| `pipeline.py` | Self-contained extraction + matching logic |
| `static/index.html` | The single-page UI |
| `static/sample_messages.json` | 30 bundled sample messages |
| `requirements.txt` | Flask, gunicorn, boto3 |
| `Dockerfile` | Production container image |
| `apprunner.yaml` | App Runner source-build config |

## Endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET | `/` | The web UI |
| GET | `/sample` | The 30 sample messages |
| GET | `/health` | Health check (`{"status":"ok","bedrock":true}`) |
| POST | `/api/process` | Run the pipeline |

## Run locally

```bash
cd web-app
pip install -r requirements.txt

# Dev server:
python app.py
# Or exactly as production runs it:
gunicorn --bind 0.0.0.0:8000 app:app
```

Open http://localhost:8000.

---

## Deploy to AWS App Runner (public HTTPS URL)

> Run these from an AWS-authenticated terminal or **AWS CloudShell**, in
> `us-east-1`. App Runner gives you an auto-scaling HTTPS endpoint with no
> servers to manage.

### Step 1 — Enable Bedrock model access
Console → **Bedrock** → *Model access* → enable **`anthropic.claude-sonnet-4-6`**.
Without this, extraction automatically falls back to offline mode.

### Step 2 — Create an instance role so the app can call Bedrock

```bash
cat > trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "tasks.apprunner.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name AuraAiAppRunnerRole \
  --assume-role-policy-document file://trust.json

cat > bedrock-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:Converse"],
    "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6"
  }]
}
EOF

aws iam put-role-policy \
  --role-name AuraAiAppRunnerRole \
  --policy-name BedrockInvoke \
  --policy-document file://bedrock-policy.json
```

### Step 3 — Deploy

**Option A — Build the container image and push to ECR, then point App Runner at it:**

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
REPO=aura-ai-web

# Create an ECR repo and log in
aws ecr create-repository --repository-name $REPO --region $REGION || true
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# Build and push (run from web-app/)
docker build -t $REPO .
docker tag $REPO:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
```

Then in the Console: **App Runner → Create service → Container registry →
Amazon ECR**, pick the image, set **port 8000**, attach the **instance role**
`AuraAiAppRunnerRole`, and create. App Runner returns a public HTTPS URL.

**Option B — Deploy straight from GitHub source (uses `apprunner.yaml`):**
In the Console: **App Runner → Create service → Source code → GitHub**,
connect this repo, set the source directory to `web-app`, attach the
`AuraAiAppRunnerRole` instance role, and create.

### Step 4 — Verify

```bash
# App Runner shows the service URL; then:
curl https://<your-service-url>/health
# -> {"status":"ok","bedrock":true}
```

Open the URL in a browser, click **Load 30 sample messages**, and **Process**.

## Configuration (environment variables)

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `AWS_REGION` | `us-east-1` | |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-6` | |
| `USE_BEDROCK` | `auto` | `auto` (detect), `1` (force on), `0` (force offline) |
| `PORT` | `8000` | |
```
