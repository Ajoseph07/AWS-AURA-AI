#!/usr/bin/env bash
#
# create-tables.sh
# Creates the three AURA-AI DynamoDB tables using the AWS CLI.
#
# Run this on a machine that is authenticated to AWS (aws login / aws configure),
# or in AWS CloudShell (which is already authenticated).
#
# Each table:
#   - Single String partition key
#   - On-demand billing (PAY_PER_REQUEST)
#   - Standard table class
#
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"

echo "Creating AURA-AI DynamoDB tables in region: ${REGION}"

create_table() {
  local table_name="$1"
  local key_name="$2"

  echo "-> Creating ${table_name} (partition key: ${key_name}) ..."
  aws dynamodb create-table \
    --table-name "${table_name}" \
    --attribute-definitions AttributeName="${key_name}",AttributeType=S \
    --key-schema AttributeName="${key_name}",KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --table-class STANDARD \
    --region "${REGION}"
}

create_table "AuraAlerts"    "alertId"
create_table "AuraRequests"  "requestId"
create_table "AuraResources" "resourceId"

echo ""
echo "Waiting for tables to become ACTIVE ..."
for t in AuraAlerts AuraRequests AuraResources; do
  aws dynamodb wait table-exists --table-name "$t" --region "${REGION}"
  echo "   $t is ready."
done

echo ""
echo "Done. Current tables:"
aws dynamodb list-tables --region "${REGION}" --output table
