# Terraform (studies) with a separate IAM user, not the root key

Saved 2026-11-03 at the owner's request. Nothing here touches Todira: Todira's backup key belongs to the separate IAM
user `todira-backup-bot` (checked with diagnose-aws-key-identity.yaml) and must stay as it is.

## Why
A root access key controls the whole AWS account and has no MFA. If it leaks (a file on the laptop, code pushed to
GitHub, malware), someone can launch servers on the owner's card or delete Todira's server. An IAM user with its own key
works the same for Terraform, but can only do what it was allowed.

## Now
Root user -> Security credentials -> Access keys -> the root key -> **Actions -> Deactivate** (reversible).
https://console.aws.amazon.com/iam/home#/security_credentials

## When Terraform is needed again (about 2 minutes)
1. IAM -> Users -> Create user, name `terraform`.
   https://console.aws.amazon.com/iam/home#/users/create
2. Permissions: Attach policies directly -> `AmazonEC2FullAccess` (add others the exercise needs, e.g. S3).
3. Open the new user -> Security credentials -> Create access key -> Command Line Interface.
4. On the computer: `aws configure`, paste the new key and secret, region `eu-west-1` (or the exercise's region).
5. Run `terraform plan` to check it works, then delete the deactivated root key.

## Tips for the exercises
- Use an Amazon Linux 2023 or Ubuntu AMI, not Amazon Linux 1 (AWS sends end-of-life warnings for AL1).
- Always `terraform destroy` at the end; check EC2 -> Instances in that region shows 0.
- Never touch the Stockholm (eu-north-1) region: that is Todira's server.
