# MicroShop: CI/CD Pipeline for a Cloud-Native Microservices App

Cloud Computing mini project (MSc CS, Sem 3).
Every `git push` automatically **tests → builds Docker images → pushes to a registry → deploys to AWS → health-checks** the live site. Data lives in DynamoDB, order alerts go out through SNS, and all logs flow into CloudWatch.

## Cloud services used (8)

| # | Service | Provider | Role in the project | Model |
|---|---|---|---|---|
| 1 | **EC2** | AWS | Virtual server that runs the Docker containers | IaaS |
| 2 | **DynamoDB** | AWS | NoSQL database: `microshop-products` and `microshop-orders` tables | Managed DB (PaaS) |
| 3 | **SNS** | AWS | Sends an email for every new order | Managed messaging |
| 4 | **CloudWatch Logs** | AWS | Collects logs from all 3 containers centrally | Monitoring |
| 5 | **IAM** | AWS | Role on EC2 grants DB/SNS/logs access with no keys in code | Security |
| 6 | **Elastic IP** | AWS | Fixed public IP for the server | Networking |
| 7 | **GitHub Actions** | GitHub | Runs the CI/CD pipeline | CI/CD (PaaS) |
| 8 | **GitHub Container Registry** | GitHub | Stores versioned Docker images | Registry |

## Architecture

```
 Developer ── git push ──▶ GitHub repo
                              │
                              ▼
                 GitHub Actions pipeline
   ┌──────────────┬───────────────────────┬────────────────────────────┐
   │ 1. TEST      │ 2. BUILD & PUSH       │ 3. DEPLOY                  │
   │ pytest, AWS  │ docker build x3 →     │ SSH to EC2 → compose pull  │
   │ mocked (moto)│ GHCR (sha + latest)   │ + up → smoke test          │
   └──────────────┴───────────────────────┴────────────────────────────┘
                                                   │
                                                   ▼
   Users ── http ──▶ Elastic IP ──▶ EC2 (Docker, IAM role attached)
                      ┌───────────────────────────────────────────────┐
                      │ frontend (nginx: UI + API gateway) :80        │
                      │   ├─▶ product-service :5001 ──▶ DynamoDB      │
                      │   └─▶ order-service   :5002 ──▶ DynamoDB      │
                      │          │  └── REST ──▶ product-service      │
                      │          └──▶ SNS ──▶ email                   │
                      │ all container logs ──▶ CloudWatch Logs        │
                      └───────────────────────────────────────────────┘
```

## Time plan (about 6–6.5 hours)

| Time | Task |
|---|---|
| 0:00–0:45 | Read the code, push it to GitHub |
| 0:45–1:30 | DynamoDB tables, SNS topic + email, IAM role |
| 1:30–2:30 | Launch EC2, Elastic IP, install Docker |
| 2:30–3:00 | GitHub secrets |
| 3:00–4:00 | Run pipeline, fix errors, test the live site, check CloudWatch |
| 4:00–4:30 | Rehearse the demo |
| 4:30–6:30 | Screenshots, report/PPT, viva prep |

> **Use the same region for everything.** AWS Academy Learner Lab: use **us-east-1 (N. Virginia)**. Normal account: **ap-south-1 (Mumbai)** is closest to you.

## Step 1: Push the code to GitHub

1. Create a new **public** repo called `microshop` (no README).
2. In this project folder:

```bash
git init
git add .
git commit -m "Initial commit: microservices + CI/CD"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/microshop.git
git push -u origin main
```

Check that `.github/workflows/ci-cd.yml` is on GitHub. **Test** and **build** jobs should go green; **deploy** fails until Step 7. That's expected.

## Step 2: DynamoDB tables

**DynamoDB → Create table**, twice:

| Table name | Partition key | Type |
|---|---|---|
| `microshop-products` | `id` | **Number** |
| `microshop-orders` | `id` | **String** |

Leave other settings as default. You don't add any items: the product service fills in the starter products itself on first start.

## Step 3: SNS topic for order emails

1. **SNS → Topics → Create topic** → type **Standard**, name `microshop-orders` → Create.
2. Copy the **Topic ARN** (looks like `arn:aws:sns:us-east-1:123456789012:microshop-orders`).
3. **Create subscription** → protocol **Email** → your email → Create.
4. Open your inbox and click **Confirm subscription** (check spam). Emails only arrive after confirming.

## Step 4: IAM role for EC2

- **AWS Academy Learner Lab:** skip this step. You'll use the ready-made **LabInstanceProfile**.
- **Normal AWS account:** **IAM → Roles → Create role** → trusted entity **AWS service → EC2** → attach:
  `AmazonDynamoDBFullAccess`, `AmazonSNSFullAccess`, `CloudWatchAgentServerPolicy` → name it `microshop-ec2-role` → Create.
  (Full access is fine for a demo. In the viva, say production would use least-privilege policies limited to these two tables and one topic.)

## Step 5: Launch EC2 and install Docker

1. **EC2 → Launch instance**
   - Name `microshop-server`, AMI **Ubuntu Server 24.04 LTS**, type `t2.micro` / `t3.micro`
   - Key pair: create one and download the `.pem`. **Learner Lab:** use `vockey`; download `labsuser.pem` from *AWS Details*.
   - Network: allow **SSH (22) from Anywhere** and **HTTP (80) from Anywhere**
   - **Advanced details:**
     - **IAM instance profile:** `microshop-ec2-role` (or `LabInstanceProfile` in Learner Lab)
     - **Metadata response hop limit:** `2` ← important, lets the containers use the IAM role
2. Launch, then connect (**Connect → EC2 Instance Connect**, or `ssh -i key.pem ubuntu@IP`).
3. Install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Reconnect and check `docker compose version` works without `sudo`.

## Step 6: Elastic IP

**EC2 → Elastic IPs → Allocate Elastic IP address → Allocate**, then **Actions → Associate** → choose your instance. Use this IP from now on. It stays the same even if the instance (or Learner Lab session) restarts.

## Step 7: GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `EC2_HOST` | the Elastic IP |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | entire contents of the `.pem` file, including BEGIN/END lines |
| `AWS_REGION` | e.g. `us-east-1` |
| `SNS_TOPIC_ARN` | the topic ARN from Step 3 |

No AWS access keys are stored anywhere. The server gets permissions from its IAM role.

## Step 8: Run and check

1. **Actions → CI/CD Pipeline → Run workflow.** Wait for all jobs to go green.
2. Open `http://YOUR-ELASTIC-IP`. Place an order: you should get the email within seconds.
3. **DynamoDB → Explore items** shows the products (stock going down) and your orders.
4. **CloudWatch → Log groups → `microshop`** shows one log stream per container, including lines like `Order 3fa9c2e1 placed: 2 x USB-C Hub = Rs. 2998`.

## Optional: run locally

With Docker Desktop and AWS credentials exported in your shell (Learner Lab: *AWS Details → AWS CLI*), plus `AWS_REGION`: `docker compose up --build`, then http://localhost:8080.
Tests need no AWS at all: `cd product-service && pip install -r requirements.txt -r requirements-dev.txt && pytest -v`

## Demo script (7–8 minutes)

1. Walk through the services table and architecture diagram.
2. Open the live site, place an order. Your **phone gets the SNS email**.
3. Show the order and reduced stock in **DynamoDB**, and the matching log lines in **CloudWatch**.
4. **Live CD:** in GitHub's web editor, add a product to `SEED_PRODUCTS` in `product-service/app.py`:
   `{"id": 5, "name": "Wireless Mouse", "price": 899, "stock": 15},`
   Commit. Show the pipeline stages running, then refresh: the new product appears, the commit hash in the top strip changes, and **old orders are still there** because data lives in DynamoDB, not the container.
5. **CI protects production:** break a test (e.g. change `404` to `200` in `product-service/test_app.py`) and commit. The pipeline stops at *test*; nothing is deployed. Revert afterwards.
6. Show the versioned images under GitHub → your profile → **Packages**, and `docker ps` on the server.

## Troubleshooting

| Problem | Fix |
|---|---|
| Site loads but says "Database is unavailable", logs show `Unable to locate credentials` | IAM role not attached, or hop limit is 1. **EC2 → Actions → Security → Modify IAM role**, and **Actions → Instance settings → Modify instance metadata options → hop limit 2**. Then `docker compose -f docker-compose.prod.yml restart` on the server (or re-run the pipeline) |
| `ResourceNotFoundException` in logs | Table name typo or table in a different region than `AWS_REGION` |
| `AccessDeniedException` | Role is missing a policy (Step 4) |
| No order email | Subscription not confirmed, wrong `SNS_TOPIC_ARN` secret, or check spam |
| Deploy fails starting containers: awslogs error | Role lacks CloudWatch permission (`CloudWatchAgentServerPolicy`), or `AWS_REGION` secret missing |
| `ssh: handshake failed` / `unable to authenticate` | Incomplete `EC2_SSH_KEY` or wrong `EC2_USER` |
| `i/o timeout` on deploy | Port 22 not open to Anywhere, or wrong IP |
| `permission denied ... docker.sock` | Log out and back in after `usermod -aG docker ubuntu` |
| `unauthorized` pulling from ghcr.io | GitHub → Packages → each `microshop-*` package → settings → make **Public** |

## Possible viva questions

- **CI vs CD?** CI: every change is automatically built and tested. CD: every change that passes is automatically released.
- **Why microservices?** Independent development, deployment and scaling; stop order-service and products still load.
- **Why Docker?** The same image runs on the GitHub runner and EC2; containers are lighter than VMs because they share the host kernel.
- **Why DynamoDB instead of MySQL on the same server?** Fully managed (no patching/backups), scales automatically, and data survives container redeploys. Each service owns its own table: the *database-per-service* pattern.
- **How do two customers not buy the same last item?** The stock update is a single atomic DynamoDB `UpdateItem` with condition `stock >= quantity`, so there's no race condition.
- **How do tests run without AWS?** `moto` fakes DynamoDB and SNS in memory, so CI is fast, free and needs no credentials.
- **How does the app get AWS permissions without keys?** The IAM role attached to EC2 gives temporary credentials through the instance metadata service; boto3 picks them up automatically. Hop limit 2 lets containers reach it.
- **Why SNS instead of sending email from code?** Decoupling: order-service just publishes an event; SNS handles delivery, retries and multiple subscribers (email, SMS, Lambda) without code changes.
- **What if stock is reserved but saving the order fails?** That's a distributed transaction problem. A real system would use the Saga pattern with a compensating "release stock" call, or a queue like SQS.
- **Why tag images with the commit SHA?** Traceability and rollback to any exact version.
- **IaaS / PaaS / SaaS?** EC2 is IaaS; DynamoDB, SNS, CloudWatch, GitHub Actions are managed/PaaS-style services.
- **Future work:** run on ECS/EKS with multiple replicas behind a load balancer, HTTPS with a domain, Terraform for all the AWS setup, CloudWatch alarms, least-privilege IAM policies, SQS between services.

## Cleanup (avoid charges)

Terminate the EC2 instance, **release the Elastic IP** (an unattached Elastic IP is billed), delete both DynamoDB tables, the SNS topic and the `microshop` log group.
