# Deploy — single EC2 box + Docker (simplest live AWS)

One small EC2 instance runs the whole app in one container. A host folder
(`~/runs`) is mounted into the container so the **memory persists** (the
`results_*.tsv` notebook + the git keep/discard history). Redeploys are one command.

> Nothing here runs automatically. Run these yourself when your AWS CLI is
> configured (`aws configure`, an IAM user with EC2 permissions).

## 0. Pick your settings
```bash
export AWS_REGION=eu-west-2          # your region
export KEY_NAME=autoresearch
export SG_NAME=autoresearch-sg
```

## 1. SSH key pair (to log into the box)
```bash
aws ec2 create-key-pair --key-name $KEY_NAME --region $AWS_REGION \
  --query 'KeyMaterial' --output text > ~/.ssh/$KEY_NAME.pem
chmod 400 ~/.ssh/$KEY_NAME.pem
```

## 2. Security group — allow SSH (22) and HTTP (80)
```bash
SG_ID=$(aws ec2 create-security-group --group-name $SG_NAME \
  --description "autoresearch" --region $AWS_REGION --query GroupId --output text)
MYIP=$(curl -s ifconfig.me)
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp \
  --port 22 --cidr $MYIP/32 --region $AWS_REGION              # SSH from just you
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp \
  --port 80 --cidr 0.0.0.0/0 --region $AWS_REGION             # HTTP for the reviewer
```

## 3. Launch the instance (Amazon Linux 2023, Docker via user-data)
```bash
AMI=$(aws ssm get-parameters --names \
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --region $AWS_REGION --query 'Parameters[0].Value' --output text)

IID=$(aws ec2 run-instances --image-id $AMI --instance-type t3.medium \
  --key-name $KEY_NAME --security-group-ids $SG_ID \
  --user-data file://deploy/ec2_user_data.sh \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=autoresearch}]' \
  --region $AWS_REGION --query 'Instances[0].InstanceId' --output text)

aws ec2 wait instance-running --instance-ids $IID --region $AWS_REGION
HOST=$(aws ec2 describe-instances --instance-ids $IID --region $AWS_REGION \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "instance: $IID   public IP: $HOST"
# give cloud-init ~60s to finish installing Docker before deploying
```
(`t3.medium` recommended — the image build runs `npm`+`pip`. `t3.small` works but is tight.)

## 4. Put the OpenAI key on the box (a .env, never committed)
```bash
ssh -i ~/.ssh/$KEY_NAME.pem ec2-user@$HOST \
  "echo 'OPENAI_API_KEY=sk-proj-...your-key...' > ~/.env"
```

## 5. Ship the code + build + run
```bash
EC2_HOST=$HOST EC2_KEY=~/.ssh/$KEY_NAME.pem ./deploy/ship.sh
```
Open **http://$HOST/** — that's the live app the reviewer can use.

## Redeploy after code changes
```bash
EC2_HOST=$HOST EC2_KEY=~/.ssh/$KEY_NAME.pem ./deploy/ship.sh
```

## Notes
- **Persistence:** memory lives in `~/runs` on the instance's EBS volume — survives
  container restarts and reboots. It is lost only if you terminate the instance; for
  durability across instance replacement, put `~/runs` on a separate EBS volume.
- **HTTPS:** this serves plain HTTP (fine for a demo). For TLS, front it with Caddy
  or an ALB + ACM cert.
- **Cost:** a t3.medium is a few cents/hour — stop it when idle:
  `aws ec2 stop-instances --instance-ids $IID --region $AWS_REGION`.
- **Teardown:** `aws ec2 terminate-instances --instance-ids $IID --region $AWS_REGION`.
