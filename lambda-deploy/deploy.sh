#!/usr/bin/env bash
# =============================================================================
# Deploy AURA AI to AWS Lambda + Function URL (public HTTPS, no servers).
#
# Run from your Mac in the repo:   bash lambda-deploy/deploy.sh
#
# Prereqs: you're logged in (aws login --profile AJ) and in the repo root.
# Region is us-east-2 (your project's Region). Everything is idempotent — you
# can re-run this to redeploy after code changes.
# =============================================================================
set -euo pipefail

# ---- config -----------------------------------------------------------------
PROFILE="${AWS_PROFILE_OVERRIDE:-AJ}"
REGION="us-east-2"
FN_NAME="aura-ai-web"
ROLE_NAME="aura-ai-lambda-role"
# Turn on live Bedrock extraction in the deployed app. Set to "0" for offline.
USE_BEDROCK="${USE_BEDROCK:-1}"

# ---- locate repo paths ------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AURA="$REPO_ROOT/aura-ai"
WEB="$AURA/web"
BUILD="$SCRIPT_DIR/build"
ZIP="$SCRIPT_DIR/aura-ai-lambda.zip"

echo "==> Packaging application"
rm -rf "$BUILD" "$ZIP"
mkdir -p "$BUILD/web"

# Python pipeline modules (bundled flat at the package root)
cp "$AURA"/*.py "$BUILD/"
# The Lambda entry point
cp "$SCRIPT_DIR/lambda_function.py" "$BUILD/"
# HTML pages the handler serves from ./web/
cp "$WEB/map.html" "$WEB/dashboard.html" "$WEB/index.html" "$BUILD/web/"
# JSON data files the handler reads from the package root
cp "$AURA/demo_scenario.json" "$AURA/sample_messages.json" "$BUILD/"

# Drop the CLI-only demo module (not needed, imports argparse-only path)
rm -f "$BUILD/demo.py"

( cd "$BUILD" && zip -qr "$ZIP" . )
echo "    packaged $(du -h "$ZIP" | cut -f1) -> $ZIP"

# ---- IAM execution role (create once, idempotent) ---------------------------
echo "==> Ensuring IAM role: $ROLE_NAME"
if ! aws iam get-role --role-name "$ROLE_NAME" --profile "$PROFILE" >/dev/null 2>&1; then
  TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST" --profile "$PROFILE" >/dev/null
  echo "    created role"
  # Basic execution (CloudWatch Logs)
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --profile "$PROFILE"
  # Allow calling Bedrock for live extraction
  BEDROCK_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:Converse"],"Resource":"*"}]}'
  aws iam put-role-policy --role-name "$ROLE_NAME" \
    --policy-name aura-bedrock --policy-document "$BEDROCK_POLICY" --profile "$PROFILE"
  echo "    attached policies; waiting 10s for IAM to propagate..."
  sleep 10
else
  echo "    role already exists"
fi
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text --profile "$PROFILE")"

# ---- create or update the function ------------------------------------------
ENV_VARS="Variables={USE_BEDROCK=$USE_BEDROCK,BEDROCK_REGION=$REGION,BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0,AURA_LIVE_HAZARDS=0}"

if aws lambda get-function --function-name "$FN_NAME" --region "$REGION" --profile "$PROFILE" >/dev/null 2>&1; then
  echo "==> Updating existing function code"
  aws lambda update-function-code --function-name "$FN_NAME" \
    --zip-file "fileb://$ZIP" --region "$REGION" --profile "$PROFILE" >/dev/null
  aws lambda wait function-updated --function-name "$FN_NAME" --region "$REGION" --profile "$PROFILE"
  aws lambda update-function-configuration --function-name "$FN_NAME" \
    --timeout 30 --memory-size 512 --environment "$ENV_VARS" \
    --region "$REGION" --profile "$PROFILE" >/dev/null
else
  echo "==> Creating function"
  aws lambda create-function --function-name "$FN_NAME" \
    --runtime python3.12 --handler lambda_function.handler \
    --role "$ROLE_ARN" --zip-file "fileb://$ZIP" \
    --timeout 30 --memory-size 512 --environment "$ENV_VARS" \
    --region "$REGION" --profile "$PROFILE" >/dev/null
  aws lambda wait function-active --function-name "$FN_NAME" --region "$REGION" --profile "$PROFILE"
fi

# ---- public Function URL (create once) --------------------------------------
echo "==> Ensuring public Function URL"
if ! aws lambda get-function-url-config --function-name "$FN_NAME" --region "$REGION" --profile "$PROFILE" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "$FN_NAME" \
    --auth-type NONE --region "$REGION" --profile "$PROFILE" >/dev/null
  # Allow public (unauthenticated) invocation of the URL
  aws lambda add-permission --function-name "$FN_NAME" \
    --statement-id FunctionURLAllowPublic --action lambda:InvokeFunctionUrl \
    --principal "*" --function-url-auth-type NONE \
    --region "$REGION" --profile "$PROFILE" >/dev/null 2>&1 || true
fi

URL="$(aws lambda get-function-url-config --function-name "$FN_NAME" \
  --query 'FunctionUrl' --output text --region "$REGION" --profile "$PROFILE")"

echo ""
echo "============================================================"
echo "  AURA AI is deployed! Public URL:"
echo "    $URL"
echo ""
echo "  Pages:"
echo "    ${URL}            (map — home)"
echo "    ${URL}dashboard   (dashboard + search)"
echo "============================================================"
