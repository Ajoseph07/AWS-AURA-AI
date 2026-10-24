# AURA-AI DynamoDB Tables

This folder defines three DynamoDB tables for the AURA-AI project.

| Table            | Partition key      | Type     | Billing    | Table class |
| ---------------- | ------------------ | -------- | ---------- | ----------- |
| `AuraAlerts`     | `alertId`          | String   | On-demand  | Standard    |
| `AuraRequests`   | `requestId`        | String   | On-demand  | Standard    |
| `AuraResources`  | `resourceId`       | String   | On-demand  | Standard    |

- **On-demand** billing = `PAY_PER_REQUEST` (no capacity to provision; you pay per read/write).
- **Region:** `us-east-1` (the project's assigned Region).

> **Note:** These must be run from a machine that is authenticated to AWS
> (via `aws login` / `aws configure`) or from **AWS CloudShell**, which is already
> authenticated. Pick whichever option below is easiest for you.

---

## Option 1 — AWS CLI script (quickest)

```bash
cd infrastructure
chmod +x create-tables.sh
./create-tables.sh
```

The script creates all three tables, waits until they are `ACTIVE`, and lists them.
It uses `AWS_REGION` if set, otherwise defaults to `us-east-1`.

### Or run the raw commands one by one

```bash
aws dynamodb create-table \
  --table-name AuraAlerts \
  --attribute-definitions AttributeName=alertId,AttributeType=S \
  --key-schema AttributeName=alertId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --table-class STANDARD \
  --region us-east-1

aws dynamodb create-table \
  --table-name AuraRequests \
  --attribute-definitions AttributeName=requestId,AttributeType=S \
  --key-schema AttributeName=requestId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --table-class STANDARD \
  --region us-east-1

aws dynamodb create-table \
  --table-name AuraResources \
  --attribute-definitions AttributeName=resourceId,AttributeType=S \
  --key-schema AttributeName=resourceId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --table-class STANDARD \
  --region us-east-1
```

---

## Option 2 — CloudFormation (infrastructure-as-code)

Deploys all three tables as a single, repeatable, deletable stack.

```bash
aws cloudformation deploy \
  --template-file infrastructure/dynamodb-tables.yaml \
  --stack-name aura-ai-dynamodb \
  --region us-east-1
```

To remove all three tables later:

```bash
aws cloudformation delete-stack --stack-name aura-ai-dynamodb --region us-east-1
```

---

## Option 3 — AWS Management Console (click-through)

For each of the three tables:

1. Sign in to the AWS Console and make sure the Region (top-right) is **us-east-1**.
2. Go to **DynamoDB** → **Tables** → **Create table**.
3. **Table name:** e.g. `AuraAlerts`.
4. **Partition key:** e.g. `alertId`, type **String**. Leave sort key empty.
5. Under **Table settings**, choose **Customize settings**.
6. **Capacity mode:** **On-demand**.
7. **Table class:** **DynamoDB Standard**.
8. Click **Create table**.

Repeat with:
- `AuraRequests` / partition key `requestId` (String)
- `AuraResources` / partition key `resourceId` (String)

---

## Verify the tables exist

```bash
aws dynamodb list-tables --region us-east-1
aws dynamodb describe-table --table-name AuraAlerts --region us-east-1
```
